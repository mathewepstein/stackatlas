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
MTF = "stacks/edge-prod/messaging.tf"
AUDIT = "admin-api/src/main/java/com/acme/admin/AuditEvents.java"
EXPECTED_EDGES = [
    ("function:edge/notify", "repo:billing-api", "heuristic", ["prod"],
     [(TF, 68), ("stacks/edge-prod/src/notify.py", 3)]),
    ("function:edge/retry", "queue:notify-retry", "exact", ["prod"],
     [(MTF, 18), ("stacks/edge-prod/src/retry.py", 10)]),
    ("gateway:edge/public", "repo:orders-orchestration", "heuristic", ["prod"], [(TF, 42)]),
    ("gateway:partner/partner", "repo:pricing-svc", "heuristic", [],
     [("stacks/partner/main.tf", 18)]),
    ("queue:audit-log", "repo:platform-mono/admin-api", "exact", ["prod"],
     [(AUDIT, 8), ("admin-api/src/main/resources/application-prod.properties", 2)]),
    ("queue:orders-events", "function:edge/notify", "exact", ["prod"], [(MTF, 24)]),
    ("queue:orders-events", "repo:orders-orchestration", "exact", ["prod"],
     [(f"{JAVA}/OrderEventsListener.java", 6), (MTF, 37)]),
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
    ("repo:notifications-worker", "topic:alerts", "exact", ["prod"],
     [(".env.production", 1), ("alerts.py", 10)]),
    ("repo:orders-orchestration", "repo:inventory-svc", "exact", [], [("build.gradle.kts", 8)]),
    ("repo:orders-orchestration", "repo:orders-service", "exact", [],
     [(f"{JAVA}/OrdersClient.java", 5)]),
    ("repo:orders-orchestration", "repo:pricing-svc", "heuristic", ["dev"],
     [(f"{JAVA}/PricingClient.java", 5), (f"{RES}/application-dev.yml", 2),
      (f"{RES}/application.yml", 5)]),
    ("repo:orders-service", "datastore:postgres/orders-db", "exact", ["prod"],
     [(f"{RES}/application-prod.properties", 2), (f"{RES}/application.yml", 5)]),
    ("repo:orders-service", "queue:orders-events", "heuristic", ["prod"],
     [(f"{JAVA}/OrderEventsPublisher.java", 17), (f"{RES}/application-prod.properties", 3)]),
    ("repo:orders-service", "repo:inventory-svc", "exact", ["prod"],
     [(f"{JAVA}/InventoryClient.java", 6), (f"{RES}/application-prod.properties", 1),
      (f"{RES}/application.yml", 7)]),
    ("repo:orders-service", "repo:pricing-svc", "heuristic", ["prod"], [(TF, 100)]),
    ("repo:platform-infra", "bucket:acme-assets", "exact", ["prod"], [(TF, 93)]),
    ("repo:platform-infra", "datastore:postgres/orders-db", "exact", ["prod"], [(TF, 75)]),
    ("repo:platform-infra", "datastore:redis/orders-cache", "exact", ["prod"], [(TF, 80)]),
    ("repo:platform-infra", "function:edge/notify", "exact", ["prod"], [(TF, 61)]),
    ("repo:platform-infra", "function:edge/retry", "exact", ["prod"], [(MTF, 13)]),
    ("repo:platform-infra", "gateway:edge/public", "exact", ["prod"], [(TF, 22)]),
    ("repo:platform-infra", "gateway:partner/partner", "exact", [],
     [("stacks/partner/main.tf", 1)]),
    ("repo:platform-infra", "queue:notify-retry", "exact", ["prod"], [(MTF, 3)]),
    ("repo:platform-infra", "queue:orders-events", "exact", ["prod"], [(TF, 85)]),
    ("repo:platform-infra", "topic:alerts", "exact", ["prod"], [(TF, 89)]),
    ("repo:platform-mono/admin-api", "repo:pricing-svc", "exact", ["prod"],
     [("admin-api/src/main/java/com/acme/admin/PricingClient.java", 5),
      ("admin-api/src/main/resources/application-prod.properties", 1)]),
    ("repo:platform-mono/admin-api", "topic:price-changes", "exact", [], [(AUDIT, 10)]),
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
    ("topic:alerts", "queue:orders-events", "exact", ["prod"], [(MTF, 29)]),
    ("topic:inventory-updates", "repo:platform-mono/admin-api", "exact", [], [(AUDIT, 4)]),
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
        ["event"] * 4
        + ["datastore", "deploy", "deploy", "datastore", "deploy", "event", "datastore", "event"]
        + ["deploy"] * 10
        + ["event", "event", "event", "datastore"]
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
        ("function:edge/retry", "function", "function", ["prod"], []),
        ("gateway:edge/public", "gateway", "edge", ["prod"], ["POST /v1/orders/{proxy+}"]),
        ("gateway:partner/partner", "gateway", "edge", [], []),
        ("queue:audit-log", "queue", "queue", ["prod"], []),
        ("queue:notify-retry", "queue", "queue", ["prod"], []),
        ("queue:orders-events", "queue", "queue", ["prod"], []),
        ("topic:alerts", "topic", "topic", ["prod"], []),
        ("topic:inventory-updates", "topic", "topic", [], []),
        ("topic:price-changes", "topic", "topic", [], []),
        ("workload:orders/orders-web", "workload", "service", ["dev", "prod"], []),
    ]
    by = {n.id: n for n in graph.nodes}
    assert by["gateway:edge/public"].sha == by["repo:platform-infra"].sha
    assert by["queue:audit-log"].sha is None


