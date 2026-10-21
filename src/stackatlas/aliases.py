import re
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, Protocol

from stackatlas.config import Config
from stackatlas.detectors.base import iter_files, url_parts
from stackatlas.files import (
    PLACEHOLDER,
    flat_properties,
    flat_yaml,
    load_json_or_yaml,
    load_toml,
    load_yaml_docs,
    read_lines,
    read_text,
)
from stackatlas.names import slug
from stackatlas.schema import Kind

TIER_CONFIG, TIER_DECLARED, TIER_NAME, TIER_DERIVED, TIER_LEARNED = 0, 1, 2, 3, 4
SERVICE_SUFFIXES = {
    "microservice", "service", "svc", "ms", "api", "server", "backend", "worker",
    "orchestration", "orch", "ui", "web", "frontend", "app", "http", "https", "rest", "client",
}
GENERIC_APP_NAMES = {
    "app", "apps", "api", "web", "www", "frontend", "backend", "server", "client", "ui",
    "service", "services", "src", "lib", "libs", "cli", "core", "common", "shared", "tools",
    "scripts", "docs", "examples", "packages", "test", "tests", "demo", "sample", "samples",
    "playground", "main", "auth", "login",
}
SUFFIX_FAMILIES = (
    ({"microservice", "service", "svc", "ms"}, ("service", "svc", "ms")),
    ({"orchestration", "orch"}, ("orch",)),
)
CONFIG_FILE = re.compile(r"^(?:application|bootstrap)(?:-[\w]+)?\.(?:ya?ml|properties)$")
COMPOSE_FILE = re.compile(r"^(?:docker-)?compose(?:\.[\w-]+)?\.ya?ml$")
OPENAPI_FILE = re.compile(r"^(?:openapi|swagger)(?:\.[\w-]+)?\.(?:ya?ml|json)$")
GRADLE_NAME = re.compile(r"rootProject\.name\s*=\s*[\"']([^\"']+)[\"']")
GO_MODULE = re.compile(r"^module\s+(\S+)", re.M)
PORT = re.compile(r":\d+$")


class _Repo(Protocol):
    name: str
    path: Path


class _Declared(Protocol):
    id: str
    name: str
    aliases: tuple[str, ...]


class AliasIndex:
    def __init__(self) -> None:
        self._entries: dict[str, dict[int, set[str]]] = {}
        self._squashed: dict[str, dict[int, set[str]]] = {}

    def add(self, alias: str, node_id: str, tier: int) -> None:
        key = normalize(alias)
        if key:
            self._entries.setdefault(key, {}).setdefault(tier, set()).add(node_id)
            self._squashed.setdefault(squash(key), {}).setdefault(tier, set()).add(node_id)

    def lookup(self, alias: str) -> str | None:
        return _best(self._entries.get(normalize(alias)))

    def lookup_squashed(self, alias: str) -> str | None:
        return _best(self._squashed.get(squash(normalize(alias))))

    def lookup_prefixed(self, alias: str, prefixes: tuple[str, ...]) -> str | None:
        return self._lookup_where(alias, lambda n: n.startswith(prefixes))

    def lookup_excluding(self, alias: str, node_id: str) -> str | None:
        return self._lookup_where(alias, lambda n: n != node_id)

    def _lookup_where(self, alias: str, keep: Callable[[str], bool]) -> str | None:
        tiers = self._entries.get(normalize(alias))
        for tier in sorted(tiers or {}):
            nodes = {n for n in tiers[tier] if keep(n)}
            if nodes:
                return next(iter(nodes)) if len(nodes) == 1 else None
        return None

    def remove(self, alias: str, node_id: str) -> None:
        key = normalize(alias)
        for table, k in ((self._entries, key), (self._squashed, squash(key))):
            for tier, nodes in list(table.get(k, {}).items()):
                nodes.discard(node_id)
                if not nodes:
                    del table[k][tier]

    def tier(self, alias: str) -> int | None:
        tiers = self._entries.get(normalize(alias))
        if not tiers:
            return None
        best = min(tiers)
        return best if len(tiers[best]) == 1 else None


def _best(tiers: dict[int, set[str]] | None) -> str | None:
    if not tiers:
        return None
    nodes = tiers[min(tiers)]
    return next(iter(nodes)) if len(nodes) == 1 else None


def squash(alias: str) -> str:
    return re.sub(r"[-_.]", "", alias)


def normalize(alias: str) -> str:
    alias = alias.strip().lower()
    if "://" in alias:
        parts = url_parts(alias)
        if not parts:
            return ""
        host, path = parts
        return f"{host}{path}".replace("_", "-")
    alias = alias.split("?", 1)[0].rstrip("/")
    host, _, rest = alias.partition("/")
    host = PORT.sub("", host)
    return (f"{host}/{rest}" if rest else host).replace("_", "-")


def strip_service_suffix(name: str) -> str:
    return name_candidates(name)[-1]


def name_candidates(name: str) -> list[str]:
    parts = re.split(r"[-_]", name.lower())
    candidates = ["-".join(parts)]
    while len(parts) > 1 and parts[-1] in SERVICE_SUFFIXES:
        parts.pop()
        candidates.append("-".join(parts))
    return candidates


def name_variants(name: str) -> set[str]:
    norm = normalize(name)
    parts = norm.split("-")
    if len(parts) < 2 or parts[-1] not in SERVICE_SUFFIXES:
        return set()
    base = "-".join(parts[:-1])
    variants = {base}
    for family, outputs in SUFFIX_FAMILIES:
        if parts[-1] in family:
            variants |= {f"{base}-{suffix}" for suffix in outputs}
    return variants - {norm}


