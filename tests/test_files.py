from pathlib import Path

import pytest

from stackatlas.files import write_atomic


def test_write_atomic_replaces_content_and_leaves_no_temp_file(tmp_path):
    target = tmp_path / "graph.json"
    target.write_text("old")
    write_atomic(target, "new")
    assert target.read_text() == "new"
    assert [p.name for p in tmp_path.iterdir()] == ["graph.json"]


def test_write_atomic_keeps_old_content_when_the_write_fails(tmp_path, monkeypatch):
    target = tmp_path / "graph.json"
    target.write_text("old")
    real = Path.write_text

    def half_then_fail(self, text, *args, **kwargs):
        real(self, text[: len(text) // 2], *args, **kwargs)
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", half_then_fail)
    with pytest.raises(OSError):
        write_atomic(target, "new content")
    assert target.read_text() == "old"
