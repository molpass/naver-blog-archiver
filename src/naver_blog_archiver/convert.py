"""S2 — post body -> Markdown (clean-room, two editor eras).

A Naver blog may span two editors:
  - SmartEditor ONE (newer posts): `.se-main-container` + `.se-component` blocks.
  - Legacy editor   (older posts): `#postViewArea div.post-view` plain HTML (<p>/<span>).
The era is detected from the DOM (not the logNo), since some newer logNos are still legacy.

Both are converted here from the *facts* of Naver's DOM — no third-party code. Images are
downloaded locally (Referer set) and referenced by relative path, so the archive is
self-contained. Unsupported components never crash a post: they leave a placeholder comment.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from .config import Config
from .naver_api import (
    download_binary,
    fetch_post_html,
    fetch_summary_content,
    has_summary_fold,
)

_SUPPORTED_SE = {
    "se-text", "se-sectionTitle", "se-quotation", "se-image", "se-imageGroup",
    "se-horizontalLine", "se-code", "se-oglink", "se-table",
}


def _clean(text: str) -> str:
    return html.unescape(text).replace("\xa0", " ").strip()


def sanitize_segment(name: str) -> str:
    """Make a category/segment safe as a folder name."""
    s = _clean(name)
    s = re.sub(r'[<>:"/\\|?*]', "", s).strip().rstrip(".")
    return s or "_"


def detect_era(soup: BeautifulSoup) -> str:
    return "se" if soup.select_one(".se-main-container") else "legacy"


# --------------------------------------------------------------------------- #
# image collection: we gather (url, alt) refs; download happens in the pipeline #
# --------------------------------------------------------------------------- #
@dataclass
class ImageRef:
    url: str
    alt: str = ""


@dataclass
class Converted:
    era: str
    markdown: str
    images: list[ImageRef] = field(default_factory=list)
    components: list[str] = field(default_factory=list)   # se- types seen (se era)
    unsupported: list[str] = field(default_factory=list)


def _img_url(tag: Tag) -> str | None:
    img = tag.select_one("img")
    if img is None:
        return None
    return img.get("data-lazy-src") or img.get("src") or img.get("data-src")


def _se_component_type(c: Tag) -> str:
    for x in c.get("class", []):
        if x.startswith("se-") and x != "se-component" and not x.startswith("se-l-"):
            return x
    return "se-?"


def convert_se(container: Tag, images: list[ImageRef]) -> Converted:
    out: list[str] = []
    seen: list[str] = []
    unsupported: list[str] = []
    for c in container.select(".se-component"):
        t = _se_component_type(c)
        seen.append(t)
        if t == "se-text":
            for p in c.select(".se-text-paragraph"):
                txt = _clean(p.get_text(" ", strip=True))
                out.append(txt if txt else "")
        elif t == "se-sectionTitle":
            out.append(f"## {_clean(c.get_text(' ', strip=True))}")
        elif t == "se-quotation":
            for line in _clean(c.get_text("\n", strip=True)).splitlines():
                out.append(f"> {line}")
        elif t in ("se-image", "se-imageGroup"):
            for sub in (c.select(".se-image") or [c]):
                url = _img_url(sub)
                if not url:
                    continue
                alt = (sub.select_one("img") or {}).get("alt", "") if sub.select_one("img") else ""
                images.append(ImageRef(url, _clean(alt)))
                out.append(f"@@IMG{len(images) - 1}@@")
        elif t == "se-horizontalLine":
            out.append("---")
        elif t == "se-code":
            code = c.get_text("\n", strip=False)
            out.append("```\n" + code.strip("\n") + "\n```")
        elif t == "se-oglink":
            a = c.select_one("a")
            if a and a.get("href"):
                out.append(f"[{_clean(a.get_text(' ', strip=True)) or a['href']}]({a['href']})")
        elif t == "se-table":
            out.append(_table_to_md(c))
        else:
            unsupported.append(t)
            out.append(f"<!-- unsupported: {t} -->")
        out.append("")
    md = "\n".join(out).strip() + "\n"
    return Converted("se", md, images, seen, unsupported)


def _table_to_md(c: Tag) -> str:
    rows = []
    for tr in c.select("tr"):
        cells = [_clean(td.get_text(" ", strip=True)) for td in tr.select("td, th")]
        if cells:
            rows.append("| " + " | ".join(cells) + " |")
    if not rows:
        return "<!-- empty table -->"
    if len(rows) >= 1:
        sep = "| " + " | ".join("---" for _ in rows[0].split("|")[1:-1]) + " |"
        rows.insert(1, sep)
    return "\n".join(rows)


def convert_legacy(area: Tag, images: list[ImageRef]) -> Converted:
    """Legacy plain-HTML body -> md: block text, images, links. Inline styles dropped."""
    out: list[str] = []
    # Top-level blocks: paragraphs/divs. Images and links handled inline.
    for img in area.select("img"):
        url = img.get("data-lazy-src") or img.get("src") or img.get("data-src")
        if url and not url.startswith("data:"):
            images.append(ImageRef(url, _clean(img.get("alt", ""))))
            img.replace_with(f"@@IMG{len(images) - 1}@@")
    for a in area.select("a[href]"):
        txt = _clean(a.get_text(" ", strip=True))
        if txt:
            a.replace_with(f"[{txt}]({a['href']})")
    for block in area.find_all(["p", "div"], recursive=True):
        # leaf-ish blocks only (no nested p/div) to avoid double emit
        if block.find(["p", "div"]):
            continue
        txt = _clean(block.get_text(" ", strip=True))
        if txt:
            out.append(txt)
            out.append("")
    md = "\n".join(out).strip() + "\n"
    return Converted("legacy", md, images, [], [])


def convert_html(post_html: str) -> Converted:
    soup = BeautifulSoup(post_html, "html.parser")
    era = detect_era(soup)
    images: list[ImageRef] = []
    if era == "se":
        return convert_se(soup.select_one(".se-main-container"), images)
    area = soup.select_one("div.post-view") or soup.select_one("#postViewArea")
    if area is None:
        return Converted("unknown", "<!-- no recognizable body container -->\n", [], [], ["no-body"])
    return convert_legacy(area, images)


def convert_summary_html(summary_html: str) -> Converted:
    """Convert the full body returned by SummaryContentFetch (legacy <P> HTML)."""
    soup = BeautifulSoup(summary_html, "html.parser")
    images: list[ImageRef] = []
    area = soup.select_one("div.post-view") or soup.body or soup
    conv = convert_legacy(area, images)
    return Converted("legacy-summary", conv.markdown, conv.images, [], [])


# --------------------------------------------------------------------------- #
# pipeline: fetch -> convert -> download images -> frontmatter -> write        #
# --------------------------------------------------------------------------- #
def _frontmatter(post: dict, source_url: str) -> str:
    fm = [
        "---",
        f'title: "{_clean(post.get("title","")).replace(chr(34), chr(39))}"',
        f'logNo: "{post.get("logNo")}"',
        f'category: "{_clean(post.get("categoryPath",""))}"',
        f'date: "{post.get("addDate","")}"',
        f"source: {source_url}",
        "---",
        "",
    ]
    return "\n".join(fm)


@dataclass
class ConvertReport:
    log_no: str
    era: str
    category: str
    components: dict
    unsupported: list
    images_ok: int
    images_fail: int
    md_bytes: int
    md_path: str


def convert_post(cfg: Config, client: httpx.Client, post: dict) -> ConvertReport:
    from collections import Counter

    log_no = post["logNo"]
    cat_path = sanitize_segment_path(post.get("categoryPath", "_"))
    html_text = fetch_post_html(client, cfg.blog_id, log_no)
    # "더보기" summary post: the PostView body is truncated; fetch the full body separately.
    if has_summary_fold(html_text):
        full = fetch_summary_content(client, cfg.blog_id, log_no)
        conv = convert_summary_html(full) if full else convert_html(html_text)
    else:
        conv = convert_html(html_text)

    # download images
    assets_dir = cfg.assets_dir / cat_path
    posts_dir = cfg.posts_dir / cat_path
    assets_dir.mkdir(parents=True, exist_ok=True)
    posts_dir.mkdir(parents=True, exist_ok=True)

    md = conv.markdown
    ok = fail = 0
    for i, ref in enumerate(conv.images):
        ext = _ext_of(ref.url)
        fname = f"{log_no}_{i}{ext}"
        dest = assets_dir / fname
        try:
            data = download_binary(client, ref.url, cfg.blog_id)
            dest.write_bytes(data)
            rel = _relpath(posts_dir, dest)
            md = md.replace(f"@@IMG{i}@@", f"![{ref.alt}]({rel})")
            ok += 1
        except (httpx.HTTPError, OSError):
            md = md.replace(f"@@IMG{i}@@", f"<!-- image download failed: {ref.url} -->")
            fail += 1

    source_url = f"https://blog.naver.com/{cfg.blog_id}/{log_no}"
    full = _frontmatter(post, source_url) + md
    md_path = posts_dir / f"{log_no}.md"
    md_path.write_text(full, encoding="utf-8")

    return ConvertReport(
        log_no=log_no, era=conv.era, category=post.get("categoryPath", ""),
        components=dict(Counter(conv.components)), unsupported=conv.unsupported,
        images_ok=ok, images_fail=fail, md_bytes=len(full.encode("utf-8")),
        md_path=str(md_path),
    )


def sanitize_segment_path(path: str) -> str:
    return "/".join(sanitize_segment(seg) for seg in path.split("/") if seg)


def _ext_of(url: str) -> str:
    name = urlparse(url).path.rsplit("/", 1)[-1]
    ext = Path(name).suffix.lower()
    return ext if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp") else ".jpg"


def _relpath(from_dir: Path, to_file: Path) -> str:
    import os
    return os.path.relpath(to_file, from_dir).replace("\\", "/")
