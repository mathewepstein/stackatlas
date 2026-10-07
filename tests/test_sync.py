import subprocess

import pytest

from stackatlas.github import RepoInfo
from stackatlas.sync import auth_env, sync_repo


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def origin(tmp_path):
    repo = tmp_path / "origin"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "dev@example.com")
    _git(repo, "config", "user.name", "Test Dev")
    (repo / "go.mod").write_text("module example.com/x\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "init")
    return repo


def _info(origin, pushed_at="2026-01-01T00:00:00Z"):
    return RepoInfo(
        name="x",
        full_name="acme/x",
        clone_url=origin.as_uri(),
        html_url="https://github.com/acme/x",
        default_branch="main",
        pushed_at=pushed_at,
    )


def _head(path):
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_clones_and_reports_sha(origin, tmp_path):
    synced = sync_repo(_info(origin), tmp_path / "cache", token=None)
    assert (synced.path / "go.mod").exists()
    assert synced.sha == _head(origin)


def test_skips_when_pushed_at_unchanged(origin, tmp_path):
    cache = tmp_path / "cache"
    sync_repo(_info(origin), cache, token=None)
    (origin / "new.txt").write_text("x")
    _git(origin, "add", ".")
    _git(origin, "commit", "-m", "second")
    synced = sync_repo(_info(origin), cache, token=None)
    assert not (synced.path / "new.txt").exists()


def test_refreshes_when_pushed_at_changes(origin, tmp_path):
    cache = tmp_path / "cache"
    sync_repo(_info(origin), cache, token=None)
    (origin / "new.txt").write_text("x")
    _git(origin, "add", ".")
    _git(origin, "commit", "-m", "second")
    synced = sync_repo(_info(origin, pushed_at="2026-02-01T00:00:00Z"), cache, token=None)
    assert (synced.path / "new.txt").exists()
    assert synced.sha == _head(origin)


def test_token_never_lands_in_git_config(origin, tmp_path):
    synced = sync_repo(_info(origin), tmp_path / "cache", token="secret-token")
    assert "secret-token" not in (synced.path / ".git" / "config").read_text()


def test_auth_env_scopes_header_to_clone_host():
    env = auth_env("https://github.com/acme/x.git", "tok")
    assert env["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert env["GIT_CONFIG_VALUE_0"].startswith("AUTHORIZATION: basic ")
    assert "tok" not in env["GIT_CONFIG_VALUE_0"]
