import json
from datetime import UTC, datetime

from stackatlas.schema import (
    Evidence,
    Graph,
    Node,
    Unresolved,
    dump_graph,
    dump_unresolved,
    graph_json_schema,
)


def test_graph_serializes_camel_case_with_schema_version():
    graph = Graph(
        org="acme",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
        nodes=[Node(id="repo:web", name="web", kind="frontend", layer="frontend")],
    )
    data = json.loads(dump_graph(graph))
    assert data["schemaVersion"] == 1
    assert data["generatedAt"].startswith("2026-01-01")
    assert data["nodes"][0]["layer"] == "frontend"
    assert data["edges"] == []


def test_unresolved_dumps_as_camel_case_list():
    items = [
        Unresolved(
            ref="x.io", kind="host", count=1, repos=["web"],
            evidence=[Evidence(path="a.ts", line=1, snippet="s")],
        )
    ]
    data = json.loads(dump_unresolved(items))
    assert data[0]["ref"] == "x.io"
    assert data[0]["evidence"][0] == {"path": "a.ts", "line": 1, "snippet": "s", "url": None}


def test_json_schema_describes_nodes_and_edges():
    schema = graph_json_schema()
    assert {"nodes", "edges", "schemaVersion"} <= set(schema["properties"])
