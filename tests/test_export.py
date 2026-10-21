import pytest

from stackatlas.export import ExportError, export_site


@pytest.fixture
def inputs(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>stackatlas</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    out = tmp_path / "out"
    out.mkdir()
    (out / "graph.json").write_text('{"nodes": []}')
    (out / "unresolved.json").write_text("[]")
    (out / "secret.txt").write_text("x")
    return dist, out


def test_export_copies_viewer_and_out_files(inputs, tmp_path):
    dist, out = inputs
    site = tmp_path / "site"
    assert export_site(out, site, dist) == site
    assert (site / "index.html").read_text() == (dist / "index.html").read_text()
    assert (site / "assets" / "app.js").exists()
    assert (site / "graph.json").read_text() == '{"nodes": []}'
    assert (site / "unresolved.json").read_text() == "[]"
    assert not (site / "secret.txt").exists()


def test_export_without_unresolved_file(inputs, tmp_path):
    dist, out = inputs
    (out / "unresolved.json").unlink()
    site = tmp_path / "site"
    export_site(out, site, dist)
    assert (site / "graph.json").exists()
    assert not (site / "unresolved.json").exists()


def test_export_refuses_non_empty_site_without_force(inputs, tmp_path):
    dist, out = inputs
    site = tmp_path / "site"
    site.mkdir()
    (site / "old.txt").write_text("keep")
    with pytest.raises(ExportError, match="--force"):
        export_site(out, site, dist)
    assert (site / "old.txt").exists()
    assert not (site / "index.html").exists()


def test_export_force_replaces_site(inputs, tmp_path):
    dist, out = inputs
    site = tmp_path / "site"
    site.mkdir()
    (site / "old.txt").write_text("stale")
    export_site(out, site, dist, force=True)
    assert not (site / "old.txt").exists()
    assert (site / "index.html").exists()


def test_export_into_empty_existing_dir(inputs, tmp_path):
    dist, out = inputs
    site = tmp_path / "site"
    site.mkdir()
    export_site(out, site, dist)
    assert (site / "graph.json").exists()


def test_export_missing_viewer_build_fails(inputs, tmp_path):
    _, out = inputs
    with pytest.raises(ExportError, match="viewer"):
        export_site(out, tmp_path / "site", tmp_path / "nope")


def test_export_missing_graph_fails(inputs, tmp_path):
    dist, _ = inputs
    with pytest.raises(ExportError, match="stackatlas scan"):
        export_site(tmp_path / "empty", tmp_path / "site", dist)
