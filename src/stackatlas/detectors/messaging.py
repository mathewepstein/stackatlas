import re
from pathlib import Path

from stackatlas.config import Config
from stackatlas.detectors import java_http, py_http
from stackatlas.detectors.base import (
    Reference,
    Role,
    balanced,
    env_entries,
    env_from_path,
    is_comment,
    is_env_file,
    is_secret,
    scrub,
    var_names,
)
from stackatlas.files import PLACEHOLDER, read_lines
from stackatlas.names import literal_parts

JAVA = {".java", ".kt", ".scala", ".groovy"}
MESSAGING_KEY = re.compile(r"(sqs|sns|queue|topic|jms|kafka|rabbit|amqp|pubsub)", re.I)
ARN = re.compile(r"^arn:aws:(sqs|sns):[^:]*:[^:]*:([^:\s]+)$", re.I)
SQS_URL = re.compile(r"^https?://sqs\.[^/]+/[^/]+/([^/\s?]+)/?$", re.I)
NAME = re.compile(r"^[A-Za-z0-9*][A-Za-z0-9_.*-]*$")
LETTER = re.compile(r"[A-Za-z]")
LITERAL_WORDS = {"true", "false", "yes", "no", "null", "none", "on", "off"}

LISTENERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "JmsListener": ("queue", ("destination",)),
    "SqsListener": ("queue", ("value", "queueNames", "")),
    "KafkaListener": ("topic", ("topics", "")),
    "RabbitListener": ("queue", ("queues", "")),
}
LISTENER = re.compile(r"@(JmsListener|SqsListener|KafkaListener|RabbitListener)\s*\(")
STRINGS = re.compile(r"\{[^}]*\}|\[[^\]]*\]|\"[^\"]*\"")
QUOTED = re.compile(r"\"([^\"]*)\"")
TEMPLATE_ENGINES = {"jms": "queue", "kafka": "topic", "rabbit": "queue"}
TEMPLATE_SEND = re.compile(
    r"\b\w*?(jms|kafka|rabbit)\w*\s*\.\s*(?:send|convertAndSend|sendDefault)\s*\(\s*"
    r"(\"[^\"]*\"|[A-Za-z_]\w*)\s*[,)]",
    re.I,
)
BUILDER = re.compile(r"\.\s*(queueUrl|topicArn)\s*\(\s*(\"[^\"]*\"|[A-Za-z_]\w*)\s*\)")
BUILDER_ENGINES = {"queueUrl": "queue", "topicArn": "topic"}
PRODUCE_HINT = re.compile(r"[Ss]endMessage|[Pp]ublish")
CONSUME_HINT = re.compile(r"[Rr]eceiveMessage")
STATEMENT_END = re.compile(r"[;{}]\s*$")
MAX_STATEMENT_LINES = 10
VALUE_FIELD = re.compile(
    r"@Value\(\s*\"\\?\$\{([\w.\-]+)(?::[^}]*)?\}\"\s*\)\s*"
    r"((?:[\w<>\[\],?.]+\s+)*)([A-Za-z_]\w*)\s*(?=[;=:,)])"
)

PY_CALL = re.compile(
    r"\.\s*(send_message_batch|send_message|publish_batch|publish|receive_message)\s*\("
)
PY_KW = re.compile(
    r"\b(QueueUrl|TopicArn)\s*=\s*(\"[^\"]*\"|'[^']*'|[\w.]+(?:\s*[\(\[][^\)\]]*[\)\]])?)"
)
PY_ENGINES = {"QueueUrl": "queue", "TopicArn": "topic"}
PY_ASSIGN = re.compile(r"^\s*([A-Za-z_]\w*)\s*(?::[^=]*)?=\s*(.+?)\s*$")
PY_LITERAL = re.compile(r"^(?:\"([^\"]*)\"|'([^']*)')$")


def messaging_name(value: str) -> tuple[str | None, str] | None:
    value = value.strip()
    if not value or "${" in value:
        return None
    m = ARN.match(value)
    if m:
        engine = "queue" if m.group(1).lower() == "sqs" else "topic"
        return _named(engine, m.group(2))
    m = SQS_URL.match(value)
    if m:
        return _named("queue", m.group(1))
    if "://" in value or not NAME.match(value) or value.lower() in LITERAL_WORDS:
        return None
    return _named(None, value)


def _named(engine: str | None, raw: str) -> tuple[str | None, str] | None:
    name = literal_parts(raw)
    return (engine, name) if name and LETTER.search(name) else None


def event_value(key: str | None, value: str) -> tuple[str | None, str] | None:
    found = messaging_name(value)
    if found and (found[0] or (key and MESSAGING_KEY.search(key))):
        return found
    return None


def detect_file(repo: str, rel: str, path: Path, config: Config) -> list[Reference]:
    name = path.name
    if is_env_file(name):
        env = env_from_path(rel, config.envs)
        items = [(k, v, n, env, line) for k, v, n, line in env_entries(path)]
        return _config_refs(repo, rel, items)
    if java_http.CONFIG_FILE.match(name) and name not in java_http.BUILD_FILES:
        lines = read_lines(path)
        entries = java_http.config_entries(rel, path, config)
        return _config_refs(repo, rel, [(k, v, n, env, lines[n - 1]) for k, v, n, env in entries])
    if path.suffix in JAVA:
        return _java_refs(repo, rel, read_lines(path))
    if path.suffix == ".py" and not py_http.SKIP.match(name):
        return _python_refs(repo, rel, read_lines(path))
    return []


Entry = tuple[str, str, int, str | None, str]


