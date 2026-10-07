import pytest

from stackatlas.classify import classify_repo


@pytest.mark.parametrize(
    ("repo", "kind"),
    [
        ("web-portal", "frontend"),
        ("checkout-ui", "frontend"),
        ("admin-next", "frontend"),
        ("ui-kit", "library"),
        ("gateway-node", "service"),
        ("orders-service", "service"),
        ("orders-orchestration", "service"),
        ("java-commons", "library"),
        ("billing-api", "service"),
        ("notifications-worker", "service"),
        ("py-helpers", "library"),
        ("inventory-svc", "service"),
        ("pricing-svc", "service"),
        ("go-kit", "library"),
        ("platform-infra", "infra"),
        ("deploy-charts", "infra"),
        ("handbook", "unknown"),
    ],
)
def test_classify_fixture_repos(acme, repo, kind):
    assert classify_repo(acme / repo) == kind


def test_test_fixtures_are_ignored(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "tool"\n')
    nested = tmp_path / "tests" / "fixtures" / "api"
    nested.mkdir(parents=True)
    (nested / "pyproject.toml").write_text('dependencies = ["fastapi"]\n')
    assert classify_repo(tmp_path) == "library"


def test_go_http_server_struct_is_service(tmp_path):
    (tmp_path / "go.mod").write_text("module example.com/x\n")
    (tmp_path / "server.go").write_text("srv := &http.Server{Handler: mux}\nsrv.Serve(ln)\n")
    assert classify_repo(tmp_path) == "service"


def test_node_modules_are_ignored(tmp_path):
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "main.tf").write_text("")
    assert classify_repo(tmp_path) == "unknown"
