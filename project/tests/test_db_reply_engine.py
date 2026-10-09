# -*- coding: utf-8 -*-
import sys
import os
import tempfile
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from db_reply_engine import DBReplyEngine, DB_REPLY_STATE_SCHEMA, REPLY_BANK_SCHEMA


def test_ensure_schema():
    tmp = tempfile.mkdtemp(prefix="dbtest_")
    db_path = os.path.join(tmp, "test.db")

    engine = DBReplyEngine(db_path)
    engine.ensure_schema()

    conn = sqlite3.connect(db_path)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    conn.close()

    assert "reply_bank" in tables, f"reply_bank not found in {tables}"
    print("  [PASS] ensure_schema creates reply_bank table")


def test_add_row_returns_id():
    tmp = tempfile.mkdtemp(prefix="dbtest_")
    db_path = os.path.join(tmp, "test.db")

    engine = DBReplyEngine(db_path)
    engine.ensure_schema()

    id1 = engine.add_row("normal", "GREETING", "hi", "hello there", 2.0)
    id2 = engine.add_row("flirty", "GREETING", "hey", "heyy sexy", 5.0)
    id3 = engine.add_row("normal", "MIDDLE_CHAT", "wyd", "nothin wbu", 1.0)

    assert id1 == 1, f"Expected id=1, got {id1}"
    assert id2 == 2, f"Expected id=2, got {id2}"
    assert id3 == 3, f"Expected id=3, got {id3}"

    assert len(engine._rows) == 3
    assert engine._rows[0]["mood"] == "normal"
    assert engine._rows[1]["mood"] == "flirty"
    print("  [PASS] add_row returns correct incremental ids")


def test_reload_from_disk():
    tmp = tempfile.mkdtemp(prefix="dbtest_")
    db_path = os.path.join(tmp, "test.db")

    engine = DBReplyEngine(db_path)
    engine.ensure_schema()

    engine.add_row("normal", "GREETING", "hi", "hello", 1.0)
    engine.add_row("shy", "GREETING", "hi", "h... hi", 1.0)
    engine.add_row("aggressive", "MIDDLE_CHAT", "fu", "what did you say?", 3.0)

    engine2 = DBReplyEngine(db_path)
    engine2.ensure_schema()
    engine2.reload()

    assert engine2.stats()["rows"] == 3
    assert len(engine2.stats()["moods"]) == 3

    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT COUNT(*) FROM reply_bank").fetchone()[0]
    conn.close()
    assert rows == 3
    print("  [PASS] reload loads all rows from disk")


def test_exact_match():
    tmp = tempfile.mkdtemp(prefix="dbtest_")
    db_path = os.path.join(tmp, "test.db")

    engine = DBReplyEngine(db_path)
    engine.ensure_schema()

    engine.add_row("normal", "GREETING", "hi", "hello there", 2.0)
    engine.add_row("normal", "GREETING", "hey", "heyy you", 1.0)
    engine.add_row("flirty", "GREETING", "hi", "heyy cutie", 3.0)
    engine.reload()

    r = engine.get_reply("normal", "GREETING", "hi")
    assert r in ("hello there", "heyy you"), f"Got unexpected: {r}"

    r2 = engine.get_reply("flirty", "GREETING", "hi")
    assert r2 == "heyy cutie", f"Got: {r2}"

    print("  [PASS] exact trigger+mood+stage match works")


def test_like_match():
    tmp = tempfile.mkdtemp(prefix="dbtest_")
    db_path = os.path.join(tmp, "test.db")

    engine = DBReplyEngine(db_path)
    engine.ensure_schema()

    engine.add_row("normal", "MIDDLE_CHAT", "how are you", "im good wbu", 2.0)
    engine.add_row("normal", "MIDDLE_CHAT", "good", "nice", 1.0)
    engine.reload()

    r = engine.get_reply("normal", "MIDDLE_CHAT", "hey how are you doing today")
    assert r == "im good wbu", f"Expected LIKE match, got: {r}"

    print("  [PASS] LIKE trigger %msg% match works")


def test_weighted_pick():
    tmp = tempfile.mkdtemp(prefix="dbtest_")
    db_path = os.path.join(tmp, "test.db")

    engine = DBReplyEngine(db_path)
    engine.ensure_schema()

    engine.add_row("normal", "GREETING", "hi", "HIGH_WEIGHT", 100.0)
    engine.add_row("normal", "GREETING", "hi", "LOW_WEIGHT", 0.01)
    engine.reload()

    results = {"HIGH_WEIGHT": 0, "LOW_WEIGHT": 0}
    for _ in range(200):
        r = engine.get_reply("normal", "GREETING", "hi")
        results[r] += 1

    assert results["HIGH_WEIGHT"] > results["LOW_WEIGHT"] * 5, \
        f"High weight should dominate: {results}"
    print(f"  [PASS] weighted pick: HIGH={results['HIGH_WEIGHT']} LOW={results['LOW_WEIGHT']}")


