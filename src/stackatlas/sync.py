import base64
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from stackatlas.github import RepoInfo

MANIFEST = "manifest.json"


@dataclass(frozen=True)
class SyncedRepo:
    info: RepoInfo
    path: Path
    sha: str


def auth_env(clone_url: str, token: str | None) -> dict[str, str]:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if not token:
        return env
    parts = urlsplit(clone_url)
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    env.update(
        GIT_CONFIG_COUNT="1",
        GIT_CONFIG_KEY_0=f"http.{parts.scheme}://{parts.netloc}/.extraheader",
        GIT_CONFIG_VALUE_0=f"AUTHORIZATION: basic {basic}",
    )
    return env


def sync_repo(info: RepoInfo, cache_dir: Path, token: str | None) -> SyncedRepo:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / info.name
    manifest = _load_manifest(cache_dir)

    fresh = path.exists() and info.pushed_at and manifest.get(info.name) == info.pushed_at
    if not fresh:
        if path.exists():
            shutil.rmtree(path)
        subprocess.run(
            ["git", "clone", "--quiet", "--depth", "1", "--branch", info.default_branch,
             info.clone_url, str(path)],
            env=auth_env(info.clone_url, token),
            check=True,
            capture_output=True,
        )
        manifest = _load_manifest(cache_dir)
        manifest[info.name] = info.pushed_at
        (cache_dir / MANIFEST).write_text(json.dumps(manifest, indent=2))

    return SyncedRepo(info=info, path=path, sha=head_sha(path) or "")


def head_sha(path: Path) -> str | None:
    if not (path / ".git").exists():
        return None
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True
    )
    return result.stdout.strip() or None


def _load_manifest(cache_dir: Path) -> dict[str, str | None]:
    path = cache_dir / MANIFEST
    if not path.exists():
        return {}
    return json.loads(path.read_text())
