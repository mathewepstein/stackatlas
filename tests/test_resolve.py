from pathlib import Path

from stackatlas.aliases import AliasIndex
from stackatlas.config import Config
from stackatlas.detectors import Reference
from stackatlas.resolve import resolve
from stackatlas.scan import ScannedRepo

REPOS = [
    ScannedRepo(name="web", path=Path("/x/web")),
    ScannedRepo(name="orders", path=Path("/x/orders")),
    ScannedRepo(name="billing-api", path=Path("/x/billing-api")),
]


def ref(repo, value, kind="url", path="a.ts", line=1, key=None, env=None):
    return Reference(repo, path, line, f"{path}:{line}", kind, value, key=key, env=env)


def index(aliases: dict[str, str], tier: int = 1) -> AliasIndex:
    idx = AliasIndex()
    for alias, node in aliases.items():
        idx.add(alias, node, tier)
    return idx


def run(refs, aliases, config=None, repos=REPOS):
    return resolve(refs, index(aliases), config or Config(), repos)


def test_exact_host_match():
    edges, externals, unresolved = run(
        [ref("web", "https://orders.acme.com/api")], {"orders.acme.com": "repo:orders"}
    )
    assert [(e.source, e.target, e.type, e.confidence, e.envs) for e in edges] == [
        ("repo:web", "repo:orders", "http", "exact", []),
    ]
    assert [(v.path, v.line) for v in edges[0].evidence] == [("a.ts", 1)]
    assert externals == [] and unresolved == []


def test_host_plus_first_path_segment_match():
    edges, _, _ = run(
        [ref("web", "https://api.acme.com/orders/123")],
        {"api.acme.com/orders": "repo:orders", "api.acme.com": "repo:gateway"},
    )
    assert [(e.target, e.confidence) for e in edges] == [("repo:orders", "exact")]


def test_env_prefixed_host_is_heuristic_and_tags_env():
    edges, _, _ = run(
        [ref("web", "https://dev-orders.acme.com"), ref("web", "https://orders.stage.acme.com")],
        {"orders.acme.com": "repo:orders"},
    )
    assert [(e.target, e.confidence, e.envs) for e in edges] == [
        ("repo:orders", "heuristic", ["dev", "stage"]),
    ]


def test_first_label_fallback_is_heuristic():
    edges, _, _ = run(
        [ref("web", "http://billing-api.internal:8080")], {"billing-api": "repo:billing-api"}
    )
    assert [(e.target, e.confidence) for e in edges] == [("repo:billing-api", "heuristic")]


def test_var_with_values_merges_evidence_and_envs():
    refs = [
        ref("web", "VITE_ORDERS_URL", kind="var", path="src/api.ts", line=3),
        ref("web", "https://orders.acme.com", path=".env.production", key="VITE_ORDERS_URL",
            env="prod"),
        ref("web", "https://dev-orders.acme.com", path=".env.development", key="VITE_ORDERS_URL",
            env="dev"),
    ]
    edges, _, _ = run(refs, {"orders.acme.com": "repo:orders"})
    [edge] = edges
    assert (edge.target, edge.confidence, edge.envs) == ("repo:orders", "exact", ["dev", "prod"])
    assert [(v.path, v.line) for v in edge.evidence] == [
        (".env.development", 1), (".env.production", 1), ("src/api.ts", 3),
    ]


def test_var_without_values_falls_back_to_name():
    edges, _, _ = run(
        [ref("web", "VITE_BILLING_API_URL", kind="var")], {"billing": "repo:billing-api"}
    )
    assert [(e.target, e.confidence) for e in edges] == [("repo:billing-api", "heuristic")]


def test_var_lookup_is_relaxed_across_key_styles():
    refs = [
        ref("orders", "inventory.base-url", kind="var", path="A.java"),
        ref("orders", "http://inventory-svc:8080", path=".env", key="INVENTORY_BASE_URL"),
    ]
    edges, _, _ = run(refs, {"inventory-svc": "repo:inventory"})
    assert [(e.target, len(e.evidence)) for e in edges] == [("repo:inventory", 2)]


def test_nested_placeholder_resolves_two_hops():
    refs = [
        ref("orders", "pricing.url", kind="var", path="A.java"),
        ref("orders", "PRICING_URL", kind="var", path="application.yml", key="pricing.url"),
        ref("orders", "https://pricing.acme.com", path=".env", key="PRICING_URL"),
    ]
    edges, _, _ = run(refs, {"pricing.acme.com": "repo:pricing"})
    assert [(e.target, [v.path for v in e.evidence]) for e in edges] == [
        ("repo:pricing", [".env", "A.java", "application.yml"]),
    ]


