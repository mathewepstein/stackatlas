import json
from datetime import UTC, datetime

from typer.testing import CliRunner

from stackatlas import cli
from stackatlas.cli import app
from stackatlas.runtime import RuntimeData

runner = CliRunner()


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
