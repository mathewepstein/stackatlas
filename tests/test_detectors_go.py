from stackatlas.config import Config
from stackatlas.detectors import detect, go_http


def test_fixture_go_repos(acme):
    inv = detect("inventory-svc", acme / "inventory-svc", Config(), [go_http])
    assert [(r.path, r.line, r.kind, r.value) for r in inv] == [
        ("internal/pricing/client.go", 10, "var", "PRICING_URL"),
    ]
    pricing = detect("pricing-svc", acme / "pricing-svc", Config(), [go_http])
    assert [(r.path, r.line, r.kind, r.value) for r in pricing] == [
        ("internal/fx/client.go", 5, "url", "https://api.exchangerate.host/latest"),
    ]


def test_lookupenv_and_raw_strings(tmp_path):
    (tmp_path / "a.go").write_text(
        'u, _ := os.LookupEnv("ORDERS_URL")\nconst b = `https://billing.acme.com`\n'
    )
    refs = detect("x", tmp_path, Config(), [go_http])
    assert [(r.kind, r.value) for r in refs] == [
        ("var", "ORDERS_URL"), ("url", "https://billing.acme.com"),
    ]
