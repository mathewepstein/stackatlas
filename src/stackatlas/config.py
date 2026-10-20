from fnmatch import fnmatch
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from stackatlas.schema import Kind

DEFAULT_IGNORE_HOSTS = [
    "localhost", "127.0.0.1", "0.0.0.0", "*.local",
    "example.com", "*.example.com", "example.org", "*.example.org",
    "www.w3.org", "json-schema.org", "schemas.xmlsoap.org", "schema.org", "*.schema.org",
    "github.com", "www.github.com", "*.wikipedia.org",
    "twitter.com", "www.twitter.com", "x.com", "facebook.com", "www.facebook.com",
    "linkedin.com", "www.linkedin.com", "instagram.com", "www.instagram.com",
    "youtube.com", "www.youtube.com", "youtu.be", "vimeo.com", "player.vimeo.com",
]
DEFAULT_ENVS = {
    "dev": ["dev", "development", "develop", "local"],
    "stage": ["stage", "staging", "qa", "uat", "preprod"],
    "prod": ["prod", "production", "live"],
}


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
    aliases: dict[str, list[str]] = Field(default_factory=dict)
    apps: dict[str, list[str]] = Field(default_factory=dict)
    host_patterns: list[str] = Field(default_factory=list)
    shared_config_names: list[str] = Field(default_factory=lambda: ["global", "application"])
    ignore_hosts: list[str] = Field(default_factory=lambda: list(DEFAULT_IGNORE_HOSTS))
    envs: dict[str, list[str]] = Field(
        default_factory=lambda: {k: list(v) for k, v in DEFAULT_ENVS.items()}
    )

    def ignores_host(self, host: str) -> bool:
        return any(fnmatch(host, p) for p in self.ignore_hosts)

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
