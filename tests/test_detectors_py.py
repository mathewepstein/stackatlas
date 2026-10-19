from stackatlas.config import Config
from stackatlas.detectors import detect, py_http


def test_fixture_billing_api(acme):
    refs = detect("billing-api", acme / "billing-api", Config(), [py_http])
    assert [(r.path, r.line, r.kind, r.value, r.key) for r in refs] == [
        ("app/clients.py", 5, "url", "http://pricing-svc:8080", "PRICING_URL"),
        ("app/clients.py", 6, "var", "INVENTORY_URL", None),
    ]


def test_fixture_notifications_worker(acme):
    refs = detect("notifications-worker", acme / "notifications-worker", Config(), [py_http])
    assert [(r.line, r.kind, r.value) for r in refs] == [
        (5, "url", "https://hooks.slack.com/services/example"),
        (6, "var", "BILLING_URL"),
    ]


def test_settings_attribute_getenv_forms_and_secrets(tmp_path):
    (tmp_path / "a.py").write_text(
        "a = settings.ORDERS_URL\n"
        "b = os.getenv('BILLING_HOST', 'billing-api')\n"
        "c = os.environ.get('SECRET_KEY')\n"
        "d = environ['PRICING_ENDPOINT']\n"
    )
    refs = detect("x", tmp_path, Config(), [py_http])
    assert [(r.kind, r.value) for r in refs] == [
        ("var", "ORDERS_URL"), ("var", "BILLING_HOST"), ("var", "PRICING_ENDPOINT"),
    ]


def test_datastore_vars_ignored(tmp_path):
    (tmp_path / "a.py").write_text(
        "db = os.environ['DATABASE_URL']\nq = os.getenv('SQS_QUEUE_URL')\n"
    )
    assert detect("x", tmp_path, Config(), [py_http]) == []


def test_test_files_skipped(tmp_path):
    (tmp_path / "test_a.py").write_text('u = "https://mock.thirdparty.io"\n')
    (tmp_path / "a_test.py").write_text('u = "https://mock.thirdparty.io"\n')
    (tmp_path / "conftest.py").write_text('u = "https://mock.thirdparty.io"\n')
    assert detect("x", tmp_path, Config(), [py_http]) == []
