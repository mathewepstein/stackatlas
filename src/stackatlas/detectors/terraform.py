import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from stackatlas.config import Config
from stackatlas.detectors.base import (
    CiFile,
    Declared,
    Detection,
    Reference,
    canonical_env,
    clean_url,
    is_http_key,
    is_http_url,
    is_secret,
    looks_like_host,
    scrub,
    strip_env,
)
from stackatlas.detectors.ci import REGISTRY
from stackatlas.detectors.messaging import event_value, messaging_name
from stackatlas.names import GENERIC_NAMES, kebab, literal_parts, var_to_name
from stackatlas.tf import UNKNOWN, Block, Stack, find_stacks, unq

CONFIG_KEY = re.compile(r"^/config/([^/_]+)_([^/]+)/(.+)$")
GITHUB_REPO = re.compile(r"github\.com[/:][^/]+/([A-Za-z0-9_.-]+?)(?:\.git)?/?$")
GATEWAYS = ("aws_apigatewayv2_api", "aws_api_gateway_rest_api")
DOMAINS = ("aws_apigatewayv2_domain_name", "aws_api_gateway_domain_name")
MAPPINGS = ("aws_apigatewayv2_api_mapping", "aws_api_gateway_base_path_mapping")
API_REF = re.compile(r"(?:aws_apigatewayv2_api|aws_api_gateway_rest_api)\.([A-Za-z0-9_-]+)")
DOMAIN_REF = re.compile(
    r"(?:aws_apigatewayv2_domain_name|aws_api_gateway_domain_name)\.([A-Za-z0-9_-]+)"
)
ARCHIVE_REF = re.compile(r"data\.archive_file\.([A-Za-z0-9_-]+)")
LAMBDA_REF = re.compile(r"aws_lambda_function\.([A-Za-z0-9_-]+)")
MODULE_PATH = re.compile(r"path\.module\}?/([^\"'\s)]+)")
DATASTORES = {
    "aws_db_instance": ("engine", "identifier", "db"),
    "aws_rds_cluster": ("engine", "cluster_identifier", "db"),
    "aws_elasticache_replication_group": ("engine", "replication_group_id", "redis"),
    "aws_elasticache_cluster": ("engine", "cluster_id", "redis"),
    "aws_dynamodb_table": (None, "name", "dynamodb"),
}
NAMED = {
    "aws_sqs_queue": ("queue", "name"),
    "aws_sns_topic": ("topic", "name"),
    "aws_s3_bucket": ("bucket", "bucket"),
}
WORKLOAD_KINDS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Rollout"}


def detect_repo(repo: str, root: Path, config: Config) -> Detection:
    out = Detection()
    for stack in find_stacks(root):
        _Scan(repo, stack, config, out).run()
    return out


