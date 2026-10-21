# stackatlas

Map every frontend, service, orchestration, and infra layer in a GitHub org. Every edge links back to the file and line that proves it.

`stackatlas scan` shallow-clones each repo, reads source and config for outbound references (HTTP base URLs, Feign clients, env vars, queue and topic names, JDBC URLs, Terraform gateway integrations, Helm values, CI deploy targets, OpenAPI specs), resolves each reference to the repo that answers to it, and writes `graph.json` plus an `unresolved.json` to-do list. `stackatlas serve` opens the interactive viewer; `stackatlas export` writes it as a static site. A Datadog service map can be overlaid to mark which static edges carry traffic.

The acme fixture org from the test suite is published to https://mathewepstein.github.io/stackatlas/ by `.github/workflows/pages.yml`.

## Install

```
pipx install stackatlas
```

Until the first PyPI release: `pipx install git+https://github.com/mathewepstein/stackatlas`. Python 3.11 or newer. The viewer ships prebuilt inside the package, so Node is not needed.

## Quick start

```
stackatlas init                 # check GitHub (and Datadog) access, write stackatlas.yml
stackatlas scan                 # clone + scan → out/graph.json, out/unresolved.json
stackatlas serve out            # viewer at http://127.0.0.1:8000/
stackatlas export out site      # viewer + data as one directory for static hosting
```

`scan --org acme`, `scan --local ~/code` and `scan --runtime datadog` override what `init` wrote. `stackatlas schema` prints the graph.json JSON Schema.

The GitHub token is read from `GITHUB_TOKEN`, `GH_TOKEN`, or `gh auth token` (read-only: contents + metadata). Datadog keys are read from `DD_API_KEY`/`DD_APP_KEY` (or `DATADOG_API_KEY`/`DATADOG_APP_KEY`) and `DD_SITE`. Credentials are never written to disk.

## GitHub Action

Rebuild the map on a schedule and publish it to GitHub Pages from a repo in your org. The complete workflow is [`examples/map.yml`](examples/map.yml); the core is:

```yaml
- id: stackatlas
  uses: mathewepstein/stackatlas@v0.1.0
  with:
    org: acme
    token: ${{ secrets.STACKATLAS_TOKEN }}
- uses: actions/upload-pages-artifact@v5
  with:
    path: ${{ steps.stackatlas.outputs.site }}
- uses: actions/deploy-pages@v5
```

| Input | Default | Notes |
|---|---|---|
| `org` | required | GitHub org or user to scan |
| `token` | required | A workflow's own `GITHUB_TOKEN` sees only its repo. Use a fine-grained PAT or GitHub App token with `contents: read` and `metadata: read` on every repo in the org. |
| `config` | `stackatlas.yml` | Read from the calling repo |
| `out`, `site` | `out`, `site` | Output directories; `site` is also the action's output |
| `cache` | `true` | Keeps the shallow clones in the calling repo's Actions cache, keyed by org, so unchanged repos are skipped on the next run |
| `datadog-api-key`, `datadog-app-key`, `datadog-site` | unset | When set, runtime traffic is overlaid (`--runtime datadog`) |
| `python-version` | `3.12` | |

Enable Pages once on the repo (Settings → Pages → Source: GitHub Actions). Use `@main` until the first tagged release exists.

## Viewer

Columns run frontend → gateway → orchestration → service → function/workload → datastore → external. Click a node to light its upstream and downstream hops; click an edge for its evidence lines, GitHub permalinks and runtime traces. Solid edges are exact, dashed are heuristic, dotted were only seen at runtime; green was seen in runtime traffic, orange was not. Filters live in the URL hash, so a view can be shared. External, function and bucket nodes start hidden; queues and topics appear when they carry an event edge to a visible node. The Unresolved tab lists what still needs an alias.

## How edges are found

Detectors read source and config files for outbound references and match them against an alias index built from every name a repo answers to: its repo name, `spring.application.name`, Kubernetes `Service` names and `Ingress` hosts, docker-compose service names, OpenAPI titles and `servers[].url`, Terraform-declared hosts, and `aliases:` from config. Matches on a declared host or name are `exact`; matches that needed an env prefix stripped, a first hostname label, or a variable name turned into a service name are `heuristic`. Hosts that match nothing become `external:<host>` nodes and are listed in `unresolved.json`, sorted by frequency. That list is the to-do list for `aliases:`.

[`docs/detectors.md`](docs/detectors.md) describes each detector: HTTP (JS/TS, Java/Kotlin, Python, Go), Terraform, Helm and Kubernetes, CI, datastores, messaging (SQS, SNS, JMS, Kafka, RabbitMQ) and OpenAPI.

Env var values whose key looks like a secret (`secret`, `token`, `password`, `key`) are never read. URL userinfo and query strings are stripped from evidence snippets, including JDBC and Mongo credentials.

## Config

Optional `stackatlas.yml` (a complete example is [`examples/stackatlas.yml`](examples/stackatlas.yml)):

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
apps:
  platform-mono: ["portal-api", "web/portal-ui"]
host_patterns: ["{env}-{name}.acme.internal"]
shared_config_names: ["global", "application"]
ignore_hosts: ["localhost", "127.0.0.1", "*.example.com"]
envs:
  dev: ["dev", "development", "local"]
  stage: ["stage", "staging", "qa"]
  prod: ["prod", "production"]
runtime:
  sources: ["datadog"]
  datadog:
    envs: { prod: production }
    window_days: 7
```

A monorepo becomes one `group` node plus one node per app (`repo:platform-mono/portal-api`, with `parent`). Apps come from gradle `include`, maven `<modules>`, pnpm/npm workspaces, `go.work`, or, when the root has no manifest, any directory up to two levels down that has one. `apps` replaces that detection for a repo. Evidence attributes to the deepest app containing the file; config outside every app serves all of them.

`host_patterns` declares a hostname for every repo and app per env token (`{env}`, `{name}`), for orgs whose ingress hosts follow a convention that is not in git. Matches on them are `exact`.

`ignore_hosts` and `envs` replace the defaults when set. `envs` maps the env tag on an edge to the tokens found in file names (`.env.production`, `application-dev.yml`) and hostnames (`dev-orders.acme.com`).

`runtime.datadog.envs` maps stackatlas env names to Datadog `env` tags; without it the names are used as they are. Edges seen in traffic get `observed: true` and a trace entry; edges between two instrumented services with no traffic get `observed: false`; pairs seen only at runtime become edges with `confidence: observed`.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

Apache-2.0
