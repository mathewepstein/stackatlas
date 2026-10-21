import re
from pathlib import Path

from stackatlas.config import Config
from stackatlas.detectors.base import (
    Reference,
    balanced,
    canonical_env,
    clean_url,
    env_from_path,
    is_comment,
    is_http_key,
    is_http_url,
    is_secret,
    line_refs,
    scrub,
    value_ref,
)
from stackatlas.files import PLACEHOLDER, flat_properties, flat_yaml, read_lines

SOURCE = {".java", ".kt"}
CONFIG_FILE = re.compile(r"^(?:(?:application|bootstrap)(?:-[\w]+)?\.ya?ml|.*\.properties)$")
BUILD_FILES = {"gradle.properties"}
VAR = re.compile(r"\$\{([\w.\-]+)(?::[^}]*)?\}|System\.getenv\(\s*\"([\w.\-]+)\"")
PLACEHOLDER_DEFAULT = re.compile(r"\$\{([\w.\-]+):(https?://[^}\s\"]+)\}")
FEIGN = re.compile(r"@FeignClient\s*\(")
FEIGN_NAME = re.compile(r"\b(?:name|value)\s*=\s*\"([^\"]*)\"")
FEIGN_BARE = re.compile(r"@FeignClient\s*\(\s*\"([^\"]*)\"")
FEIGN_URL = re.compile(r"\burl\s*=\s*\"([^\"]*)\"")
PROFILE_KEYS = ("spring.config.activate.on-profile", "spring.profiles")


def detect_file(repo: str, rel: str, path: Path, config: Config) -> list[Reference]:
    if path.suffix in SOURCE:
        return _source_refs(repo, rel, path)
    if CONFIG_FILE.match(path.name) and path.name not in BUILD_FILES:
        return _config_refs(repo, rel, path, config)
    return []


def _source_refs(repo: str, rel: str, path: Path) -> list[Reference]:
    lines = read_lines(path)
    refs: list[Reference] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if FEIGN.search(line) and not is_comment(line):
            block, span = balanced(lines, i)
            refs.extend(_feign_refs(repo, rel, i + 1, block))
            i += span
            continue
        refs.extend(_line_refs(repo, rel, i + 1, line))
        i += 1
    return refs


def _feign_refs(repo: str, rel: str, lineno: int, block: str) -> list[Reference]:
    snippet = scrub(block)
    named = FEIGN_NAME.search(block) or FEIGN_BARE.search(block)
    name = named.group(1) if named and named.group(1) else None
    url = FEIGN_URL.search(block)
    if url and url.group(1):
        value = url.group(1)
        if is_http_url(value):
            return [Reference(repo, rel, lineno, snippet, "url", clean_url(value), fallback=name)]
        m = PLACEHOLDER.match(value)
        if m:
            var, default = m.group(1), m.group(2)
            if default and is_http_url(default):
                return [
                    Reference(
                        repo, rel, lineno, snippet, "url", clean_url(default), key=var,
                        fallback=name,
                    )
                ]
            return [Reference(repo, rel, lineno, snippet, "var", var, fallback=name)]
    if name:
        return [Reference(repo, rel, lineno, snippet, "name", name)]
    return []


def _line_refs(repo: str, rel: str, lineno: int, line: str) -> list[Reference]:
    if is_comment(line):
        return []
    snippet = scrub(line)
    refs = [
        Reference(repo, rel, lineno, snippet, "url", clean_url(m.group(2)), key=m.group(1))
        for m in PLACEHOLDER_DEFAULT.finditer(line)
    ]
    rest = PLACEHOLDER_DEFAULT.sub("", line)
    refs.extend(line_refs(repo, rel, lineno, rest, VAR, snippet=snippet))
    return refs


def config_entries(rel: str, path: Path, config: Config) -> list[tuple[str, str, int, str | None]]:
    file_env = env_from_path(rel, config.envs)
    lines = read_lines(path)
    if path.suffix == ".properties":
        entries = [(0, key, value, lineno) for key, value, lineno in flat_properties(lines)]
        profiles: dict[int, str | None] = {}
    else:
        entries = flat_yaml(lines)
        profiles = {
            doc: canonical_env(value, config.envs)
            for doc, key, value, _ in entries
            if key in PROFILE_KEYS
        }
    return [
        (key, value, lineno, profiles.get(doc) or file_env) for doc, key, value, lineno in entries
    ]


def _config_refs(repo: str, rel: str, path: Path, config: Config) -> list[Reference]:
    lines = read_lines(path)
    refs: list[Reference] = []
    for key, value, lineno, env in config_entries(rel, path, config):
        ref = _config_value_ref(repo, rel, lineno, lines[lineno - 1], key, value, env)
        if ref:
            refs.append(ref)
    return refs


def _config_value_ref(
    repo: str, rel: str, lineno: int, line: str, key: str, value: str, env: str | None
) -> Reference | None:
    m = PLACEHOLDER.match(value)
    if not m:
        return value_ref(repo, rel, lineno, line, key, value, env)
    var, default = m.group(1), m.group(2)
    if default:
        return value_ref(repo, rel, lineno, line, key, default, env)
    if is_secret(key) or is_secret(var) or not is_http_key(key):
        return None
    return Reference(repo, rel, lineno, scrub(line), "var", var, key=key, env=env)
