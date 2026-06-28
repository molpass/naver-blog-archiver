"""Naver public-blog API access (clean-room).

Written from scratch against the *facts* of Naver's public endpoints (URLs + response
shapes) — no third-party source is reused. Two read-only endpoints power S1's index:

  - mobile category list : GET m.blog.naver.com/api/blogs/{id}/category-list  (JSON)
  - post title list      : GET blog.naver.com/PostTitleListAsync.naver        (JSON-ish*)

* PostTitleListAsync appends a `pagingHtml` field whose raw HTML breaks strict JSON; we slice
  it off before parsing. Titles arrive percent-encoded and are decoded here.
"""
from __future__ import annotations

import json
from urllib.parse import unquote

import httpx

DESKTOP = "https://blog.naver.com"
MOBILE = "https://m.blog.naver.com"

_UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
_UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"
)


def make_client(timeout: float = 20.0) -> httpx.Client:
    return httpx.Client(timeout=timeout, follow_redirects=True)


def fetch_category_tree(client: httpx.Client, blog_id: str) -> list[dict]:
    """Return the raw mylogCategoryList (entries incl. divider lines)."""
    r = client.get(
        f"{MOBILE}/api/blogs/{blog_id}/category-list",
        headers={"User-Agent": _UA_MOBILE, "Referer": f"{MOBILE}/{blog_id}"},
    )
    r.raise_for_status()
    return r.json()["result"]["mylogCategoryList"]


def parse_post_title_list(raw: str) -> dict:
    """Parse a PostTitleListAsync body into {postList, countPerPage, totalCount}.

    Slices the trailing `,"pagingHtml":...` (unescaped HTML) that breaks strict JSON.
    """
    head = raw.split(',"pagingHtml"', 1)[0]
    if not head.rstrip().endswith("}"):
        head += "}"
    return json.loads(head)


def fetch_post_page(
    client: httpx.Client,
    blog_id: str,
    current_page: int = 1,
    count_per_page: int = 30,
    category_no: int = 0,
) -> dict:
    """Fetch one page of the post title list. categoryNo=0 = all posts."""
    r = client.get(
        f"{DESKTOP}/PostTitleListAsync.naver",
        params={
            "blogId": blog_id,
            "currentPage": current_page,
            "categoryNo": category_no,
            "countPerPage": count_per_page,
        },
        headers={"User-Agent": _UA_DESKTOP, "Referer": f"{DESKTOP}/{blog_id}"},
    )
    r.raise_for_status()
    return parse_post_title_list(r.text)


def decode_title(raw_title: str) -> str:
    """Naver returns titles percent-encoded with '+' for spaces."""
    return unquote(raw_title.replace("+", " "))
