from stackatlas.config import Config
from stackatlas.detectors import terraform

EDGE = "stacks/edge-prod/main.tf"


def test_fixture_declares_infra_nodes(acme):
    found = terraform.detect_repo("platform-infra", acme / "platform-infra", Config())
    by = {d.id: d for d in found.declared}
    assert sorted(by) == [
        "bucket:acme-assets",
        "datastore:postgres/orders-db",
        "datastore:redis/orders-cache",
        "function:edge/notify",
        "gateway:edge/public",
        "gateway:partner/partner",
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


def test_fixture_refs_and_owners(acme):
    found = terraform.detect_repo("platform-infra", acme / "platform-infra", Config())
    refs = sorted(found.refs, key=lambda r: (r.path, r.line))
    assert [
        (r.path, r.line, r.source, r.owner, r.kind, r.value, r.key, r.env, r.fallback)
        for r in refs
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
    assert not any("secret" in r.snippet for r in found.refs)
    assert found.owners == [
        ("platform-infra", "stacks/edge-prod/src/notify.py", "function:edge/notify"),
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
