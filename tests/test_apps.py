import json

from stackatlas.apps import find_apps


def mk(root, *paths):
    for p in paths:
        (root / p).parent.mkdir(parents=True, exist_ok=True)
        (root / p).write_text("")


def test_gradle_include_forms(tmp_path):
    (tmp_path / "settings.gradle").write_text(
        "rootProject.name = 'mono'\ninclude 'a', 'b'\ninclude(':c:d')\ninclude ':e'\n"
        "includeBuild('../other')\n"
    )
    mk(tmp_path, "a/build.gradle", "b/build.gradle", "c/d/build.gradle", "e/build.gradle")
    assert find_apps(tmp_path) == ["a", "b", "c/d", "e"]


def test_maven_modules(tmp_path):
    (tmp_path / "pom.xml").write_text(
        '<project xmlns="http://maven.apache.org/POM/4.0.0"><modules>'
        "<module>api</module><module>worker</module></modules></project>"
    )
    mk(tmp_path, "api/pom.xml", "worker/pom.xml")
    assert find_apps(tmp_path) == ["api", "worker"]


def test_pnpm_and_package_json_workspaces(tmp_path):
    (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - apps/*\n  - '!apps/skip'\n")
    (tmp_path / "package.json").write_text(json.dumps({"workspaces": ["tools/*"]}))
    mk(tmp_path, "apps/web/package.json", "apps/skip/package.json", "apps/nopkg/README.md",
       "tools/cli/package.json")
    assert find_apps(tmp_path) == ["apps/web", "tools/cli"]


def test_workspace_glob_for_the_root_is_not_a_sub_app(tmp_path):
    (tmp_path / "pnpm-workspace.yaml").write_text("packages:\n  - '.'\n  - './'\n  - './apps/*'\n")
    mk(tmp_path, "package.json", "apps/web/package.json")
    assert find_apps(tmp_path) == ["apps/web"]


def test_go_work(tmp_path):
    (tmp_path / "go.work").write_text("go 1.22\n\nuse (\n\t./svc/a\n\t./svc/b\n)\n")
    mk(tmp_path, "svc/a/go.mod", "svc/b/go.mod")
    assert find_apps(tmp_path) == ["svc/a", "svc/b"]


def test_manifest_sweep_only_when_root_has_none(tmp_path):
    mk(tmp_path, "docker-compose.yml", "src/frontend/package.json",
       "src/backend/serverless.yaml", "src/backend/lib/package.json", "docs/readme.md")
    assert find_apps(tmp_path) == ["src/backend", "src/frontend"]
    (tmp_path / "package.json").write_text("{}")
    assert find_apps(tmp_path) == []


def test_configured_apps_win(tmp_path):
    (tmp_path / "settings.gradle").write_text("include 'a'\n")
    mk(tmp_path, "a/build.gradle", "x/build.gradle")
    assert find_apps(tmp_path, ["x", "missing"]) == ["x"]
