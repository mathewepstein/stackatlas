from stackatlas.config import Config, load_config


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


def test_includes_respects_globs():
    config = Config(include=["orders-*", "web-*"], exclude=["*-legacy"])
    assert config.includes("orders-service")
    assert not config.includes("orders-legacy")
    assert not config.includes("billing-api")


def test_layer_rules_then_kind_default():
    config = Config(layers={"orchestration": ["*-orchestration"]})
    assert config.layer_for("orders-orchestration", "service") == "orchestration"
    assert config.layer_for("orders-service", "service") == "service"
    assert config.layer_for("web", "frontend") == "frontend"
