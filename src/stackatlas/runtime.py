from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

import httpx

from stackatlas.aliases import GENERIC_APP_NAMES, SERVICE_SUFFIXES, AliasIndex, name_candidates
from stackatlas.config import Config
from stackatlas.schema import Edge, Graph, Trace, Unresolved

GLUED_SUFFIXES = sorted(SERVICE_SUFFIXES, key=len, reverse=True)


class MissingCredentials(Exception):
    pass


@dataclass(frozen=True)
class RuntimeData:
    source: str
    env: str
    start: datetime
    end: datetime
    services: frozenset[str]
    pairs: frozenset[tuple[str, str]]


class RuntimeSource(Protocol):
    def fetch(self) -> list[RuntimeData]: ...


class Datadog:
    def __init__(
        self,
        envs: dict[str, str],
        window_days: int,
        api_key: str,
        app_key: str,
        site: str,
        client: httpx.Client | None = None,
        now: datetime | None = None,
    ) -> None:
        self.envs = envs
        self.window_days = window_days
        self.client = client or httpx.Client(base_url=f"https://api.{site}", timeout=60)
        self.now = now
        self._headers = {"DD-API-KEY": api_key, "DD-APPLICATION-KEY": app_key}

    def fetch(self) -> list[RuntimeData]:
        end = self.now or datetime.now(UTC)
        start = end - timedelta(days=self.window_days)
        data: list[RuntimeData] = []
        for env, dd_env in self.envs.items():
            params = {"env": dd_env, "start": int(start.timestamp()), "end": int(end.timestamp())}
            response = self.client.get(
                "/api/v1/service_dependencies", params=params, headers=self._headers
            )
            response.raise_for_status()
            services: set[str] = set()
            pairs: set[tuple[str, str]] = set()
            for caller, entry in response.json().items():
                services.add(caller)
                for callee in entry.get("calls", []):
                    services.add(callee)
                    pairs.add((caller, callee))
            data.append(
                RuntimeData("datadog", env, start, end, frozenset(services), frozenset(pairs))
            )
        return data


def datadog_keys(environ: Mapping[str, str]) -> tuple[str, str, str] | None:
    api_key = environ.get("DD_API_KEY") or environ.get("DATADOG_API_KEY")
    app_key = environ.get("DD_APP_KEY") or environ.get("DATADOG_APP_KEY")
    if not api_key or not app_key:
        return None
    return api_key, app_key, environ.get("DD_SITE") or "datadoghq.com"


def datadog_source(config: Config, environ: Mapping[str, str]) -> Datadog:
    keys = datadog_keys(environ)
    if not keys:
        raise MissingCredentials(
            "Datadog needs DD_API_KEY and DD_APP_KEY (or DATADOG_API_KEY and DATADOG_APP_KEY)."
        )
    settings = config.runtime.datadog
    envs = settings.envs or {env: env for env in config.envs}
    return Datadog(envs, settings.window_days, *keys)


def validate_datadog(environ: Mapping[str, str], client: httpx.Client | None = None) -> bool:
    keys = datadog_keys(environ)
    if not keys:
        return False
    api_key, _, site = keys
    client = client or httpx.Client(base_url=f"https://api.{site}", timeout=30)
    response = client.get("/api/v1/validate", headers={"DD-API-KEY": api_key})
    return response.status_code == 200 and response.json().get("valid") is True


def apply_runtime(
    graph: Graph,
    unresolved: list[Unresolved],
    index: AliasIndex,
    config: Config,
    data: list[RuntimeData],
    exclude: set[str] | None = None,
) -> tuple[Graph, list[Unresolved]]:
    return _Overlay(graph, index, config, data, exclude or set()).run(unresolved)


