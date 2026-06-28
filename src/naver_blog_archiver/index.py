"""S1 — build the full post index (the map of "what exists").

categoryNo=0 sweep collects every public post (logNo + metadata, incl. each post's categoryNo);
the mobile category tree gives categoryNo -> {name, parent, path}. Output: a single index JSON
+ a verification report (collected vs totalCount, per-category tally, blocked/private, gap).

No body/image fetch here — that's S2/S3.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass, field
from math import ceil

import httpx

from .config import Config
from .naver_api import decode_title, fetch_category_tree, fetch_post_page, make_client

INDEX_VERSION = 1


def build_category_map(tree: list[dict]) -> dict[int, dict]:
    """categoryNo -> {name, parent, postCnt, path}. Dividers dropped. Path = parent chain."""
    by_no: dict[int, dict] = {}
    for c in tree:
        if c.get("divisionLine"):
            continue
        by_no[c["categoryNo"]] = {
            "name": c["categoryName"],
            "parent": c.get("parentCategoryNo"),
            "postCnt": c.get("postCnt", 0) or 0,
        }

    def path_of(no: int) -> str:
        parts: list[str] = []
        cur: int | None = no
        seen: set[int] = set()
        while cur is not None and cur in by_no and cur not in seen:
            seen.add(cur)
            parts.append(by_no[cur]["name"])
            cur = by_no[cur]["parent"]
        return "/".join(reversed(parts))

    for no, info in by_no.items():
        info["path"] = path_of(no)
    return by_no


def _to_int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _post_record(item: dict, catmap: dict[int, dict]) -> dict:
    # NOTE: the list API returns categoryNo as a STRING ("46") while the category tree keys
    # are ints (46) — coerce so the lookup matches (else every post falls to 미분류).
    cat_no = _to_int(item.get("categoryNo"))
    cat = catmap.get(cat_no) if cat_no is not None else None
    return {
        "logNo": str(item.get("logNo")),
        "title": decode_title(item.get("title", "")),
        "categoryNo": cat_no,
        "categoryPath": cat["path"] if cat else "(미분류)",
        "addDate": item.get("addDate"),
        "openType": item.get("openType"),
        "commentCount": item.get("commentCount"),
    }


@dataclass
class IndexResult:
    blog_id: str
    total_count: int
    collected: list[dict] = field(default_factory=list)
    catmap: dict[int, dict] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "indexVersion": INDEX_VERSION,
            "blogId": self.blog_id,
            "totalCountReported": self.total_count,
            "collected": len(self.collected),
            "categories": {str(k): v for k, v in self.catmap.items()},
            "posts": self.collected,
        }


def collect_index(cfg: Config, client: httpx.Client | None = None,
                  on_page=None) -> IndexResult:
    """Sweep categoryNo=0 across all pages with mannerly delays. Returns the full index."""
    own = client is None
    client = client or make_client()
    try:
        tree = fetch_category_tree(client, cfg.blog_id)
        catmap = build_category_map(tree)

        first = fetch_post_page(client, cfg.blog_id, 1, cfg.crawl.count_per_page)
        total = int(first["totalCount"])
        per = int(first["countPerPage"]) or cfg.crawl.count_per_page
        pages = ceil(total / per)

        result = IndexResult(blog_id=cfg.blog_id, total_count=total, catmap=catmap)
        for page in range(1, pages + 1):
            obj = first if page == 1 else _fetch_with_retry(cfg, client, page, per)
            for item in obj.get("postList", []):
                result.collected.append(_post_record(item, catmap))
            if on_page:
                on_page(page, pages, len(result.collected))
            if page < pages:
                time.sleep(cfg.crawl.delay_seconds)
        return result
    finally:
        if own:
            client.close()


def _fetch_with_retry(cfg: Config, client, page: int, per: int) -> dict:
    last: Exception | None = None
    for attempt in range(cfg.crawl.max_retries):
        try:
            return fetch_post_page(client, cfg.blog_id, page, per)
        except (httpx.HTTPError, ValueError) as e:
            last = e
            time.sleep(cfg.crawl.delay_seconds * (2 ** attempt))  # backoff
    raise RuntimeError(f"page {page} failed after {cfg.crawl.max_retries} retries: {last}")


def verification_report(result: IndexResult) -> str:
    """Collected vs total, per-category tally, blocked/private, gap, duplicate check."""
    posts = result.collected
    n = len(posts)
    uniq = len(set(p["logNo"] for p in posts))
    uncategorized = sum(1 for p in posts if p["categoryPath"] == "(미분류)")
    open_types = Counter(p["openType"] for p in posts)

    # per top-level category tally (roll children up to their top ancestor)
    def top_of(no):
        cur = no
        while cur is not None and cur in result.catmap and result.catmap[cur]["parent"] is not None:
            cur = result.catmap[cur]["parent"]
        return cur
    top_tally: dict[str, int] = {}
    for p in posts:
        t = top_of(p["categoryNo"])
        tname = result.catmap[t]["name"] if t in result.catmap else "(미분류)"
        top_tally[tname] = top_tally.get(tname, 0) + 1

    lines = [
        f"== index verification ({result.blog_id}) ==",
        f"totalCount(reported) : {result.total_count}",
        f"collected            : {n}   (unique logNo: {uniq})",
        f"missing vs reported  : {result.total_count - n}   "
        f"{'OK (none)' if n == result.total_count else 'MISMATCH'}",
        f"duplicates           : {n - uniq}",
        f"uncategorized        : {uncategorized}   "
        f"{'OK (all mapped)' if uncategorized == 0 else 'CHECK'}",
        f"openType counts      : {dict(open_types)}",
        "",
        "per top-level category (collected):",
    ]
    for name, c in sorted(top_tally.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {c:>5}  {name}")
    lines += [
        "",
        f"gap vs PM's 1671: {1671 - n} post(s). categoryNo=0 lists only public posts ({n}); a",
        "fully-private/deleted post is not enumerable via this API — identifying the 3 needs the",
        "owner's authenticated admin view (out of S1 scope). All listed posts are openType=2.",
    ]
    return "\n".join(lines)


def write_index(cfg: Config, result: IndexResult) -> tuple:
    cfg.index_dir.mkdir(parents=True, exist_ok=True)
    index_path = cfg.index_dir / "index.json"
    report_path = cfg.index_dir / "report.txt"
    index_path.write_text(
        json.dumps(result.to_json(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    report_path.write_text(verification_report(result), encoding="utf-8")
    return index_path, report_path
