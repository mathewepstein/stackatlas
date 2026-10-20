import re
from pathlib import Path

from stackatlas.config import Config
from stackatlas.detectors.base import CiFile, Detection, Reference, is_comment, iter_files, scrub
from stackatlas.files import read_lines

SYSTEMS = (
    (re.compile(r"^\.github/workflows/[^/]+\.ya?ml$"), "github-actions"),
    (re.compile(r"(^|/)buildspec[^/]*\.ya?ml$|(^|/)[^/]+\.buildspec\.ya?ml$"), "codebuild"),
    (re.compile(r"(^|/)Jenkinsfile$"), "jenkins"),
    (re.compile(r"^\.gitlab-ci\.ya?ml$"), "gitlab-ci"),
    (re.compile(r"^\.circleci/config\.ya?ml$"), "circleci"),
    (re.compile(r"^bitbucket-pipelines\.ya?ml$"), "bitbucket"),
    (re.compile(r"^azure-pipelines\.ya?ml$"), "azure-pipelines"),
    (re.compile(r"^cloudbuild\.ya?ml$"), "cloud-build"),
)
REGISTRY = re.compile(
    r"\b((?:[a-z0-9-]+\.)*(?:dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com"
    r"|codeartifact\.[a-z0-9-]+\.amazonaws\.com|npm\.pkg\.github\.com|ghcr\.io"
    r"|registry\.npmjs\.org|pkg\.dev|quay\.io|docker\.io|gcr\.io|azurecr\.io))\b",
    re.I,
)
S3_BUCKET = re.compile(r"s3://([A-Za-z0-9][A-Za-z0-9.-]{1,62})")
LAMBDA_NAME = re.compile(r"--function-name[ =]+([A-Za-z0-9_-]+)")


def system_for(rel: str) -> str | None:
    return next((system for pattern, system in SYSTEMS if pattern.search(rel)), None)


def detect_repo(repo: str, root: Path, config: Config) -> Detection:
    out = Detection()
    for rel, path in iter_files(root):
        system = system_for(rel)
        if not system:
            continue
        registries: set[str] = set()
        for lineno, line in enumerate(read_lines(path), 1):
            if is_comment(line):
                continue
            registries.update(m.group(1).lower() for m in REGISTRY.finditer(line))
            for pattern, kind in ((S3_BUCKET, "bucket"), (LAMBDA_NAME, "function")):
                for m in pattern.finditer(line):
                    out.refs.append(
                        Reference(
                            repo, rel, lineno, scrub(line), "name", m.group(1),
                            edge_type="deploy", engine=kind,
                        )
                    )
        out.ci.append(CiFile(repo, rel, system, tuple(sorted(registries))))
    return out
