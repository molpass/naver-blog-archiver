"""naver-blog-archiver — archive a public Naver blog to category-preserving markdown.

Deterministic core (crawl / parse / markdown / images) needs no API key. DeepInfra is an
optional S5 enrichment (tags/summary) only. Personal data (blog id, the archive) lives only
in gitignored config.toml / data/ — the repo is a generic public tool.
"""

__version__ = "0.1.0"
