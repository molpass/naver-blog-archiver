"""S3.5 — replace broken book-cover thumbnails with title text (clean-room, in-place).

The archive's broken images are almost all retired Naver book-cover hosts (bookimg.naver.com,
dead). Each is an md line of the form:

    [<!-- image download failed: IMG_URL -->](http://book.naver.com/.../book_detail.php?bid=BID)

The book's title (`span.pcol1`) and, when cleanly available, author live in the original
post's book widget. We re-fetch only the affected posts, map bid -> (title, author), and
replace each broken line with `📖 제목 — 저자` (or `📖 제목`). The messy book_detail link is
consumed by the replacement. Title not found => drop the placeholder and log the bid (no
guessing). No re-crawl of the whole blog; no movie widgets exist in this archive.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from .config import Config
from .convert import _clean
from .naver_api import fetch_post_html, make_client

# A broken book-cover line: placeholder wrapped in a link to book_detail?bid=NNN
PLACEHOLDER = re.compile(
    r"\[<!-- image download failed: (?P<img>\S+?) -->\]"
    r"\((?P<link>[^)]*?book_detail[^)]*?bid=(?P<bid>\d+)[^)]*?)\)"
)
_SEP = re.compile(r"\s{2,}|\s*[|·•]\s*")
_DATEISH = re.compile(r"\d{4}[.\-]\d")
# full publish date like 2003.03.10 / 2003-3-10 — byline noise to cut (date + trailing rating)
_DATE_FULL = re.compile(r"\d{4}\s*[.\-]\s*\d{1,2}\s*[.\-]\s*\d{1,2}")


def book_meta_from_html(html: str) -> dict[str, tuple[str, str | None]]:
    """Map bid -> (title, author|None). Title is taken from the pcol1 *inside* each book's
    title-anchor (per-book accurate — multiple books share one outerDL). Author only when
    cleanly delimited (__se_object dd's first <p>); outerDL byline mixes author+publisher
    with no separator, so it stays title-only (no guessing)."""
    soup = BeautifulSoup(html, "html.parser")
    area = (
        soup.select_one("div.post-view")
        or soup.select_one(".se_doc_viewer")
        or soup.select_one("#postViewArea")
        or soup
    )
    out: dict[str, tuple[str, str | None]] = {}
    for anchor in area.select('a[href*="book_detail"]'):
        pcol1 = anchor.select_one("span.pcol1")
        if pcol1 is None:  # the image-anchor has no title; only the title-anchor does
            continue
        m = re.search(r"bid=(\d+)", anchor.get("href", ""))
        if not m:
            continue
        title = _clean(pcol1.get_text(" ", strip=True))
        if title:
            out[m.group(1)] = (title, _author_for(anchor, title))
    return out


def _author_for(title_anchor, title: str) -> str | None:
    """Per-book byline for `📖 제목 — byline`. __se_object uses its dd's first <p> (clean
    author); every other book-widget shape uses the generic date-unit byline. Routing is by
    __se_object membership, NOT the outerDL id (books 2..n sit in nested id-less <dl>)."""
    se = title_anchor.find_parent(class_="__se_object")
    if se is not None:
        dd = se.find("dd")
        p = dd.find("p") if dd else None
        if p is None:
            return None
        cand = _SEP.split(_clean(p.get_text(" ", strip=True)))[0].strip()
        return cand if cand and not _DATEISH.search(cand) and 1 <= len(cand) <= 30 else None
    return _outerdl_byline(title_anchor, title)


def _outerdl_byline(title_anchor, title: str) -> str | None:
    """Per-book unit = smallest ancestor whose text holds a full date. From its text, drop the
    date (+trailing rating); then take the part after '|' if delimited, else strip the title.
    Handles both shapes: 'title | author publisher date' and 'title author publisher date'."""
    unit = None
    node = title_anchor
    for _ in range(6):
        node = node.parent
        if node is None:
            break
        if _DATE_FULL.search(node.get_text(" ", strip=True)):
            unit = node
            break
    if unit is None:
        return None
    text = _clean(unit.get_text(" ", strip=True))
    m = _DATE_FULL.search(text)
    if m:
        text = text[: m.start()]
    byline = text.rsplit("|", 1)[1] if "|" in text else text.replace(title, "", 1)
    byline = re.sub(r"\s+", " ", byline).strip(" .|·•")
    return byline if 2 <= len(byline) <= 40 else None


@dataclass
class FixStats:
    posts_touched: int = 0
    replaced: int = 0
    with_author: int = 0
    title_only: int = 0
    failed_bids: list[str] = field(default_factory=list)


def fix_post_md(cfg: Config, client: httpx.Client, log_no: str, md_path: Path,
                stats: FixStats) -> bool:
    text = md_path.read_text(encoding="utf-8")
    if not PLACEHOLDER.search(text):
        return False
    meta = book_meta_from_html(fetch_post_html(client, cfg.blog_id, log_no))

    def _sub(m: re.Match) -> str:
        tm = meta.get(m.group("bid"))
        if not tm:
            stats.failed_bids.append(m.group("bid"))
            return ""  # drop placeholder; no guessing
        title, author = tm
        stats.replaced += 1
        if author:
            stats.with_author += 1
            return f"📖 {title} — {author}"
        stats.title_only += 1
        return f"📖 {title}"

    new = PLACEHOLDER.sub(_sub, text)
    new = re.sub(r"\n{3,}", "\n\n", new)  # tidy blank lines left by drops
    if new != text:
        md_path.write_text(new, encoding="utf-8")
        return True
    return False


def affected_md(cfg: Config) -> list[Path]:
    """md files that still contain a broken book-cover placeholder."""
    out = []
    for f in cfg.posts_dir.rglob("*.md"):
        if PLACEHOLDER.search(f.read_text(encoding="utf-8")):
            out.append(f)
    return out


def run_fixthumbs(cfg: Config, dry_run: bool = False) -> FixStats:
    files = affected_md(cfg)
    stats = FixStats()
    if dry_run:
        for f in files:
            n = len(PLACEHOLDER.findall(f.read_text(encoding="utf-8")))
            stats.replaced += n
            stats.posts_touched += 1
        return stats

    # backup affected md before editing (under gitignored data/)
    backup = cfg.data_dir / "_backup_s35"
    backup.mkdir(parents=True, exist_ok=True)
    client = make_client()
    try:
        for f in files:
            shutil.copy2(f, backup / f"{f.stem}.md")
            if fix_post_md(cfg, client, f.stem, f, stats):
                stats.posts_touched += 1
    finally:
        client.close()
    return stats
