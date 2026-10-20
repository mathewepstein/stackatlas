import json
from pathlib import Path

from stackatlas.config import Config
from stackatlas.scan import build_graph, discover_local
from stackatlas.schema import dump_graph, dump_unresolved

GOLDEN = Path(__file__).parent / "golden"
CONFIG = Config(layers={"orchestration": ["*-orchestration"]})

JAVA = "src/main/java/com/acme/orders"
RES = "src/main/resources"
TF = "stacks/edge-prod/main.tf"
EXPECTED_EDGES = [
    ("function:edge/notify", "repo:billing-api", "heuristic", ["prod"],
     [(TF, 68), ("stacks/edge-prod/src/notify.py", 3)]),
    ("gateway:edge/public", "repo:orders-orchestration", "heuristic", ["prod"], [(TF, 42)]),
    ("gateway:partner/partner", "repo:pricing-svc", "heuristic", [],
     [("stacks/partner/main.tf", 18)]),
    ("repo:admin-next", "repo:gateway-node", "exact", ["prod"],
     [(".env.production", 1), ("lib/api.ts", 1)]),
    ("repo:billing-api", "datastore:redis/orders-cache", "heuristic", ["prod"], [(".env", 2)]),
    ("repo:billing-api", "repo:inventory-svc", "heuristic", [],
     [(".env", 1), ("app/clients.py", 6)]),
    ("repo:billing-api", "repo:pricing-svc", "exact", [], [("app/clients.py", 5)]),
    ("repo:checkout-ui", "bucket:acme-assets", "exact", ["prod"], [("buildspec.yml", 5)]),
    ("repo:checkout-ui", "repo:gateway-node", "exact", [], [(".env", 1), ("src/http.ts", 3)]),
    ("repo:deploy-charts", "workload:orders/orders-web", "exact", ["dev", "prod"],
     [("charts/orders/templates/deployment.yaml", 3)]),
    ("repo:gateway-node", "repo:billing-api", "heuristic", [], [("src/routes.js", 3)]),
    ("repo:gateway-node", "repo:orders-orchestration", "exact", ["prod"],
     [("src/routes.js", 2), (TF, 7)]),
    ("repo:inventory-svc", "repo:pricing-svc", "heuristic", [],
     [("internal/pricing/client.go", 10)]),
    ("repo:notifications-worker", "datastore:mongo/events-mongo.acme.internal", "exact", ["prod"],
     [("worker.py", 7)]),
    ("repo:notifications-worker", "external:hooks.slack.com", "exact", [], [("worker.py", 5)]),
    ("repo:notifications-worker", "function:edge/notify", "exact", ["prod"],
     [("buildspec.yml", 5)]),
    ("repo:notifications-worker", "repo:billing-api", "heuristic", [], [("worker.py", 6)]),
    ("repo:orders-orchestration", "repo:orders-service", "exact", [],
     [(f"{JAVA}/OrdersClient.java", 5)]),
    ("repo:orders-orchestration", "repo:pricing-svc", "heuristic", ["dev"],
     [(f"{JAVA}/PricingClient.java", 5), (f"{RES}/application-dev.yml", 2),
      (f"{RES}/application.yml", 5)]),
    ("repo:orders-service", "datastore:postgres/orders-db", "exact", ["prod"],
     [(f"{RES}/application-prod.properties", 2), (f"{RES}/application.yml", 5)]),
    ("repo:orders-service", "repo:inventory-svc", "exact", ["prod"],
     [(f"{JAVA}/InventoryClient.java", 6), (f"{RES}/application-prod.properties", 1),
      (f"{RES}/application.yml", 7)]),
    ("repo:orders-service", "repo:pricing-svc", "heuristic", ["prod"], [(TF, 100)]),
    ("repo:platform-infra", "bucket:acme-assets", "exact", ["prod"], [(TF, 93)]),
    ("repo:platform-infra", "datastore:postgres/orders-db", "exact", ["prod"], [(TF, 75)]),
    ("repo:platform-infra", "datastore:redis/orders-cache", "exact", ["prod"], [(TF, 80)]),
    ("repo:platform-infra", "function:edge/notify", "exact", ["prod"], [(TF, 61)]),
    ("repo:platform-infra", "gateway:edge/public", "exact", ["prod"], [(TF, 22)]),
    ("repo:platform-infra", "gateway:partner/partner", "exact", [],
     [("stacks/partner/main.tf", 1)]),
    ("repo:platform-infra", "queue:orders-events", "exact", ["prod"], [(TF, 85)]),
    ("repo:platform-infra", "topic:alerts", "exact", ["prod"], [(TF, 89)]),
    ("repo:platform-mono/admin-api", "repo:pricing-svc", "exact", ["prod"],
     [("admin-api/src/main/java/com/acme/admin/PricingClient.java", 5),
      ("admin-api/src/main/resources/application-prod.properties", 1)]),
    ("repo:platform-mono/portal-api", "repo:orders-service", "exact", [],
     [("portal-api/src/main/java/com/acme/portal/OrdersClient.java", 5)]),
    ("repo:platform-mono/web/portal-ui", "repo:platform-mono/portal-api", "heuristic", [],
     [("web/portal-ui/.env", 1), ("web/portal-ui/src/api.ts", 1)]),
    ("repo:pricing-svc", "external:api.exchangerate.host", "exact", [],
     [("internal/fx/client.go", 5)]),
    ("repo:web-portal", "external:analytics.thirdparty.io", "exact", ["prod"],
     [(".env.production", 2), ("src/analytics.ts", 1)]),
    ("repo:web-portal", "repo:orders-orchestration", "exact", ["dev", "prod"],
     [(".env.development", 1), (".env.production", 1), ("src/api.ts", 1)]),
    ("workload:orders/orders-web", "datastore:postgres/orders-db", "heuristic", ["dev", "prod"],
     [("charts/orders/templates/deployment.yaml", 19)]),
    ("workload:orders/orders-web", "repo:pricing-svc", "heuristic", ["dev", "prod"],
     [("charts/orders/templates/deployment.yaml", 17)]),
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
        ("prod-events-mongo.acme.internal", "host", 1),
    ]
    types = [e.type for e in result.graph.edges if e.type != "http"]
    assert types == (
        ["datastore", "deploy", "deploy", "datastore", "deploy", "datastore"]
        + ["deploy"] * 8 + ["datastore"]
    )


