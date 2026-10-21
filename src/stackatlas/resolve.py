from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol

from stackatlas.aliases import (
    TIER_LEARNED,
    TIER_NAME,
    AliasIndex,
    name_candidates,
    strip_service_suffix,
)
from stackatlas.config import Config
from stackatlas.detectors.base import Reference, env_from_host, strip_env, url_parts
from stackatlas.detectors.messaging import messaging_name
from stackatlas.names import GENERIC_NAMES, relax, var_to_name
from stackatlas.schema import Confidence, Edge, Evidence, Kind, Node, Unresolved

MAX_HOPS = 3
MAX_UNRESOLVED_EVIDENCE = 5
EVENT_PREFIXES = ("queue:", "topic:")
GENERIC_LABELS = GENERIC_NAMES | {
    "test", "www", "blog", "cdn", "static", "assets", "mail", "smtp", "admin", "docs", "demo",
    "sandbox", "auth", "login", "db", "database", "cache", "redis", "mongo", "mysql", "postgres",
    "rds",
}


class _Repo(Protocol):
    name: str
    path: Path
    sha: str | None
    url: str | None


@dataclass
class _Outcome:
    chain: list[Reference]
    target: str | None = None
    confidence: Confidence = "exact"
    env: str | None = None
    unresolved: tuple[str, str] | None = None
    inferred: Kind | None = None


@dataclass
class _EdgeAcc:
    exact: bool = False
    envs: set[str] = field(default_factory=set)
    evidence: dict[tuple[str, int], Evidence] = field(default_factory=dict)


@dataclass
class _UnresolvedAcc:
    repos: set[str] = field(default_factory=set)
    evidence: dict[tuple[str, str, int], Evidence] = field(default_factory=dict)


def _is_repo(target: str | None) -> bool:
    return bool(target) and not target.startswith("external:")


def resolve(
    refs: list[Reference],
    index: AliasIndex,
    config: Config,
    repos: Iterable[_Repo],
    apps: dict[str, list[str]] | None = None,
    owners: Iterable[tuple[str, str, str]] | None = None,
) -> tuple[list[Edge], list[Node], list[Unresolved]]:
    return _Resolver(
        refs, index, config, {r.name: r for r in repos}, apps or {}, list(owners or [])
    ).run()


