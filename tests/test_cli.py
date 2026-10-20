import json
from datetime import UTC, datetime

import httpx
import pytest
import yaml
from typer.testing import CliRunner

from stackatlas import cli
from stackatlas.cli import app
from stackatlas.runtime import RuntimeData

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_scan_local_writes_graph(acme, tmp_path):
    out = tmp_path / "out"
    result = runner.invoke(app, ["scan", "--local", str(acme), "--out", str(out)])
    assert result.exit_code == 0, result.output
    data = json.loads((out / "graph.json").read_text())
    assert data["org"] == "acme"
    assert len(data["nodes"]) == 34
    assert len(data["edges"]) == 38
    assert len(json.loads((out / "unresolved.json").read_text())) == 4
    assert "38 edges" in result.output and "4 unresolved" in result.output


class _FakeSource:
    def fetch(self):
        now = datetime(2026, 10, 20, tzinfo=UTC)
        pairs = frozenset({("orders-orchestration", "orders-service")})
        services = frozenset({"orders-orchestration", "orders-service"})
        return [RuntimeData("datadog", "prod", now, now, services, pairs)]


def test_scan_runtime_overlays_observed_edges(acme, tmp_path, monkeypatch):
    monkeypatch.setitem(cli.RUNTIME_SOURCES, "datadog", lambda config: _FakeSource())
    out = tmp_path / "out"
    args = ["scan", "--local", str(acme), "--out", str(out), "--runtime", "datadog"]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    edges = json.loads((out / "graph.json").read_text())["edges"]
    assert [e["target"] for e in edges if e["observed"]] == ["repo:orders-service"]
    assert "1 observed, 0 not seen, 0 runtime-only" in result.output


def test_scan_runtime_without_keys_fails_cleanly(acme, tmp_path, monkeypatch):
    for var in ("DD_API_KEY", "DATADOG_API_KEY", "DD_APP_KEY", "DATADOG_APP_KEY"):
        monkeypatch.delenv(var, raising=False)
    args = ["scan", "--local", str(acme), "--out", str(tmp_path), "--runtime", "datadog"]
    result = runner.invoke(app, args)
    assert result.exit_code != 0
    assert "DD_API_KEY" in result.output


def test_scan_rejects_unknown_runtime(acme, tmp_path):
    args = ["scan", "--local", str(acme), "--out", str(tmp_path), "--runtime", "xray"]
    result = runner.invoke(app, args)
    assert result.exit_code != 0


def test_scan_reads_local_and_runtime_from_config(acme, tmp_path, monkeypatch):
    monkeypatch.setitem(cli.RUNTIME_SOURCES, "datadog", lambda config: _FakeSource())
    cfg = tmp_path / "stackatlas.yml"
    cfg.write_text(f"local: {acme}\nruntime:\n  sources: [datadog]\n")
    out = tmp_path / "out"
    result = runner.invoke(app, ["scan", "--config", str(cfg), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "1 observed" in result.output
    assert json.loads((out / "graph.json").read_text())["org"] == "acme"


def test_scan_flag_overrides_config_source(acme, tmp_path):
    cfg = tmp_path / "stackatlas.yml"
    cfg.write_text("org: someone\n")
    out = tmp_path / "out"
    args = ["scan", "--config", str(cfg), "--local", str(acme), "--out", str(out)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output


def _init(tmp_path, monkeypatch, args, user_input="", dd=True):
    monkeypatch.setattr(cli, "resolve_token", lambda: "tok")
    monkeypatch.setattr(cli, "check_owner", lambda owner, token: 12)
    monkeypatch.setattr(cli, "validate_datadog", lambda environ: dd)
    path = tmp_path / "stackatlas.yml"
    result = runner.invoke(app, ["init", "--path", str(path), *args], input=user_input)
    return result, path


def test_init_writes_org_and_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "k")
    monkeypatch.setenv("DD_APP_KEY", "a")
    result, path = _init(tmp_path, monkeypatch, ["--org", "acme"], "y\n")
    assert result.exit_code == 0, result.output
    assert yaml.safe_load(path.read_text()) == {
        "org": "acme", "runtime": {"sources": ["datadog"]},
    }
    assert "12 repos" in result.output
    assert "stackatlas scan" in result.output and "stackatlas serve" in result.output
    assert "tok" not in path.read_text() and "k\n" not in path.read_text()


def test_init_prompts_for_org(tmp_path, monkeypatch):
    for var in ("DD_API_KEY", "DATADOG_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    result, path = _init(tmp_path, monkeypatch, [], "acme\n")
    assert result.exit_code == 0, result.output
    assert yaml.safe_load(path.read_text()) == {"org": "acme"}
    assert "Datadog" in result.output


def test_init_local_skips_github(tmp_path, monkeypatch):
    for var in ("DD_API_KEY", "DATADOG_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(cli, "check_owner", lambda owner, token: pytest.fail("called"))
    path = tmp_path / "stackatlas.yml"
    result = runner.invoke(app, ["init", "--path", str(path), "--local", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert yaml.safe_load(path.read_text()) == {"local": str(tmp_path)}


def test_init_refuses_to_overwrite(tmp_path, monkeypatch):
    (tmp_path / "stackatlas.yml").write_text("org: old\n")
    result, path = _init(tmp_path, monkeypatch, ["--org", "acme"])
    assert result.exit_code != 0
    assert path.read_text() == "org: old\n"
    result, path = _init(tmp_path, monkeypatch, ["--org", "acme", "--force"], "n\n")
    assert result.exit_code == 0, result.output
    assert yaml.safe_load(path.read_text())["org"] == "acme"


def test_init_fails_on_bad_github_access(tmp_path, monkeypatch):
    def denied(owner, token):
        request = httpx.Request("GET", "https://api.github.com/orgs/acme")
        raise httpx.HTTPStatusError("x", request=request, response=httpx.Response(404))

    monkeypatch.setattr(cli, "resolve_token", lambda: "tok")
    monkeypatch.setattr(cli, "check_owner", denied)
    path = tmp_path / "stackatlas.yml"
    result = runner.invoke(app, ["init", "--path", str(path), "--org", "acme"])
    assert result.exit_code != 0
    assert "404" in result.output
    assert not path.exists()


def test_init_rejects_invalid_datadog_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("DD_API_KEY", "k")
    monkeypatch.setenv("DD_APP_KEY", "a")
    result, path = _init(tmp_path, monkeypatch, ["--org", "acme"], dd=False)
    assert result.exit_code == 0, result.output
    assert yaml.safe_load(path.read_text()) == {"org": "acme"}
    assert "invalid" in result.output.lower()


def test_scan_requires_exactly_one_source(tmp_path):
    result = runner.invoke(app, ["scan", "--out", str(tmp_path)])
    assert result.exit_code != 0


def test_scan_org_without_token_fails_cleanly(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "resolve_token", lambda: None)
    result = runner.invoke(app, ["scan", "--org", "acme", "--out", str(tmp_path)])
    assert result.exit_code != 0
    assert "token" in result.output.lower()


def test_resolve_token_prefers_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "from-env")
    assert cli.resolve_token() == "from-env"


def test_schema_command_prints_json_schema():
    result = runner.invoke(app, ["schema"])
    assert result.exit_code == 0
    assert "schemaVersion" in json.loads(result.output)["properties"]
