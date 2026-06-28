# naver-blog-archiver

Archive a **public** Naver blog — all categories, all pages, with images — into
category-preserving Markdown. A generic tool: your blog id and the archived data live only in
gitignored `config.toml` / `data/`, never in this repo.

> Status: scaffolding (S0). Crawling lands in S1+. See `PROJECT.md` for the staged plan.

## Design

- **Deterministic core, no API key.** Crawl, parse (Naver SmartEditor `se-` components),
  Markdown, and image download are all deterministic. An optional later stage can add
  DeepInfra tags/summaries — never required.
- **Category-preserving.** Each post keeps its Naver category; the archive mirrors it as
  `data/posts/{category}/` + `data/assets/{category}/`.
- **Mannerly.** Polite request delays, retries with backoff, resume-on-interrupt.

## Quick start (dev)

```bash
py -3.11 -m venv .venv
.venv/Scripts/activate          # Windows; source .venv/bin/activate on Linux
pip install -e .[dev]
cp config.example.toml config.toml   # then set blog_id
nba config
nba --help
```

## Layout

```
src/                  crawler / parser / converter core
config.example.toml   generic example (no blog id)
data/   (gitignored)  index/  posts/{category}/  assets/{category}/
DOC/    (gitignored)  research & design notes
config.toml (gitignored)  blog id + local paths
```

## Cross-machine

Code syncs via git. `data/`, `DOC/`, `config.toml` are gitignored, so they move by **USB
only** — pull code on both machines, carry data on USB. No conflicts (code/data paths split).

## Credits

Clean-room implementation — **no third-party code is reused**. Understanding of Naver's
SmartEditor `se-` DOM structure and public API response shapes was informed by the prior work
of [`betarixm/naver-blog.md`](https://github.com/betarixm/naver-blog.md) and
[`hyungyunlim`](https://github.com/hyungyunlim); their code is referenced for structure only,
not copied. This project is independently written and MIT-licensed.

## License

MIT (tool only; contains no blog content).
