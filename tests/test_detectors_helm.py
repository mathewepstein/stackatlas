from stackatlas.config import Config
from stackatlas.detectors import helm_k8s
from stackatlas.helm import render

CHART = "charts/orders"


def test_render_resolves_values_fullname_and_ranges():
    values = {"fullnameOverride": "prod-x", "ingress": {"hosts": [{"host": "a.acme.com"}]}}
    text = (
        '{{- $fullName := include "c.fullname" . -}}\n'
        "name: {{ $fullName }}\n"
        "chart: {{ .Chart.Name }}\n"
        "rel: {{ .Release.Name }}\n"
        "{{- range .Values.ingress.hosts }}\n"
        "host: {{ .host | quote }}\n"
        "{{- end }}\n"
        "tag: {{ .Values.image.tag | default .Chart.AppVersion }}\n"
    )
    assert render(text, values, "c").splitlines() == [
        "", "name: prod-x", "chart: c", 'rel: "*"', "", 'host: "a.acme.com"', "", 'tag: "*"',
    ]


def test_fixture_chart_declares_workload(acme):
    found = helm_k8s.detect_repo("deploy-charts", acme / "deploy-charts", Config())
    [wl] = found.declared
    assert (wl.id, wl.name, wl.kind, wl.layer, wl.envs) == (
        "workload:orders/orders-web", "orders-web", "workload", "service", ("dev", "prod"),
    )
    assert wl.aliases == (
        "prod-orders-web", "orders-web", "orders-web.acme.com", "dev-orders-web",
        "dev-orders-web.acme.com",
    )
    assert (wl.path, wl.line) == (f"{CHART}/templates/deployment.yaml", 3)
    refs = sorted(found.refs, key=lambda r: (r.line, r.env or ""))
    assert [(r.line, r.kind, r.value, r.env, r.edge_type, r.source) for r in refs] == [
        (17, "url", "https://pricing.acme.com", "dev", "http", "workload:orders/orders-web"),
        (17, "url", "https://pricing.acme.com", "prod", "http", "workload:orders/orders-web"),
        (19, "url", "dev-orders-db.acme.internal:5432/orders", "dev", "datastore",
         "workload:orders/orders-web"),
        (19, "url", "prod-orders-db.acme.internal:5432/orders", "prod", "datastore",
         "workload:orders/orders-web"),
    ]
    assert all(r.path == f"{CHART}/templates/deployment.yaml" for r in refs)


def test_raw_manifests_in_manifest_less_repo(tmp_path):
    (tmp_path / "k8s").mkdir()
    (tmp_path / "k8s" / "app.yaml").write_text(
        "apiVersion: apps/v1\nkind: StatefulSet\nmetadata:\n  name: stage-cache\n"
        "spec:\n  template:\n    spec:\n      containers:\n        - name: c\n"
        "          env:\n            - name: ORDERS_URL\n              value: https://orders.acme.com\n"
        "---\napiVersion: v1\nkind: Service\nmetadata:\n  name: cache-svc\n"
    )
    found = helm_k8s.detect_repo("manifests", tmp_path, Config())
    [wl] = found.declared
    assert (wl.id, wl.aliases, wl.envs) == (
        "workload:manifests/cache", ("stage-cache", "cache", "cache-svc"), ("stage",),
    )
    assert [(r.value, r.source, r.env) for r in found.refs] == [
        ("https://orders.acme.com", "workload:manifests/cache", "stage"),
    ]
    (tmp_path / "package.json").write_text("{}")
    assert helm_k8s.detect_repo("app", tmp_path, Config()).declared == []
