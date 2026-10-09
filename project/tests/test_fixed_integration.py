# -*- coding: utf-8 -*-
"""
Integration test for FixedSmsEngine — all 5 scenarios.
Run: python test_fixed_integration.py
"""
import asyncio
import os
import tempfile
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import Database
from fixed_sms_engine import FixedSmsEngine


async def main():
    tmpdir = tempfile.mkdtemp(prefix="fsm_integration_")
    db_path = os.path.join(tmpdir, "test.db")
    db = Database(db_path)
    await db.init()

    passed = 0
    failed = 0

    def check(name, cond):
        nonlocal passed, failed
        if cond:
            print(f"  PASS: {name}")
            passed += 1
        else:
            print(f"  FAIL: {name}")
            failed += 1

    # Setup: 4 txt files, 5 lines each, prefixed with filename
    folder1 = os.path.join(tmpdir, "scripts1")
    os.makedirs(folder1)
    for i in range(1, 5):
        with open(os.path.join(folder1, f"chat{i}.txt"), "w") as f:
            for j in range(1, 6):
                f.write(f"chat{i}_line{j}\n")

    snap_file = os.path.join(tmpdir, "snap.txt")
    with open(snap_file, "w") as f:
        f.write("testuser123\n")

    config = {
        "snap_username": "fallback_snap",
        "fixed_sms": {
            "enabled": True,
            "folder": "",
            "loop": True,
            "snap_username_file": snap_file,
        },
    }
    engine = FixedSmsEngine(db, config)
    await engine.load_snap_username()
    result = await engine.set_folder(folder1)
    assert result["ok"], f"set_folder failed: {result}"

    # ═══ Scenario 1: Line-by-line (single session) ═══
    print("\n=== Scenario 1: Line-by-line ===")
    replies = []
    for _ in range(12):
        r = await engine.get_reply("test", "s1")
        replies.append(r.strip() if r else None)
    check("12 replies returned", all(r is not None for r in replies))
    check("line 1 = chatX_line1", "_line1" in replies[0])
    check("line 2 = chatX_line2", "_line2" in replies[1])
    check("line 5 = chatX_line5", "_line5" in replies[4])
    check("line 6 wraps to line1", "_line1" in replies[5])
    check("line 12 wraps to line2", "_line2" in replies[11])
    prefix = replies[0].split("_line")[0]
    check("all same file", all(r.startswith(prefix) for r in replies if r))

    # ═══ Scenario 2: DISTINCT FILE PER SESSION ═══
    print("\n=== Scenario 2: Distinct file per session ===")
    await db.clear_folder_assignments(folder1)
    session_files = {}
    for i in range(1, 5):
        r = await engine.get_reply("test", f"s_distinct_{i}")
        if r:
            fname = r.strip().split("_line")[0]
            session_files[f"s_distinct_{i}"] = fname
    files_used = set(session_files.values())
    check("4 sessions -> 4 distinct files", len(files_used) == 4)
    check("no duplicate files", len(files_used) == len(session_files))

    print("  Session assignments:")
    for s, f in session_files.items():
        print(f"    {s} -> {f}")

    # S5 wraps
    r5 = await engine.get_reply("test", "s_distinct_5")
    check("S5 gets a file (wrap)", r5 is not None)
    if r5:
        f5 = r5.strip().split("_line")[0]
        check("S5 reuses a file (pool exhausted)", f5 in files_used)

    # ═══ Scenario 3: Persistence (reload engine) ═══
    print("\n=== Scenario 3: Persistence ===")
    r_before = await engine.get_reply("test", "s_persist")
    line_before = r_before.strip() if r_before else ""
    r_before2 = await engine.get_reply("test", "s_persist")
    line_before2 = r_before2.strip() if r_before2 else ""

    engine2 = FixedSmsEngine(db, config)
    engine2._folder_path = folder1
    r_after = await engine2.get_reply("test", "s_persist")
    line_after = r_after.strip() if r_after else ""

    check("resume returns next line", line_after != line_before2)
    prefix_persist = line_before.split("_line")[0]
    check("same file after reload", line_after.startswith(prefix_persist))

    line_num_before = int(line_before2.split("_line")[1])
    line_num_after = int(line_after.split("_line")[1])
    check("line number advanced by 1", line_num_after == line_num_before + 1)

    # ═══ Scenario 4: Snap username ═══
    print("\n=== Scenario 4: Snap username ===")
    await engine.load_snap_username()
    replaced = engine.replace_username("hi %username%")
    check("snap replaced from file", replaced == "hi testuser123")

    os.remove(snap_file)
    await engine.load_snap_username()
    replaced2 = engine.replace_username("hi %username%")
    check("fallback to config snap", "fallback_snap" in replaced2)

    # ═══ Scenario 5: Folder change ═══
    print("\n=== Scenario 5: Folder change ===")
    folder2 = os.path.join(tmpdir, "scripts2")
    os.makedirs(folder2)
    for i in range(1, 4):
        with open(os.path.join(folder2, f"new{i}.txt"), "w") as f:
            for j in range(1, 4):
                f.write(f"new{i}_line{j}\n")

    result2 = await engine.set_folder(folder2)
    check("folder2 set ok", result2.get("ok"))
    check("folder2 has 3 files", len(result2.get("files", [])) == 3)

    old_assignments = await db.get_folder_assignments(folder1)
    check("old folder assignments cleared", len(old_assignments) == 0)

    r_new = await engine.get_reply("test", "s_folder_change")
    check("new folder reply", r_new is not None)
    if r_new:
        check("reply from new folder", r_new.strip().startswith("new"))

    await db.close()

    print(f"\n{'='*50}")
    print(f"  Integration Results: {passed} passed, {failed} failed")
    print(f"{'='*50}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())