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


def test_se_doc_viewer_variant_is_recognized() -> None:
    # SmartEditor 2.0 variant: id=post-view{n}, class se_doc_viewer (no .post-view class)
    html = ('<div id="post-view123" class="se_doc_viewer">'
            '<p>SE2 본문 문단입니다</p></div>')
    c = convert_html(html)
    assert c.era == "legacy"
    assert "SE2 본문 문단입니다" in c.markdown


def test_summary_fold_detection_and_cdata() -> None:
    from naver_blog_archiver.naver_api import _SUMMARY_CDATA, has_summary_fold
    assert has_summary_fold("<a class='con_link _getSummaryContent _param(1|x)'>더보기</a>")
    assert not has_summary_fold("<div class='post-view'><p>short</p></div>")
    xml = ("<post><logNo>1</logNo><summaryContent><![CDATA["
           "<div class='post-view'><P>접힌 전체 본문</P></div>]]></summaryContent></post>")
    inner = "".join(_SUMMARY_CDATA.findall(xml))
    assert "접힌 전체 본문" in inner


def test_convert_summary_html() -> None:
    from naver_blog_archiver.convert import convert_summary_html
    full = "<div class='post-view'><P>접힌 본문 첫 문단</P><P>둘째 문단</P></div>"
    c = convert_summary_html(full)
    assert c.era == "legacy-summary"
    assert "접힌 본문 첫 문단" in c.markdown and "둘째 문단" in c.markdown
