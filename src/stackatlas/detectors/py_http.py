import re
from pathlib import Path

from stackatlas.config import Config
from stackatlas.detectors.base import Reference, line_refs
from stackatlas.files import read_lines

SKIP = re.compile(r"^(?:test_.*|.*_test|conftest)\.py$")
VAR = re.compile(
    r"(?:os\.environ\.get|os\.environ|os\.getenv|environ\.get|environ|getenv|settings)"
    r"\s*[\(\[.]\s*[\"']?([A-Z][A-Z0-9_]*)[\"']?"
)


def detect_file(repo: str, rel: str, path: Path, config: Config) -> list[Reference]:
    if path.suffix != ".py" or SKIP.match(path.name):
        return []
    refs: list[Reference] = []
    for lineno, line in enumerate(read_lines(path), 1):
        refs.extend(line_refs(repo, rel, lineno, line, VAR))
    return refs