class _Resolver:
    def __init__(
        self,
        refs: list[Reference],
        index: AliasIndex,
        config: Config,
        repos: dict[str, _Repo],
        apps: dict[str, list[str]],
        owners: list[tuple[str, str, str]],
    ) -> None:
        self.refs = refs
        self.index = index
        self.config = config
        self.repos = repos
        self.owners: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for repo, subs in apps.items():
            self.owners[repo].extend((sub, f"repo:{repo}/{sub}") for sub in subs)
        for repo, prefix, node in owners:
            self.owners[repo].append((prefix, node))
        for entries in self.owners.values():
            entries.sort(key=lambda e: len(e[0]), reverse=True)
        self.edges: dict[tuple[str, str, str], _EdgeAcc] = defaultdict(_EdgeAcc)
        self.unresolved: dict[tuple[str, str], _UnresolvedAcc] = defaultdict(_UnresolvedAcc)
        self.externals: dict[str, Node] = {}
        self.inferred: dict[str, tuple[Kind, set[str]]] = {}
        self._owner_nodes: dict[str, str | None] = {}
        self.values: dict[tuple[str, str], list[Reference]] = defaultdict(list)
        for ref in refs:
            node = self.node_for(ref)
            if ref.key and node:
                self.values[(node, relax(ref.key))].append(ref)

    def node_for(self, ref: Reference) -> str | None:
        if ref.source:
            return ref.source
        if ref.owner is not None:
            if ref.owner == "*":
                return "*"
            if ref.owner not in self._owner_nodes:
                self._owner_nodes[ref.owner] = self._owner_node(ref)
            return self._owner_nodes[ref.owner]
        for prefix, node in self.owners.get(ref.repo, ()):
            if ref.path == prefix or ref.path.startswith(prefix + "/"):
                return node
        return f"repo:{ref.repo}"

    def _owner_node(self, ref: Reference) -> str | None:
        owner = ref.owner or ""
        found = messaging_name(owner) if ref.edge_type == "event" else None
        if found and found[0]:
            outcome = self._event_outcome([ref], owner, None)
            self._note_inferred(outcome)
            return outcome.target
        return self._name_outcome([ref], owner, "exact").target

    def _values_for(self, ref: Reference) -> list[Reference]:
        key = relax(ref.value)
        for scope in dict.fromkeys([self.node_for(ref), f"repo:{ref.repo}", "*"]):
            found = self.values.get((scope or "", key))
            if found:
                return found
        return []

    def run(self) -> tuple[list[Edge], list[Node], list[Unresolved]]:
        self._learn_aliases()
        for ref in self.refs:
            if ref.edge_type == "event" and ref.role is None:
                continue
            source = self.node_for(ref)
            if not source or source == "*":
                continue
            for outcome in self._outcomes(ref, 0):
                self._record(source, ref.repo, outcome, reverse=ref.role == "consume")
        return self._edge_list(), self._external_list(), self._unresolved_list()

    def _learn_aliases(self) -> None:
        for ref in self.refs:
            if not ref.fallback:
                continue
            target = self.index.lookup(ref.fallback)
            tier = self.index.tier(ref.fallback)
            if not target or tier is None or tier > TIER_NAME:
                continue
            for out in self._raw_outcomes(ref, 0):
                if out.unresolved and out.unresolved[0] == "host":
                    self.index.add(out.unresolved[1], target, TIER_LEARNED)

    def _outcomes(self, ref: Reference, depth: int, engine: str | None = None) -> list[_Outcome]:
        engine = engine or ref.engine
        if ref.kind == "name":
            if ref.edge_type == "deploy":
                return [self._deploy_outcome(ref)]
            if ref.edge_type == "event":
                return [self._event_outcome([ref], ref.value, engine)]
            return [self._name_outcome([ref], ref.value, "exact")]
        return self._apply_fallback(ref, self._raw_outcomes(ref, depth, engine))

    def _event_outcome(self, chain: list[Reference], raw: str, engine: str | None) -> _Outcome:
        found = messaging_name(raw)
        if not found:
            return _Outcome(chain, unresolved=("name", raw))
        kind: Kind = found[0] or engine or "queue"
        name = found[1]
        env = chain[-1].env or env_from_host(name, self.config.envs)
        stripped = strip_env(name, self.config.envs) or name
        prefixes = (f"{kind}:",) if found[0] or engine else EVENT_PREFIXES
        candidates: list[tuple[str, Confidence]] = [(name, "exact")]
        if stripped != name:
            candidates.append((stripped, "heuristic"))
        for candidate, confidence in candidates:
            target = self.index.lookup_prefixed(candidate, prefixes)
            if target:
                return _Outcome(chain, target, confidence, env)
        return _Outcome(chain, f"{kind}:{stripped}", "exact", env, inferred=kind)

    def _deploy_outcome(self, ref: Reference) -> _Outcome:
        env = ref.env or env_from_host(ref.value, self.config.envs)
        stripped = strip_env(ref.value, self.config.envs) or ref.value
        for candidate, confidence in ((ref.value, "exact"), (stripped, "heuristic")):
            target = self.index.lookup(candidate)
            if target:
                return _Outcome([ref], target, confidence, env)
        kind: Kind = ref.engine or "bucket"
        node = f"{kind}:{stripped}"
        return _Outcome([ref], node, "exact", env, unresolved=("name", ref.value), inferred=kind)

    def _raw_outcomes(
        self, ref: Reference, depth: int, engine: str | None = None
    ) -> list[_Outcome]:
        if ref.kind == "url":
            return self._url_outcomes(ref)
        return self._var_outcomes(ref, depth, engine)

    def _apply_fallback(self, ref: Reference, outcomes: list[_Outcome]) -> list[_Outcome]:
        if not ref.fallback:
            return outcomes
        named = self._name_outcome([ref], ref.fallback, "exact")
        if not named.target:
            return outcomes
        if any(_is_repo(o.target) for o in outcomes):
            tier = self.index.tier(ref.fallback)
            if named.confidence != "exact" or tier is None or tier > TIER_NAME:
                return outcomes
            return [
                replace(o, confidence="exact") if o.target == named.target else o
                for o in outcomes
            ]
        if not outcomes:
            return [named]
        return [
            replace(o, target=named.target, confidence=named.confidence, unresolved=None)
            for o in outcomes
        ]

    def _url_outcomes(self, ref: Reference) -> list[_Outcome]:
        parts = url_parts(ref.value)
        if not parts:
            return []
        host, path = parts
        if self.config.ignores_host(host):
            return []
        env = ref.env or env_from_host(host, self.config.envs)
        if ref.edge_type == "datastore":
            return self._datastore_outcomes(ref, host, env)
        for candidate, confidence in self._url_candidates(host, path):
            target = self.index.lookup(candidate)
            if target:
                return [_Outcome([ref], target, confidence, env)]
        return [_Outcome([ref], f"external:{host}", "exact", env, unresolved=("host", host))]

    def _datastore_outcomes(self, ref: Reference, host: str, env: str | None) -> list[_Outcome]:
        stripped = strip_env(host, self.config.envs) or host
        candidates = [(host, "exact")]
        if stripped != host:
            candidates.append((stripped, "heuristic"))
        first = stripped.split(".")[0]
        if first != stripped and first not in GENERIC_LABELS:
            candidates.append((first, "heuristic"))
        for candidate, confidence in candidates:
            target = self.index.lookup(candidate)
            if target:
                return [_Outcome([ref], target, confidence, env)]
        node = f"datastore:{ref.engine or 'db'}/{stripped}"
        return [
            _Outcome([ref], node, "exact", env, unresolved=("host", host), inferred="datastore")
        ]

    def _url_candidates(self, host: str, path: str) -> list[tuple[str, Confidence]]:
        segments = [s for s in path.split("/") if s]
        candidates: list[tuple[str, Confidence]] = []
        if segments:
            candidates.append((f"{host}/{'/'.join(segments)}", "exact"))
            if len(segments) > 1:
                candidates.append((f"{host}/{segments[0]}", "exact"))
        candidates.append((host, "exact"))
        stripped = strip_env(host, self.config.envs) or host
        if stripped != host:
            candidates.append((stripped, "heuristic"))
        first = stripped.split(".")[0]
        if first != stripped and first not in GENERIC_LABELS:
            candidates.append((first, "heuristic"))
            base = strip_service_suffix(first)
            if base != first and base not in GENERIC_LABELS:
                candidates.append((base, "heuristic"))
        return candidates

    def _name_outcome(self, chain: list[Reference], name: str, confidence: Confidence) -> _Outcome:
        candidates = name_candidates(name)
        for i, candidate in enumerate(candidates):
            target = self.index.lookup(candidate)
            if target:
                return _Outcome(chain, target, confidence if i == 0 else "heuristic")
        target = self.index.lookup_squashed(name)
        if target:
            return _Outcome(chain, target, "heuristic")
        return _Outcome(chain, unresolved=("name", candidates[0]))

    def _var_outcomes(
        self, ref: Reference, depth: int, engine: str | None = None
    ) -> list[_Outcome]:
        event = ref.edge_type == "event"
        if depth < MAX_HOPS:
            outcomes: list[_Outcome] = []
            for value in self._values_for(ref):
                if value is ref or (value.edge_type == "event") != event:
                    continue
                for out in self._outcomes(value, depth + 1, engine):
                    chain = [ref, *out.chain]
                    outcomes.append(
                        _Outcome(
                            chain, out.target, out.confidence, out.env, out.unresolved,
                            out.inferred,
                        )
                    )
            if any(o.target for o in outcomes):
                return outcomes
        name = var_to_name(ref.value)
        if event:
            return [_Outcome([ref], unresolved=("name", name))]
        if name in GENERIC_NAMES:
            target = self.index.lookup(name)
            return [_Outcome([ref], target, "heuristic")] if target else []
        return [self._name_outcome([ref], name, "heuristic")]

    def _record(self, source: str, repo: str, outcome: _Outcome, reverse: bool = False) -> None:
        if outcome.unresolved:
            kind, value = outcome.unresolved
            acc = self.unresolved[(kind, value)]
            acc.repos.add(repo)
            for r in outcome.chain:
                acc.evidence.setdefault((r.repo, r.path, r.line), self._evidence(r))
        target = outcome.target
        if not target or target == source:
            return
        if target.startswith("external:"):
            host = target.split(":", 1)[1]
            self.externals[host] = Node(id=target, name=host, kind="external", layer="external")
        else:
            self._note_inferred(outcome)
        ends = (target, source) if reverse else (source, target)
        edge = self.edges[(*ends, outcome.chain[0].edge_type)]
        edge.exact = edge.exact or outcome.confidence == "exact"
        if outcome.env:
            edge.envs.add(outcome.env)
        for r in outcome.chain:
            edge.evidence.setdefault((r.path, r.line), self._evidence(r))

    def _note_inferred(self, outcome: _Outcome) -> None:
        if outcome.inferred and outcome.target:
            _, envs = self.inferred.setdefault(outcome.target, (outcome.inferred, set()))
            if outcome.env:
                envs.add(outcome.env)

    def _evidence(self, ref: Reference) -> Evidence:
        repo = self.repos.get(ref.repo)
        url = None
        if repo and repo.url and repo.sha:
            url = f"{repo.url}/blob/{repo.sha}/{ref.path}#L{ref.line}"
        return Evidence(path=ref.path, line=ref.line, snippet=ref.snippet, url=url)

    def _edge_list(self) -> list[Edge]:
        return [
            Edge(
                source=source,
                target=target,
                type=edge_type,
                confidence="exact" if acc.exact else "heuristic",
                envs=sorted(acc.envs),
                evidence=[acc.evidence[k] for k in sorted(acc.evidence)],
            )
            for (source, target, edge_type), acc in sorted(self.edges.items())
        ]

    def _external_list(self) -> list[Node]:
        nodes = [self.externals[host] for host in sorted(self.externals)]
        for node, (kind, envs) in self.inferred.items():
            name = node.split("/", 1)[1] if "/" in node else node.split(":", 1)[1]
            nodes.append(Node(id=node, name=name, kind=kind, layer=kind, envs=sorted(envs)))
        return sorted(nodes, key=lambda n: n.id)

    def _unresolved_list(self) -> list[Unresolved]:
        items = [
            Unresolved(
                ref=value,
                kind=kind,
                count=len(acc.evidence),
                repos=sorted(acc.repos),
                evidence=[acc.evidence[k] for k in sorted(acc.evidence)][:MAX_UNRESOLVED_EVIDENCE],
            )
            for (kind, value), acc in self.unresolved.items()
        ]
        return sorted(items, key=lambda u: (-u.count, u.ref))
