from stackatlas.config import Config
from stackatlas.detectors import ci

ECR = "123456789012.dkr.ecr.us-east-1.amazonaws.com"


def test_fixture_ci_files_and_deploy_refs(acme):
    worker = ci.detect_repo("notifications-worker", acme / "notifications-worker", Config())
    assert [(c.system, c.path, c.registries, c.declared_in) for c in worker.ci] == [
        ("codebuild", "buildspec.yml", (ECR,), None),
    ]
    assert [(r.kind, r.value, r.edge_type, r.engine, r.line) for r in worker.refs] == [
        ("name", "prod-notify", "deploy", "function", 5),
    ]
    kit = ci.detect_repo("ui-kit", acme / "ui-kit", Config())
    assert [(c.system, c.path, c.registries) for c in kit.ci] == [
        ("github-actions", ".github/workflows/release.yml", ("npm.pkg.github.com",)),
    ]
    assert kit.refs == []
    checkout = ci.detect_repo("checkout-ui", acme / "checkout-ui", Config())
    assert [(r.kind, r.value, r.edge_type, r.engine, r.line) for r in checkout.refs] == [
        ("name", "acme-assets-prod", "deploy", "bucket", 5),
    ]


def test_ci_systems_and_variable_targets(tmp_path):
    files = {
        "Jenkinsfile": "sh 'aws s3 sync build s3://${BUCKET}/x'\n",
        ".gitlab-ci.yml": "deploy:\n  script:\n    - echo hi\n",
        ".circleci/config.yml": "version: 2\n",
        "bitbucket-pipelines.yml": "pipelines: {}\n",
        "devops/codebuild/ecr-deploy.buildspec.yml": "phases: {}\n",
        "src/app.py": "x = 's3://not-ci-file'\n",
    }
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    found = ci.detect_repo("x", tmp_path, Config())
    assert sorted((c.system, c.path) for c in found.ci) == [
        ("bitbucket", "bitbucket-pipelines.yml"),
        ("circleci", ".circleci/config.yml"),
        ("codebuild", "devops/codebuild/ecr-deploy.buildspec.yml"),
        ("gitlab-ci", ".gitlab-ci.yml"),
        ("jenkins", "Jenkinsfile"),
    ]
    assert found.refs == []
