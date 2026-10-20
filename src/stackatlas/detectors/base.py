import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from stackatlas.classify import SKIP_DIRS
from stackatlas.config import Config
from stackatlas.files import read_lines, unquote
from stackatlas.schema import EdgeType, Kind

RefKind = Literal["url", "name", "var"]

MAX_SNIPPET = 200
COMMENT_STARTS = ("//", "#", "*", "/*", "<!--")
VISIBLE_HIDDEN_DIRS = {".github", ".circleci"}
PLACEHOLDER_ENVS = {"example", "sample", "template", "dist"}

SECRET_KEY = re.compile(r"(secret|token|password|passwd|credential|key)(?![a-z])", re.I)
URLISH_KEY = re.compile(
    r"(url|uri|host|hostname|endpoint|base|origin|domain|addr|address|fqdn)$", re.I
)
NON_HTTP_KEY = re.compile(
    r"(datasource|jdbc|redis|mongo|sqs|sns|kafka|rabbit|amqp|database|queue|topic|bucket"
    r"|dynamo|elasticsearch|opensearch|smtp)",
    re.I,
)
QUOTED_URL = re.compile(r"""["'`](https?://[^\s"'`<>]+)""")
XMLNS = re.compile(r"""\bxmlns(?::[\w.-]+)?\s*=\s*["'][^"']*["']""")
ANY_URL = re.compile(r"""https?://[^\s"'`<>)]+""")
DATASTORE_URL = re.compile(
    r"""\b(jdbc:[a-z0-9]+|rediss?|mongodb(?:\+srv)?|postgres(?:ql)?|mysql|mariadb)://([^\s"'`<>]+)"""
    r"""|\b(jdbc:oracle):[a-z]+:@([^\s"'`<>]+)""",
    re.I,
)
DATASTORE_KEY = re.compile(
    r"(datasource|jdbc|redis|mongo|database|dynamo|elasticsearch|opensearch|memcache|cassandra"
    r"|postgres|mysql|(?:^|[._-])db(?:[._-]|$))",
    re.I,
)
ENGINES = {
    "postgresql": "postgres", "postgres": "postgres", "mysql": "mysql", "mariadb": "mariadb",
    "redis": "redis", "rediss": "redis", "mongodb": "mongo", "mongodb+srv": "mongo",
    "oracle": "oracle", "sqlserver": "sqlserver",
}
KEY_ENGINES = (
    ("redis", "redis"), ("mongo", "mongo"), ("dynamo", "dynamodb"), ("postgres", "postgres"),
    ("mysql", "mysql"), ("elasticsearch", "search"), ("opensearch", "search"),
    ("memcache", "memcached"), ("cassandra", "cassandra"),
)
HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?(:\d+)?$")
ENV_FILE = re.compile(r"^\.env\.([A-Za-z0-9]+)(?:\.local)?$")
PROFILE_FILE = re.compile(r"^(?:application|bootstrap)-([A-Za-z0-9]+)\.(?:ya?ml|properties)$")
NAMED_ENV_FILE = re.compile(r"^([A-Za-z0-9]+)\.env$")
NAMED_PROPERTIES_FILE = re.compile(r"^([A-Za-z0-9]+)\.properties$")
ENV_KV = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


@dataclass(frozen=True)
class Reference:
    repo: str
    path: str
    line: int
    snippet: str
    kind: RefKind
    value: str
    key: str | None = None
    env: str | None = None
    edge_type: EdgeType = "http"
    fallback: str | None = None
    source: str | None = None
    owner: str | None = None
    engine: str | None = None


@dataclass(frozen=True)
class Declared:
    id: str
    name: str
    kind: Kind
    layer: str
    repo: str
    path: str
    line: int
    snippet: str
    aliases: tuple[str, ...] = ()
    envs: tuple[str, ...] = ()
    endpoints: tuple[str, ...] = ()


@dataclass(frozen=True)
class CiFile:
    repo: str
    path: str
    system: str
    registries: tuple[str, ...] = ()
    declared_in: str | None = None


@dataclass
class Detection:
    refs: list[Reference] = field(default_factory=list)
    declared: list[Declared] = field(default_factory=list)
    owners: list[tuple[str, str, str]] = field(default_factory=list)
    ci: list[CiFile] = field(default_factory=list)


def iter_files(root: Path) -> Iterator[tuple[str, Path]]:
    for path in _walk(root):
        yield path.relative_to(root).as_posix(), path


def _walk(root: Path) -> Iterator[Path]:
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return
    for entry in entries:
        if entry.is_dir():
            hidden = entry.name.startswith(".") and entry.name not in VISIBLE_HIDDEN_DIRS
            if entry.name not in SKIP_DIRS and not hidden:
                yield from _walk(entry)
        elif entry.is_file():
            yield entry


def is_comment(line: str) -> bool:
    return line.lstrip().startswith(COMMENT_STARTS)


def is_secret(key: str) -> bool:
    return bool(SECRET_KEY.search(key))


def is_urlish(key: str) -> bool:
    return bool(URLISH_KEY.search(key.replace("-", "_").replace(".", "_")))


def is_http_key(key: str) -> bool:
    return is_urlish(key) and not NON_HTTP_KEY.search(key)


def is_http_url(value: str) -> bool:
    return value.lower().startswith(("http://", "https://"))


def looks_like_host(value: str) -> bool:
    return bool(HOST.match(value)) and any(c in value for c in ".:-")


