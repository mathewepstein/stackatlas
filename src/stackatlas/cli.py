import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import httpx
import typer
import yaml

from stackatlas.config import Config, load_config
from stackatlas.github import check_owner
from stackatlas.runtime import (
    MissingCredentials,
    RuntimeData,
    RuntimeSource,
    datadog_keys,
    datadog_source,
    validate_datadog,
)
from stackatlas.scan import build_graph, discover_github, discover_local
from stackatlas.schema import (
    dump_graph,
    dump_unresolved,
    graph_json_schema,
    viewer_json_schema,
)
from stackatlas.serve import ServeError, make_server

app = typer.Typer(no_args_is_help=True, add_completion=False)

DEFAULT_CACHE = Path.home() / ".cache" / "stackatlas"
RUNTIME_SOURCES: dict[str, Callable[[Config], RuntimeSource]] = {
    "datadog": lambda config: datadog_source(config, os.environ),
}


def resolve_token() -> str | None:
    for var in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(var):
            return os.environ[var]
    try:
        result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True)
    except FileNotFoundError:
        return None
    return result.stdout.strip() or None


@app.command()
def scan(
    org: Annotated[str | None, typer.Option(help="GitHub org or user to scan.")] = None,
    local: Annotated[Path | None, typer.Option(help="Directory of existing checkouts.")] = None,
    out: Annotated[Path, typer.Option(help="Output directory.")] = Path("out"),
    config: Annotated[Path | None, typer.Option(help="Path to stackatlas.yml.")] = None,
    cache_dir: Annotated[Path, typer.Option(help="Clone cache.")] = DEFAULT_CACHE,
    workers: Annotated[int, typer.Option(help="Parallel clones.")] = 8,
    runtime: Annotated[
        list[str] | None, typer.Option(help="Runtime source to overlay: datadog.")
    ] = None,
) -> None:
    """Discover and classify every repo, then write graph.json."""
    cfg = load_config(config or Path("stackatlas.yml"))
    if org is None and local is None:
        org = cfg.org
        local = Path(cfg.local).expanduser() if cfg.local else None
    if (org is None) == (local is None):
        raise typer.BadParameter("pass exactly one of --org or --local, or run `stackatlas init`")
    runtime = runtime if runtime is not None else cfg.runtime.sources
    for name in runtime:
        if name not in RUNTIME_SOURCES:
            raise typer.BadParameter(f"unknown runtime source {name!r}")
    traces = _fetch_runtime(runtime, cfg)

    if local is not None:
        repos = discover_local(local, cfg)
        owner = local.resolve().name
    else:
        token = resolve_token()
        if not token:
            typer.echo("No GitHub token: set GITHUB_TOKEN or run `gh auth login`.", err=True)
            raise typer.Exit(1)
        try:
            repos, failed = discover_github(org, token, cfg, cache_dir / org, workers)
        except httpx.HTTPStatusError as exc:
            typer.echo(f"GitHub API error: {exc.response.status_code} {exc.request.url}", err=True)
            raise typer.Exit(1) from exc
        for name in failed:
            typer.echo(f"skipped {name}: clone failed", err=True)
        owner = org

    result = build_graph(owner, repos, cfg, traces)
    graph = result.graph
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.json").write_text(dump_graph(graph))
    (out / "unresolved.json").write_text(dump_unresolved(result.unresolved))
    typer.echo(f"{len(graph.nodes)} nodes, {len(graph.edges)} edges → {out / 'graph.json'}")
    typer.echo(f"{len(result.unresolved)} unresolved → {out / 'unresolved.json'}")
    if traces:
        seen = sum(e.observed is True and e.confidence != "observed" for e in graph.edges)
        unseen = sum(e.observed is False for e in graph.edges)
        only = sum(e.confidence == "observed" for e in graph.edges)
        typer.echo(f"runtime: {seen} observed, {unseen} not seen, {only} runtime-only")


def _fetch_runtime(names: list[str], config: Config) -> list[RuntimeData]:
    data: list[RuntimeData] = []
    for name in names:
        try:
            data.extend(RUNTIME_SOURCES[name](config).fetch())
        except MissingCredentials as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(1) from exc
        except httpx.HTTPStatusError as exc:
            typer.echo(f"{name} API error: {exc.response.status_code}", err=True)
            raise typer.Exit(1) from exc
    return data


@app.command()
def init(
    org: Annotated[str | None, typer.Option(help="GitHub org or user to scan.")] = None,
    local: Annotated[Path | None, typer.Option(help="Directory of existing checkouts.")] = None,
    path: Annotated[Path, typer.Option(help="Config file to write.")] = Path("stackatlas.yml"),
    force: Annotated[bool, typer.Option(help="Overwrite an existing config.")] = False,
) -> None:
    """Check GitHub and runtime access, then write stackatlas.yml."""
    if path.exists() and not force:
        typer.echo(f"{path} already exists; pass --force to overwrite.", err=True)
        raise typer.Exit(1)
    if org is None and local is None:
        org = typer.prompt("GitHub org or user (blank for a local directory)", default="")
        if not org:
            org = None
            local = Path(typer.prompt("Directory of checkouts")).expanduser()
    data: dict[str, Any] = {}
    if org:
        token = resolve_token()
        if not token:
            typer.echo("No GitHub token: set GITHUB_TOKEN or run `gh auth login`.", err=True)
            raise typer.Exit(1)
        try:
            count = check_owner(org, token)
        except httpx.HTTPStatusError as exc:
            typer.echo(f"GitHub API error: {exc.response.status_code} {exc.request.url}", err=True)
            raise typer.Exit(1) from exc
        typer.echo(f"GitHub: {org} ok, {count} repos visible")
        data["org"] = org
    else:
        data["local"] = str(local)
    if datadog_keys(os.environ) is None:
        typer.echo("Datadog: no DD_API_KEY/DD_APP_KEY set, runtime overlay skipped")
    elif not validate_datadog(os.environ):
        typer.echo("Datadog: keys are invalid, runtime overlay skipped")
    elif typer.confirm("Datadog keys found. Overlay runtime traffic on the graph?", default=True):
        data["runtime"] = {"sources": ["datadog"]}
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    typer.echo(f"wrote {path}. Next: `stackatlas scan`, then `stackatlas serve out`.")


@app.command()
def serve(
    out: Annotated[Path, typer.Argument(help="Directory holding graph.json.")] = Path("out"),
    port: Annotated[int, typer.Option(help="Port to listen on.")] = 8000,
) -> None:
    """Serve the viewer for a scanned graph."""
    try:
        server = make_server(out, port)
    except ServeError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"stackatlas viewer at http://127.0.0.1:{server.server_address[1]}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


@app.command()
def schema(
    all_outputs: Annotated[
        bool, typer.Option("--all", help="Include unresolved.json, as the viewer uses.")
    ] = False,
) -> None:
    """Print the graph.json JSON Schema."""
    typer.echo(json.dumps(viewer_json_schema() if all_outputs else graph_json_schema(), indent=2))
