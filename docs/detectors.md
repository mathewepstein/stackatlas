# How edges are found

Every detector emits references: a URL, a name, or a variable, with the repo, file, line and a scrubbed snippet. The resolver matches each reference against an alias index built from every name a repo answers to: its repo name and variants (`customer-microservice` → `customer`, `customer-service`, `customer-svc`, `customer-ms`), `spring.application.name`, Kubernetes `Service` names and `Ingress` hosts, docker-compose service names, OpenAPI titles and `servers[].url`, Terraform-declared hosts, and `aliases:` from config.

Matches on a declared host or name are `exact`. Matches that needed an env prefix stripped (`dev-orders.acme.com`), a first hostname label, or a variable name turned into a service name (`BILLING_URL` to `billing`) are `heuristic`. Hosts that match nothing become `external:<host>` nodes and are listed in `unresolved.json`, sorted by frequency. That list is the to-do list for `aliases:`.

## HTTP

JS/TS, Java/Kotlin, Python and Go sources and their config files: URL literals, `VITE_*`/`NEXT_PUBLIC_*`/`process.env` lookups and `.env*` values, Spring `@FeignClient` names and URLs, `${placeholder}` properties in `application*.yml|properties` (including `---` profile documents and `${key:default}` defaults), `os.environ`/`os.getenv`/`os.Getenv`. A variable reference is followed through same-node config, then repo-root config, then the shared config store, up to three hops. A Feign `name` that is a repo name, declared name or config alias of the same node the URL resolved to makes the edge `exact`.

## Terraform

Any directory with `*.tf` files, except `modules/`, is a stack. Locals and variable defaults are interpolated; anything else becomes `*`, and a host such as `*-orders.*` still resolves by its literal label. Each stack's env comes from its path, and the same resource across env stacks is one node with env tags.

- API gateways: `gateway:<stack>/<name>` from `aws_apigatewayv2_api` and `aws_api_gateway_rest_api`, with their custom domains as aliases and route keys as endpoints. Integrations give `gateway → service` edges from `integration_uri`, `overwrite:header.Host`, `server_name_to_verify`, or module arguments such as `backend_fqdn`.
- Lambda: `function:<stack>/<name>` from `aws_lambda_function`, with its environment variables and the zipped source (`data.archive_file`) attributed to the function, so references inside the Lambda's own code become the function's edges.
- Datastores: `datastore:<engine>/<name>` from RDS, ElastiCache and DynamoDB. SQS, SNS and S3 become `queue:`, `topic:` and `bucket:` nodes.
- Config store: SSM parameters named `/config/<app>_<env>/<key>` count as that app's config; names in `shared_config_names` serve every app.
- Messaging wiring: `aws_lambda_event_source_mapping` gives `queue → function`; `aws_sns_topic_subscription` gives `topic → queue` or `topic → function`. References to `aws_sqs_queue.<x>.url|arn|name` and `aws_sns_topic.<x>.arn|name` (and the `data.` forms) resolve to the resource's name.
- The declaring repo gets a `deploy` edge to every node it declares.

## Helm and Kubernetes

Charts and raw manifests in repos that have no app manifest of their own (chart and ops repos) add `workload:<chart>/<name>` nodes for Deployments, StatefulSets, DaemonSets, Jobs and CronJobs. Templates are rendered line for line from `values.yaml` and `values-<env>.yaml` (`.Values`, `include "x.fullname"`, `.Chart.Name`, `range` over the first item, `default`, `quote`; anything else becomes `"*"`), so Ingress hosts and Service names become the workload's aliases and container env values become its references, with one node per workload across env value files. Terraform `helm_release` and `kubernetes_manifest` resources declare workloads too.

## CI

GitHub Actions, CodeBuild buildspecs, Jenkinsfile, GitLab CI, CircleCI, Bitbucket Pipelines, Azure Pipelines and Cloud Build definitions are recorded on the node as `ci: [{system, path, registries}]`, with the registry hosts (ECR, CodeArtifact, GitHub Packages, npm, ghcr, ...) they publish to. Terraform `aws_codebuild_project` resources attach to the repo named in their source location, with `repo` set to the declaring repo. Literal `s3://bucket` and `--function-name` targets in CI commands become `deploy` edges.

## Datastores

JDBC, Redis, Mongo, Postgres and MySQL URLs anywhere in source or config, and config keys that name a datastore (`spring.redis.host`, `DB_HOST`, `spring.data.mongodb.uri`), make `datastore` edges. The target is the Terraform datastore node when the host or its first label matches one, otherwise a `datastore:<engine>/<host>` node with env prefixes stripped, so dev, stage and prod collapse into one node with env tags.

## Messaging

Code references carry a role, `produce` or `consume`, and resolve through the same variable chain as HTTP references.

- Java consumers: `@JmsListener(destination)`, `@SqsListener(value | queueNames)`, `@KafkaListener(topics)`, `@RabbitListener(queues)`. Java producers: `JmsTemplate`/`KafkaTemplate`/`RabbitTemplate` `send`, `convertAndSend` and `sendDefault`, and AWS SDK builders `.queueUrl(...)` / `.topicArn(...)`, whose role comes from `sendMessage`/`publish` (produce) or `receiveMessage` (consume) in the enclosing statement. A field argument is followed to its `@Value("${key}")`.
- Python boto3: `send_message`, `send_message_batch`, `publish` and `publish_batch` produce; `receive_message` consumes. `QueueUrl=` / `TopicArn=` may be a literal, an `os.environ` lookup, or a module-level variable holding either.
- Config: `.env*` and Spring config values under keys containing `sqs`, `sns`, `queue`, `topic`, `jms`, `kafka`, `rabbit`, `amqp` or `pubsub`, and any value that is an SQS/SNS ARN or an SQS URL.

The queue or topic name is taken from the ARN (`arn:aws:sqs:<region>:<account>:<name>`), the SQS URL, or the plain value, env-stripped, and looked up among Terraform-declared `queue:`/`topic:` nodes. If nothing matches, an inferred `queue:<name>` or `topic:<name>` node is created. Edges have type `event`: a producer gives `service → queue`, a consumer gives `queue → service`, so a flow reads producer → queue → consumer with evidence on both hops. Config keys with queue words but no code use make no edge.

## OpenAPI

A spec is any `.yaml`, `.yml` or `.json` file whose top-level `openapi` or `swagger` key holds a version and that has a `paths` map; file names do not matter. Its `METHOD /path` endpoints attach to the owner node: the spec's own repo or sub-app, unless `info.title` or a `servers[].url` (or swagger `host` + `basePath`) resolves to another node, which then owns the endpoints. A spec with no owner in an infra repo, a repo of unknown kind, or a monorepo root is listed in `unresolved.json` as a `name`. Self-owned specs add their title and servers to the alias index.

A generator `inputSpec` in `build.gradle`, `build.gradle.kts`, `pom.xml` or `openapitools.json` that points at a spec in the repo makes an `http` edge from the building repo to the spec's owner, with the build-file line as evidence. A spec consumed by the repo's own generator is never treated as the repo's own API.

## Secret safety

Env var values whose key looks like a secret (`secret`, `token`, `password`, `key`) are never read. SSM values under such keys are dropped at capture and `aws_secretsmanager_*` resources are never read. URL userinfo and query strings are stripped from evidence snippets, including JDBC and Mongo credentials.
