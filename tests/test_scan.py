import json
from pathlib import Path

from stackatlas.config import Config
from stackatlas.scan import build_graph, discover_local
from stackatlas.schema import dump_graph, dump_unresolved

GOLDEN = Path(__file__).parent / "golden"
CONFIG = Config(layers={"orchestration": ["*-orchestration"]})

JAVA = "src/main/java/com/acme/orders"
RES = "src/main/resources"
EXPECTED_EDGES = [
    ("repo:admin-next", "repo:gateway-node", "exact", ["prod"],
     [(".env.production", 1), ("lib/api.ts", 1)]),
    ("repo:billing-api", "repo:inventory-svc", "heuristic", [],
     [(".env", 1), ("app/clients.py", 6)]),
    ("repo:billing-api", "repo:pricing-svc", "exact", [], [("app/clients.py", 5)]),
    ("repo:checkout-ui", "repo:gateway-node", "exact", [], [(".env", 1), ("src/http.ts", 3)]),
    ("repo:gateway-node", "repo:billing-api", "heuristic", [], [("src/routes.js", 3)]),
    ("repo:inventory-svc", "repo:pricing-svc", "heuristic", [],
     [("internal/pricing/client.go", 10)]),
    ("repo:notifications-worker", "external:hooks.slack.com", "exact", [], [("worker.py", 5)]),
    ("repo:notifications-worker", "repo:billing-api", "heuristic", [], [("worker.py", 6)]),
    ("repo:orders-orchestration", "repo:orders-service", "exact", [],
     [(f"{JAVA}/OrdersClient.java", 5)]),
    ("repo:orders-orchestration", "repo:pricing-svc", "heuristic", ["dev"],
     [(f"{JAVA}/PricingClient.java", 5), (f"{RES}/application-dev.yml", 2),
      (f"{RES}/application.yml", 5)]),
    ("repo:orders-service", "repo:inventory-svc", "exact", ["prod"],
     [(f"{JAVA}/InventoryClient.java", 6), (f"{RES}/application-prod.properties", 1),
      (f"{RES}/application.yml", 7)]),
    ("repo:pricing-svc", "external:api.exchangerate.host", "exact", [],
     [("internal/fx/client.go", 5)]),
    ("repo:web-portal", "external:analytics.thirdparty.io", "exact", ["prod"],
     [(".env.production", 2), ("src/analytics.ts", 1)]),
    ("repo:web-portal", "repo:orders-orchestration", "exact", ["dev", "prod"],
     [(".env.development", 1), (".env.production", 1), ("src/api.ts", 1)]),
]


def test_local_scan_matches_golden(acme):
    result = build_graph("acme", discover_local(acme), CONFIG)
    data = json.loads(dump_graph(result.graph))
    data.pop("generatedAt")
    assert data == json.loads((GOLDEN / "acme.json").read_text())
    unresolved = json.loads(dump_unresolved(result.unresolved))
    assert unresolved == json.loads((GOLDEN / "acme-unresolved.json").read_text())


def test_fixture_edges(acme):
    result = build_graph("acme", discover_local(acme), CONFIG)
    got = [
        (e.source, e.target, e.confidence, e.envs, [(v.path, v.line) for v in e.evidence])
        for e in result.graph.edges
    ]
    assert got == EXPECTED_EDGES


def test_fixture_external_nodes_and_unresolved(acme):
    result = build_graph("acme", discover_local(acme), CONFIG)
    externals = [n.id for n in result.graph.nodes if n.kind == "external"]
    assert externals == [
        "external:analytics.thirdparty.io",
        "external:api.exchangerate.host",
        "external:hooks.slack.com",
    ]
    assert [(u.ref, u.kind, u.count) for u in result.unresolved] == [
        ("analytics.thirdparty.io", "host", 2),
        ("api.exchangerate.host", "host", 1),
        ("hooks.slack.com", "host", 1),
        ("orders", "name", 1),
    ]


def test_no_secret_values_in_output(acme):
    result = build_graph("acme", discover_local(acme), CONFIG)
    assert "not-a-real-key" not in dump_graph(result.graph)
    assert "not-a-real-key" not in dump_unresolved(result.unresolved)


def test_overrides_win_over_classifier(acme):
    overrides = {"handbook": {"kind": "service", "layer": "docs"}}
    config = Config.model_validate({"overrides": overrides})
    graph = build_graph("acme", discover_local(acme), config).graph
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
