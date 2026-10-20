from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic.alias_generators import to_camel
from pydantic.json_schema import models_json_schema

Kind = Literal[
    "frontend", "service", "infra", "library", "group", "unknown", "external",
    "gateway", "function", "datastore", "queue", "topic", "bucket", "workload",
]
EdgeType = Literal["http", "event", "deploy", "datastore", "depends"]
Confidence = Literal["exact", "heuristic", "observed"]


class _Model(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        json_schema_serialization_defaults_required=True,
    )


class Evidence(_Model):
    path: str
    line: int
    snippet: str
    url: str | None = None


class Trace(_Model):
    source: str
    env: str
    start: datetime
    end: datetime


class CiEntry(_Model):
    system: str
    path: str
    repo: str | None = None
    registries: list[str] = Field(default_factory=list)


class Node(_Model):
    id: str
    name: str
    kind: Kind
    layer: str
    repo: str | None = None
    url: str | None = None
    sha: str | None = None
    parent: str | None = None
    envs: list[str] = Field(default_factory=list)
    endpoints: list[str] = Field(default_factory=list)
    ci: list[CiEntry] = Field(default_factory=list)


class Edge(_Model):
    source: str
    target: str
    type: EdgeType
    confidence: Confidence
    envs: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    observed: bool | None = None
    traces: list[Trace] = Field(default_factory=list)


class Graph(_Model):
    schema_version: Literal[1] = 1
    org: str
    generated_at: datetime
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


class Unresolved(_Model):
    ref: str
    kind: Literal["host", "name", "service"]
    count: int
    repos: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


def dump_graph(graph: Graph) -> str:
    return graph.model_dump_json(by_alias=True, indent=2)


def dump_unresolved(items: list[Unresolved]) -> str:
    return TypeAdapter(list[Unresolved]).dump_json(items, by_alias=True, indent=2).decode()


def graph_json_schema() -> dict[str, Any]:
    return Graph.model_json_schema(by_alias=True)


def viewer_json_schema() -> dict[str, Any]:
    _, schema = models_json_schema(
        [(Graph, "serialization"), (Unresolved, "serialization")],
        by_alias=True,
        ref_template="#/$defs/{model}",
    )
    return {
        "title": "Outputs",
        "type": "object",
        "properties": {
            "graph": {"$ref": "#/$defs/Graph"},
            "unresolved": {"type": "array", "items": {"$ref": "#/$defs/Unresolved"}},
        },
        "required": ["graph", "unresolved"],
        "additionalProperties": False,
        "$defs": schema["$defs"],
    }