def test_fallback_engine():
    tmp = tempfile.mkdtemp(prefix="dbtest_")
    db_path = os.path.join(tmp, "test.db")

    engine = DBReplyEngine(db_path, fallback_engine="FALLBACK_OK")
    engine.ensure_schema()
    engine.reload()

    r = engine.get_reply("normal", "GREETING", "hi")
    assert r == "FALLBACK_OK", f"Got: {r}"

    engine.add_row("normal", "GREETING", "hi", "real_reply", 1.0)
    r2 = engine.get_reply("normal", "GREETING", "hi")
    assert r2 == "real_reply", f"Should get real reply, got: {r2}"

    print("  [PASS] fallback_engine returns when no match, superseded by real rows")


def test_stats():
    tmp = tempfile.mkdtemp(prefix="dbtest_")
    db_path = os.path.join(tmp, "test.db")

    engine = DBReplyEngine(db_path)
    engine.ensure_schema()

    engine.add_row("normal", "GREETING", "hi", "hello", 1.0)
    engine.add_row("normal", "MIDDLE_CHAT", "wyd", "nmu", 1.0)
    engine.add_row("flirty", "GREETING", "hi", "heyy", 1.0)
    engine.add_row("shy", "GREETING", "hi", "h-hi", 1.0)

    s = engine.stats()
    assert s["rows"] == 4
    assert "normal" in s["moods"]
    assert "flirty" in s["moods"]
    assert "shy" in s["moods"]
    assert s["triggers"] == 2

    print(f"  [PASS] stats: {s}")


def test_no_match_no_fallback():
    tmp = tempfile.mkdtemp(prefix="dbtest_")
    db_path = os.path.join(tmp, "test.db")

    engine = DBReplyEngine(db_path)
    engine.ensure_schema()

    engine.add_row("flirty", "GREETING", "hi", "heyy", 1.0)
    engine.reload()

    r = engine.get_reply("aggressive", "GREETING", "yo")
    assert r is None, f"Expected None, got: {r}"

    print("  [PASS] no match + no fallback -> None")


def test_cross_stage_no_match():
    tmp = tempfile.mkdtemp(prefix="dbtest_")
    db_path = os.path.join(tmp, "test.db")

    engine = DBReplyEngine(db_path)
    engine.ensure_schema()

    engine.add_row("normal", "GREETING", "hi", "hello", 1.0)
    engine.reload()

    r = engine.get_reply("normal", "END", "hi")
    assert r == "hello", f"cross-stage should still match by mood, got: {r}"

    print("  [PASS] cross-stage fallback matches by mood")


def test_weight_default_zero():
    tmp = tempfile.mkdtemp(prefix="dbtest_")
    db_path = os.path.join(tmp, "test.db")

    engine = DBReplyEngine(db_path)
    engine.ensure_schema()
    engine.add_row("normal", "GREETING", "hi", "hello", 0.0)
    engine.add_row("normal", "GREETING", "hi", "world", 0.0)
    engine.reload()

    r = engine.get_reply("normal", "GREETING", "hi")
    assert r in ("hello", "world"), f"Got: {r}"

    print("  [PASS] zero-weight rows handled gracefully")


def test_empty_incoming_msg():
    tmp = tempfile.mkdtemp(prefix="dbtest_")
    db_path = os.path.join(tmp, "test.db")

    engine = DBReplyEngine(db_path)
    engine.ensure_schema()
    engine.add_row("normal", "GREETING", "hi", "hello", 1.0)

    r = engine.get_reply("normal", "GREETING", "")
    assert r is None, f"Empty msg should return None, got: {r}"

    engine2 = DBReplyEngine(db_path, fallback_engine="FB")
    engine2.ensure_schema()
    engine2.reload()
    r2 = engine2.get_reply("normal", "GREETING", "")
    assert r2 == "FB", f"Empty msg with fallback: {r2}"

    print("  [PASS] empty incoming_msg handled")


def test_multiple_like_candidates_weighted():
    tmp = tempfile.mkdtemp(prefix="dbtest_")
    db_path = os.path.join(tmp, "test.db")

    engine = DBReplyEngine(db_path)
    engine.ensure_schema()

    engine.add_row("normal", "MIDDLE_CHAT", "hello", "LOW", 0.01)
    engine.add_row("normal", "MIDDLE_CHAT", "hello world", "HIGH", 100.0)
    engine.reload()

    results = {"LOW": 0, "HIGH": 0}
    for _ in range(200):
        r = engine.get_reply("normal", "MIDDLE_CHAT", "hello world")
        results[r] += 1

    assert results["HIGH"] > results["LOW"] * 5, f"LIKE weighted: {results}"
    print(f"  [PASS] LIKE weighting: HIGH={results['HIGH']} LOW={results['LOW']}")


if __name__ == "__main__":
    tests = [
        test_ensure_schema,
        test_add_row_returns_id,
        test_reload_from_disk,
        test_exact_match,
        test_like_match,
        test_weighted_pick,
        test_fallback_engine,
        test_stats,
        test_no_match_no_fallback,
        test_cross_stage_no_match,
        test_weight_default_zero,
        test_empty_incoming_msg,
        test_multiple_like_candidates_weighted,
    ]

    failed = 0
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"  [FAIL] {test.__name__}: {e}")
            import traceback; traceback.print_exc()
            failed += 1

    print(f"\n  {len(tests) - failed}/{len(tests)} passed, {failed} failed")
    sys.exit(1 if failed else 0)
