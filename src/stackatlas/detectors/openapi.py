import posixpath
import re
from dataclasses import replace
from pathlib import Path
from typing import Any

from stackatlas.config import Config
from stackatlas.detectors.base import (
    Detection,
    Reference,
    Spec,
    clean_url,
    is_comment,
    iter_files,
    scrub,
)
from stackatlas.files import load_json_or_yaml, read_lines, read_text
from stackatlas.names import slug

SPEC_SUFFIXES = {".yaml", ".yml", ".json"}
SPEC_HINT = re.compile(r"\b(openapi|swagger)[\"']?\s*:")
SPEC_KEY = re.compile(r"^\s*[\"']?(openapi|swagger)[\"']?\s*:")
VERSION = re.compile(r"^\d")
METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
BUILD_FILES = {"build.gradle", "build.gradle.kts", "pom.xml", "openapitools.json"}
INPUT_SPEC = re.compile(r"inputSpec[\"']?\s*(?:=|\.set\(|>|:)\s*[\"']?([^\"'<>\s)]+)")
ROOT_PREFIXES = ("$rootDir/", "${rootDir}/", "${project.rootDir}/", "${rootProject.projectDir}/")
LOCAL_PREFIXES = (
    "$projectDir/", "${projectDir}/", "${project.basedir}/", "${project.projectDir}/",
    "${basedir}/", "./",
)


def detect_repo(repo: str, root: Path, config: Config) -> Detection:
    out = Detection()
    builds: list[tuple[str, Path]] = []
    for rel, path in iter_files(root):
        if path.name in BUILD_FILES:
            builds.append((rel, path))
        elif path.suffix in SPEC_SUFFIXES:
            spec = _spec(repo, rel, path)
            if spec:
                out.specs.append(spec)
    by_path = {s.path: s for s in out.specs}
    consumed: set[str] = set()
    for rel, path in builds:
        out.refs.extend(_generator_refs(repo, rel, path, by_path, consumed))
    out.specs = [replace(s, consumed=s.path in consumed) for s in out.specs]
    return out


def _spec(repo: str, rel: str, path: Path) -> Spec | None:
    text = read_text(path)
    if not text or not SPEC_HINT.search(text):
        return None
    data = load_json_or_yaml(path)
    version = data.get("openapi") or data.get("swagger")
    paths = data.get("paths")
    if not isinstance(version, str) or not VERSION.match(version) or not isinstance(paths, dict):
        return None
    lines = text.splitlines()
    line = next((i for i, raw in enumerate(lines, 1) if SPEC_KEY.match(raw)), 1)
    title = _dict(data.get("info")).get("title")
    return Spec(
        repo=repo,
        path=rel,
        line=line,
        snippet=scrub(lines[line - 1]) if lines else "",
        title=title if isinstance(title, str) and title.strip() else None,
        servers=_servers(data),
        endpoints=sorted(
            f"{method.upper()} {route}"
            for route, item in paths.items()
            if isinstance(item, dict)
            for method in item
            if isinstance(method, str) and method.lower() in METHODS
        ),
    )


def _servers(data: dict[str, Any]) -> list[str]:
    servers = []
    for server in _list(data.get("servers")):
        url = _dict(server).get("url")
        if not isinstance(url, str) or "://" not in url:
            continue
        host = url.split("://", 1)[1].split("/", 1)[0]
        if "{" in host:
            continue
        servers.append(clean_url(url.split("{", 1)[0]).rstrip("/"))
    host = data.get("host")
    if isinstance(host, str) and "{" not in host:
        base_path = data.get("basePath")
        servers.append((host + (base_path if isinstance(base_path, str) else "")).rstrip("/"))
    return list(dict.fromkeys(servers))


def _generator_refs(
    repo: str, rel: str, path: Path, specs: dict[str, Spec], consumed: set[str]
) -> list[Reference]:
    base = posixpath.dirname(rel)
    refs = []
    for lineno, line in enumerate(read_lines(path), 1):
        if is_comment(line):
            continue
        for m in INPUT_SPEC.finditer(line):
            spec = specs.get(_spec_path(m.group(1), base) or "")
            if spec:
                consumed.add(spec.path)
                refs.extend(_spec_refs(repo, rel, lineno, scrub(line), spec))
    return refs


def _spec_path(raw: str, base: str) -> str | None:
    for prefix in ROOT_PREFIXES:
        if raw.startswith(prefix):
            return posixpath.normpath(raw[len(prefix):])
    for prefix in LOCAL_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
            break
    if "$" in raw or raw.startswith("/"):
        return None
    return posixpath.normpath(posixpath.join(base, raw)) if base else posixpath.normpath(raw)


def _spec_refs(repo: str, rel: str, lineno: int, snippet: str, spec: Spec) -> list[Reference]:
    name = slug(spec.title) if spec.title else None
    if spec.servers:
        return [
            Reference(repo, rel, lineno, snippet, "url", server, fallback=name)
            for server in spec.servers
        ]
    if name:
        return [Reference(repo, rel, lineno, snippet, "name", name)]
    return []


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []
