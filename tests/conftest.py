from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def acme() -> Path:
    return FIXTURES / "acme"


def _write_generic_chart(root: Path) -> None:
    chart = root / "helm-deploy"
    (chart / "templates").mkdir(parents=True)
    (chart / "Chart.yaml").write_text("apiVersion: v2\nname: helm-deploy\nversion: 0.1.0\n")
    (chart / "values.yaml").write_text("fullnameOverride: dev-sc\n")
    (chart / "templates" / "deployment.yaml").write_text(
        '{{- $fullName := include "helm-deploy.fullname" . -}}\n'
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: {{ $fullName }}\n"
    )


@pytest.fixture
def generic_chart():
    return _write_generic_chart
