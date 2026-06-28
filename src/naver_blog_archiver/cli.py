"""CLI entry. S0 ships `config`; `index`/`fetch`/`build` are S1+ (declared, stubbed)."""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .config import load_config


def _ensure_utf8_stdio() -> None:
    # Naver content + Korean output; a Windows console defaults to cp949 and would crash.
    for stream in (sys.stdout, sys.stderr):
        rc = getattr(stream, "reconfigure", None)
        if rc is not None:
            try:
                rc(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nba",
        description="naver-blog-archiver — archive a public Naver blog to category-preserving markdown.",
    )
    p.add_argument("-c", "--config", metavar="PATH", default=None,
                   help="path to config.toml (default: <repo>/config.toml)")
    sub = p.add_subparsers(dest="command", metavar="<command>")
    sub.add_parser("version", help="print version")
    sub.add_parser("config", help="show resolved config")
    # S1+ surface (stubs in S0).
    sub.add_parser("index", help="[S1] collect every logNo across all pages (full index JSON)")
    sub.add_parser("fetch", help="[S3] download posts -> markdown + images")
    sub.add_parser("build", help="[S4] export to WordPress (category-preserving)")
    return p


def main(argv: list[str] | None = None) -> int:
    _ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "version":
        print(__version__)
        return 0

    from pathlib import Path
    cfg = load_config(Path(args.config) if args.config else None)

    if args.command == "config":
        print("naver-blog-archiver — resolved config")
        print(f"  blog_id        : {cfg.blog_id}")
        print(f"  data_dir       : {cfg.data_dir}")
        print(f"  crawl.delay    : {cfg.crawl.delay_seconds}s, retries {cfg.crawl.max_retries}, "
              f"perPage {cfg.crawl.count_per_page}")
        print(f"  deepinfra key  : {'PRESENT' if cfg.deepinfra.api_key_present else 'ABSENT'} "
              "(optional, S5)")
        return 0

    if args.command == "index":
        from .index import collect_index, verification_report, write_index
        if cfg.blog_id in ("", "YOUR_BLOG_ID"):
            print("Set blog_id in config.toml first (copy config.example.toml).")
            return 2
        print(f"indexing blog '{cfg.blog_id}' (categoryNo=0 sweep, delay {cfg.crawl.delay_seconds}s)…")

        def _progress(page, pages, collected):
            print(f"  page {page}/{pages}  collected {collected}", flush=True)

        result = collect_index(cfg, on_page=_progress)
        index_path, report_path = write_index(cfg, result)
        print()
        print(verification_report(result))
        print(f"\nindex  -> {index_path}\nreport -> {report_path}")
        return 0

    if args.command in ("fetch", "build"):
        print(f"`{args.command}` is not implemented yet — scheduled for a later slice (see PROJECT.md).")
        return 2

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
