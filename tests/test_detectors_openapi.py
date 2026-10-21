import json

from stackatlas.config import Config
from stackatlas.detectors import openapi

SPEC = (
    "openapi: 3.0.3\n"
    "info:\n  title: Inventory Service\n  version: '1'\n"
    "servers:\n  - url: https://inventory.acme.com\n  - url: https://{env}.acme.com\n"
    "paths:\n"
    "  /items/{id}:\n    get:\n      summary: one\n    delete: {}\n"
    "  /items:\n    post: {}\n    parameters: []\n"
)


def _write(root, files):
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)


def test_specs_are_found_by_content(tmp_path):
    swagger = {"swagger": "2.0", "info": {"title": "Old"}, "host": "old.acme.com",
               "basePath": "/v1", "paths": {"/x": {"get": {}}}}
    _write(tmp_path, {
        "docs/inventory/api.yaml": SPEC,
        "legacy.json": json.dumps(swagger),
        "k8s/deploy.yaml": "kind: Deployment\nmetadata:\n  name: x\n",
        "package.json": json.dumps({"name": "x", "openapi": "not a spec"}),
        "notes.yaml": "openapi_version: 3\n",
    })
    found = openapi.detect_repo("docs", tmp_path, Config())
    assert [(s.path, s.title, s.servers, s.endpoints) for s in found.specs] == [
        ("docs/inventory/api.yaml", "Inventory Service", ["https://inventory.acme.com"],
         ["DELETE /items/{id}", "GET /items/{id}", "POST /items"]),
        ("legacy.json", "Old", ["old.acme.com/v1"], ["GET /x"]),
    ]
    assert found.refs == []
    assert [s.consumed for s in found.specs] == [False, False]


def test_generator_input_spec_becomes_a_ref(tmp_path):
    _write(tmp_path, {
        "specs/inventory.yaml": SPEC,
        "specs/bare.yaml": "openapi: 3.0.0\ninfo:\n  title: Bare API\npaths: {}\n",
        "build.gradle": (
            "plugins {\n  id 'org.openapi.generator' version '7.10.0'\n}\n"
            "openApiGenerate {\n"
            '    inputSpec = "$projectDir/specs/inventory.yaml"\n'
            "}\n"
        ),
        "client/build.gradle.kts": (
            'openApiGenerate {\n    inputSpec.set("$rootDir/specs/bare.yaml")\n}\n'
        ),
        "pom.xml": (
            "<project><build><plugins><plugin>\n"
            "  <configuration>\n"
            "    <inputSpec>${project.basedir}/specs/missing.yaml</inputSpec>\n"
            "  </configuration>\n"
            "</plugin></plugins></build></project>\n"
        ),
    })
    found = openapi.detect_repo("orders", tmp_path, Config())
    assert [(r.path, r.line, r.kind, r.value, r.fallback) for r in found.refs] == [
        ("build.gradle", 5, "url", "https://inventory.acme.com", "inventory-service"),
        ("client/build.gradle.kts", 2, "name", "bare-api", None),
    ]
    assert [(s.path, s.consumed) for s in found.specs] == [
        ("specs/bare.yaml", True), ("specs/inventory.yaml", True),
    ]
