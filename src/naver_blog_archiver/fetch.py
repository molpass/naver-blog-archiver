"""S3 — full archive crawl with resume.

Sweeps the S1 index, converting every post to md + local images via the S2/S2.5 pipeline.
Resumable: a progress manifest records per-logNo status so a re-run continues only the
pending/failed posts (already-converted posts are skipped, not re-downloaded). Mannerly:
a conservative delay between posts, longer backoff after a failure.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from .config import Config
from .convert import convert_post
from .naver_api import make_client

PROGRESS_NAME = "progress.json"
_MIN_VALID_BYTES = 60  # an md smaller than this is treated as empty/failed


def progress_path(cfg: Config) -> Path:
    return cfg.index_dir / PROGRESS_NAME


def load_progress(cfg: Config) -> dict:
    p = progress_path(cfg)
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
    return {}


def save_progress(cfg: Config, prog: dict) -> None:
    cfg.index_dir.mkdir(parents=True, exist_ok=True)
    tmp = progress_path(cfg).with_suffix(".json.tmp")
    tmp.write_text(json.dumps(prog, ensure_ascii=False), encoding="utf-8")
    tmp.replace(progress_path(cfg))  # atomic-ish rename


def load_index_posts(cfg: Config) -> list[dict]:
    data = json.loads((cfg.index_dir / "index.json").read_text(encoding="utf-8"))
    return data["posts"]


def _is_done(cfg: Config, log_no: str, prog: dict) -> bool:
    rec = prog.get(log_no)
    if not rec or rec.get("status") != "done":
        return False
    md = rec.get("md_path")
    return bool(md) and Path(md).is_file() and Path(md).stat().st_size >= _MIN_VALID_BYTES


def run_fetch(cfg: Config, limit: int | None = None, on_progress=None) -> dict:
    posts = load_index_posts(cfg)
    prog = load_progress(cfg)
    client = make_client()
    done = skipped = failed = 0
    processed = 0
    try:
        for i, post in enumerate(posts):
            log_no = post["logNo"]
            if _is_done(cfg, log_no, prog):
                skipped += 1
                continue
            if limit is not None and processed >= limit:
                break
            processed += 1
            try:
                rep = convert_post(cfg, client, post)
                prog[log_no] = {
                    "status": "done",
                    "era": rep.era,
                    "category": post.get("categoryPath", ""),
                    "images_ok": rep.images_ok,
                    "images_fail": rep.images_fail,
                    "unsupported": rep.unsupported,
                    "md_bytes": rep.md_bytes,
                    "md_path": rep.md_path,
                }
                done += 1
            except Exception as e:  # never let one post stop the crawl
                prog[log_no] = {"status": "failed", "error": str(e)[:200],
                                "category": post.get("categoryPath", "")}
                failed += 1
                time.sleep(cfg.crawl.delay_seconds * 2)  # longer wait after a failure
            save_progress(cfg, prog)
            if on_progress:
                on_progress(i + 1, len(posts), done, failed, log_no)
            time.sleep(cfg.crawl.delay_seconds)
    finally:
        client.close()
    return {"done": done, "skipped": skipped, "failed": failed, "total": len(posts)}


def verify_archive(cfg: Config) -> str:
    """Compare the archive against the index: missing, failed, per-category, stats."""
    posts = load_index_posts(cfg)
    prog = load_progress(cfg)
    index_logs = {p["logNo"] for p in posts}

    done = {ln for ln in index_logs if _is_done(cfg, ln, prog)}
    failed = sorted(ln for ln, r in prog.items() if r.get("status") == "failed")
    missing = sorted(index_logs - done - set(failed))

    # per top-level category, from the index
    cats = json.loads((cfg.index_dir / "index.json").read_text(encoding="utf-8"))["categories"]

    def top_name(cat_no):
        cur = cat_no
        while cur is not None and str(cur) in cats and cats[str(cur)]["parent"] is not None:
            cur = cats[str(cur)]["parent"]
        return cats[str(cur)]["name"] if str(cur) in cats else "(미분류)"

    idx_tally: Counter = Counter()
    got_tally: Counter = Counter()
    for p in posts:
        tn = top_name(p["categoryNo"])
        idx_tally[tn] += 1
        if p["logNo"] in done:
            got_tally[tn] += 1

    summary_posts = sum(1 for r in prog.values() if r.get("era") == "legacy-summary")
    img_ok = sum(r.get("images_ok", 0) for r in prog.values() if r.get("status") == "done")
    img_fail = sum(r.get("images_fail", 0) for r in prog.values() if r.get("status") == "done")
    unsupported: Counter = Counter()
    for r in prog.values():
        for u in r.get("unsupported", []):
            unsupported[u] += 1
    era_tally = Counter(r.get("era") for r in prog.values() if r.get("status") == "done")

    lines = [
        "== fetch verification ==",
        f"index total     : {len(index_logs)}",
        f"converted (done): {len(done)}",
        f"failed          : {len(failed)}",
        f"missing         : {len(missing)}   {'OK (none)' if not missing else missing[:20]}",
        "",
        "per top-level category  (got / index):",
    ]
    for tn in sorted(idx_tally, key=lambda k: -idx_tally[k]):
        mark = "OK" if got_tally[tn] == idx_tally[tn] else "MISMATCH"
        lines.append(f"  {got_tally[tn]:>5} / {idx_tally[tn]:<5}  {tn}   {mark}")
    lines += [
        "",
        f"era breakdown   : {dict(era_tally)}",
        f"더보기(summary) : {summary_posts} posts (full body fetched)",
        f"images          : {img_ok} ok, {img_fail} failed",
        f"unsupported se- : {dict(unsupported) or '(none)'}",
    ]
    if failed:
        lines += ["", f"failed logNos ({len(failed)}): {failed[:30]}"]
    return "\n".join(lines)


def write_report(cfg: Config) -> Path:
    report = cfg.index_dir / "fetch-report.txt"
    report.write_text(verify_archive(cfg), encoding="utf-8")
    return report
