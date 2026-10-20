from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

VIEWER_DIST = Path(__file__).parent / "viewer_dist"
OUT_FILES = ("graph.json", "unresolved.json")


class ServeError(Exception):
    pass


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, out: Path, **kwargs) -> None:
        self.out = out
        super().__init__(*args, **kwargs)

    def translate_path(self, path: str) -> str:
        name = path.split("?", 1)[0].split("#", 1)[0].lstrip("/")
        if name in OUT_FILES:
            return str(self.out / name)
        return super().translate_path(path)

    def log_message(self, format: str, *args) -> None:
        pass


def make_server(
    out: Path, port: int, dist: Path = VIEWER_DIST, host: str = "127.0.0.1"
) -> ThreadingHTTPServer:
    if not (dist / "index.html").exists():
        raise ServeError(f"viewer build not found at {dist}; run `pnpm -C viewer build`")
    if not (out / "graph.json").exists():
        raise ServeError(f"no graph.json in {out}; run `stackatlas scan` first")
    handler = partial(_Handler, out=out.resolve(), directory=str(dist))
    try:
        return ThreadingHTTPServer((host, port), handler)
    except OSError as exc:
        raise ServeError(f"port {port} is in use; pass --port") from exc
