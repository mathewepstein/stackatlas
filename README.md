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

Terraform stacks (any directory with `*.tf`, except `modules/`) add infrastructure nodes and edges: API gateways (`gateway:<stack>/<name>`, with their custom domains as aliases and route keys as endpoints) and their integrations (`integration_uri`, `overwrite:header.Host`, `server_name_to_verify`, module arguments such as `backend_fqdn`); Lambda functions (`function:`) with their environment variables and their zipped source attributed to the function; RDS, ElastiCache and DynamoDB (`datastore:<engine>/<name>`); SQS, SNS and S3 (`queue:`, `topic:`, `bucket:`); and SSM parameters named `/config/<app>_<env>/<key>`, which count as that app's config (shared names in `shared_config_names` serve every app). Locals and variable defaults are interpolated; anything else becomes `*`, and a host such as `*-orders.*` still resolves by its literal label. Each stack's env comes from its path (`cd-prod/.../prod_wapi`), and the same resource across env stacks is one node with env tags. The declaring repo gets a `deploy` edge to every node.

Helm charts and raw Kubernetes manifests in repos that have no app manifest of their own (chart and ops repos) add `workload:<chart>/<name>` nodes for Deployments, StatefulSets, DaemonSets, Jobs and CronJobs. Templates are rendered line for line from `values.yaml` and `values-<env>.yaml` (`.Values`, `include "x.fullname"`, `.Chart.Name`, `range` over the first item, `default`, `quote`; anything else becomes `"*"`), so Ingress hosts and Service names become the workload's aliases and container env values become its references, with one node per workload across env value files. Terraform `helm_release` and `kubernetes_manifest` resources declare workloads too.

CI definitions (GitHub Actions, CodeBuild buildspecs, Jenkinsfile, GitLab CI, CircleCI, Bitbucket, Azure Pipelines, Cloud Build) are recorded on the node as `ci: [{system, path, registries}]`, with registry hosts (ECR, CodeArtifact, GitHub Packages, npm, ghcr, ...) they publish to. Terraform `aws_codebuild_project` resources attach to the repo named in their source location, with `repo` set to the declaring repo. Literal `s3://bucket` and `--function-name` targets in CI commands become `deploy` edges.

Datastore references come from JDBC, Redis, Mongo, Postgres and MySQL URLs anywhere in source or config, and from config keys that name a datastore (`spring.redis.host`, `DB_HOST`, `spring.data.mongodb.uri`). They make `datastore` edges to a terraform datastore node when the host or its first label matches one, otherwise to a `datastore:<engine>/<host>` node with env prefixes stripped so dev, stage and prod collapse into one node with env tags.

Env var values whose key looks like a secret (`secret`, `token`, `password`, `key`) are never read. URL userinfo and query strings are stripped from evidence snippets, including JDBC and Mongo credentials.

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
apps:
  platform-mono: ["portal-api", "web/portal-ui"]
host_patterns: ["{env}-{name}.acme.internal"]
shared_config_names: ["global", "application"]
ignore_hosts: ["localhost", "127.0.0.1", "*.example.com"]
envs:
  dev: ["dev", "development", "local"]
  stage: ["stage", "staging", "qa"]
  prod: ["prod", "production"]
```

A monorepo becomes one `group` node plus one node per app (`repo:platform-mono/portal-api`, with `parent`). Apps come from gradle `include`, maven `<modules>`, pnpm/npm workspaces, `go.work`, or, when the root has no manifest, any directory up to two levels down that has one. `apps` replaces that detection for a repo. Evidence attributes to the deepest app containing the file; config outside every app serves all of them.

`host_patterns` declares a hostname for every repo and app per env token (`{env}`, `{name}`), for orgs whose ingress hosts follow a convention that is not in git. Matches on them are `exact`.

`ignore_hosts` and `envs` replace the defaults when set. `envs` maps the env tag on an edge to the tokens found in file names (`.env.production`, `application-dev.yml`) and hostnames (`dev-orders.acme.com`).

## License

Apache-2.0