def _config_refs(repo: str, rel: str, items: list[Entry]) -> list[Reference]:
    refs = []
    for key, value, lineno, env, line in items:
        if is_secret(key):
            continue
        m = PLACEHOLDER.match(value)
        if m:
            if not m.group(2):
                continue
            value = m.group(2)
        if event_value(key, value):
            refs.append(
                Reference(
                    repo, rel, lineno, scrub(line), "name", value, key=key, env=env,
                    edge_type="event",
                )
            )
    return refs


def _ref(
    repo: str, rel: str, lineno: int, snippet: str, raw: str, role: Role, engine: str
) -> Reference | None:
    raw = raw.lstrip("\\")
    m = PLACEHOLDER.match(raw)
    if m:
        var, default = m.group(1), m.group(2)
        if default:
            return Reference(
                repo, rel, lineno, snippet, "name", default, key=var, edge_type="event",
                role=role, engine=engine,
            )
        return Reference(
            repo, rel, lineno, snippet, "var", var, edge_type="event", role=role, engine=engine
        )
    if not messaging_name(raw):
        return None
    return Reference(
        repo, rel, lineno, snippet, "name", raw, edge_type="event", role=role, engine=engine
    )


def _java_refs(repo: str, rel: str, lines: list[str]) -> list[Reference]:
    fields = {m.group(3): m.group(1) for m in VALUE_FIELD.finditer("\n".join(lines))}
    refs: list[Reference] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if is_comment(line):
            i += 1
            continue
        m = LISTENER.search(line)
        if m:
            block, span = balanced(lines, i)
            engine, targets = _destinations(m.group(1), block)
            for target in targets:
                ref = _ref(repo, rel, i + 1, scrub(block), target, "consume", engine)
                if ref:
                    refs.append(ref)
            i += span
            continue
        refs.extend(_java_line_refs(repo, rel, lines, i, fields))
        i += 1
    return refs


def _destinations(annotation: str, block: str) -> tuple[str, list[str]]:
    engine, attrs = LISTENERS[annotation]
    for attr in attrs:
        if attr:
            m = re.search(rf"\b{attr}\s*=\s*({STRINGS.pattern})", block)
        else:
            m = re.match(rf"@{annotation}\s*\(\s*({STRINGS.pattern})", block)
        if m:
            return engine, QUOTED.findall(m.group(1))
    return engine, []


def _java_line_refs(
    repo: str, rel: str, lines: list[str], i: int, fields: dict[str, str]
) -> list[Reference]:
    line = lines[i]
    refs = []
    for m in TEMPLATE_SEND.finditer(line):
        target = _java_arg(m.group(2), fields)
        engine = TEMPLATE_ENGINES[m.group(1).lower()]
        if target:
            ref = _ref(repo, rel, i + 1, scrub(line), target, "produce", engine)
            if ref:
                refs.append(ref)
    for m in BUILDER.finditer(line):
        target = _java_arg(m.group(2), fields)
        role = _builder_role(lines, i)
        if target and role:
            ref = _ref(repo, rel, i + 1, scrub(line), target, role, BUILDER_ENGINES[m.group(1)])
            if ref:
                refs.append(ref)
    return refs


def _java_arg(arg: str, fields: dict[str, str]) -> str | None:
    if arg.startswith('"'):
        return arg.strip('"')
    key = fields.get(arg)
    return f"${{{key}}}" if key else None


def _builder_role(lines: list[str], i: int) -> Role | None:
    start = i
    while start > 0 and i - start < MAX_STATEMENT_LINES:
        if STATEMENT_END.search(lines[start - 1]):
            break
        start -= 1
    text = " ".join(lines[start : i + 1])
    if CONSUME_HINT.search(text):
        return "consume"
    if PRODUCE_HINT.search(text):
        return "produce"
    return None


def _python_refs(repo: str, rel: str, lines: list[str]) -> list[Reference]:
    assigns: dict[str, str] = {}
    literals: dict[str, str] = {}
    for line in lines:
        m = PY_ASSIGN.match(line)
        if not m:
            continue
        names = var_names(py_http.VAR, m.group(2))
        if names:
            assigns[m.group(1)] = names[0]
            continue
        lit = PY_LITERAL.match(m.group(2))
        if lit:
            literals[m.group(1)] = lit.group(1) if lit.group(1) is not None else lit.group(2)
    refs: list[Reference] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = PY_CALL.search(line)
        if not m or is_comment(line):
            i += 1
            continue
        role: Role = "consume" if m.group(1) == "receive_message" else "produce"
        block, span = balanced(lines, i)
        for kw in PY_KW.finditer(block):
            ref = _python_ref(repo, rel, i + 1, scrub(line), kw, role, assigns, literals)
            if ref:
                refs.append(ref)
        i += span
    return refs


def _python_ref(
    repo: str,
    rel: str,
    lineno: int,
    snippet: str,
    kw: re.Match[str],
    role: Role,
    assigns: dict[str, str],
    literals: dict[str, str],
) -> Reference | None:
    engine = PY_ENGINES[kw.group(1)]
    expr = kw.group(2)
    lit = PY_LITERAL.match(expr)
    if lit:
        value = lit.group(1) if lit.group(1) is not None else lit.group(2)
    else:
        names = var_names(py_http.VAR, expr)
        var = names[0] if names else assigns.get(expr)
        if var:
            return Reference(
                repo, rel, lineno, snippet, "var", var, edge_type="event", role=role, engine=engine
            )
        value = literals.get(expr, "")
    if not messaging_name(value):
        return None
    return Reference(
        repo, rel, lineno, snippet, "name", value, edge_type="event", role=role, engine=engine
    )
