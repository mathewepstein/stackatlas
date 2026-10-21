from stackatlas.config import Config
from stackatlas.detectors import terraform

EDGE = "stacks/edge-prod/main.tf"
MESSAGING = "stacks/edge-prod/messaging.tf"


def test_fixture_declares_infra_nodes(acme):
    found = terraform.detect_repo("platform-infra", acme / "platform-infra", Config())
    by = {d.id: d for d in found.declared}
    assert sorted(by) == [
        "bucket:acme-assets",
        "datastore:postgres/orders-db",
        "datastore:redis/orders-cache",
        "function:edge/notify",
        "function:edge/retry",
        "gateway:edge/public",
        "gateway:partner/partner",
        "queue:notify-retry",
        "queue:orders-events",
        "topic:alerts",
    ]
    gw = by["gateway:edge/public"]
    assert (gw.name, gw.kind, gw.layer, gw.envs) == ("public-api", "gateway", "edge", ("prod",))
    assert gw.aliases == ("edge.acme.com",)
    assert gw.endpoints == ("POST /v1/orders/{proxy+}",)
    assert (gw.path, gw.line) == (EDGE, 22)
    assert by["gateway:partner/partner"].aliases == ("partner.acme.com",)
    fn = by["function:edge/notify"]
    assert (fn.name, fn.kind, fn.aliases) == ("notify", "function", ("prod-notify", "notify"))
    assert by["datastore:postgres/orders-db"].aliases == ("prod-orders-db", "orders-db")
    assert by["bucket:acme-assets"].aliases == ("acme-assets-prod", "acme-assets")
    assert by["queue:orders-events"].envs == ("prod",)
    assert by["queue:notify-retry"].aliases == ("notify-retry",)
    assert (by["function:edge/retry"].path, by["function:edge/retry"].line) == (MESSAGING, 13)


def test_fixture_refs_and_owners(acme):
    found = terraform.detect_repo("platform-infra", acme / "platform-infra", Config())
    refs = sorted(found.refs, key=lambda r: (r.path, r.line))
    assert [
        (r.path, r.line, r.source, r.owner, r.kind, r.value, r.key, r.env, r.fallback)
        for r in refs if r.edge_type == "http"
    ] == [
        (EDGE, 7, None, "*", "url", "https://orders.acme.com", "orders.url", "prod", "orders"),
        (EDGE, 42, "gateway:edge/public", None, "url", "prod-orders-orchestration.acme.com",
         None, "prod", None),
        (EDGE, 68, "function:edge/notify", None, "url", "https://billing-api.acme.com",
         "BILLING_URL", "prod", None),
        (EDGE, 100, None, "orders-service", "url", "https://pricing.acme.com", "pricing.url",
         "prod", "pricing"),
        ("stacks/partner/main.tf", 18, "gateway:partner/partner", None, "url",
         "pricing.acme.com", "backend_fqdn", None, None),
    ]
    assert [
        (r.line, r.source, r.owner, r.value, r.key, r.role, r.engine)
        for r in refs if r.edge_type == "event"
    ] == [
        (18, "function:edge/retry", None, "arn:aws:sqs:::*-notify-retry", "RETRY_QUEUE_URL",
         None, None),
        (24, "function:edge/notify", None, "arn:aws:sqs:::orders-events", None, "consume",
         "queue"),
        (29, None, "arn:aws:sqs:::orders-events", "arn:aws:sns:::prod-alerts", None, "consume",
         "topic"),
        (37, None, "orders-orchestration", "*-orders-events", "aws.sqs.orderEventsQueue", None,
         None),
    ]
    assert all(r.path == MESSAGING and r.env == "prod" for r in refs if r.edge_type == "event")
    assert not any("secret" in r.snippet for r in found.refs)
    assert found.owners == [
        ("platform-infra", "stacks/edge-prod/src/notify.py", "function:edge/notify"),
        ("platform-infra", "stacks/edge-prod/src/retry.py", "function:edge/retry"),
    ]


def test_codebuild_projects_attach_ci_to_their_source_repo(acme):
    found = terraform.detect_repo("platform-infra", acme / "platform-infra", Config())
    assert [(c.repo, c.system, c.path, c.declared_in, c.registries) for c in found.ci] == [
        ("orders-service", "codebuild", EDGE, "platform-infra", ()),
    ]


def test_helm_release_and_kubernetes_manifest_declare_workloads(tmp_path):
    (tmp_path / "main.tf").write_text(
        'resource "helm_release" "sc" {\n  name  = "dev-sc"\n  chart = "../helm-deploy"\n'
        '  set {\n    name  = "ingress.hosts[0].host"\n    value = "dev-sc.acme.app"\n  }\n}\n'
        'resource "kubernetes_manifest" "job" {\n  manifest = {\n    apiVersion = "batch/v1"\n'
        '    kind       = "CronJob"\n    metadata   = { name = "prod-nightly" }\n  }\n}\n'
    )
    found = terraform.detect_repo("infra", tmp_path, Config())
    assert [(d.id, d.kind, d.layer, d.aliases, d.envs) for d in found.declared] == [
        ("workload:infra/sc", "workload", "service", ("dev-sc", "sc", "dev-sc.acme.app"), ("dev",)),
        ("workload:infra/nightly", "workload", "service", ("prod-nightly", "nightly"), ("prod",)),
    ]


