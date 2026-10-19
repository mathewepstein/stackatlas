import re
from pathlib import Path

from stackatlas.config import Config
from stackatlas.detectors.base import Reference, line_refs
from stackatlas.files import read_lines

VAR = re.compile(r"os\.(?:Getenv|LookupEnv)\(\s*\"([A-Za-z0-9_]+)\"")


def detect_file(repo: str, rel: str, path: Path, config: Config) -> list[Reference]:
    if path.suffix != ".go" or path.name.endswith("_test.go"):
        return []
    refs: list[Reference] = []
    for lineno, line in enumerate(read_lines(path), 1):
        refs.extend(line_refs(repo, rel, lineno, line, VAR))
    return refs
