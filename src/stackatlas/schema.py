from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Kind = Literal["frontend", "service", "infra", "library", "unknown"]
EdgeType = Literal["http", "event", "deploy", "datastore", "depends"]
Confidence = Literal["exact", "heuristic"]


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Evidence(_Model):
    path: str
    line: int
    snippet: str
    url: str | None = None


class Node(_Model):
    id: str
    name: str
    kind: Kind
    layer: str
    repo: str | None = None
    url: str | None = None
    sha: str | None = None
    envs: list[str] = Field(default_factory=list)
    endpoints: list[str] = Field(default_factory=list)


class Edge(_Model):
    source: str
    target: str
    type: EdgeType
    confidence: Confidence
    envs: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)


class Graph(_Model):
    schema_version: Literal[1] = 1
    org: str
    generated_at: datetime
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


def dump_graph(graph: Graph) -> str:
    return graph.model_dump_json(by_alias=True, indent=2)


def graph_json_schema() -> dict[str, Any]:
    return Graph.model_json_schema(by_alias=True)
