from stackatlas.aliases import (
    AliasIndex,
    build_index,
    declared_names,
    name_candidates,
    name_variants,
    strip_service_suffix,
)
from stackatlas.config import Config
from stackatlas.scan import ScannedRepo


def test_strip_service_suffix():
    assert strip_service_suffix("orders-service") == "orders"
    assert strip_service_suffix("customer-microservice") == "customer"
    assert strip_service_suffix("customer-ms-http") == "customer"
    assert strip_service_suffix("checkout_ui") == "checkout"
    assert strip_service_suffix("web-portal") == "web-portal"
    assert strip_service_suffix("api") == "api"


def test_name_candidates_are_progressive():
    assert name_candidates("customer-ms-http") == ["customer-ms-http", "customer-ms", "customer"]
    assert name_candidates("web-portal") == ["web-portal"]


def test_name_variants_follow_the_suffix_family():
    assert name_variants("customer-microservice") == {
        "customer", "customer-ms", "customer-svc", "customer-service",
    }
    assert name_variants("signup-orchestration") == {"signup", "signup-orch"}
    assert name_variants("billing-api") == {"billing"}
    assert name_variants("web-portal") == set()


def test_squashed_lookup():
    index = AliasIndex()
    index.add("customer-microservice", "repo:customer-microservice", 2)
    assert index.lookup("customermicroservice") is None
    assert index.lookup_squashed("customer_microservice") == "repo:customer-microservice"
    assert index.lookup_squashed("CustomerMicroService") == "repo:customer-microservice"


def test_declared_names_from_fixture(acme):
    assert declared_names(acme / "orders-orchestration") == {
        "orders-orchestration", "orders.acme.com",
    }
    assert declared_names(acme / "gateway-node") == {
        "gateway-node", "acme-gateway", "api.acme.com",
    }
    assert declared_names(acme / "ui-kit") == {"ui-kit"}
    assert declared_names(acme / "inventory-svc") == {"inventory-svc"}
    assert declared_names(acme / "py-helpers") == {"acme-py-helpers"}
    assert declared_names(acme / "orders-service") == {"orders-service"}
    assert declared_names(acme / "handbook") == set()


def test_declared_names_more_sources(tmp_path):
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  orders:\n    image: x\n  db:\n    image: postgres\n"
    )
    (tmp_path / "k8s.yaml").write_text(
        "kind: Service\nmetadata:\n  name: orders-svc\n"
        "---\n"
        "kind: Ingress\nspec:\n  tls:\n    - hosts: [orders.acme.com]\n"
        "  rules:\n    - host: Orders.acme.com\n"
    )
    (tmp_path / "swagger.json").write_text(
        '{"info": {"title": "Orders API"}, "host": "api.acme.com", "basePath": "/orders/v1/"}'
    )
    (tmp_path / "settings.gradle.kts").write_text('rootProject.name = "orders-core"\n')
    (tmp_path / "templates").mkdir()
    (tmp_path / "templates" / "svc.yaml").write_text(
        "kind: Service\nmetadata:\n  name: {{ .Values.name }}\n"
    )
    assert declared_names(tmp_path) == {
        "orders", "db", "orders-svc", "orders.acme.com", "orders-api",
        "api.acme.com/orders/v1", "orders-core",
    }


def test_index_tiers_and_ambiguity(acme):
    repos = [ScannedRepo(name=p.name, path=p) for p in sorted(acme.iterdir())]
    kinds = {"deploy-charts": "infra", "platform-infra": "infra"}
    config = Config(aliases={"orders-service": ["legacy-orders.acme.com"]})
    index = build_index(repos, kinds, config)
    assert index.lookup("legacy-orders.acme.com") == "repo:orders-service"
    assert index.lookup("orders.acme.com") == "repo:orders-orchestration"
    assert index.lookup("ORDERS-SERVICE") == "repo:orders-service"
    assert index.lookup("orders") is None
    assert index.lookup("orders-ms") == "repo:orders-service"
    assert index.lookup("orders-orch") == "repo:orders-orchestration"
    assert index.lookup("billing") == "repo:billing-api"
    assert index.lookup("api.acme.com") == "repo:gateway-node"
    assert index.lookup("nope") is None


def test_infra_repos_only_contribute_their_name(tmp_path):
    (tmp_path / "charts" / "pricing").mkdir(parents=True)
    (tmp_path / "charts" / "pricing" / "Chart.yaml").write_text("name: pricing\n")
    (tmp_path / "k8s.yaml").write_text("kind: Service\nmetadata:\n  name: pricing\n")
    repos = [ScannedRepo(name="deploy-charts", path=tmp_path)]
    index = build_index(repos, {"deploy-charts": "infra"}, Config())
    assert index.lookup("pricing") is None
    assert index.lookup("deploy-charts") == "repo:deploy-charts"
    as_service = build_index(repos, {"deploy-charts": "service"}, Config())
    assert as_service.lookup("pricing") == "repo:deploy-charts"


def test_higher_tier_resolves_lower_tier_conflict():
    index = AliasIndex()
    index.add("api.acme.com", "repo:a", 1)
    index.add("api.acme.com", "repo:b", 1)
    assert index.lookup("api.acme.com") is None
    index.add("https://api.acme.com:443/", "repo:a", 0)
    assert index.lookup("api.acme.com") == "repo:a"
