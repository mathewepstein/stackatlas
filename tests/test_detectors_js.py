from pathlib import Path

from stackatlas.config import Config
from stackatlas.detectors import detect, js_http


def refs_for(root: Path):
    return detect("x", root, Config(), [js_http])


def test_fixture_web_portal(acme):
    refs = detect("web-portal", acme / "web-portal", Config(), [js_http])
    by = {(r.path, r.line): r for r in refs}
    api = by["src/api.ts", 1]
    assert (api.kind, api.value) == ("var", "VITE_ORDERS_URL")
    dev = by[".env.development", 1]
    assert (dev.kind, dev.value, dev.key, dev.env) == (
        "url", "https://dev-orders.acme.com", "VITE_ORDERS_URL", "dev",
    )
    assert by[".env.production", 1].env == "prod"
    assert (".env.production", 3) not in by
    assert not any("not-a-real-key" in r.snippet for r in refs)


def test_url_literal_next_to_var_keeps_key_and_scrubs_query(tmp_path):
    (tmp_path / "a.js").write_text(
        'const u = process.env.ORDERS_URL || "https://orders.acme.com/v1?token=abc";\n'
    )
    [ref] = refs_for(tmp_path)
    assert (ref.kind, ref.value, ref.key) == ("url", "https://orders.acme.com/v1", "ORDERS_URL")
    assert "token=abc" not in ref.snippet


def test_xmlns_attributes_are_not_urls(tmp_path):
    (tmp_path / "Icon.vue").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:v="https://vecta.io/nano">\n'
        '<a href="https://acme.com/help">\n'
    )
    assert [(r.value, r.line) for r in refs_for(tmp_path)] == [("https://acme.com/help", 2)]


def test_comment_lines_test_files_and_node_modules_skipped(tmp_path):
    (tmp_path / "a.ts").write_text('// "https://docs.thirdparty.io"\nconst x = 1\n')
    (tmp_path / "a.spec.ts").write_text('const u = "https://mock.thirdparty.io"\n')
    (tmp_path / "node_modules" / "m").mkdir(parents=True)
    (tmp_path / "node_modules" / "m" / "i.js").write_text('fetch("https://cdn.thirdparty.io")\n')
    assert refs_for(tmp_path) == []


def test_non_urlish_and_secret_env_vars_ignored(tmp_path):
    (tmp_path / "a.ts").write_text(
        "const m = process.env.NODE_ENV\nconst k = process.env.API_KEY_URL\n"
    )
    assert refs_for(tmp_path) == []


def test_bracket_access_and_bare_host_values(tmp_path):
    (tmp_path / "a.ts").write_text('const h = process.env["ORDERS_HOST"]\n')
    (tmp_path / ".env").write_text("ORDERS_HOST=orders.acme.com\nDEBUG=true\nPORT=8080\n")
    refs = refs_for(tmp_path)
    assert [(r.kind, r.value) for r in refs] == [("url", "orders.acme.com"), ("var", "ORDERS_HOST")]


def test_unknown_env_tokens_are_not_tagged(tmp_path):
    (tmp_path / ".env.platformlink").write_text("VITE_API_URL=https://api.acme.com\n")
    (tmp_path / ".env.staging").write_text("VITE_API_URL=https://stage-api.acme.com\n")
    refs = refs_for(tmp_path)
    assert [(r.path, r.env) for r in refs] == [
        (".env.platformlink", None), (".env.staging", "stage"),
    ]


def test_env_file_userinfo_is_stripped(tmp_path):
    (tmp_path / ".env").write_text("SENTRY_DSN=https://abc123@o1.ingest.sentry.io/42\n")
    [ref] = refs_for(tmp_path)
    assert ref.value == "https://o1.ingest.sentry.io/42"
    assert "abc123" not in ref.snippet
