import re
from pathlib import Path

from stackatlas.config import Config
from stackatlas.detectors.base import Reference, env_file_refs, is_env_file, line_refs
from stackatlas.files import read_lines

SOURCE = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".vue", ".svelte"}
SKIP = re.compile(r"\.(test|spec|stories|d)\.[cm]?[jt]sx?$|\.min\.js$")
VAR = re.compile(
    r"(?:import\.meta\.env|process\.env)"
    r"(?:\.([A-Z][A-Z0-9_]*)|\[[\"']([A-Z][A-Z0-9_]*)[\"']\])"
)


def detect_file(repo: str, rel: str, path: Path, config: Config) -> list[Reference]:
    if is_env_file(path.name):
        return env_file_refs(repo, rel, path, config)
    if path.suffix not in SOURCE or SKIP.search(path.name):
        return []
    refs: list[Reference] = []
    for lineno, line in enumerate(read_lines(path), 1):
        refs.extend(line_refs(repo, rel, lineno, line, VAR))
    return refs
