from collections.abc import Iterable
from pathlib import Path
from types import ModuleType
from typing import Protocol

from stackatlas.config import Config
from stackatlas.detectors import go_http, java_http, js_http, py_http
from stackatlas.detectors.base import Reference, iter_files

DETECTORS: list[ModuleType] = [js_http, java_http, py_http, go_http]


class _Repo(Protocol):
    name: str
    path: Path


def detect(
    repo: str, root: Path, config: Config, detectors: list[ModuleType] | None = None
) -> list[Reference]:
    refs: list[Reference] = []
    for rel, path in iter_files(root):
        for detector in detectors or DETECTORS:
            refs.extend(detector.detect_file(repo, rel, path, config))
    return refs


def run_detectors(repos: Iterable[_Repo], config: Config) -> list[Reference]:
    refs: list[Reference] = []
    for repo in repos:
        refs.extend(detect(repo.name, repo.path, config))
    return refs


__all__ = [
    "DETECTORS", "Reference", "detect", "go_http", "java_http", "js_http", "py_http",
    "run_detectors",
]
