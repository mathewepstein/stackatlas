import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from stackatlas.config import Config
from stackatlas.runtime import (
    Datadog,
    MissingCredentials,
    RuntimeData,
    datadog_source,
    validate_datadog,
)
from stackatlas.scan import build_graph, discover_local

FIXTURE = Path(__file__).parent / "fixtures" / "datadog" / "prod.json"
NOW = datetime(2026, 10, 20, tzinfo=UTC)
CONFIG = Config(layers={"orchestration": ["*-orchestration"]})


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.datadoghq.com")


def _prod():
    return Datadog(
        {"prod": "prod"}, 7, "k", "a", "datadoghq.com",
        client=_client(lambda r: httpx.Response(200, json=json.loads(FIXTURE.read_text()))),
        now=NOW,
    ).fetch()


def test_datadog_fetch_sends_keys_env_and_window():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"a": {"calls": ["b"]}, "c": {}})

    source = Datadog({"prod": "production"}, 7, "k", "a", "datadoghq.com", _client(handler), NOW)
    data = source.fetch()
    request = seen[0]
    assert request.url.path == "/api/v1/service_dependencies"
    assert dict(request.url.params) == {
        "env": "production",
        "start": str(int((NOW - timedelta(days=7)).timestamp())),
        "end": str(int(NOW.timestamp())),
    }
    assert (request.headers["DD-API-KEY"], request.headers["DD-APPLICATION-KEY"]) == ("k", "a")
    assert data == [
        RuntimeData(
            "datadog", "prod", NOW - timedelta(days=7), NOW,
            frozenset({"a", "b", "c"}), frozenset({("a", "b")}),
        )
    ]


def test_datadog_fetch_raises_on_http_error():
    source = Datadog({"prod": "prod"}, 7, "k", "a", "datadoghq.com",
                     _client(lambda r: httpx.Response(403, json={})), NOW)
    with pytest.raises(httpx.HTTPStatusError):
        source.fetch()


def test_datadog_source_reads_either_key_names_and_defaults_envs():
    source = datadog_source(
        Config(), {"DATADOG_API_KEY": "k", "DD_APP_KEY": "a", "DD_SITE": "us5.datadoghq.com"}
    )
    assert source.envs == {"dev": "dev", "stage": "stage", "prod": "prod"}
    assert source.window_days == 7
    assert str(source.client.base_url) == "https://api.us5.datadoghq.com"


def test_datadog_source_uses_configured_envs():
    config = Config.model_validate(
        {"runtime": {"datadog": {"envs": {"prod": "production"}, "window_days": 3}}}
    )
    source = datadog_source(config, {"DD_API_KEY": "k", "DD_APP_KEY": "a"})
    assert (source.envs, source.window_days) == ({"prod": "production"}, 3)
    assert str(source.client.base_url) == "https://api.datadoghq.com"


def test_datadog_source_without_keys_fails():
    with pytest.raises(MissingCredentials):
        datadog_source(Config(), {"DD_API_KEY": "k"})


def test_validate_datadog():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"valid": request.headers["DD-API-KEY"] == "good"})

    env = {"DD_API_KEY": "good", "DD_APP_KEY": "a"}
    assert validate_datadog(env, _client(handler)) is True
    assert seen[0].url.path == "/api/v1/validate"
    assert validate_datadog({"DD_API_KEY": "bad", "DD_APP_KEY": "a"}, _client(handler)) is False
    forbidden = _client(lambda r: httpx.Response(403, json={"errors": ["Forbidden"]}))
    assert validate_datadog(env, forbidden) is False


def _overlay(acme):
    return build_graph("acme", discover_local(acme), CONFIG, _prod())


