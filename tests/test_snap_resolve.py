"""resolve_snap_usernames — snap.txt ফাইল priority + fallback টেস্ট।"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eva.brain.flow_reply_engine import resolve_snap_usernames


def test_file_takes_priority(tmp_path, monkeypatch):
    f = tmp_path / "snap.txt"
    f.write_text("# comment\nuser_a\nuser_b\n\nuser_c\n", encoding="utf-8")
    monkeypatch.setattr("eva.paths.project_root", lambda: tmp_path)
    cfg = {"snap_file": "snap.txt", "snap_usernames": ["ignored1", "ignored2"]}
    assert resolve_snap_usernames(cfg) == ["user_a", "user_b", "user_c"]


def test_fallback_to_comma_list_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("eva.paths.project_root", lambda: tmp_path)
    cfg = {"snap_file": "nope.txt", "snap_usernames": ["a", " b ", "", "c"]}
    assert resolve_snap_usernames(cfg) == ["a", "b", "c"]


def test_empty_file_falls_back(tmp_path, monkeypatch):
    f = tmp_path / "snap.txt"
    f.write_text("# only comments\n", encoding="utf-8")
    monkeypatch.setattr("eva.paths.project_root", lambda: tmp_path)
    cfg = {"snap_file": "snap.txt", "snap_usernames": ["x"]}
    assert resolve_snap_usernames(cfg) == ["x"]


def test_nothing_set_gives_empty():
    assert resolve_snap_usernames({}) == []
