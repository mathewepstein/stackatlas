import json
from pathlib import Path

from stackatlas.config import Config
from stackatlas.scan import build_graph, discover_local
from stackatlas.schema import dump_graph

GOLDEN = Path(__file__).parent / "golden" / "acme-nodes.json"


def test_local_scan_matches_golden(acme):
    config = Config(layers={"orchestration": ["*-orchestration"]})
    graph = build_graph("acme", discover_local(acme), config)
    data = json.loads(dump_graph(graph))
    data.pop("generatedAt")
    assert data == json.loads(GOLDEN.read_text())


def test_overrides_win_over_classifier(acme):
    overrides = {"handbook": {"kind": "service", "layer": "docs"}}
    config = Config.model_validate({"overrides": overrides})
    graph = build_graph("acme", discover_local(acme), config)
    node = next(n for n in graph.nodes if n.name == "handbook")
    assert (node.kind, node.layer) == ("service", "docs")


def test_discover_local_descends_into_container_dirs(tmp_path):
    (tmp_path / "group" / "app-a" / ".git").mkdir(parents=True)
    (tmp_path / "group" / "notes").mkdir()
    (tmp_path / "solo" / ".git").mkdir(parents=True)
    repos = discover_local(tmp_path)
    assert [r.name for r in repos] == ["app-a", "solo"]


def test_discover_local_skips_hidden_and_excluded(tmp_path):
    (tmp_path / ".cache").mkdir()
    (tmp_path / "keep").mkdir()
    (tmp_path / "skip-me").mkdir()
    (tmp_path / "file.txt").write_text("")
    repos = discover_local(tmp_path, Config(exclude=["skip-*"]))
    assert [r.name for r in repos] == ["keep"]
    assert repos[0].sha is None