def test_openapi_endpoints_attach_to_the_spec_owner(acme):
    graph = build_graph("acme", discover_local(acme), CONFIG).graph
    by = {n.id: n for n in graph.nodes}
    assert by["repo:inventory-svc"].endpoints == ["GET /stock/{sku}"]
    assert by["repo:pricing-svc"].endpoints == ["GET /quote/{sku}", "GET /rates", "POST /rates"]
    assert by["repo:orders-orchestration"].endpoints == []
    assert by["repo:handbook"].endpoints == []


def test_vendor_spec_consumed_by_a_generator_is_not_the_repo_itself(tmp_path):
    repo = tmp_path / "billing"
    (repo / "specs").mkdir(parents=True)
    (repo / "specs" / "vendor.yaml").write_text(
        "openapi: 3.0.3\ninfo:\n  title: API Reference\nservers:\n"
        "  - url: https://gw.vendorpay.com/v4/gateway\npaths:\n  /charge:\n    post: {}\n"
    )
    (repo / "build.gradle").write_text(
        'openApiGenerate {\n    inputSpec = "$projectDir/specs/vendor.yaml".toString()\n}\n'
    )
    result = build_graph("acme", discover_local(tmp_path), Config())
    assert [(e.source, e.target, [(v.path, v.line) for v in e.evidence])
            for e in result.graph.edges] == [
        ("repo:billing", "external:gw.vendorpay.com", [("build.gradle", 2)]),
    ]
    assert all(n.endpoints == [] for n in result.graph.nodes)
    assert [(u.ref, u.kind) for u in result.unresolved] == [("gw.vendorpay.com", "host")]


def test_unowned_spec_in_docs_repo_is_reported(tmp_path):
    (tmp_path / "wiki").mkdir()
    (tmp_path / "wiki" / "ledger.yaml").write_text(
        "openapi: 3.0.0\ninfo:\n  title: Ledger API\nservers:\n  - url: https://ledger.acme.com\n"
        "paths:\n  /entries:\n    get: {}\n"
    )
    result = build_graph("acme", discover_local(tmp_path), Config())
    assert all(n.endpoints == [] for n in result.graph.nodes)
    assert [(u.ref, u.kind, u.repos, [(v.path, v.line) for v in u.evidence])
            for u in result.unresolved] == [
        ("ledger-api", "name", ["wiki"], [("ledger.yaml", 1)]),
    ]


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
