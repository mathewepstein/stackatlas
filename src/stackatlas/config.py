from fnmatch import fnmatch
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from stackatlas.schema import Kind


class Override(BaseModel):
    kind: Kind | None = None
    layer: str | None = None


class Config(BaseModel):
    include: list[str] = Field(default_factory=lambda: ["*"])
    exclude: list[str] = Field(default_factory=list)
    skip_archived: bool = True
    skip_forks: bool = True
    layers: dict[str, list[str]] = Field(default_factory=dict)
    overrides: dict[str, Override] = Field(default_factory=dict)

    def includes(self, name: str) -> bool:
        return any(fnmatch(name, p) for p in self.include) and not any(
            fnmatch(name, p) for p in self.exclude
        )

    def layer_for(self, name: str, kind: Kind) -> str:
        for layer, patterns in self.layers.items():
            if any(fnmatch(name, p) for p in patterns):
                return layer
        return kind


def load_config(path: Path | None) -> Config:
    if path is None or not path.exists():
        return Config()
    return Config.model_validate(yaml.safe_load(path.read_text()) or {})
