import json
import re
from collections.abc import Iterator
from pathlib import Path

from stackatlas.schema import Kind

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "target", "build", "dist", ".venv", "venv",
    "__pycache__", ".next", ".nuxt", ".terraform",
    "test", "tests", "__tests__", "fixtures", "testdata",
}

UI_FRAMEWORKS = {
    "react", "vue", "svelte", "solid-js", "preact", "ember-source", "lit",
}
APP_FRAMEWORKS = {
    "next", "nuxt", "astro", "@sveltejs/kit", "@remix-run/react", "@angular/core", "gatsby",
}
NODE_SERVERS = {
    "express", "fastify", "koa", "@nestjs/core", "@hapi/hapi", "hono", "restify",
}
JVM_SERVERS = (
    "spring-boot", "org.springframework.boot", "io.quarkus", "io.micronaut",
    "dropwizard", "io.ktor", "javalin", "helidon",
)
PY_SERVERS = (
    "fastapi", "flask", "django", "starlette", "aiohttp", "tornado", "sanic", "litestar",
)
GO_SERVERS = (
    "github.com/gin-gonic/gin", "github.com/go-chi/chi", "github.com/labstack/echo",
    "github.com/gofiber/fiber", "github.com/gorilla/mux", "google.golang.org/grpc",
)
GO_SERVE_CALLS = ("ListenAndServe(", "http.Server{", "grpc.NewServer(")
INFRA_FILES = {
    "Chart.yaml", "kustomization.yaml", "cdk.json", "serverless.yml",
    "serverless.yaml", "Pulumi.yaml",
}
INDEX_HTML = ("index.html", "public/index.html", "src/index.html")
JVM_MANIFESTS = ("pom.xml", "build.gradle", "build.gradle.kts")
PY_MANIFESTS = ("pyproject.toml", "setup.py", "setup.cfg", "Pipfile")
LIB_MANIFESTS = ("package.json", "go.mod", "Cargo.toml", *JVM_MANIFESTS, *PY_MANIFESTS)

MAX_DEPTH = 4
MAX_GO_FILES = 500


def classify_repo(root: Path) -> Kind:
    files = list(_walk(root, MAX_DEPTH))
    if _is_frontend(root):
        return "frontend"
    if _is_service(root, files):
        return "service"
    if any(f.name in INFRA_FILES or f.suffix == ".tf" for f in files):
        return "infra"
    if any((root / m).exists() for m in LIB_MANIFESTS) or _requirements(root):
        return "library"
    return "unknown"


def _walk(root: Path, depth: int) -> Iterator[Path]:
    try:
        entries = list(root.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.is_dir():
            if depth > 0 and entry.name not in SKIP_DIRS:
                yield from _walk(entry, depth - 1)
        else:
            yield entry


def _node_deps(root: Path) -> set[str]:
    path = root / "package.json"
    if not path.exists():
        return set()
    try:
        pkg = json.loads(path.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return set()
    return set(pkg.get("dependencies", {})) | set(pkg.get("devDependencies", {}))


def _is_frontend(root: Path) -> bool:
    deps = _node_deps(root)
    if "@nestjs/core" in deps:
        return False
    if deps & APP_FRAMEWORKS:
        return True
    return bool(deps & UI_FRAMEWORKS) and any((root / p).exists() for p in INDEX_HTML)


def _is_service(root: Path, files: list[Path]) -> bool:
    if _node_deps(root) & NODE_SERVERS:
        return True
    if _text_has(files, JVM_MANIFESTS, JVM_SERVERS):
        return True
    if _py_server(root, files):
        return True
    return _go_server(root, files)


def _text_has(files: list[Path], names: tuple[str, ...], needles: tuple[str, ...]) -> bool:
    for f in files:
        if f.name in names:
            text = _read(f)
            if any(n in text for n in needles):
                return True
    return False


def _requirements(root: Path) -> list[Path]:
    return sorted(root.glob("requirements*.txt"))


def _py_server(root: Path, files: list[Path]) -> bool:
    manifests = [f for f in files if f.name in PY_MANIFESTS] + _requirements(root)
    pattern = re.compile(r"(?<![\w-])(" + "|".join(PY_SERVERS) + r")(?![\w-])", re.IGNORECASE)
    return any(pattern.search(_read(f)) for f in manifests)


def _go_server(root: Path, files: list[Path]) -> bool:
    gomod = root / "go.mod"
    if not gomod.exists():
        return False
    if any(s in _read(gomod) for s in GO_SERVERS):
        return True
    go_files = [f for f in files if f.suffix == ".go"][:MAX_GO_FILES]
    return any(any(c in _read(f) for c in GO_SERVE_CALLS) for f in go_files)


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except OSError:
        return ""
