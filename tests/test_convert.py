"""S2 unit tests — both era parsers, image refs, unsupported graceful, sanitization (offline)."""
from __future__ import annotations

from naver_blog_archiver.convert import (
    convert_html,
    detect_era,
    sanitize_segment,
    sanitize_segment_path,
)

_SE_HTML = """
<div class="se-main-container">
  <div class="se-component se-sectionTitle se-l-default"><span class="se-text-paragraph">제목</span></div>
  <div class="se-component se-text se-l-default"><p class="se-text-paragraph">첫 문단</p>
     <p class="se-text-paragraph">둘째 문단</p></div>
  <div class="se-component se-image se-l-default"><img class="se-image-resource"
     src="https://x.naver.net/a.jpg" alt="사진"></div>
  <div class="se-component se-horizontalLine se-l-default"></div>
  <div class="se-component se-sticker se-l-default">sticker</div>
</div>
"""

_LEGACY_HTML = """
<div id="postViewArea"><div class="post-view">
  <p class="0"><span style="font-size:11pt">레거시 문단 하나</span></p>
  <p><a href="https://example.com">링크</a></p>
  <p><img src="https://x.naver.net/old.jpg" alt="old"></p>
</div></div>
"""


def test_detect_and_convert_se() -> None:
    from bs4 import BeautifulSoup
    assert detect_era(BeautifulSoup(_SE_HTML, "html.parser")) == "se"
    c = convert_html(_SE_HTML)
    assert c.era == "se"
    assert "## 제목" in c.markdown
    assert "첫 문단" in c.markdown and "둘째 문단" in c.markdown
    assert "---" in c.markdown
    assert len(c.images) == 1 and c.images[0].url.endswith("a.jpg")
    assert "@@IMG0@@" in c.markdown          # placeholder before download
    # unsupported component is graceful (placeholder comment, no crash)
    assert "se-sticker" in c.unsupported
    assert "<!-- unsupported: se-sticker -->" in c.markdown


def test_convert_legacy() -> None:
    from bs4 import BeautifulSoup
    assert detect_era(BeautifulSoup(_LEGACY_HTML, "html.parser")) == "legacy"
    c = convert_html(_LEGACY_HTML)
    assert c.era == "legacy"
    assert "레거시 문단 하나" in c.markdown
    assert "[링크](https://example.com)" in c.markdown
    assert len(c.images) == 1 and "@@IMG0@@" in c.markdown


def test_sanitize() -> None:
    assert sanitize_segment("자작 글") == "자작 글"
    assert sanitize_segment("a/b:c*?") == "abc"
    assert sanitize_segment_path("마음나누기/단상") == "마음나누기/단상"


def test_unknown_body_is_graceful() -> None:
    c = convert_html("<html><body><p>no container</p></body></html>")
    assert c.era == "unknown"
    assert "no recognizable body" in c.markdown
