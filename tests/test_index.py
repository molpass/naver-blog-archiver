"""S1 unit tests — category map, path building, response parsing, record shaping (offline)."""
from __future__ import annotations

from naver_blog_archiver.index import build_category_map, _post_record
from naver_blog_archiver.naver_api import decode_title, parse_post_title_list

# Minimal tree mirroring the real shape: a top category + a child + a divider.
_TREE = [
    {"categoryNo": 99, "categoryName": "구분선", "divisionLine": True, "parentCategoryNo": None},
    {"categoryNo": 19, "categoryName": "마음나누기", "parentCategoryNo": None, "postCnt": 1021},
    {"categoryNo": 46, "categoryName": "단상", "parentCategoryNo": 19, "postCnt": 378},
]


def test_category_map_drops_dividers_and_builds_paths() -> None:
    m = build_category_map(_TREE)
    assert 99 not in m  # divider dropped
    assert m[19]["path"] == "마음나누기"
    assert m[46]["path"] == "마음나누기/단상"  # child path includes parent
    assert m[46]["parent"] == 19


def test_post_record_maps_category_and_decodes_title() -> None:
    m = build_category_map(_TREE)
    # categoryNo arrives as a STRING from the list API — must still map.
    item = {"logNo": 123, "title": "%EC%82%AC%EB%9E%91+%EC%9D%B4%EC%95%BC%EA%B8%B0",
            "categoryNo": "46", "addDate": "2020"}
    rec = _post_record(item, m)
    assert rec["logNo"] == "123"
    assert rec["title"] == "사랑 이야기"           # percent-decoded, '+' -> space
    assert rec["categoryNo"] == 46                 # coerced to int
    assert rec["categoryPath"] == "마음나누기/단상"  # string categoryNo still maps


def test_uncategorized_when_category_missing() -> None:
    m = build_category_map(_TREE)
    rec = _post_record({"logNo": 1, "title": "x", "categoryNo": 777}, m)
    assert rec["categoryPath"] == "(미분류)"


def test_parse_post_title_list_strips_paginghtml() -> None:
    raw = '{"totalCount":2,"countPerPage":30,"postList":[{"logNo":1}],"pagingHtml":"<div>broken</div>"}'
    obj = parse_post_title_list(raw)
    assert obj["totalCount"] == 2
    assert obj["postList"][0]["logNo"] == 1


def test_decode_title_handles_plus_and_percent() -> None:
    assert decode_title("a+b") == "a b"
    assert decode_title("%ED%95%9C%EA%B8%80") == "한글"