def is_env_file(name: str) -> bool:
    return name == ".env" or name.startswith(".env.") or bool(NAMED_ENV_FILE.match(name))


def clean_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        host, port = parts.hostname, parts.port
    except ValueError:
        return url.split("?", 1)[0]
    if not host:
        return url.split("?", 1)[0]
    suffix = f":{port}" if port else ""
    return f"{parts.scheme}://{host}{suffix}{parts.path}"


def url_parts(value: str) -> tuple[str, str] | None:
    raw = value if "://" in value else f"//{value}"
    try:
        parts = urlsplit(raw)
        host = parts.hostname
    except ValueError:
        return None
    if not host or not HOST.match(host):
        return None
    return host.lower(), parts.path.rstrip("/")


def datastore_parts(url: str) -> tuple[str, str] | None:
    m = DATASTORE_URL.search(url)
    if not m:
        return None
    if m.group(3):
        host, _, rest = m.group(4).partition(":")
        port = rest.split(":")[0].split("/")[0]
        return "oracle", f"{host}:{port}" if port else host
    scheme = m.group(1).lower().removeprefix("jdbc:")
    try:
        parts = urlsplit(f"//{m.group(2)}")
        host, port = parts.hostname, parts.port
    except ValueError:
        return None
    if not host:
        return None
    suffix = f":{port}" if port else ""
    return ENGINES.get(scheme, scheme), f"{host}{suffix}{parts.path.rstrip('/')}"


def clean_datastore_url(url: str) -> str:
    parts = datastore_parts(url)
    return f"{parts[0]}://{parts[1]}" if parts else url.split("?", 1)[0]


def engine_for_key(key: str) -> str:
    lowered = key.lower()
    return next((engine for needle, engine in KEY_ENGINES if needle in lowered), "db")


def scrub(line: str) -> str:
    line = ANY_URL.sub(lambda m: clean_url(m.group(0)), line.strip())
    return DATASTORE_URL.sub(lambda m: clean_datastore_url(m.group(0)), line)[:MAX_SNIPPET]


def known_env_tokens(envs: dict[str, list[str]]) -> set[str]:
    return set(envs) | {t for tokens in envs.values() for t in tokens}


def canonical_env(token: str, envs: dict[str, list[str]]) -> str | None:
    token = token.lower()
    if token in PLACEHOLDER_ENVS:
        return None
    for env, tokens in envs.items():
        if token == env or token in tokens:
            return env
    return None


def env_from_path(rel: str, envs: dict[str, list[str]]) -> str | None:
    name = rel.rsplit("/", 1)[-1]
    for pattern in (ENV_FILE, PROFILE_FILE, NAMED_ENV_FILE, NAMED_PROPERTIES_FILE):
        m = pattern.match(name)
        if m:
            return canonical_env(m.group(1), envs)
    return None


def env_from_host(host: str, envs: dict[str, list[str]]) -> str | None:
    known = known_env_tokens(envs)
    for token in re.split(r"[.-]", host):
        if token in known:
            return canonical_env(token, envs)
    return None


def strip_env(host: str, envs: dict[str, list[str]]) -> str:
    known = known_env_tokens(envs)
    labels = []
    for label in host.split("."):
        parts = [p for p in label.split("-") if p not in known]
        if parts:
            labels.append("-".join(parts))
    return ".".join(labels)


def var_names(pattern: re.Pattern[str], line: str) -> list[str]:
    names = []
    for m in pattern.finditer(line):
        name = next((g for g in m.groups() if g), None)
        if name:
            names.append(name)
    return names


def line_refs(
    repo: str,
    rel: str,
    lineno: int,
    line: str,
    var_pattern: re.Pattern[str],
    env: str | None = None,
    snippet: str | None = None,
) -> list[Reference]:
    if is_comment(line):
        return []
    urls = [clean_url(u) for u in QUOTED_URL.findall(XMLNS.sub("", line))]
    names = [n for n in var_names(var_pattern, line) if is_http_key(n) and not is_secret(n)]
    snippet = snippet if snippet is not None else scrub(line)
    if urls:
        key = names[0] if names else None
        return [Reference(repo, rel, lineno, snippet, "url", u, key=key, env=env) for u in urls]
    return [Reference(repo, rel, lineno, snippet, "var", n, env=env) for n in names]


def value_ref(
    repo: str, rel: str, lineno: int, line: str, key: str, value: str, env: str | None
) -> Reference | None:
    if is_secret(key):
        return None
    if is_http_url(value):
        return Reference(repo, rel, lineno, scrub(line), "url", clean_url(value), key=key, env=env)
    if is_http_key(key) and looks_like_host(value):
        return Reference(repo, rel, lineno, scrub(line), "url", value, key=key, env=env)
    return None


def env_entries(path: Path) -> list[tuple[str, str, int, str]]:
    entries = []
    for lineno, line in enumerate(read_lines(path), 1):
        m = ENV_KV.match(line)
        if m and not line.lstrip().startswith("#"):
            entries.append((m.group(1), unquote(m.group(2)), lineno, line))
    return entries


def env_file_refs(repo: str, rel: str, path: Path, config: Config) -> list[Reference]:
    env = env_from_path(rel, config.envs)
    refs = []
    for key, value, lineno, line in env_entries(path):
        ref = value_ref(repo, rel, lineno, line, key, value, env)
        if ref:
            refs.append(ref)
    return refs
