import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from stackatlas.files import load_json_or_yaml

UNKNOWN = "*"
ACTION = re.compile(r"\{\{-?\s*(.*?)\s*-?\}\}")
CONTROL = re.compile(r"^\s*\{\{-?\s*(if|else|end|range|with|define|template|include)\b.*\}\}-?\s*$")
ASSIGN = re.compile(r"^\s*\{\{-?\s*\$([A-Za-z_]\w*)\s*:=\s*(.*?)\s*-?\}\}\s*$")
RANGE = re.compile(r"^\s*\{\{-?\s*range\s+(.*?)\s*-?\}\}")
VALUES_FILE = re.compile(r"^(?:values[-.]([A-Za-z0-9]+)|([A-Za-z0-9]+)[-.]values)\.ya?ml$")


class _Renderer:
    def __init__(self, values: dict[str, Any], chart: str) -> None:
        self.values = values
        self.chart = chart
        self.vars: dict[str, Any] = {}
        self.scope: list[Any] = []

    def render(self, text: str) -> str:
        out = []
        for line in text.splitlines():
            m = ASSIGN.match(line)
            if m:
                self.vars[m.group(1)] = self.eval(m.group(2))
                out.append("")
                continue
            m = RANGE.match(line)
            if m:
                items = self.eval(m.group(1), raw=True)
                self.scope.append(items[0] if isinstance(items, list) and items else UNKNOWN)
                out.append("")
                continue
            if CONTROL.match(line):
                if re.match(r"^\s*\{\{-?\s*end\b", line) and self.scope:
                    self.scope.pop()
                out.append("")
                continue
            out.append(ACTION.sub(lambda m: self.text(self.eval(m.group(1))), line))
        return "\n".join(out) + ("\n" if text.endswith("\n") else "")

    def text(self, value: Any) -> str:
        if value is None or value == UNKNOWN:
            return f'"{UNKNOWN}"'
        return value if isinstance(value, str) else str(value)

    def eval(self, expr: str, raw: bool = False) -> Any:
        parts = [p.strip() for p in expr.split("|")]
        value = self.primary(parts[0])
        for step in parts[1:]:
            name, _, arg = step.partition(" ")
            if name == "default" and (value is None or value == UNKNOWN or value == ""):
                value = self.primary(arg.strip())
            elif name == "quote" and isinstance(value, str):
                value = f'"{value}"'
        if raw:
            return value
        return value if isinstance(value, (str, int, float, bool)) else None

    def primary(self, expr: str) -> Any:
        if expr.startswith('"') and expr.endswith('"'):
            return expr[1:-1]
        if re.fullmatch(r"-?\d+(\.\d+)?", expr):
            return expr
        m = re.match(r'^(?:include|template)\s+"([^"]+)"', expr)
        if m:
            return self.named(m.group(1))
        if expr.startswith("$") and not expr.startswith("$."):
            name = expr[1:].split(".", 1)
            base = self.vars.get(name[0])
            return self.lookup(base, name[1]) if len(name) > 1 else base
        expr = expr.removeprefix("$")
        if expr.startswith(".Values"):
            return self.lookup(self.values, expr.removeprefix(".Values").lstrip("."))
        if expr == ".Chart.Name":
            return self.chart
        if expr.startswith((".Chart", ".Release", ".Capabilities")):
            return UNKNOWN
        if expr.startswith(".") and self.scope:
            return self.lookup(self.scope[-1], expr.lstrip("."))
        return UNKNOWN

    def named(self, template: str) -> Any:
        if template.endswith(".fullname"):
            override = self.values.get("fullnameOverride") or self.values.get("nameOverride")
            return override or self.chart
        if template.endswith(".name"):
            return self.values.get("nameOverride") or self.chart
        return UNKNOWN

    def lookup(self, base: Any, path: str) -> Any:
        value = base
        for part in [p for p in path.split(".") if p]:
            if not isinstance(value, dict):
                return UNKNOWN
            value = value.get(part)
        return UNKNOWN if value is None else value


def render(text: str, values: dict[str, Any], chart: str) -> str:
    return _Renderer(values, chart).render(text)


def chart_values(
    chart_dir: Path, env_for: Callable[[str], str | None]
) -> dict[str | None, dict[str, Any]]:
    base = load_json_or_yaml(chart_dir / "values.yaml")
    variants: dict[str | None, dict[str, Any]] = {None: base}
    for path in sorted(chart_dir.iterdir()):
        m = VALUES_FILE.match(path.name)
        env = env_for(m.group(1) or m.group(2)) if m else None
        if env:
            variants[env] = deep_merge(base, load_json_or_yaml(path))
    return variants


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
