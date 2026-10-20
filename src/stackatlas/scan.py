import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from stackatlas.aliases import build_index
from stackatlas.apps import find_apps
from stackatlas.classify import classify_repo
from stackatlas.config import Config
from stackatlas.detectors import CiFile, Declared, run_detectors
from stackatlas.github import filter_repos, list_repos
from stackatlas.resolve import resolve
from stackatlas.runtime import RuntimeData, apply_runtime
from stackatlas.schema import CiEntry, Edge, Evidence, Graph, Kind, Node, Unresolved
from stackatlas.sync import head_sha, sync_repo


@dataclass(frozen=True)
class ScannedRepo:
    name: str
    path: Path
    sha: str | None = None
    full_name: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class ScanResult:
    graph: Graph
    unresolved: list[Unresolved]


def discover_local(root: Path, config: Config | None = None) -> list[ScannedRepo]:
    config = config or Config()
    found: list[ScannedRepo] = []
    for path in _repo_dirs(root):
        if config.includes(path.name):
            found.append(ScannedRepo(name=path.name, path=path, sha=head_sha(path)))
    return sorted(found, key=lambda r: r.name)


def _repo_dirs(root: Path, require_git: bool = False) -> list[Path]:
    dirs = [p for p in sorted(root.iterdir()) if p.is_dir() and not p.name.startswith(".")]
    result: list[Path] = []
    for path in dirs:
        if (path / ".git").exists():
            result.append(path)
        elif _has_git_child(path):
            result.extend(_repo_dirs(path, require_git=True))
        elif not require_git:
            result.append(path)
    return result


def _has_git_child(path: Path) -> bool:
    return any((c / ".git").exists() for c in path.iterdir() if c.is_dir())


def discover_github(
    owner: str, token: str, config: Config, cache_dir: Path, workers: int = 8
) -> tuple[list[ScannedRepo], list[str]]:
    repos = filter_repos(list_repos(owner, token), config)
    scanned: list[ScannedRepo] = []
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(sync_repo, r, cache_dir, token): r for r in repos}
        for future in as_completed(futures):
            info = futures[future]
            try:
                synced = future.result()
            except subprocess.CalledProcessError:
                failed.append(info.name)
                continue
            scanned.append(
                ScannedRepo(
                    name=info.name,
                    path=synced.path,
                    sha=synced.sha,
                    full_name=info.full_name,
                    url=info.html_url,
                )
            )
    return sorted(scanned, key=lambda r: r.name), sorted(failed)


def build_graph(
    org: str, repos: list[ScannedRepo], config: Config, runtime: list[RuntimeData] | None = None
) -> ScanResult:
    nodes = []
    kinds: dict[str, Kind] = {}
    apps: dict[str, list[str]] = {}
    for repo in repos:
        subs = find_apps(repo.path, config.apps.get(repo.name))
        apps[repo.name] = subs
        root_kind: Kind = "group" if subs else classify_repo(repo.path)
        nodes.append(_node(repo, repo.name, repo.name, repo.path, config, kinds, root_kind))
        for sub in subs:
            name = sub.rsplit("/", 1)[-1]
            node = _node(repo, f"{repo.name}/{sub}", name, repo.path / sub, config, kinds)
            nodes.append(node.model_copy(update={"parent": f"repo:{repo.name}"}))
    detection = run_detectors(repos, config)
    by_name = {r.name: r for r in repos}
    declared, deploy = _declared(detection.declared, by_name, config)
    index = build_index(repos, kinds, config, apps, declared)
    edges, externals, unresolved = resolve(
        detection.refs, index, config, repos, apps, detection.owners
    )
    infra = [_infra_node(d, by_name.get(d.repo), config) for d in declared]
    nodes = _attach_ci(nodes, detection.ci, apps, by_name)
    graph = Graph(
        org=org,
        generated_at=datetime.now(UTC),
        nodes=sorted(nodes + infra + externals, key=lambda n: n.id),
        edges=_merge_edges(edges + deploy),
    )
    if runtime:
        generic = {d.id for d in declared if d.generic}
        graph, unresolved = apply_runtime(graph, unresolved, index, config, runtime, generic)
    return ScanResult(graph, unresolved)