class _Overlay:
    def __init__(
        self,
        graph: Graph,
        index: AliasIndex,
        config: Config,
        data: list[RuntimeData],
        exclude: set[str],
    ) -> None:
        self.graph = graph
        self.index = index
        self.data = data
        self.integrations = config.runtime.integrations
        self.engines = {e for e in self.integrations.values() if e}
        self.node_ids = {n.id for n in graph.nodes} - exclude
        self._resolved: dict[str, str | None] = {}
        self.covered: dict[str, set[str]] = defaultdict(set)
        self.seen: dict[tuple[str, str], list[RuntimeData]] = defaultdict(list)
        self.missing: dict[str, int] = defaultdict(int)
        for item in data:
            self._collect(item)

    def _node(self, name: str) -> str | None:
        if name not in self._resolved:
            self._resolved[name] = self._lookup(name)
        return self._resolved[name]

    def _lookup(self, name: str) -> str | None:
        for candidate in name_candidates(name):
            target = self.index.lookup(candidate)
            if target in self.node_ids:
                return target
        target = self.index.lookup_squashed(name)
        if target in self.node_ids:
            return target
        for suffix in GLUED_SUFFIXES:
            base = name.removesuffix(suffix)
            if base != name and len(base) >= 3 and base[-1].isalnum():
                return None if base in GENERIC_APP_NAMES else self._lookup(base)
        return None

    def _collect(self, item: RuntimeData) -> None:
        for name in item.services:
            node = None if name in self.integrations else self._node(name)
            if node:
                self.covered[item.env].add(node)
        for caller, callee in sorted(item.pairs):
            if caller in self.integrations:
                continue
            source = self._node(caller)
            if callee in self.integrations:
                engine = self.integrations[callee]
                if source and engine:
                    self.seen[(source, f"engine:{engine}")].append(item)
                elif not source:
                    self.missing[caller] += 1
                continue
            target = self._node(callee)
            for name, node in ((caller, source), (callee, target)):
                if not node:
                    self.missing[name] += 1
            if source and target and source != target:
                self.seen[(source, target)].append(item)

    def run(self, unresolved: list[Unresolved]) -> tuple[Graph, list[Unresolved]]:
        static = {(e.source, e.target) for e in self.graph.edges if e.type == "http"}
        edges = [self._classify(e) for e in self.graph.edges]
        for (source, target), hits in self.seen.items():
            if target.startswith("engine:") or (source, target) in static:
                continue
            edges.append(
                Edge(
                    source=source,
                    target=target,
                    type="http",
                    confidence="observed",
                    envs=sorted({h.env for h in hits}),
                    observed=True,
                    traces=_traces(hits),
                )
            )
        services = [
            Unresolved(ref=name, kind="service", count=count)
            for name, count in self.missing.items()
        ]
        graph = self.graph.model_copy(
            update={"edges": sorted(edges, key=lambda e: (e.source, e.target, e.type))}
        )
        return graph, sorted(unresolved + services, key=lambda u: (-u.count, u.ref))

    def _classify(self, edge: Edge) -> Edge:
        if edge.type == "http":
            key = (edge.source, edge.target)
        else:
            engines = sorted(_engine(edge.target) & self.engines)
            if edge.type != "datastore" or not engines:
                return edge
            key = (edge.source, f"engine:{engines[0]}")
        hits = self.seen.get(key, [])
        if hits:
            return edge.model_copy(update={"observed": True, "traces": _traces(hits)})
        envs = [d.env for d in self.data if not edge.envs or d.env in edge.envs]
        targets_covered = key[1].startswith("engine:")
        for env in envs:
            covered = self.covered[env]
            if edge.source in covered and (targets_covered or edge.target in covered):
                return edge.model_copy(update={"observed": False})
        return edge


def _engine(target: str) -> set[str]:
    if not target.startswith("datastore:"):
        return set()
    return set(target.split(":", 1)[1].split("/", 1)[0].split("-"))


def _traces(hits: list[RuntimeData]) -> list[Trace]:
    return [Trace(source=h.source, env=h.env, start=h.start, end=h.end) for h in hits]
