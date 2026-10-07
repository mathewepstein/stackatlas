import json

from typer.testing import CliRunner

from stackatlas import cli
from stackatlas.cli import app

runner = CliRunner()


def test_scan_local_writes_graph(acme, tmp_path):
    out = tmp_path / "out"
    result = runner.invoke(app, ["scan", "--local", str(acme), "--out", str(out)])
    assert result.exit_code == 0, result.output
    data = json.loads((out / "graph.json").read_text())
    assert data["org"] == "acme"
    assert len(data["nodes"]) == 17


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
