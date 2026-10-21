import shutil
from pathlib import Path

from stackatlas.serve import OUT_FILES, VIEWER_DIST, check_inputs


class ExportError(Exception):
    pass


def export_site(out: Path, site: Path, dist: Path = VIEWER_DIST, force: bool = False) -> Path:
    problem = check_inputs(out, dist)
    if problem:
        raise ExportError(problem)
    if site.exists() and any(site.iterdir()):
        if not force:
            raise ExportError(f"{site} is not empty; pass --force to replace it")
        shutil.rmtree(site)
    shutil.copytree(dist, site, dirs_exist_ok=True)
    for name in OUT_FILES:
        if (out / name).exists():
            shutil.copy2(out / name, site / name)
    return site
