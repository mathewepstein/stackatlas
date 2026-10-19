# stackatlas

Map every frontend, service, orchestration, and infra layer in a GitHub org. Every edge links back to the file and line that proves it.

Status: early development. Implemented: repo discovery and classification, HTTP edges for JS/TS, Java/Kotlin, Python, and Go, an alias index that maps hostnames and service names back to repos, and an `unresolved.json` report of what could not be mapped.

## Install

```
pip install -e ".[dev]"
```

## Usage

```
export GITHUB_TOKEN=...            # read-only: contents + metadata
stackatlas scan --org acme         # clone + scan → ./out/graph.json + unresolved.json
stackatlas scan --local ~/code     # scan existing checkouts, no GitHub
stackatlas schema                  # print graph.json JSON Schema
```

The token is read from `GITHUB_TOKEN`, `GH_TOKEN`, or `gh auth token`. It is never written to disk.

## How edges are found

Detectors read source and config files for outbound references: URL literals, `VITE_*`/`NEXT_PUBLIC_*`/`process.env` lookups and `.env*` values, Spring `@FeignClient` names and `${placeholder}` properties, `os.environ`/`os.getenv`/`os.Getenv`. Each reference is matched against an alias index built from every name a repo answers to: its repo name, `spring.application.name`, Kubernetes `Service` names and `Ingress` hosts, docker-compose service names, OpenAPI `servers[].url`, and `aliases:` from config.

Matches on a declared host or name are `exact`. Matches that needed an env prefix stripped (`dev-orders.acme.com`), a first hostname label, or a variable name turned into a service name (`BILLING_URL` to `billing`) are `heuristic`. Hosts that match nothing become `external:<host>` nodes and are listed in `unresolved.json`, sorted by frequency. That list is the to-do list for `aliases:`.

Env var values whose key looks like a secret (`secret`, `token`, `password`, `key`) are never read. URL userinfo and query strings are stripped from evidence snippets.

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
aliases:
  orders-service: ["orders.acme.com", "orders-legacy"]
ignore_hosts: ["localhost", "127.0.0.1", "*.example.com"]
envs:
  dev: ["dev", "development", "local"]
  stage: ["stage", "staging", "qa"]
  prod: ["prod", "production"]
```

`ignore_hosts` and `envs` replace the defaults when set. `envs` maps the env tag on an edge to the tokens found in file names (`.env.production`, `application-dev.yml`) and hostnames (`dev-orders.acme.com`).

## License

Apache-2.0