def _merge_edges(edges: list[Edge]) -> list[Edge]:
    merged: dict[tuple[str, str, str], Edge] = {}
    for edge in edges:
        key = (edge.source, edge.target, edge.type)
        if key not in merged:
            merged[key] = edge
            continue
        seen = merged[key]
        evidence = {(v.path, v.line): v for v in seen.evidence + edge.evidence}
        merged[key] = seen.model_copy(
            update={
                "confidence": "exact" if "exact" in (seen.confidence, edge.confidence)
                else "heuristic",
                "envs": sorted(set(seen.envs) | set(edge.envs)),
                "evidence": [evidence[k] for k in sorted(evidence)],
            }
        )
    return [merged[k] for k in sorted(merged)]


def _declared(
    items: list[Declared], repos: dict[str, ScannedRepo], config: Config
) -> tuple[list[Declared], list[Edge]]:
    merged: dict[str, Declared] = {}
    evidence: dict[tuple[str, str], dict[tuple[str, int], Evidence]] = defaultdict(dict)
    envs: dict[tuple[str, str], set[str]] = defaultdict(set)
    for d in items:
        if d.id in merged:
            m = merged[d.id]
            merged[d.id] = replace(
                m,
                aliases=tuple(dict.fromkeys(m.aliases + d.aliases)),
                envs=tuple(sorted(set(m.envs + d.envs))),
                endpoints=tuple(sorted(set(m.endpoints + d.endpoints))),
                generic=m.generic and d.generic,
            )
        else:
            merged[d.id] = d
        key = (f"repo:{d.repo}", d.id)
        envs[key].update(d.envs)
        url = _evidence_url(repos.get(d.repo), d.path, d.line)
        evidence[key].setdefault((d.path, d.line), Evidence(path=d.path, line=d.line,
                                                             snippet=d.snippet, url=url))
    deploy = [
        Edge(
            source=source,
            target=target,
            type="deploy",
            confidence="exact",
            envs=sorted(envs[(source, target)]),
            evidence=[ev[k] for k in sorted(ev)],
        )
        for (source, target), ev in sorted(evidence.items())
    ]
    return list(merged.values()), deploy


def _attach_ci(
    nodes: list[Node],
    files: list[CiFile],
    apps: dict[str, list[str]],
    repos: dict[str, ScannedRepo],
) -> list[Node]:
    entries: dict[str, list[CiEntry]] = defaultdict(list)
    for f in files:
        if f.declared_in:
            if f.repo not in repos:
                continue
            node = f"repo:{f.repo}"
        else:
            node = f"repo:{f.repo}"
            for sub in sorted(apps.get(f.repo, []), key=len, reverse=True):
                if f.path.startswith(sub + "/"):
                    node = f"repo:{f.repo}/{sub}"
                    break
        entries[node].append(
            CiEntry(system=f.system, path=f.path, repo=f.declared_in, registries=list(f.registries))
        )
    return [
        n.model_copy(update={"ci": sorted(entries[n.id], key=lambda c: (c.system, c.path))})
        if n.id in entries else n
        for n in nodes
    ]


def _infra_node(d: Declared, repo: ScannedRepo | None, config: Config) -> Node:
    layer = config.layer_for(d.name, d.kind)
    return Node(
        id=d.id,
        name=d.name,
        kind=d.kind,
        layer=d.layer if layer == d.kind else layer,
        repo=repo.full_name if repo else None,
        url=repo.url if repo else None,
        sha=repo.sha if repo else None,
        envs=list(d.envs),
        endpoints=list(d.endpoints),
    )


def _evidence_url(repo: ScannedRepo | None, path: str, line: int) -> str | None:
    if repo and repo.url and repo.sha:
        return f"{repo.url}/blob/{repo.sha}/{path}#L{line}"
    return None


def _node(
    repo: ScannedRepo,
    key: str,
    name: str,
    path: Path,
    config: Config,
    kinds: dict[str, Kind],
    kind: Kind | None = None,
) -> Node:
    override = config.overrides.get(key)
    kind = (override and override.kind) or kind or classify_repo(path)
    layer = (override and override.layer) or config.layer_for(name, kind)
    kinds[key] = kind
    return Node(
        id=f"repo:{key}",
        name=name,
        kind=kind,
        layer=layer,
        repo=repo.full_name,
        url=repo.url,
        sha=repo.sha,
    )