def test_ci_entries_attach_to_nodes(acme):
    by = {n.id: n for n in build_graph("acme", discover_local(acme), CONFIG).graph.nodes}
    worker = by["repo:notifications-worker"].ci
    assert [(c.system, c.path, c.repo, c.registries) for c in worker] == [
        ("codebuild", "buildspec.yml", None, ["123456789012.dkr.ecr.us-east-1.amazonaws.com"]),
    ]
    assert [(c.system, c.path, c.registries) for c in by["repo:ui-kit"].ci] == [
        ("github-actions", ".github/workflows/release.yml", ["npm.pkg.github.com"]),
    ]
    assert [(c.system, c.path, c.repo) for c in by["repo:orders-service"].ci] == [
        ("codebuild", "stacks/edge-prod/main.tf", "platform-infra"),
    ]
    assert by["repo:web-portal"].ci == []


def test_terraform_declares_infra_nodes(acme):
    graph = build_graph("acme", discover_local(acme), CONFIG).graph
    infra = [n for n in graph.nodes if n.kind not in ("external",) and not n.id.startswith("repo:")]
    assert [(n.id, n.kind, n.layer, n.envs, n.endpoints) for n in infra] == [
        ("bucket:acme-assets", "bucket", "bucket", ["prod"], []),
        ("datastore:mongo/events-mongo.acme.internal", "datastore", "datastore", ["prod"], []),
        ("datastore:postgres/orders-db", "datastore", "datastore", ["prod"], []),
        ("datastore:redis/orders-cache", "datastore", "datastore", ["prod"], []),
        ("function:edge/notify", "function", "function", ["prod"], []),
        ("gateway:edge/public", "gateway", "edge", ["prod"], ["POST /v1/orders/{proxy+}"]),
        ("gateway:partner/partner", "gateway", "edge", [], []),
        ("queue:orders-events", "queue", "queue", ["prod"], []),
        ("topic:alerts", "topic", "topic", ["prod"], []),
        ("workload:orders/orders-web", "workload", "service", ["dev", "prod"], []),
    ]
    by = {n.id: n for n in graph.nodes}
    assert by["gateway:edge/public"].sha == by["repo:platform-infra"].sha


def test_monorepo_sub_apps_become_nodes(acme):
    graph = build_graph("acme", discover_local(acme), CONFIG).graph
    by = {n.id: n for n in graph.nodes}
    root = by["repo:platform-mono"]
    assert (root.kind, root.layer, root.parent) == ("group", "group", None)
    children = [n for n in graph.nodes if n.parent]
    assert [(n.id, n.name, n.kind, n.parent) for n in children] == [
        ("repo:platform-mono/admin-api", "admin-api", "service", "repo:platform-mono"),
        ("repo:platform-mono/portal-api", "portal-api", "service", "repo:platform-mono"),
        ("repo:platform-mono/web/portal-ui", "portal-ui", "frontend", "repo:platform-mono"),
    ]
    assert all((n.sha, n.repo, n.url) == (root.sha, root.repo, root.url) for n in children)


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


def test_deploy_edges_from_ci_and_terraform_merge(tmp_path):
    repo = tmp_path / "site"
    repo.mkdir()
    (repo / "main.tf").write_text('resource "aws_s3_bucket" "x" {\n  bucket = "site-assets"\n}\n')
    (repo / "buildspec.yml").write_text("phases:\n  build:\n    commands:\n      - aws s3 sync . s3://site-assets\n")
    graph = build_graph("acme", discover_local(tmp_path), Config()).graph
    deploys = [e for e in graph.edges if e.type == "deploy"]
    assert [(e.source, e.target, [(v.path, v.line) for v in e.evidence]) for e in deploys] == [
        ("repo:site", "bucket:site-assets", [("buildspec.yml", 4), ("main.tf", 1)]),
    ]


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
