"""FixedReplyEngine — fixed txt ফাইল থেকে line-by-line reply টেস্ট।"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eva.brain.fixed_reply_engine import FixedReplyEngine


def _write(tmp_path: Path, lines: list[str]) -> Path:
    p = tmp_path / "script.txt"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def test_opener_is_first_line(tmp_path):
    eng = FixedReplyEngine(_write(tmp_path, ["# comment", "line one", "line two"]))
    p = {"id": "p1"}
    assert eng.opener(p) == "line one"


def test_replies_are_sequential(tmp_path):
    eng = FixedReplyEngine(_write(tmp_path, ["one", "two", "three"]))
    p = {"id": "p1"}
    assert eng.opener(p) == "one"       # opener = ১ম line
    out = [eng.reply(p, "msg") for _ in range(3)]
    assert out == ["two", "three", ""]  # পরেরগুলো sequential; শেষে ""


def test_exhausted_returns_empty_and_finished(tmp_path):
    eng = FixedReplyEngine(_write(tmp_path, ["only line"]))
    p = {"id": "p1"}
    assert eng.opener(p) == "only line"
    assert eng.reply(p, "hi") == ""     # ফুরিয়ে গেছে
    assert eng.finished("p1") is True
    assert eng.remaining("p1") == 0


def test_partners_are_independent(tmp_path):
    eng = FixedReplyEngine(_write(tmp_path, ["a", "b", "c"]))
    p1, p2 = {"id": "p1"}, {"id": "p2"}
    assert eng.opener(p1) == "a"
    assert eng.reply(p1, "x") == "b"
    assert eng.opener(p2) == "a"      # নতুন partner প্রথম লাইন থেকে শুরু করে
    assert eng.reply(p2, "y") == "b"
    assert eng.reply(p1, "z") == "c"


def test_forget_resets_pointer(tmp_path):
    eng = FixedReplyEngine(_write(tmp_path, ["a", "b", "c"]))
    p = {"id": "p1"}
    eng.opener(p); eng.reply(p, "x")
    eng.forget("p1")
    assert eng.finished("p1") is False
    assert eng.opener(p) == "a"


def test_comments_and_blank_lines_skipped(tmp_path):
    eng = FixedReplyEngine(_write(tmp_path, ["# hdr", "", "  ", "real1", "#mid", "real2"]))
    p = {"id": "p1"}
    assert eng.opener(p) == "real1"
    assert eng.reply(p, "x") == "real2"


def test_timing_matches_flow(tmp_path):
    from eva.brain.flow_reply_engine import DEFAULT_TIMING
    eng = FixedReplyEngine(_write(tmp_path, ["x"]))
    assert eng.timing == DEFAULT_TIMING
    d = eng.delay_for("hello there")
    assert 0.5 <= d <= 20
