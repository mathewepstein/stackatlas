from collections.abc import Iterable
from pathlib import Path
from types import ModuleType
from typing import Protocol

from stackatlas.config import Config
from stackatlas.detectors import (
    ci,
    datastore,
    go_http,
    helm_k8s,
    java_http,
    js_http,
    messaging,
    openapi,
    py_http,
    terraform,
)
from stackatlas.detectors.base import CiFile, Declared, Detection, Reference, Spec, iter_files

DETECTORS: list[ModuleType] = [js_http, java_http, py_http, go_http, datastore, messaging]
REPO_DETECTORS: list[ModuleType] = [terraform, ci, helm_k8s, openapi]


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


def run_detectors(repos: Iterable[_Repo], config: Config) -> Detection:
    out = Detection()
    for repo in repos:
        out.refs.extend(detect(repo.name, repo.path, config))
        for detector in REPO_DETECTORS:
            found = detector.detect_repo(repo.name, repo.path, config)
            out.refs.extend(found.refs)
            out.declared.extend(found.declared)
            out.owners.extend(found.owners)
            out.ci.extend(found.ci)
            out.specs.extend(found.specs)
    return out


__all__ = [
    "DETECTORS", "REPO_DETECTORS", "CiFile", "Declared", "Detection", "Reference", "Spec", "ci",
    "datastore", "detect", "go_http", "helm_k8s", "java_http", "js_http", "messaging", "openapi",
    "py_http", "run_detectors", "terraform",
]
