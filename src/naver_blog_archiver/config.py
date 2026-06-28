"""Config: blog id, paths, crawl manners, optional DeepInfra. TOML, pathlib only."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _expand(p: str | os.PathLike[str]) -> Path:
    path = Path(p).expanduser()
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


@dataclass
class CrawlConfig:
    delay_seconds: float = 1.5
    max_retries: int = 4
    count_per_page: int = 30


@dataclass
class DeepInfraConfig:
    api_key_env: str = "DEEPINFRA_API_KEY"
    llm_model: str = "google/gemma-3-27b-it"

    @property
    def api_key_present(self) -> bool:
        return bool(os.environ.get(self.api_key_env))


@dataclass
class Config:
    blog_id: str
    data_dir: Path
    crawl: CrawlConfig = field(default_factory=CrawlConfig)
    deepinfra: DeepInfraConfig = field(default_factory=DeepInfraConfig)

    @property
    def index_dir(self) -> Path:
        return self.data_dir / "index"

    @property
    def posts_dir(self) -> Path:
        return self.data_dir / "posts"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"


def default_config_path() -> Path:
    return REPO_ROOT / "config.toml"


def load_config(path: Path | None = None) -> Config:
    cfg_path = path or default_config_path()
    raw: dict = {}
    if cfg_path.is_file():
        with cfg_path.open("rb") as fh:
            raw = tomllib.load(fh)

    c_raw = raw.get("crawl", {})
    d_raw = raw.get("deepinfra", {})
    return Config(
        blog_id=str(raw.get("blog_id", "YOUR_BLOG_ID")),
        data_dir=_expand(raw.get("data_dir", "data")),
        crawl=CrawlConfig(
            delay_seconds=float(c_raw.get("delay_seconds", 1.5)),
            max_retries=int(c_raw.get("max_retries", 4)),
            count_per_page=int(c_raw.get("count_per_page", 30)),
        ),
        deepinfra=DeepInfraConfig(
            api_key_env=d_raw.get("api_key_env", "DEEPINFRA_API_KEY"),
            llm_model=d_raw.get("llm_model", "google/gemma-3-27b-it"),
        ),
    )