def build_index(
    repos: Iterable[_Repo],
    kinds: dict[str, Kind],
    config: Config,
    apps: dict[str, list[str]] | None = None,
    declared: Iterable[_Declared] = (),
) -> AliasIndex:
    index = AliasIndex()
    apps = apps or {}
    for repo in repos:
        subs = apps.get(repo.name, [])
        _add_node(index, f"repo:{repo.name}", repo.name, repo.path, kinds, config, subs)
        for sub in subs:
            name = sub.rsplit("/", 1)[-1]
            _add_node(index, f"repo:{repo.name}/{sub}", name, repo.path / sub, kinds, config)
    for item in declared:
        if item.name.lower() not in GENERIC_APP_NAMES:
            index.add(item.name, item.id, TIER_NAME)
        for alias in item.aliases:
            if alias.lower() not in GENERIC_APP_NAMES:
                index.add(alias, item.id, TIER_DECLARED)
    return index


def _host_patterns(index: AliasIndex, node: str, name: str, config: Config) -> None:
    for pattern in config.host_patterns:
        if "{env}" not in pattern:
            index.add(pattern.format(name=name), node, TIER_CONFIG)
            continue
        for env, tokens in config.envs.items():
            for token in dict.fromkeys([env, *tokens]):
                index.add(pattern.format(env=token, name=name), node, TIER_CONFIG)


def _add_node(
    index: AliasIndex,
    node: str,
    name: str,
    path: Path,
    kinds: dict[str, Kind],
    config: Config,
    exclude: list[str] = (),
) -> None:
    key = node.removeprefix("repo:")
    for alias in config.aliases.get(key, []):
        index.add(alias, node, TIER_CONFIG)
    if kinds.get(key) not in ("group", "infra"):
        _host_patterns(index, node, name, config)
    if "/" not in node or name.lower() not in GENERIC_APP_NAMES:
        index.add(name, node, TIER_NAME)
        for variant in name_variants(name) - GENERIC_APP_NAMES:
            index.add(variant, node, TIER_DERIVED)
    if kinds.get(key) != "infra":
        for alias in declared_names(path, exclude) - GENERIC_APP_NAMES:
            index.add(alias, node, TIER_DECLARED)


def declared_names(root: Path, exclude: list[str] = ()) -> set[str]:
    names = set(_manifest_names(root))
    for rel, path in iter_files(root):
        if any(rel == e or rel.startswith(e + "/") for e in exclude):
            continue
        name = path.name
        if CONFIG_FILE.match(name):
            names |= _spring_names(path)
        elif COMPOSE_FILE.match(name):
            names |= _compose_services(path)
        elif OPENAPI_FILE.match(name):
            names |= _openapi_names(path)
        elif path.suffix in (".yml", ".yaml"):
            names |= _k8s_names(path)
    return {normalize(n) for n in names if n} - {""}


def _manifest_names(root: Path) -> list[str]:
    names: list[str] = []
    pkg = load_json_or_yaml(root / "package.json")
    if isinstance(pkg.get("name"), str):
        names.append(pkg["name"].split("/")[-1])
    py = load_toml(root / "pyproject.toml")
    for section in (py.get("project"), py.get("tool", {}).get("poetry")):
        if isinstance(section, dict) and isinstance(section.get("name"), str):
            names.append(section["name"])
    m = GO_MODULE.search(read_text(root / "go.mod"))
    if m:
        names.append(m.group(1).split("/")[-1])
    names.extend(_pom_artifact(root / "pom.xml"))
    for settings in ("settings.gradle", "settings.gradle.kts"):
        m = GRADLE_NAME.search(read_text(root / settings))
        if m:
            names.append(m.group(1))
    return names


def _pom_artifact(path: Path) -> list[str]:
    text = read_text(path)
    if not text:
        return []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    for child in root:
        if child.tag.rsplit("}", 1)[-1] == "artifactId" and child.text:
            return [child.text.strip()]
    return []


def _spring_names(path: Path) -> set[str]:
    lines = read_lines(path)
    if path.suffix == ".properties":
        entries = [(key, value) for key, value, _ in flat_properties(lines)]
    else:
        entries = [(key, value) for _, key, value, _ in flat_yaml(lines)]
    names = set()
    for key, value in entries:
        m = PLACEHOLDER.match(value)
        if m:
            value = m.group(2) or ""
        if key == "spring.application.name":
            names.add(value)
        elif key == "server.servlet.context-path":
            names.add(value.strip("/"))
    return names


def _compose_services(path: Path) -> set[str]:
    services = load_json_or_yaml(path).get("services")
    return set(services) if isinstance(services, dict) else set()


def _openapi_names(path: Path) -> set[str]:
    data = load_json_or_yaml(path)
    names = set()
    title = _dict(data.get("info")).get("title")
    if isinstance(title, str):
        names.add(slug(title))
    for server in _list(data.get("servers")):
        url = _dict(server).get("url")
        if isinstance(url, str) and "://" in url:
            host = url.split("://", 1)[1].split("/")[0]
            if "{" not in host:
                names.add(url)
    host = data.get("host")
    if isinstance(host, str):
        base_path = data.get("basePath")
        names.add(host + (base_path if isinstance(base_path, str) else ""))
    return names


def _k8s_names(path: Path) -> set[str]:
    names = set()
    for doc in load_yaml_docs(path):
        kind = doc.get("kind")
        meta = _dict(doc.get("metadata"))
        spec = _dict(doc.get("spec"))
        if kind == "Service" and isinstance(meta.get("name"), str):
            names.add(meta["name"])
        elif kind == "Ingress":
            for rule in _list(spec.get("rules")):
                host = _dict(rule).get("host")
                if isinstance(host, str):
                    names.add(host)
            for tls in _list(spec.get("tls")):
                names.update(h for h in _list(_dict(tls).get("hosts")) if isinstance(h, str))
    return names


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
