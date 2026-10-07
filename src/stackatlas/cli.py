import json
import os
import subprocess
from pathlib import Path
from typing import Annotated

import httpx
import typer

from stackatlas.config import load_config
from stackatlas.scan import build_graph, discover_github, discover_local
from stackatlas.schema import dump_graph, graph_json_schema

app = typer.Typer(no_args_is_help=True, add_completion=False)

DEFAULT_CACHE = Path.home() / ".cache" / "stackatlas"


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
) -> None:
    """Discover and classify every repo, then write graph.json."""
    if (org is None) == (local is None):
        raise typer.BadParameter("pass exactly one of --org or --local")
    cfg = load_config(config or Path("stackatlas.yml"))

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

    graph = build_graph(owner, repos, cfg)
    out.mkdir(parents=True, exist_ok=True)
    (out / "graph.json").write_text(dump_graph(graph))
    typer.echo(f"{len(graph.nodes)} nodes → {out / 'graph.json'}")


@app.command()
def schema() -> None:
    """Print the graph.json JSON Schema."""
    typer.echo(json.dumps(graph_json_schema(), indent=2))
