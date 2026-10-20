from stackatlas.tf import find_stacks, load_stack


def test_interpolation_resolves_locals_and_var_defaults(tmp_path):
    (tmp_path / "main.tf").write_text(
        'locals {\n  env = "prod"\n  host = "${local.env}-x.${var.tld}"\n'
        '  nested = { a = "${local.host}/v1" }\n  bare = local.env\n  unknown = local.missing\n}\n'
        'variable "tld" {\n  default = "acme.com"\n}\n'
        'variable "secret" {\n  type = string\n}\n'
        'resource "aws_sqs_queue" "q" {\n  name = "${local.env}-q-${var.secret}"\n}\n'
    )
    stack = load_stack(tmp_path, "")
    assert stack.text(stack.locals["host"]) == "prod-x.acme.com"
    assert stack.text(stack.locals["nested"]["a"]) == "prod-x.acme.com/v1"
    assert stack.text(stack.locals["bare"]) == "prod"
    assert stack.text(stack.locals["unknown"]) == "*"
    [queue] = stack.resources("aws_sqs_queue")
    assert (queue.name, stack.text(queue.body["name"]), queue.line) == ("q", "prod-q-*", 14)


def test_find_stacks_skips_module_dirs_and_reports_lines(tmp_path):
    for rel in ("stacks/edge/a.tf", "stacks/edge/b.tf", "modules/x/main.tf", "docs/readme.md"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("")
    (tmp_path / "stacks/edge/b.tf").write_text(
        '\nmodule "m" {\n  source = "../../modules/x"\n}\n'
    )
    stacks = find_stacks(tmp_path)
    assert [s.rel for s in stacks] == ["stacks/edge"]
    [mod] = stacks[0].modules()
    assert (mod.name, mod.path, mod.line) == ("m", "stacks/edge/b.tf", 2)
