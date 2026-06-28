"""S3.5 unit tests — placeholder regex, widget meta extraction, conservative author (offline)."""
from __future__ import annotations

from naver_blog_archiver.thumbfix import PLACEHOLDER, book_meta_from_html

_MD_LINE = ("[<!-- image download failed: http://bookimg.naver.com/x.jpg -->]"
            "(http://book.naver.com/bookdb/book_detail.php?bid=121273)")

# __se_object widget: title in span.pcol1, author in dd's first <p>
_HTML_SE = """
<div class="post-view"><div class="__se_object">
  <a class="con_link" href="http://book.naver.com/bookdb/book_detail.php?bid=555">
    <img src="http://bookimg.naver.com/x.jpg"><span class="pcol1">반지의 제왕 세트</span></a>
  <dd><p>J.R.R. 톨킨<span>|</span>씨앗을뿌리는사람</p><p>2003.03.10</p></dd>
</div></div>
"""

# outerDL widget: dd wraps the title (no clean author) -> title-only
_HTML_DL = """
<div class="post-view"><dl id="outerDL">
  <dt><a href="http://book.naver.com/bookdb/book_detail.php?bid=121273">
    <img src="http://bookimg.naver.com/y.jpg"></a></dt>
  <dd><h4><a href="http://book.naver.com/bookdb/book_detail.php?bid=121273">
    <span class="pcol1">당신의 이름은 무엇입니까</span></a></h4></dd>
</dl></div>
"""


def test_placeholder_regex_extracts_bid() -> None:
    m = PLACEHOLDER.search(_MD_LINE)
    assert m and m.group("bid") == "121273"
    assert m.group("img").endswith("x.jpg")


def test_se_widget_title_and_author() -> None:
    meta = book_meta_from_html(_HTML_SE)
    assert "555" in meta
    title, author = meta["555"]
    assert title == "반지의 제왕 세트"
    assert author == "J.R.R. 톨킨"  # dd first <p>, split before separator, not a date


def test_outerdl_widget_title_only() -> None:
    meta = book_meta_from_html(_HTML_DL)
    title, author = meta["121273"]
    assert title == "당신의 이름은 무엇입니까"
    assert author is None  # no clean author -> title only (no guessing)
