import re
from pathlib import Path

from stackatlas.config import Config
from stackatlas.detectors import java_http
from stackatlas.detectors.base import (
    DATASTORE_KEY,
    DATASTORE_URL,
    Reference,
    datastore_parts,
    engine_for_key,
    env_entries,
    env_from_path,
    is_comment,
    is_env_file,
    is_secret,
    is_urlish,
    looks_like_host,
    scrub,
)
from stackatlas.files import PLACEHOLDER, read_lines

SOURCE = {
    ".java", ".kt", ".scala", ".groovy", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".py",
    ".go", ".rb", ".php", ".cs",
}
SKIP = re.compile(
    r"\.(test|spec|stories|d)\.[cm]?[jt]sx?$|\.min\.js$|_test\.(go|py)$|(^|/)test_[^/]*\.py$"
)


def detect_file(repo: str, rel: str, path: Path, config: Config) -> list[Reference]:
    name = path.name
    if is_env_file(name):
        env = env_from_path(rel, config.envs)
        items = [(k, v, n, env, line) for k, v, n, line in env_entries(path)]
        return _entries(repo, rel, items)
    if java_http.CONFIG_FILE.match(name) and name not in java_http.BUILD_FILES:
        lines = read_lines(path)
        entries = java_http.config_entries(rel, path, config)
        return _entries(repo, rel, [(k, v, n, env, lines[n - 1]) for k, v, n, env in entries])
    if path.suffix in SOURCE and not SKIP.search(rel):
        return _literals(repo, rel, path)
    return []


Entry = tuple[str, str, int, str | None, str]


def _entries(repo: str, rel: str, items: list[Entry]) -> list[Reference]:
    refs = []
    for key, value, lineno, env, line in items:
        ref = _entry_ref(repo, rel, lineno, line, key, value, env)
        if ref:
            refs.append(ref)
    return refs


def _entry_ref(
    repo: str, rel: str, lineno: int, line: str, key: str, value: str, env: str | None
) -> Reference | None:
    if is_secret(key):
        return None
    m = PLACEHOLDER.match(value)
    if m:
        var, default = m.group(1), m.group(2)
        if not default:
            if DATASTORE_KEY.search(key) and not is_secret(var):
                return Reference(
                    repo, rel, lineno, scrub(line), "var", var, key=key, env=env,
                    edge_type="datastore",
                )
            return None
        value = default
    parts = datastore_parts(value)
    if parts:
        engine, host = parts
    elif DATASTORE_KEY.search(key) and is_urlish(key) and looks_like_host(value):
        engine, host = engine_for_key(key), value
    else:
        return None
    return Reference(
        repo, rel, lineno, scrub(line), "url", host, key=key, env=env, edge_type="datastore",
        engine=engine,
    )


def _literals(repo: str, rel: str, path: Path) -> list[Reference]:
    refs = []
    for lineno, line in enumerate(read_lines(path), 1):
        if is_comment(line):
            continue
        for m in DATASTORE_URL.finditer(line):
            parts = datastore_parts(m.group(0))
            if parts:
                refs.append(
                    Reference(
                        repo, rel, lineno, scrub(line), "url", parts[1], edge_type="datastore",
                        engine=parts[0],
                    )
                )
    return refs
