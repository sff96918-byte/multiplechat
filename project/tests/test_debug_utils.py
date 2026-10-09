# -*- coding: utf-8 -*-
"""Tests for improved debug_utils — level control, trace stats, crashes, inspector, dump."""
import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "src"
sys.path.insert(0, str(SRC))

import debug_utils as du

passed = 0
failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        print(f"  FAIL: {name} {detail}")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="dbgtest_"))

    # ── level control ──
    print("== level control ==")
    check("default level INFO", du.get_debug_level() == logging.INFO,
          f"got {du.get_debug_level()}")
    check("set_debug_level DEBUG", du.set_debug_level("DEBUG") == logging.DEBUG)
    check("set_debug_level int 20", du.set_debug_level(20) == logging.INFO)
    check("set_debug_level bogus -> INFO", du.set_debug_level("bogus") == logging.INFO)
    du.set_debug_level("DEBUG")

    dl = du.DebugLogger("lvltest", log_dir=tmp, console=False)
    check("new logger honors global DEBUG", dl.level == logging.DEBUG)
    dl.change_level("CRITICAL")
    check("change_level CRITICAL", dl.level == logging.CRITICAL)
    du.set_debug_level("DEBUG")
    check("global set updates existing handler", dl.level == logging.DEBUG)

    # ── jsonl file output ──
    print("== jsonl output ==")
    dl.change_level("DEBUG")
    dl.info("hello", uid="u1", status=200)
    dl.debug("dbg line")
    try:
        raise ValueError("boom")
    except ValueError as e:
        dl.error("failed", exc=e)
    for h in dl._logger.handlers:
        h.flush()
    lines = du.read_jsonl(dl.path, tail=50)
    check("3 lines written", len(lines) == 3, f"got {len(lines)}")
    check("msg ok", lines[0]["msg"] == "hello")
    check("data field", lines[0].get("data", {}).get("uid") == "u1")
    check("utc ts ends +00:00", lines[0]["ts"].endswith("+00:00"))
    check("exc captured", lines[2]["exc"].startswith("ValueError"))
    check("tb captured", "test_debug_utils" in lines[2].get("tb", ""))

    # INFO gating
    dl.change_level("WARNING")
    dl.info("should be gated")
    for h in dl._logger.handlers:
        h.flush()
    check("INFO gated at WARNING", len(du.read_jsonl(dl.path, tail=50)) == 3)
    dl.change_level("DEBUG")

    # ── read_jsonl ──
    print("== read_jsonl ==")
    check("missing file -> []", du.read_jsonl(tmp / "nope.jsonl") == [])
    big = tmp / "big.jsonl"
    with open(big, "w") as f:
        for i in range(10):
            f.write(json.dumps({"i": i}) + "\n")
    tail = du.read_jsonl(big, tail=3)
    check("tail=3", [r["i"] for r in tail] == [7, 8, 9], f"got {tail}")

    # ── trace capture ──
    print("== trace capture ==")
    tc = du.TraceCapture(max_entries=10)
    for i in range(5):
        tc.record("joingy", "s1", "req", "/start", 200, 100 + i)
    for i in range(3):
        tc.record("joingy", "s2", "req", "/poll", 500, 50, error="x")
    tc.record("isexychat", "s3", "send", "irc", 0, 30)
    check("total 9", tc.total() == 9)
    check("errors 3", tc.total_errors() == 3)
    check("session filter", len(tc.session("joingy", "s1")) == 5)
    check("direction filter", len(tc.get_recent(direction="send")) == 1)
    st = tc.stats()
    check("stats reqs", st["total_requests"] == 9)
    check("stats err rate ~33", st["error_rate"] == 33.3, f"got {st['error_rate']}")
    check("stats per-site", st["by_site"]["isexychat"]["requests"] == 1)
    check("stats p95 >= p50", st["latency_p95_ms"] >= st["latency_p50_ms"])
    tc.clear()
    check("clear works", tc.total() == 0)

    # ── crash tracker ──
    print("== crash tracker ==")
    ct = du.CrashTracker()

    async def crash_tests():
        check("can_retry first True", (await ct.can_retry("a", "s"))[0])
        for _ in range(6):
            try:
                raise RuntimeError("flap")
            except RuntimeError as e:
                await ct.record("a", "s", e)
        n = ct.crash_count_window("a", "s", window_sec=60)
        check("window count 6", n == 6, f"got {n}")
        fl = ct.flapping(threshold=5, window_sec=60)
        check("flapping detected", len(fl) == 1 and fl[0]["crashes"] == 6, f"got {fl}")
        check("stats by_exception", ct.stats()["by_exception"].get("RuntimeError") == 6)
        check("get_recent site filter", len(ct.get_recent(site="a")) == 6)
        check("get_recent wrong site", len(ct.get_recent(site="zzz")) == 0)
        ct.reset("a", "s")
        check("reset clears session", ct.crash_count_window("a", "s", window_sec=60) == 0)
        for _ in range(2):
            try:
                raise KeyError("other")
            except KeyError as e:
                await ct.record("b", "t", e)
        ct.clear(site="a")
        check("clear(site) keeps b", ct.stats()["total"] == 2)
        ct.clear()
        check("clear all", ct.stats()["total"] == 0)

    asyncio.run(crash_tests())

    # ── state inspector ──
    print("== state inspector ==")
    insp = du.StateInspector()

    async def insp_tests():
        await insp.update("joingy", "s1", {"state": "MIDDLE", "sent": 4, "recv": 9, "extra": 1})
        s = insp.snapshot()[0]
        check("update keeps state", s["state"] == "MIDDLE")
        check("update maps sent", s["messages_sent"] == 4)
        check("update maps recv", s["messages_received"] == 9)
        check("extra preserved", s["extra"] == 1)
        before = s["last_activity"]
        await asyncio.sleep(0.01)
        await insp.touch("joingy", "s1")
        check("touch bumps activity", insp.snapshot()[0]["last_activity"] > before)
        check("stats total", insp.stats()["total"] == 1)
        check("stats sent", insp.stats()["total_sent"] == 4)
        check("snapshot site filter", len(insp.snapshot("isexychat")) == 0)
        await insp.remove("joingy", "s1")
        check("remove works", insp.snapshot() == [])

    asyncio.run(insp_tests())

    # ── export dump ──
    print("== export dump ==")
    g_tc = du.get_trace_capture()
    g_tc.record("joingy", "s1", "req", "/x", 500, 10, error="fail")
    dump = du.export_debug_dump(path=tmp / "dump.json", proxy_stats={"total": 1})
    data = json.loads(dump.read_text(encoding="utf-8"))
    check("dump file exists", dump.exists())
    check("dump sections", all(k in data for k in
          ("generated_at", "sessions", "crashes", "trace", "proxy", "logs")))
    check("dump trace err", data["trace"]["errors"][0]["error"] == "fail")
    check("dump proxy", data["proxy"]["total"] == 1)

    # restore
    du.set_debug_level("INFO")
    print("=" * 40)
    print(f"Results: {passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()