def test_env_tokens_in_block_names_do_not_split_nodes(tmp_path):
    (tmp_path / "main.tf").write_text(
        'resource "aws_apigatewayv2_api" "dev-partner-backend" {\n  name = "x"\n}\n'
        'resource "aws_lambda_function" "prod_login" {\n  function_name = "prod-login"\n}\n'
    )
    found = terraform.detect_repo("infra", tmp_path, Config())
    assert [d.id for d in found.declared] == [
        "gateway:infra/partner-backend", "function:infra/login",
    ]


MESSAGING_TF = (
    'locals {\n  env = "prod"\n}\n'
    'variable "env" {}\n'
    'resource "aws_sqs_queue" "change" {\n  name = "${var.env}-customer-change.fifo"\n}\n'
    'resource "aws_sns_topic" "alerts" {\n  name = "${local.env}-alerts"\n}\n'
    'resource "aws_lambda_function" "worker" {\n  function_name = "prod-worker"\n'
    "  environment {\n    variables = {\n      OUT_QUEUE_URL = aws_sqs_queue.change.url\n"
    '      PLAIN = "x"\n    }\n  }\n}\n'
    'resource "aws_lambda_event_source_mapping" "m" {\n'
    "  event_source_arn = aws_sqs_queue.change.arn\n"
    "  function_name    = aws_lambda_function.worker.arn\n}\n"
    'resource "aws_sns_topic_subscription" "s" {\n  topic_arn = aws_sns_topic.alerts.arn\n'
    '  protocol  = "sqs"\n  endpoint  = aws_sqs_queue.change.arn\n}\n'
    'resource "aws_sns_topic_subscription" "l" {\n  topic_arn = aws_sns_topic.alerts.arn\n'
    '  protocol  = "lambda"\n  endpoint  = aws_lambda_function.worker.arn\n}\n'
    'resource "aws_ssm_parameter" "p" {\n'
    '  name  = "/config/customerOrchestration_${local.env}/aws.sqs.customerChangeEventQueue"\n'
    '  value = "${var.env}-customer-change.fifo"\n}\n'
)


def test_interpolated_queue_names_keep_literal_parts(tmp_path):
    (tmp_path / "main.tf").write_text(MESSAGING_TF)
    found = terraform.detect_repo("infra", tmp_path, Config())
    named = [(d.id, d.name, d.aliases) for d in found.declared if d.kind in ("queue", "topic")]
    assert named == [
        ("queue:customer-change.fifo", "customer-change.fifo", ("customer-change.fifo",)),
        ("topic:alerts", "alerts", ("prod-alerts", "alerts")),
    ]


def test_messaging_wiring_refs(tmp_path):
    (tmp_path / "main.tf").write_text(MESSAGING_TF)
    found = terraform.detect_repo("infra", tmp_path, Config())
    events = [r for r in found.refs if r.edge_type == "event"]
    assert [
        (r.line, r.kind, r.value, r.role, r.engine, r.key, r.source, r.owner, r.env)
        for r in events
    ] == [
        (15, "name", "arn:aws:sqs:::*-customer-change.fifo", None, None, "OUT_QUEUE_URL",
         "function:infra/worker", None, "prod"),
        (21, "name", "arn:aws:sqs:::*-customer-change.fifo", "consume", "queue", None,
         "function:infra/worker", None, "prod"),
        (25, "name", "arn:aws:sns:::prod-alerts", "consume", "topic", None, None,
         "arn:aws:sqs:::*-customer-change.fifo", "prod"),
        (30, "name", "arn:aws:sns:::prod-alerts", "consume", "topic", None,
         "function:infra/worker", None, "prod"),
        (36, "name", "*-customer-change.fifo", None, None, "aws.sqs.customerChangeEventQueue",
         None, "customer-orchestration", "prod"),
    ]


def test_unresolvable_host_keeps_literal_label(tmp_path):
    (tmp_path / "main.tf").write_text(
        'resource "aws_apigatewayv2_api" "g" {\n  name = "g"\n}\n'
        'resource "aws_apigatewayv2_integration" "i" {\n  api_id = aws_apigatewayv2_api.g.id\n'
        '  request_parameters = { "overwrite:header.Host" = "${local.env}-orders.${local.tld}" }\n'
        "}\n"
    )
    found = terraform.detect_repo("infra", tmp_path, Config())
    assert [(r.kind, r.value, r.source) for r in found.refs] == [
        ("name", "orders", "gateway:infra/g"),
    ]
