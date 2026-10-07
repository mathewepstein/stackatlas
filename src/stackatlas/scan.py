import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from stackatlas.classify import classify_repo
from stackatlas.config import Config
from stackatlas.github import filter_repos, list_repos
from stackatlas.schema import Graph, Node
from stackatlas.sync import head_sha, sync_repo


@dataclass(frozen=True)
class ScannedRepo:
    name: str
    path: Path
    sha: str | None = None
    full_name: str | None = None
    url: str | None = None


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


def build_graph(org: str, repos: list[ScannedRepo], config: Config) -> Graph:
    nodes = []
    for repo in repos:
        override = config.overrides.get(repo.name)
        kind = (override and override.kind) or classify_repo(repo.path)
        layer = (override and override.layer) or config.layer_for(repo.name, kind)
        nodes.append(
            Node(
                id=f"repo:{repo.name}",
                name=repo.name,
                kind=kind,
                layer=layer,
                repo=repo.full_name,
                url=repo.url,
                sha=repo.sha,
            )
        )
    return Graph(
        org=org,
        generated_at=datetime.now(UTC),
        nodes=sorted(nodes, key=lambda n: n.id),
    )
