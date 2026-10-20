from stackatlas.config import Config
from stackatlas.detectors import detect, java_http


def test_fixture_orders_orchestration(acme):
    refs = detect("orders-orchestration", acme / "orders-orchestration", Config(), [java_http])
    by = {(r.path, r.line): r for r in refs}
    feign = by["src/main/java/com/acme/orders/OrdersClient.java", 5]
    assert (feign.kind, feign.value) == ("name", "orders-service")
    pricing = by["src/main/java/com/acme/orders/PricingClient.java", 5]
    assert (pricing.kind, pricing.value) == ("var", "pricing.url")
    dev = by["src/main/resources/application-dev.yml", 2]
    assert (dev.kind, dev.value, dev.key, dev.env) == (
        "url", "https://dev-pricing.acme.com", "pricing.url", "dev",
    )
    base = by["src/main/resources/application.yml", 5]
    assert (base.value, base.env) == ("https://pricing.acme.com", None)
    assert len(refs) == 4


def test_fixture_orders_service(acme):
    refs = detect("orders-service", acme / "orders-service", Config(), [java_http])
    by = {(r.path, r.line): r for r in refs}
    assert ("src/main/resources/application.yml", 5) not in by
    inv = by["src/main/resources/application.yml", 7]
    assert (inv.kind, inv.value, inv.key) == (
        "url", "http://inventory-svc:8080", "inventory.base-url",
    )
    props = by["src/main/resources/application-prod.properties", 1]
    assert (props.value, props.env) == ("https://inventory.acme.com", "prod")
    val = by["src/main/java/com/acme/orders/InventoryClient.java", 6]
    assert (val.kind, val.value) == ("var", "inventory.base-url")
    assert len(refs) == 3


def test_profile_docs_in_single_yml(tmp_path):
    (tmp_path / "application.yml").write_text(
        "orders:\n  url: https://orders.acme.com\n"
        "---\n"
        "spring:\n  config:\n    activate:\n      on-profile: stage\n"
        "orders:\n  url: https://stage-orders.acme.com\n"
    )
    refs = detect("x", tmp_path, Config(), [java_http])
    assert [(r.value, r.env, r.line) for r in refs] == [
        ("https://orders.acme.com", None, 2),
        ("https://stage-orders.acme.com", "stage", 9),
    ]


def test_placeholder_without_default_is_var_and_secrets_dropped(tmp_path):
    (tmp_path / "application.properties").write_text(
        "billing.url=${BILLING_URL}\nbilling.token=${BILLING_TOKEN}\nserver.port=8080\n"
    )
    refs = detect("x", tmp_path, Config(), [java_http])
    assert [(r.kind, r.value, r.key) for r in refs] == [("var", "BILLING_URL", "billing.url")]


def test_source_literals_value_defaults_and_comments(tmp_path):
    (tmp_path / "A.java").write_text(
        'WebClient c = WebClient.create("https://pricing.acme.com");\n'
        '@Value("${inventory.url:http://inventory-svc:8080}") String inv;\n'
        '// WebClient.create("https://old.acme.com")\n'
        'String env = System.getenv("BILLING_HOST");\n'
    )
    refs = detect("x", tmp_path, Config(), [java_http])
    assert [(r.kind, r.value, r.key) for r in refs] == [
        ("url", "https://pricing.acme.com", None),
        ("url", "http://inventory-svc:8080", "inventory.url"),
        ("var", "BILLING_HOST", None),
    ]


def test_datastore_and_queue_keys_are_not_http(tmp_path):
    (tmp_path / "A.java").write_text(
        '@Value("${spring.datasource.url}") String db;\n'
        '@Value("${aws.sqs.queue-url}") String q;\n'
    )
    (tmp_path / "application.properties").write_text(
        "spring.datasource.url=${DB_URL}\nspring.redis.host=cache.internal\n"
    )
    assert detect("x", tmp_path, Config(), [java_http]) == []


def test_feign_name_kept_as_fallback_beside_url(tmp_path):
    (tmp_path / "A.java").write_text(
        '@FeignClient(name = "credit-microservice", url = "${feign.credit.url}")\ninterface A {}\n'
        '@FeignClient(name = "pricing", url = "https://pricing.acme.com")\ninterface B {}\n'
    )
    refs = detect("x", tmp_path, Config(), [java_http])
    assert [(r.kind, r.value, r.fallback) for r in refs] == [
        ("var", "feign.credit.url", "credit-microservice"),
        ("url", "https://pricing.acme.com", "pricing"),
    ]


def test_any_properties_file_is_config_with_env_from_name(tmp_path):
    props = tmp_path / "src" / "main" / "resources" / "property"
    props.mkdir(parents=True)
    (props / "common.properties").write_text("orders.url=https://orders.acme.com\n")
    (props / "dev.properties").write_text("signupUrl = https://dev-signup.acme.com\n")
    (tmp_path / "deploy.yml").write_text("url: https://ignored.acme.com\n")
    (tmp_path / "gradle.properties").write_text("sonar.host.url=https://sonarcloud.io\n")
    refs = detect("x", tmp_path, Config(), [java_http])
    assert [(r.value, r.key, r.env) for r in refs] == [
        ("https://orders.acme.com", "orders.url", None),
        ("https://dev-signup.acme.com", "signupUrl", "dev"),
    ]


def test_feign_bare_value_and_literal_url(tmp_path):
    (tmp_path / "A.java").write_text(
        '@FeignClient("billing")\ninterface A {}\n'
        '@FeignClient(name = "x", url = "https://pricing.acme.com")\ninterface B {}\n'
    )
    refs = detect("x", tmp_path, Config(), [java_http])
    assert [(r.kind, r.value, r.line) for r in refs] == [
        ("name", "billing", 1),
        ("url", "https://pricing.acme.com", 3),
    ]
