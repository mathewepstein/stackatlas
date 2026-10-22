import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

MAX_FILE_BYTES = 512_000
KEY_LINE = re.compile(r"^([\w.\-/\[\]]+)\s*:\s*(.*)$")
KV = re.compile(r"^\s*([A-Za-z_][\w.\-]*)\s*[=:]\s*(.*?)\s*$")
PLACEHOLDER = re.compile(r"^\$\{([\w.\-]+)(?::(.*))?\}$")
BLOCK_SCALARS = ("", "|", ">", "|-", ">-")


def read_text(path: Path) -> str:
    try:
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return ""
        return path.read_text(errors="ignore")
    except OSError:
        return ""


def read_lines(path: Path) -> list[str]:
    return read_text(path).splitlines()


def write_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def unquote(value: str) -> str:
    value = re.split(r"\s+#", value, maxsplit=1)[0].strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def flat_yaml(lines: list[str]) -> list[tuple[int, str, str, int]]:
    out: list[tuple[int, str, str, int]] = []
    stack: list[tuple[int, str]] = []
    doc = 0
    for lineno, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if stripped == "---":
            doc += 1
            stack = []
            continue
        if not stripped or stripped.startswith(("#", "- ")):
            continue
        m = KEY_LINE.match(stripped)
        if not m:
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        key, value = m.group(1), m.group(2).strip()
        full = ".".join([k for _, k in stack] + [key])
        if value in BLOCK_SCALARS:
            stack.append((indent, key))
        else:
            out.append((doc, full, unquote(value), lineno))
    return out


def flat_properties(lines: list[str]) -> list[tuple[str, str, int]]:
    out: list[tuple[str, str, int]] = []
    for lineno, raw in enumerate(lines, 1):
        if raw.lstrip().startswith(("#", "!")):
            continue
        m = KV.match(raw)
        if m:
            out.append((m.group(1), unquote(m.group(2)), lineno))
    return out


def load_yaml_docs(path: Path) -> list[dict[str, Any]]:
    text = read_text(path)
    if not text or "{{" in text:
        return []
    try:
        return [d for d in yaml.safe_load_all(text) if isinstance(d, dict)]
    except yaml.YAMLError:
        return []


def load_json_or_yaml(path: Path) -> dict[str, Any]:
    text = read_text(path)
    if not text:
        return {}
    try:
        data = json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def load_toml(path: Path) -> dict[str, Any]:
    text = read_text(path)
    if not text:
        return {}
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return {}
