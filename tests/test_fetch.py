"""S3 unit tests — tidy_text (conservative), resume skip logic (offline)."""
from __future__ import annotations

from pathlib import Path

from naver_blog_archiver.config import Config
from naver_blog_archiver.convert import tidy_text
from naver_blog_archiver.fetch import _is_done


def test_tidy_removes_space_before_punct() -> None:
    assert tidy_text("합니다 .") == "합니다."
    assert tidy_text("책들을 ,") == "책들을,"


def test_tidy_adds_space_after_sentence_before_hangul() -> None:
    assert tidy_text("습니다.이 책") == "습니다. 이 책"


def test_tidy_preserves_decimals_and_latin() -> None:
    # only Hangul triggers the after-punct space — not 1.08 or Mr.Kim
    assert tidy_text("버전 1.08 입니다") == "버전 1.08 입니다"
    assert tidy_text("see Mr.Kim now") == "see Mr.Kim now"


def test_tidy_collapses_multispace() -> None:
    assert tidy_text("책   속의   길") == "책 속의 길"


def _cfg(tmp: Path) -> Config:
    from naver_blog_archiver.config import CrawlConfig, DeepInfraConfig
    return Config(blog_id="x", data_dir=tmp, crawl=CrawlConfig(), deepinfra=DeepInfraConfig())


def test_is_done_requires_valid_md(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    md = tmp_path / "posts" / "1.md"
    md.parent.mkdir(parents=True)
    md.write_text("---\ntitle: x\n---\n충분히 긴 본문 내용이 들어있다\n", encoding="utf-8")
    prog = {"1": {"status": "done", "md_path": str(md)}}
    assert _is_done(cfg, "1", prog) is True
    # not done if status missing/failed
    assert _is_done(cfg, "1", {"1": {"status": "failed"}}) is False
    # not done if md file is gone
    assert _is_done(cfg, "2", {"2": {"status": "done", "md_path": str(tmp_path / "nope.md")}}) is False


def test_is_done_rejects_tiny_md(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    md = tmp_path / "posts" / "2.md"
    md.parent.mkdir(parents=True)
    md.write_text("x", encoding="utf-8")  # too small -> treated as not done
    assert _is_done(cfg, "2", {"2": {"status": "done", "md_path": str(md)}}) is False
