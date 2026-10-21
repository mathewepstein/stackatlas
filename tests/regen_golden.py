"""Rewrite tests/golden from the acme fixture: python tests/regen_golden.py"""

import json
from pathlib import Path
from typing import Any

from stackatlas.config import Config
from stackatlas.scan import build_graph, discover_local
from stackatlas.schema import dump_graph, dump_unresolved

TESTS = Path(__file__).parent
GOLDEN = TESTS / "golden"
CONFIG = Config(layers={"orchestration": ["*-orchestration"]})


def compact(value: Any, indent: int, expand: bool = False) -> str:
    if isinstance(value, dict):
        fields = (
            f"{json.dumps(k)}: {compact(v, indent, k == 'evidence')}" for k, v in value.items()
        )
        return "{" + ", ".join(fields) + "}"
    if isinstance(value, list) and value and expand:
        pad = " " * (indent + 2)
        items = ",\n".join(pad + compact(v, indent + 2) for v in value)
        return f"[\n{items}\n{' ' * indent}]"
    return json.dumps(value)


def format_graph(data: dict[str, Any]) -> str:
    fields = [
        f"  {json.dumps(k)}: {compact(v, 2, True)}" for k, v in data.items() if k != "generatedAt"
    ]
    return "{\n" + ",\n".join(fields) + "\n}\n"


def format_unresolved(data: list[dict[str, Any]]) -> str:
    return compact(data, 0, True) + "\n"


def main() -> None:
    result = build_graph("acme", discover_local(TESTS / "fixtures" / "acme"), CONFIG)
    (GOLDEN / "acme.json").write_text(format_graph(json.loads(dump_graph(result.graph))))
    unresolved = json.loads(dump_unresolved(result.unresolved))
    (GOLDEN / "acme-unresolved.json").write_text(format_unresolved(unresolved))
    print(f"{len(result.graph.nodes)} nodes, {len(result.graph.edges)} edges, "
          f"{len(result.unresolved)} unresolved → {GOLDEN}")


if __name__ == "__main__":
    main()