def test_static_edges_are_classified(acme):
    edges = {(e.source, e.target): e for e in _overlay(acme).graph.edges}
    expected = {
        ("repo:orders-orchestration", "repo:orders-service"): True,
        ("repo:orders-orchestration", "repo:pricing-svc"): None,
        ("repo:orders-service", "repo:inventory-svc"): True,
        ("repo:orders-service", "repo:pricing-svc"): False,
        ("repo:billing-api", "repo:pricing-svc"): True,
        ("repo:billing-api", "repo:inventory-svc"): False,
        ("repo:billing-api", "datastore:redis/orders-cache"): True,
        ("repo:orders-service", "datastore:postgres/orders-db"): None,
        ("repo:gateway-node", "repo:billing-api"): None,
        ("repo:notifications-worker", "repo:billing-api"): None,
        ("repo:platform-infra", "gateway:edge/public"): None,
    }
    assert {k: edges[k].observed for k in expected} == expected


def test_observed_edges_carry_traces(acme):
    edges = {(e.source, e.target): e for e in _overlay(acme).graph.edges}
    edge = edges[("repo:orders-orchestration", "repo:orders-service")]
    assert [(t.source, t.env, t.start, t.end) for t in edge.traces] == [
        ("datadog", "prod", NOW - timedelta(days=7), NOW),
    ]
    assert edge.confidence == "exact"
    assert edges[("repo:orders-orchestration", "repo:pricing-svc")].traces == []


def test_runtime_only_pair_becomes_observed_edge(acme):
    graph = _overlay(acme).graph
    edge = next(
        e for e in graph.edges
        if (e.source, e.target) == ("repo:orders-orchestration", "repo:billing-api")
    )
    assert (edge.type, edge.confidence, edge.envs, edge.evidence, edge.observed) == (
        "http", "observed", ["prod"], [], True,
    )
    assert graph.edges == sorted(graph.edges, key=lambda e: (e.source, e.target, e.type))


def test_unresolved_runtime_names_are_reported_without_nodes(acme):
    result = _overlay(acme)
    assert not any("legacy-batch" in n.id for n in result.graph.nodes)
    assert not any("redis" == n.name or "java-aws-sdk" == n.name for n in result.graph.nodes)
    service = [(u.ref, u.kind, u.count) for u in result.unresolved if u.kind == "service"]
    assert service == [("legacy-batch", "service", 1)]


def test_without_runtime_every_edge_is_unclassified(acme):
    graph = build_graph("acme", discover_local(acme), CONFIG).graph
    assert all(e.observed is None and e.traces == [] for e in graph.edges)


def test_glued_service_suffix_resolves(acme):
    names = frozenset({"billingservice", "pricing-svc", "sapi"})
    pairs = frozenset({("billingservice", "pricing-svc"), ("sapi", "pricing-svc")})
    data = [RuntimeData("datadog", "prod", NOW, NOW, names, pairs)]
    result = build_graph("acme", discover_local(acme), CONFIG, data)
    edges = {(e.source, e.target): e for e in result.graph.edges}
    assert edges[("repo:billing-api", "repo:pricing-svc")].observed is True
    assert [u.ref for u in result.unresolved if u.kind == "service"] == ["sapi"]


def test_generic_chart_workload_is_not_a_runtime_match(tmp_path, generic_chart):
    generic_chart(tmp_path / "devops")
    (tmp_path / "auth-microservice").mkdir()
    data = [
        RuntimeData(
            "datadog", "prod", NOW, NOW, frozenset({"sc", "auth-microservice"}),
            frozenset({("sc", "auth-microservice")}),
        )
    ]
    result = build_graph("org", discover_local(tmp_path), Config(), data)
    assert "workload:helm-deploy/sc" in {n.id for n in result.graph.nodes}
    assert [e for e in result.graph.edges if e.confidence == "observed"] == []
    assert [u.ref for u in result.unresolved if u.kind == "service"] == ["sc"]


def test_runtime_env_outside_static_envs_does_not_mark_not_seen(acme):
    dev = RuntimeData(
        "datadog", "dev", NOW, NOW,
        frozenset({"orders-orchestration", "pricing-svc"}), frozenset(),
    )
    graph = build_graph("acme", discover_local(acme), CONFIG, [dev]).graph
    edges = {(e.source, e.target): e for e in graph.edges}
    assert edges[("repo:orders-orchestration", "repo:pricing-svc")].observed is False
    assert edges[("repo:orders-service", "repo:pricing-svc")].observed is None
