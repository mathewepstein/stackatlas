# Contributing

## Setup

```
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

Python 3.11 or newer.

## Checks

```
pytest
ruff check .
```

CI runs both on Python 3.11, 3.12 and 3.13, builds the wheel and checks that it bundles the viewer.

## Tests and fixtures

Write the failing test first. Detector tests use synthetic repos under `tests/fixtures/`; never add real org data. `tests/fixtures/acme` is the fixture org whose scan is snapshotted in `tests/golden/`. When a change alters the graph, run

```
python tests/regen_golden.py
```

then read the diff and update the hand-written expectations in `tests/test_scan.py` to match. `test_regen_golden_reproduces_the_committed_files` fails if the golden files are edited by hand in another layout.

## Adding a detector

Per-file detectors expose `detect_file(repo, rel, path, config) -> list[Reference]` and are listed in `DETECTORS`; per-repo detectors expose `detect_repo(repo, root, config) -> Detection` and are listed in `REPO_DETECTORS`, both in `src/stackatlas/detectors/__init__.py`. A detector emits `Reference`s (`url`, `name` or `var`) with the file, line and a scrubbed snippet; turning references into nodes and edges is `resolve.py`'s job. Drop secret values at capture with `is_secret` and scrub URLs with `scrub` or `clean_url`.

## Viewer

```
pnpm -C viewer install
pnpm -C viewer test
pnpm -C viewer build
```

`build` writes `src/stackatlas/viewer_dist/`, which is committed so that `pipx install` needs no Node. CI rebuilds it and fails if the committed files differ, so commit the rebuilt bundle with the change. After a schema change, regenerate the viewer's types:

```
stackatlas schema --all > viewer/src/schema.json && pnpm -C viewer gen:types
```

## Releasing

Bump `__version__` in `src/stackatlas/__init__.py`, commit, tag `vX.Y.Z` and push the tag. `.github/workflows/release.yml` builds the sdist and wheel, checks that the tag matches the version, publishes to PyPI through trusted publishing (environment `pypi`) and creates a GitHub Release with the files attached.

## Commits

One-line imperative subject, no body.
