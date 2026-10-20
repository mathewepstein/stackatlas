import re
import xml.etree.ElementTree as ET
from fnmatch import fnmatch
from pathlib import Path

from stackatlas.classify import SKIP_DIRS
from stackatlas.files import load_json_or_yaml, read_text

GRADLE_INCLUDE = re.compile(r"\binclude\s*\(?\s*((?:['\"][^'\"]+['\"]\s*,?\s*)+)")
QUOTED = re.compile(r"['\"]([^'\"]+)['\"]")
GO_USE = re.compile(r"^\s*use\s*(?:\(([^)]*)\)|(\S+))", re.M)
APP_MANIFESTS = (
    "package.json", "pom.xml", "build.gradle", "build.gradle.kts", "go.mod",
    "pyproject.toml", "serverless.yml", "serverless.yaml",
)
SWEEP_DEPTH = 2


def find_apps(root: Path, configured: list[str] | None = None) -> list[str]:
    if configured is not None:
        found = set(configured)
    else:
        found = _gradle(root) | _maven(root) | _workspaces(root) | _go_work(root)
        if not found and not _has_manifest(root):
            found = _sweep(root, root, SWEEP_DEPTH)
    return sorted(p for p in found if p and (root / p).is_dir())


def _gradle(root: Path) -> set[str]:
    found = set()
    for settings in ("settings.gradle", "settings.gradle.kts"):
        for m in GRADLE_INCLUDE.finditer(read_text(root / settings)):
            for name in QUOTED.findall(m.group(1)):
                found.add(name.strip(":").replace(":", "/"))
    return found


def _maven(root: Path) -> set[str]:
    text = read_text(root / "pom.xml")
    if not text:
        return set()
    try:
        tree = ET.fromstring(text)
    except ET.ParseError:
        return set()
    return {
        el.text.strip()
        for el in tree.iter()
        if el.tag.rsplit("}", 1)[-1] == "module" and el.text and el.text.strip()
    }


def _workspaces(root: Path) -> set[str]:
    globs: list[str] = []
    pnpm = load_json_or_yaml(root / "pnpm-workspace.yaml").get("packages")
    if isinstance(pnpm, list):
        globs.extend(g for g in pnpm if isinstance(g, str))
    spec = load_json_or_yaml(root / "package.json").get("workspaces")
    if isinstance(spec, dict):
        spec = spec.get("packages")
    if isinstance(spec, list):
        globs.extend(g for g in spec if isinstance(g, str))
    negative = [g[1:] for g in globs if g.startswith("!")]
    found = set()
    for pattern in (g for g in globs if not g.startswith("!")):
        if Path(pattern).as_posix() == ".":
            continue
        for path in root.glob(pattern):
            rel = path.relative_to(root).as_posix()
            if (path / "package.json").is_file() and not any(fnmatch(rel, n) for n in negative):
                found.add(rel)
    return found


def _go_work(root: Path) -> set[str]:
    found = set()
    for m in GO_USE.finditer(read_text(root / "go.work")):
        entries = m.group(1).splitlines() if m.group(1) else [m.group(2)]
        for entry in entries:
            entry = entry.split("//", 1)[0].strip()
            if entry:
                found.add(entry.removeprefix("./"))
    return found


def _has_manifest(root: Path) -> bool:
    return any((root / m).is_file() for m in APP_MANIFESTS)


def _sweep(root: Path, current: Path, depth: int) -> set[str]:
    found = set()
    try:
        entries = sorted(p for p in current.iterdir() if p.is_dir())
    except OSError:
        return found
    for entry in entries:
        if entry.name in SKIP_DIRS or entry.name.startswith("."):
            continue
        if _has_manifest(entry):
            found.add(entry.relative_to(root).as_posix())
        elif depth > 1:
            found |= _sweep(root, entry, depth - 1)
    return found
