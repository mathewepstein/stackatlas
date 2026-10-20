import re
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from stackatlas.apps import _has_manifest
from stackatlas.config import Config
from stackatlas.detectors import datastore
from stackatlas.detectors.base import (
    Declared,
    Detection,
    canonical_env,
    env_from_host,
    iter_files,
    scrub,
    strip_env,
    value_ref,
)
from stackatlas.files import load_yaml_docs, read_lines
from stackatlas.helm import UNKNOWN, chart_values, render

WORKLOADS = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob", "Rollout"}


def detect_repo(repo: str, root: Path, config: Config) -> Detection:
    out = Detection()
    if _has_manifest(root):
        return out
    files = list(iter_files(root))
    charts = sorted({path.parent for _, path in files if path.name == "Chart.yaml"})
    chart_rels = [c.relative_to(root).as_posix() for c in charts]
    for chart, rel in zip(charts, chart_rels, strict=True):
        _Chart(repo, root, chart, rel, config, out).run()
    docs = []
    for rel, path in files:
        in_chart = any(rel.startswith(c + "/") for c in chart_rels)
        if path.suffix in (".yml", ".yaml") and not in_chart:
            lines = read_lines(path)
            docs += [(doc, rel, lines) for doc in load_yaml_docs(path)]
    _Group(repo, repo, config, out).handle(docs, None, [])
    return out


class _Chart:
    def __init__(
        self, repo: str, root: Path, chart: Path, rel: str, config: Config, out: Detection
    ) -> None:
        self.repo, self.root, self.chart, self.rel, self.config, self.out = (
            repo, root, chart, rel, config, out,
        )

    def run(self) -> None:
        meta = yaml.safe_load((self.chart / "Chart.yaml").read_text(errors="ignore")) or {}
        name = str(meta.get("name") or self.chart.name)
        found = Detection()
        group = _Group(self.repo, name, self.config, found)
        templates = sorted((self.chart / "templates").glob("*.y*ml"))
        env_for = lambda token: canonical_env(token, self.config.envs)  # noqa: E731
        for env, values in chart_values(self.chart, env_for).items():
            docs = []
            for template in templates:
                rel = template.relative_to(self.root).as_posix()
                rendered = render(template.read_text(errors="ignore"), values, name)
                lines = read_lines(template)
                for doc in _safe_docs(rendered):
                    docs.append((doc, rel, lines))
            group.handle(docs, env, _value_hosts(values))
        self.out.refs.extend(found.refs)
        self.out.declared.extend(_merged(found.declared))


def _merged(items: list[Declared]) -> list[Declared]:
    merged: dict[str, Declared] = {}
    for d in items:
        if d.id not in merged:
            merged[d.id] = d
            continue
        m = merged[d.id]
        merged[d.id] = replace(
            m,
            aliases=tuple(dict.fromkeys(m.aliases + d.aliases)),
            envs=tuple(sorted(set(m.envs + d.envs))),
        )
    return list(merged.values())


class _Group:
    def __init__(self, repo: str, group: str, config: Config, out: Detection) -> None:
        self.repo, self.group, self.config, self.out = repo, group, config, out

    def handle(
        self, docs: list[tuple[dict[str, Any], str, list[str]]], env: str | None, extra: list[str]
    ) -> None:
        services, hosts, workloads = [], [], []
        for doc, rel, lines in docs:
            kind = doc.get("kind")
            name = _dict(doc.get("metadata")).get("name")
            if not isinstance(name, str) or UNKNOWN in name:
                continue
            if kind in WORKLOADS:
                workloads.append((doc, rel, lines, name, kind))
            elif kind == "Service":
                services.append(name)
            elif kind == "Ingress":
                hosts += _ingress_hosts(_dict(doc.get("spec")))
        for doc, rel, lines, name, kind in workloads:
            node_env = env or env_from_host(name, self.config.envs)
            short = strip_env(name, self.config.envs) or name
            node = f"workload:{self.group}/{short}"
            kind_line = re.compile(rf"^\s*kind:\s*{kind}\b")
            line = next((i for i, text in enumerate(lines, 1) if kind_line.match(text)), 1)
            aliases = [name, short, *hosts, *extra, *services]
            self.out.declared.append(
                Declared(
                    id=node, name=short, kind="workload", layer="service", repo=self.repo,
                    path=rel, line=line, snippet=scrub(lines[line - 1] if lines else ""),
                    aliases=tuple(a for a in dict.fromkeys(aliases) if a and UNKNOWN not in a),
                    envs=(node_env,) if node_env else (),
                )
            )
            for key, value in _container_env(doc):
                self._env_ref(rel, lines, key, value, node, node_env)

    def _env_ref(
        self, rel: str, lines: list[str], key: str, value: str, node: str, env: str | None
    ) -> None:
        line = _value_line(lines, key)
        text = lines[line - 1] if 0 < line <= len(lines) else ""
        ref = datastore._entry_ref(self.repo, rel, line, text, key, value, env)
        ref = ref or value_ref(self.repo, rel, line, text, key, value, env)
        if ref:
            self.out.refs.append(replace(ref, source=node))


def _safe_docs(text: str) -> list[dict[str, Any]]:
    try:
        return [d for d in yaml.safe_load_all(text) if isinstance(d, dict)]
    except yaml.YAMLError:
        return []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _ingress_hosts(spec: dict[str, Any]) -> list[str]:
    hosts = [_dict(r).get("host") for r in _list(spec.get("rules"))]
    for tls in _list(spec.get("tls")):
        hosts += _list(_dict(tls).get("hosts"))
    return [h for h in hosts if isinstance(h, str)]


def _value_hosts(values: Any) -> list[str]:
    found: list[str] = []
    if isinstance(values, dict):
        for key, value in values.items():
            if key in ("host", "hosts") and isinstance(value, str):
                found.append(value)
            elif key == "hosts" and isinstance(value, list):
                found += [v for v in value if isinstance(v, str)]
            found += _value_hosts(value)
    elif isinstance(values, list):
        for item in values:
            found += _value_hosts(item)
    return found


def _container_env(doc: dict[str, Any]) -> list[tuple[str, str]]:
    spec = _dict(doc.get("spec"))
    pod = _dict(_dict(spec.get("template")).get("spec"))
    if not pod:
        job = _dict(_dict(spec.get("jobTemplate")).get("spec"))
        pod = _dict(_dict(job.get("template")).get("spec"))
    pairs = []
    for container in _list(pod.get("containers")) + _list(pod.get("initContainers")):
        for entry in _list(_dict(container).get("env")):
            key, value = _dict(entry).get("name"), _dict(entry).get("value")
            if isinstance(key, str) and isinstance(value, str) and UNKNOWN not in value:
                pairs.append((key, value))
    return pairs


def _value_line(lines: list[str], key: str) -> int:
    for i, line in enumerate(lines, 1):
        if re.match(rf"^\s*-\s*name:\s*{re.escape(key)}\s*$", line):
            for j in range(i, min(i + 3, len(lines))):
                if re.match(r"^\s*value:", lines[j]):
                    return j + 1
            return i
    return 1
