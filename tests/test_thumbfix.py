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

# outerDL widget: per-book dd = '제목 | 저자 출판사 날짜 별점' -> byline '저자 출판사'
_HTML_DL = """
<div class="post-view"><dl id="outerDL">
  <dt><a href="http://book.naver.com/bookdb/book_detail.php?bid=121273">
    <img src="http://bookimg.naver.com/y.jpg"></a></dt>
  <dd id="id_dd_121273"><a href="http://book.naver.com/bookdb/book_detail.php?bid=121273">
    <span class="pcol1">당신의 이름은 무엇입니까</span></a>
    <span>|</span> 신현태 신규출판 <span>2003.03.10</span> <strong>별점</strong></dd>
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


def test_outerdl_byline_drops_date_and_rating() -> None:
    meta = book_meta_from_html(_HTML_DL)
    title, byline = meta["121273"]
    assert title == "당신의 이름은 무엇입니까"
    assert byline == "신현태 신규출판"  # '|'..date, with date+rating cut


# dt-based book (no '|' delimiter): 'title author publisher date' -> strip title + date
_HTML_DT = """
<div class="post-view"><dl id="outerDL"><dt>
  <a href="http://book.naver.com/bookdb/book_detail.php?bid=4302646">
    <span class="pcol1">통계의 미학</span></a> 정재호 이지아시아 2007.12.03
</dt></dl></div>
"""


def test_outerdl_byline_no_bar_strips_title_and_date() -> None:
    title, byline = book_meta_from_html(_HTML_DT)["4302646"]
    assert title == "통계의 미학"
    assert byline == "정재호 이지아시아"  # title + date removed, no '|' present
