import threading

import httpx
import pytest

from stackatlas.serve import ServeError, make_server


@pytest.fixture
def site(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>stackatlas</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    out = tmp_path / "out"
    out.mkdir()
    (out / "graph.json").write_text('{"nodes": []}')
    (out / "unresolved.json").write_text("[]")
    return dist, out


def _get(server, path):
    thread = threading.Thread(target=server.handle_request)
    thread.start()
    host, port = server.server_address[:2]
    response = httpx.get(f"http://{host}:{port}{path}")
    thread.join()
    return response


def test_serves_viewer_and_out_files(site):
    dist, out = site
    server = make_server(out, 0, dist)
    try:
        assert "stackatlas" in _get(server, "/").text
        assert _get(server, "/assets/app.js").status_code == 200
        assert _get(server, "/graph.json").json() == {"nodes": []}
        assert _get(server, "/unresolved.json").json() == []
        assert _get(server, "/missing.js").status_code == 404
    finally:
        server.server_close()


def test_out_dir_files_other_than_graph_are_not_served(site):
    dist, out = site
    (out / "secret.txt").write_text("x")
    server = make_server(out, 0, dist)
    try:
        assert _get(server, "/secret.txt").status_code == 404
    finally:
        server.server_close()


def test_port_in_use_fails_cleanly(site):
    dist, out = site
    first = make_server(out, 0, dist)
    try:
        with pytest.raises(ServeError, match="in use"):
            make_server(out, first.server_address[1], dist)
    finally:
        first.server_close()


def test_missing_viewer_build_fails(site, tmp_path):
    _, out = site
    with pytest.raises(ServeError, match="viewer"):
        make_server(out, 0, tmp_path / "nope")


def test_missing_graph_fails(site, tmp_path):
    dist, _ = site
    with pytest.raises(ServeError, match="stackatlas scan"):
        make_server(tmp_path, 0, dist)
