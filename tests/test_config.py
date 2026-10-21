from pathlib import Path

from stackatlas.config import Config, load_config

EXAMPLE = Path(__file__).parent.parent / "examples" / "stackatlas.yml"


def test_missing_file_gives_defaults(tmp_path):
    config = load_config(tmp_path / "nope.yml")
    assert config == Config()
    assert config.skip_archived and config.skip_forks


def test_loads_yaml(tmp_path):
    path = tmp_path / "stackatlas.yml"
    path.write_text(
        "exclude: ['*-sandbox']\n"
        "skip_forks: false\n"
        "layers:\n  orchestration: ['*-orchestration']\n"
        "overrides:\n  monolith: { kind: service, layer: orchestration }\n"
    )
    config = load_config(path)
    assert config.exclude == ["*-sandbox"]
    assert config.skip_forks is False
    assert config.layers == {"orchestration": ["*-orchestration"]}
    assert config.overrides["monolith"].kind == "service"


def test_runtime_defaults():
    config = Config()
    assert (config.org, config.local) == (None, None)
    runtime = config.runtime
    assert runtime.sources == []
    assert runtime.datadog.envs == {} and runtime.datadog.window_days == 7
    assert runtime.integrations == {
        "mysql": "mysql", "redis": "redis",
        "jms": None, "sqs": None, "sns": None, "java-aws-sdk": None,
    }


def test_includes_respects_globs():
    config = Config(include=["orders-*", "web-*"], exclude=["*-legacy"])
    assert config.includes("orders-service")
    assert not config.includes("orders-legacy")
    assert not config.includes("billing-api")


def test_loads_aliases_ignore_hosts_and_envs(tmp_path):
    path = tmp_path / "stackatlas.yml"
    path.write_text(
        "aliases:\n  orders-service: ['orders.acme.com', 'orders-legacy']\n"
        "ignore_hosts: ['*.corp.acme.com']\n"
        "envs:\n  prod: ['prd']\n"
    )
    config = load_config(path)
    assert config.aliases == {"orders-service": ["orders.acme.com", "orders-legacy"]}
    assert config.ignores_host("x.corp.acme.com")
    assert not config.ignores_host("localhost")
    assert config.envs == {"prod": ["prd"]}


def test_default_ignore_hosts_and_envs():
    config = Config()
    assert config.ignores_host("localhost")
    assert config.ignores_host("127.0.0.1")
    assert config.ignores_host("api.example.com")
    assert config.ignores_host("schema.org") and config.ignores_host("www.linkedin.com")
    assert config.ignores_host("github.com") and not config.ignores_host("api.github.com")
    assert not config.ignores_host("orders.acme.com")
    assert "dev" in config.envs and "stage" in config.envs and "prod" in config.envs


def test_example_config_loads():
    config = load_config(EXAMPLE)
    assert config.org == "acme"
    assert config.apps == {"platform-mono": ["portal-api", "web/portal-ui"]}
    assert config.runtime.sources == ["datadog"]
    assert config.runtime.datadog.envs == {"prod": "production", "stage": "staging"}


def test_layer_rules_then_kind_default():
    config = Config(layers={"orchestration": ["*-orchestration"]})
    assert config.layer_for("orders-orchestration", "service") == "orchestration"
    assert config.layer_for("orders-service", "service") == "service"
    assert config.layer_for("web", "frontend") == "frontend"
