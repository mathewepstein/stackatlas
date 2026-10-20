import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import hcl2

from stackatlas.classify import SKIP_DIRS
from stackatlas.files import read_text

UNKNOWN = "*"
MAX_DEPTH = 8
MODULE_DIRS = {"modules", "module"}
INTERP = re.compile(r"\$\{([^{}]*)\}")
REF = re.compile(r"^(local|var)\.([A-Za-z0-9_-]+)((?:\.[A-Za-z0-9_-]+|\[\"[^\"]*\"\])*)$")
INDEX = re.compile(r"\.([A-Za-z0-9_-]+)|\[\"([^\"]*)\"\]")


@dataclass(frozen=True)
class Block:
    kind: str
    type: str
    name: str
    body: dict[str, Any]
    path: str
    line: int


@dataclass
class Stack:
    rel: str
    path: Path
    locals: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    blocks: list[Block] = field(default_factory=list)
    files: dict[str, list[str]] = field(default_factory=dict)

    def resources(self, *types: str) -> list[Block]:
        return self._blocks("resource", types)

    def data(self, *types: str) -> list[Block]:
        return self._blocks("data", types)

    def modules(self) -> list[Block]:
        return self._blocks("module", ())

    def _blocks(self, kind: str, types: tuple[str, ...]) -> list[Block]:
        return [b for b in self.blocks if b.kind == kind and (not types or b.type in types)]

    def resolve(self, value: Any, depth: int = 0) -> Any:
        if isinstance(value, dict):
            return {
                unq(k): self.resolve(v, depth) for k, v in value.items() if k != "__is_block__"
            }
        if isinstance(value, list):
            return [self.resolve(v, depth) for v in value]
        if isinstance(value, str):
            return INTERP.sub(lambda m: self._expr(m.group(1).strip(), depth), unq(value))
        return value

    def text(self, value: Any) -> str | None:
        resolved = self.resolve(value)
        return resolved if isinstance(resolved, str) else None

    def _expr(self, expr: str, depth: int) -> str:
        m = REF.match(expr)
        if depth >= MAX_DEPTH or not m:
            return UNKNOWN
        scope, name, rest = m.groups()
        value = self.locals.get(name) if scope == "local" else self.variables.get(name)
        for dot, idx in INDEX.findall(rest):
            key = dot or idx
            value = value.get(key, value.get(f'"{key}"')) if isinstance(value, dict) else None
        if value is None:
            return UNKNOWN
        resolved = self.resolve(value, depth + 1)
        return resolved if isinstance(resolved, str) else UNKNOWN

    def attr_line(self, block: Block, attr: str) -> tuple[int, str]:
        lines = self.files.get(block.path, [])
        pattern = re.compile(rf"^\s*\"?{re.escape(attr)}\"?\s*=")
        for i in range(block.line - 1, len(lines)):
            if pattern.match(lines[i]):
                return i + 1, lines[i]
        header = lines[block.line - 1] if 0 < block.line <= len(lines) else ""
        return block.line, header

    def find_line(self, needles: list[str]) -> tuple[str, int, str]:
        for path, lines in self.files.items():
            for i, line in enumerate(lines, 1):
                if all(n in line for n in needles):
                    return path, i, line
        path = next(iter(self.files), "")
        return path, 1, ""


def unq(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] == '"':
        return value[1:-1]
    return value


def find_stacks(root: Path) -> list[Stack]:
    stacks = []
    for directory in sorted(_dirs(root)):
        rel = directory.relative_to(root).as_posix() if directory != root else ""
        if any(part in MODULE_DIRS for part in rel.split("/")):
            continue
        if any(p.suffix == ".tf" for p in directory.iterdir()):
            stacks.append(load_stack(root, rel))
    return stacks


def _dirs(root: Path) -> list[Path]:
    found = [root]
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return found
    for entry in entries:
        if entry.is_dir() and entry.name not in SKIP_DIRS and not entry.name.startswith("."):
            found.extend(_dirs(entry))
    return found


def load_stack(root: Path, rel: str) -> Stack:
    path = root / rel if rel else root
    stack = Stack(rel=rel, path=path)
    for tf in sorted(path.glob("*.tf")):
        text = read_text(tf)
        file_rel = f"{rel}/{tf.name}" if rel else tf.name
        stack.files[file_rel] = text.splitlines()
        try:
            doc = hcl2.loads(text)
        except Exception:
            continue
        _collect(stack, doc, file_rel)
    return stack


def _collect(stack: Stack, doc: dict[str, Any], file_rel: str) -> None:
    for item in doc.get("locals", []):
        stack.locals.update({unq(k): v for k, v in item.items() if k != "__is_block__"})
    for item in doc.get("variable", []):
        for name, body in item.items():
            if name != "__is_block__" and isinstance(body, dict):
                stack.variables[unq(name)] = body.get("default")
    for kind in ("resource", "data"):
        for item in doc.get(kind, []):
            for type_, named in item.items():
                if type_ == "__is_block__" or not isinstance(named, dict):
                    continue
                for name, body in named.items():
                    if name == "__is_block__" or not isinstance(body, dict):
                        continue
                    pattern = rf'^\s*{kind}\s+"{re.escape(unq(type_))}"\s+"{re.escape(unq(name))}"'
                    line = _line_of(stack.files[file_rel], pattern)
                    stack.blocks.append(Block(kind, unq(type_), unq(name), body, file_rel, line))
    for item in doc.get("module", []):
        for name, body in item.items():
            if name == "__is_block__" or not isinstance(body, dict):
                continue
            line = _line_of(stack.files[file_rel], rf'^\s*module\s+"{re.escape(unq(name))}"')
            stack.blocks.append(Block("module", "", unq(name), body, file_rel, line))


def _line_of(lines: list[str], pattern: str) -> int:
    regex = re.compile(pattern)
    for i, line in enumerate(lines, 1):
        if regex.match(line):
            return i
    return 1
