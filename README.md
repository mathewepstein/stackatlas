# stackatlas

Map every frontend, service, orchestration, and infra layer in a GitHub org. Every edge links back to the file and line that proves it.

Status: early development. Currently implemented: repo discovery and classification (nodes only).

## Install

```
pip install -e ".[dev]"
```

## Usage

```
export GITHUB_TOKEN=...            # read-only: contents + metadata
stackatlas scan --org acme         # clone + classify → ./out/graph.json
stackatlas scan --local ~/code     # scan existing checkouts, no GitHub
stackatlas schema                  # print graph.json JSON Schema
```

The token is read from `GITHUB_TOKEN`, `GH_TOKEN`, or `gh auth token`. It is never written to disk.

## Config

Optional `stackatlas.yml`:

```yaml
include: ["*"]
exclude: ["*-sandbox"]
skip_archived: true
skip_forks: true
layers:
  orchestration: ["*-orchestration"]
overrides:
  legacy-monolith: { kind: service }
```

## License

Apache-2.0