def test_ambiguous_name_is_unresolved():
    idx = AliasIndex()
    idx.add("orders", "repo:orders-service", 3)
    idx.add("orders", "repo:orders-orchestration", 3)
    edges, externals, unresolved = resolve(
        [ref("web", "ORDERS_URL", kind="var", path="a.js", line=2)], idx, Config(), REPOS
    )
    assert edges == [] and externals == []
    assert [(u.ref, u.kind, u.count, u.repos) for u in unresolved] == [
        ("orders", "name", 1, ["web"]),
    ]
    assert [(v.path, v.line) for v in unresolved[0].evidence] == [("a.js", 2)]


def test_unknown_host_becomes_external_node_and_unresolved():
    edges, externals, unresolved = run(
        [
            ref("web", "https://hooks.slack.com/x", line=1),
            ref("orders", "https://hooks.slack.com/y", line=7),
        ],
        {},
    )
    assert [(n.id, n.name, n.kind, n.layer) for n in externals] == [
        ("external:hooks.slack.com", "hooks.slack.com", "external", "external"),
    ]
    assert [(e.source, e.target, e.confidence) for e in edges] == [
        ("repo:orders", "external:hooks.slack.com", "exact"),
        ("repo:web", "external:hooks.slack.com", "exact"),
    ]
    assert [(u.ref, u.kind, u.count, u.repos) for u in unresolved] == [
        ("hooks.slack.com", "host", 2, ["orders", "web"]),
    ]


def test_ignored_hosts_and_self_references_produce_nothing():
    refs = [
        ref("web", "http://localhost:3000"),
        ref("web", "https://x.example.com"),
        ref("orders", "https://orders.acme.com"),
    ]
    edges, externals, unresolved = run(refs, {"orders.acme.com": "repo:orders"})
    assert edges == [] and externals == [] and unresolved == []


def test_ignored_value_still_falls_back_to_var_name():
    refs = [
        ref("web", "ORDERS_URL", kind="var", path="a.js"),
        ref("web", "http://localhost:8080", path=".env", key="ORDERS_URL"),
    ]
    edges, _, _ = run(refs, {"orders": "repo:orders"})
    assert [(e.target, e.confidence) for e in edges] == [("repo:orders", "heuristic")]


def test_evidence_permalinks_use_repo_url_and_sha():
    repos = [ScannedRepo(name="web", path=Path("/x/web"), sha="abc123", url="https://github.com/acme/web")]
    edges, _, _ = run(
        [ref("web", "https://orders.acme.com", path="src/api.ts", line=9)],
        {"orders.acme.com": "repo:orders"},
        repos=repos,
    )
    assert edges[0].evidence[0].url == "https://github.com/acme/web/blob/abc123/src/api.ts#L9"


def test_template_hosts_are_dropped():
    refs = [
        ref("web", "https://{}/api"),
        ref("web", "https://{{ .Values.host }}"),
        ref("web", "https://${HOST}/x"),
    ]
    assert run(refs, {}) == ([], [], [])


def test_var_fallback_strips_suffixes_progressively_and_splits_camel_case():
    aliases = {
        "customer-ms": "repo:customer-microservice",
        "auth-microservice": "repo:auth-microservice",
        "publisher-microservice": "repo:publisher-microservice",
    }
    refs = [
        ref("web", "CUSTOMER_MS_HTTP_ENDPOINT", kind="var", line=1),
        ref("web", "authMicroserviceUrl", kind="var", line=2),
        ref("web", "url.publisherMicroservice", kind="var", line=3),
    ]
    edges, _, unresolved = run(refs, aliases)
    assert sorted(e.target for e in edges) == [
        "repo:auth-microservice", "repo:customer-microservice", "repo:publisher-microservice",
    ]
    assert unresolved == []


def test_squashed_name_match_is_heuristic():
    edges, _, _ = run(
        [ref("web", "customermicroservice", kind="name")],
        {"customer-microservice": "repo:customer-microservice"},
    )
    assert [(e.target, e.confidence) for e in edges] == [
        ("repo:customer-microservice", "heuristic"),
    ]


def test_generic_var_names_are_not_reported_as_unresolved():
    refs = [ref("web", "BASE_URL", kind="var"), ref("web", "VITE_API_URL", kind="var")]
    assert run(refs, {}) == ([], [], [])
    edges, _, _ = run(refs, {"api": "repo:gateway"})
    assert [(e.target, e.confidence) for e in edges] == [("repo:gateway", "heuristic")]


def test_unresolved_sorted_by_count_then_ref():
    refs = [
        ref("web", "https://b.thirdparty.io", line=1),
        ref("web", "https://a.thirdparty.io", line=2),
        ref("web", "https://a.thirdparty.io", line=3),
        ref("web", "https://c.thirdparty.io", line=4),
    ]
    _, _, unresolved = run(refs, {})
    assert [(u.ref, u.count) for u in unresolved] == [
        ("a.thirdparty.io", 2), ("b.thirdparty.io", 1), ("c.thirdparty.io", 1),
    ]