class _Scan:
    def __init__(self, repo: str, stack: Stack, config: Config, out: Detection) -> None:
        self.repo = repo
        self.stack = stack
        self.config = config
        self.out = out
        self.env = self._env()
        self.logical = self._logical()

    def run(self) -> None:
        self._gateways()
        self._lambdas()
        self._datastores()
        self._named()
        self._messaging()
        self._config_store()
        self._codebuild()
        self._kubernetes()

    def _messaging(self) -> None:
        functions = self._function_nodes()
        for m in self.stack.resources("aws_lambda_event_source_mapping"):
            arn = self.stack.text(m.body.get("event_source_arn"))
            found = messaging_name(arn) if arn else None
            node = self._function(functions, m.body.get("function_name"))
            if arn and found and found[0] and node:
                self._wire(m, "event_source_arn", arn, found[0], source=node)
        for s in self.stack.resources("aws_sns_topic_subscription"):
            topic = self.stack.text(s.body.get("topic_arn"))
            found = messaging_name(topic) if topic else None
            if not topic or not found or found[0] != "topic":
                continue
            protocol = self.stack.text(s.body.get("protocol"))
            if protocol == "lambda":
                node = self._function(functions, s.body.get("endpoint"))
                if node:
                    self._wire(s, "topic_arn", topic, "topic", source=node)
            elif protocol == "sqs":
                queue = self.stack.text(s.body.get("endpoint"))
                if queue and messaging_name(queue):
                    self._wire(s, "topic_arn", topic, "topic", owner=queue)

    def _function_nodes(self) -> dict[str, str]:
        nodes = {}
        for fn in self.stack.resources("aws_lambda_function"):
            node = f"function:{self.logical}/{self._node_name(fn.name)}"
            nodes[fn.name] = node
            full = self.stack.text(fn.body.get("function_name"))
            if full and UNKNOWN not in full:
                nodes[full] = node
        return nodes

    def _function(self, nodes: dict[str, str], raw: Any) -> str | None:
        label = _match(LAMBDA_REF, raw)
        if label:
            return nodes.get(label)
        full = self.stack.text(raw)
        return nodes.get(full) if full else None

    def _wire(
        self,
        block: Block,
        attr: str,
        value: str,
        engine: str,
        source: str | None = None,
        owner: str | None = None,
    ) -> None:
        line, text = self.stack.attr_line(block, attr)
        self.out.refs.append(
            Reference(
                self.repo, block.path, line, scrub(text), "name", value, env=self.env,
                edge_type="event", role="consume", engine=engine, source=source, owner=owner,
            )
        )

    def _kubernetes(self) -> None:
        for b in self.stack.resources("helm_release"):
            name = self.stack.text(b.body.get("name"))
            if not name or UNKNOWN in name:
                name = b.name
            hosts = [
                self.stack.text(s.get("value"))
                for s in b.body.get("set") or []
                if isinstance(s, dict) and "host" in unq(str(s.get("name", ""))).lower()
            ]
            self._workload(b, name, [h for h in hosts if h])
        for b in self.stack.resources("kubernetes_manifest"):
            manifest = self.stack.resolve(b.body.get("manifest"))
            if not isinstance(manifest, dict) or manifest.get("kind") not in WORKLOAD_KINDS:
                continue
            metadata = manifest.get("metadata")
            name = metadata.get("name") if isinstance(metadata, dict) else None
            if isinstance(name, str) and UNKNOWN not in name:
                self._workload(b, name, [])

    def _workload(self, block: Block, name: str, hosts: list[str]) -> None:
        short = strip_env(name, self.config.envs) or name
        env = self.env or canonical_env(
            next((t for t in re.split(r"[.-]", name) if canonical_env(t, self.config.envs)), ""),
            self.config.envs,
        )
        self._declare(
            block, f"workload:{self.logical}/{short}", short, "workload", "service",
            [name, short, *hosts], env=env,
        )

    def _codebuild(self) -> None:
        for b in self.stack.resources("aws_codebuild_project"):
            registries = {
                m.group(1).lower()
                for _, value in _leaves(self.stack.resolve(b.body))
                for m in REGISTRY.finditer(value)
            }
            for src in b.body.get("source") or []:
                location = self.stack.text(src.get("location")) if isinstance(src, dict) else None
                m = GITHUB_REPO.search(location or "")
                if m:
                    found = tuple(sorted(registries))
                    self.out.ci.append(CiFile(m.group(1), b.path, "codebuild", found, self.repo))

    def _env(self) -> str | None:
        for token in re.split(r"[/_-]", self.stack.rel):
            env = canonical_env(token, self.config.envs) if token else None
            if env:
                return env
        local = self.stack.text(self.stack.locals.get("env"))
        return canonical_env(local, self.config.envs) if local else None

    def _logical(self) -> str:
        for segment in reversed(self.stack.rel.split("/")):
            parts = [
                p for p in re.split(r"[_-]", segment)
                if p and canonical_env(p, self.config.envs) is None
            ]
            if parts:
                return "-".join(parts).lower()
        return self.repo

    def _node_name(self, block_name: str) -> str:
        parts = [
            p for p in re.split(r"[-_]", block_name)
            if p and canonical_env(p, self.config.envs) is None
        ]
        return "-".join(parts) or block_name

    def _declare(
        self,
        block: Block,
        node: str,
        name: str,
        kind: str,
        layer: str,
        aliases: list[str],
        endpoints: list[str] | None = None,
        env: str | None = None,
    ) -> None:
        env = env or self.env
        lines = self.stack.files.get(block.path, [])
        snippet = lines[block.line - 1].strip() if 0 < block.line <= len(lines) else ""
        self.out.declared.append(
            Declared(
                id=node,
                name=name,
                kind=kind,
                layer=layer,
                repo=self.repo,
                path=block.path,
                line=block.line,
                snippet=scrub(snippet),
                aliases=tuple(a for a in dict.fromkeys(aliases) if a and UNKNOWN not in a),
                envs=(env,) if env else (),
                endpoints=tuple(sorted(endpoints or [])),
            )
        )

    def _ref(
        self,
        block: Block,
        attr: str,
        value: str,
        source: str | None,
        key: str | None = None,
        as_host: bool = False,
    ) -> None:
        line, text = self.stack.attr_line(block, attr)
        self._emit(block.path, line, text, value, key, source=source, as_host=as_host)

    def _emit(
        self,
        path: str,
        line: int,
        text: str,
        value: str,
        key: str | None,
        source: str | None = None,
        owner: str | None = None,
        fallback: str | None = None,
        as_host: bool = False,
        env: str | None = None,
    ) -> None:
        if key and is_secret(key):
            return
        env = env or self.env
        if event_value(key, value):
            ref = Reference(
                self.repo, path, line, scrub(text), "name", value, key=key, env=env,
                edge_type="event", source=source, owner=owner,
            )
            self.out.refs.append(ref)
            return
        if UNKNOWN in value:
            label = self._literal_label(value)
            if label:
                ref = Reference(self.repo, path, line, scrub(text), "name", label, env=env)
                self.out.refs.append(_with(ref, key, source, owner, fallback))
            return
        if is_http_url(value):
            value = clean_url(value)
        elif not (looks_like_host(value) and (as_host or (key and is_http_key(key)))):
            return
        ref = Reference(self.repo, path, line, scrub(text), "url", value, env=env)
        self.out.refs.append(_with(ref, key, source, owner, fallback))

    def _literal_label(self, value: str) -> str | None:
        host = value.split("://", 1)[-1].split("/", 1)[0]
        first = host.split(".")[0]
        parts = [
            p for p in first.split("-")
            if p and UNKNOWN not in p and canonical_env(p, self.config.envs) is None
        ]
        label = "-".join(parts)
        return label if label and label not in GENERIC_NAMES else None

    def _gateways(self) -> None:
        apis = self.stack.resources(*GATEWAYS)
        domains = {
            b.name: self.stack.text(b.body.get("domain_name"))
            for b in self.stack.resources(*DOMAINS)
        }
        mapped: dict[str, list[str]] = {}
        for m in self.stack.resources(*MAPPINGS):
            api = _match(API_REF, m.body.get("api_id"))
            domain = domains.get(_match(DOMAIN_REF, m.body.get("domain_name")) or "")
            if api and domain:
                mapped.setdefault(api, []).append(domain)
        if not mapped and len(apis) == 1:
            mapped[apis[0].name] = [d for d in domains.values() if d]
        routes: dict[str, list[str]] = {}
        for r in self.stack.resources("aws_apigatewayv2_route"):
            api = _match(API_REF, r.body.get("api_id"))
            key = self.stack.text(r.body.get("route_key"))
            if api and key:
                routes.setdefault(api, []).append(key)
        ids: dict[str, str] = {}
        for api in apis:
            node = f"gateway:{self.logical}/{self._node_name(api.name)}"
            ids[api.name] = node
            name = self.stack.text(api.body.get("name"))
            if not name or UNKNOWN in name:
                name = api.name
            self._declare(
                api, node, name, "gateway", "edge", mapped.get(api.name, []), routes.get(api.name)
            )
        single = next(iter(ids.values())) if len(ids) == 1 else None
        for i in self.stack.resources("aws_apigatewayv2_integration"):
            source = ids.get(_match(API_REF, i.body.get("api_id")) or "") or single
            params = self.stack.resolve(i.body.get("request_parameters") or {})
            host = params.get("overwrite:header.Host") if isinstance(params, dict) else None
            if isinstance(host, str):
                self._ref(i, "overwrite:header.Host", host, source, as_host=True)
                continue
            sni = next(
                (
                    self.stack.text(t.get("server_name_to_verify"))
                    for t in i.body.get("tls_config") or []
                    if isinstance(t, dict) and t.get("server_name_to_verify")
                ),
                None,
            )
            if sni:
                self._ref(i, "server_name_to_verify", sni, source, as_host=True)
                continue
            uri = self.stack.text(i.body.get("integration_uri"))
            if uri and is_http_url(uri):
                self._ref(i, "integration_uri", uri, source)
        for i in self.stack.resources("aws_api_gateway_integration"):
            source = ids.get(_match(API_REF, i.body.get("rest_api_id")) or "") or single
            uri = self.stack.text(i.body.get("uri"))
            if uri and is_http_url(uri):
                self._ref(i, "uri", uri, source)
        for m in self.stack.modules():
            for key, value in _leaves(self.stack.resolve(m.body)):
                if is_http_url(value) or (is_http_key(key) and looks_like_host(value)):
                    self._ref(m, key, value, single, key=key)

    def _lambdas(self) -> None:
        archives: dict[str, str] = {}
        for d in self.stack.data("archive_file"):
            raws = [d.body.get("source_file"), d.body.get("source_dir")]
            raws += [s.get("content") for s in d.body.get("source") or [] if isinstance(s, dict)]
            for raw in raws:
                m = MODULE_PATH.search(raw) if isinstance(raw, str) else None
                if m:
                    archives[d.name] = m.group(1).strip("/")
                    break
        for fn in self.stack.resources("aws_lambda_function"):
            node = f"function:{self.logical}/{self._node_name(fn.name)}"
            full = self.stack.text(fn.body.get("function_name"))
            if not full or UNKNOWN in full:
                full = fn.name
            display = strip_env(full, self.config.envs) or full
            self._declare(fn, node, display, "function", "function", [full, display])
            for env_block in fn.body.get("environment") or []:
                variables = self.stack.resolve(env_block.get("variables") or {})
                if not isinstance(variables, dict):
                    continue
                for key, value in variables.items():
                    if isinstance(value, str) and (UNKNOWN not in value or event_value(key, value)):
                        self._ref(fn, key, value, node, key=key)
            src = self._lambda_source(fn, archives)
            if src:
                prefix = f"{self.stack.rel}/{src}" if self.stack.rel else src
                self.out.owners.append((self.repo, prefix, node))

    def _lambda_source(self, fn: Block, archives: dict[str, str]) -> str | None:
        raw = fn.body.get("filename") or fn.body.get("source_dir")
        if not isinstance(raw, str):
            return None
        m = ARCHIVE_REF.search(raw)
        if m:
            return archives.get(m.group(1))
        if "${" not in raw:
            return unq(raw).removeprefix("./") or None
        return None

    def _datastores(self) -> None:
        for type_, (engine_attr, name_attr, default_engine) in DATASTORES.items():
            for b in self.stack.resources(type_):
                engine = self.stack.text(b.body.get(engine_attr)) if engine_attr else None
                if not engine or UNKNOWN in engine:
                    engine = default_engine
                self._declare_named(b, name_attr, f"datastore:{engine}/", "datastore", "datastore")

    def _named(self) -> None:
        for type_, (kind, name_attr) in NAMED.items():
            for b in self.stack.resources(type_):
                self._declare_named(b, name_attr, f"{kind}:", kind, kind)

    def _declare_named(
        self, block: Block, name_attr: str, prefix: str, kind: str, layer: str
    ) -> None:
        full = self.stack.text(block.body.get(name_attr)) or block.name
        name = literal_parts(full) if UNKNOWN in full else full
        short = strip_env(name or block.name, self.config.envs) or name or block.name
        self._declare(block, f"{prefix}{short}", short, kind, layer, [full, short])

    def _config_store(self) -> None:
        for b in self.stack.resources("aws_ssm_parameter"):
            name = self.stack.text(b.body.get("name"))
            value = self.stack.text(b.body.get("value"))
            if name and value:
                line, text = self.stack.attr_line(b, "value")
                self._config_entry(name, value, b.path, line, text)
        for name, value in _config_entries(self.stack.resolve(self.stack.locals)):
            m = CONFIG_KEY.match(name)
            if m:
                needles = [f"/config/{m.group(1)}_", f"/{m.group(3)}"]
                self._config_entry(name, value, *self.stack.find_line(needles))

    def _config_entry(self, name: str, value: str, path: str, line: int, text: str) -> None:
        m = CONFIG_KEY.match(name)
        if not m:
            return
        app, env_token, key = m.groups()
        if UNKNOWN in value and not event_value(key, value):
            return
        env = canonical_env(env_token, self.config.envs) or self.env
        owner = "*" if app in self.config.shared_config_names else kebab(app)
        fallback = var_to_name(key)
        self._emit(
            path, line, text, value, key, owner=owner, env=env,
            fallback=None if fallback in GENERIC_NAMES else fallback,
        )


def _with(
    ref: Reference, key: str | None, source: str | None, owner: str | None, fallback: str | None
) -> Reference:
    from dataclasses import replace

    return replace(ref, key=key, source=source, owner=owner, fallback=fallback)


def _match(pattern: re.Pattern[str], raw: Any) -> str | None:
    m = pattern.search(raw) if isinstance(raw, str) else None
    return m.group(1) if m else None


def _leaves(obj: Any, key: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _leaves(v, str(k))
    elif isinstance(obj, list):
        for v in obj:
            yield from _leaves(v, key)
    elif isinstance(obj, str):
        yield key, obj


def _config_entries(obj: Any) -> Iterator[tuple[str, str]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and CONFIG_KEY.match(k):
                value = v.get("value") if isinstance(v, dict) else v
                if isinstance(value, str):
                    yield k, value
            yield from _config_entries(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _config_entries(v)
