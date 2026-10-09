# -*- coding: utf-8 -*-
"""
Smoke test for fixed_sms_state + fixed_sms_file_pool DB tables.
Run: python test_fixed_state.py
"""
import asyncio
import os
import tempfile
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import Database


async def main():
    tmpdir = tempfile.mkdtemp(prefix="fixed_test_")
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

    print("=== test_session_assignment ===")
    await db.set_session_assignment("joingy", "sess1", "/folder1", "chat1.txt", 0)
    a = await db.get_session_assignment("joingy", "sess1", "/folder1")
    check("assignment created", a is not None)
    check("assigned_file correct", a and a["assigned_file"] == "chat1.txt")
    check("current_line correct", a and a["current_line"] == 0)

    print("=== test_update_line ===")
    await db.update_session_line("joingy", "sess1", "/folder1", 5)
    a = await db.get_session_assignment("joingy", "sess1", "/folder1")
    check("line updated to 5", a and a["current_line"] == 5)

    print("=== test_upsert ===")
    await db.set_session_assignment("joingy", "sess1", "/folder1", "chat2.txt", 3)
    a = await db.get_session_assignment("joingy", "sess1", "/folder1")
    check("upsert changed file", a and a["assigned_file"] == "chat2.txt")
    check("upsert changed line", a and a["current_line"] == 3)

    print("=== test_folder_assignments ===")
    await db.set_session_assignment("joingy", "sess2", "/folder1", "chat1.txt", 0)
    await db.set_session_assignment("isexychat", "sess3", "/folder1", "chat3.txt", 1)
    rows = await db.get_folder_assignments("/folder1")
    check("3 assignments in folder1", len(rows) == 3)

    print("=== test_clear_folder ===")
    await db.clear_folder_assignments("/folder1")
    rows = await db.get_folder_assignments("/folder1")
    check("folder cleared", len(rows) == 0)

    print("=== test_file_pool ===")
    files = [
        {"filename": "chat1.txt", "total_lines": 12},
        {"filename": "chat2.txt", "total_lines": 15},
        {"filename": "chat3.txt", "total_lines": 9},
    ]
    await db.upsert_file_pool("/folder1", files)
    pool = await db.get_file_pool("/folder1")
    check("pool has 3 files", len(pool) == 3)
    check("chat1 lines correct", pool[0]["total_lines"] == 12)
    check("chat2 lines correct", pool[1]["total_lines"] == 15)
    check("chat3 lines correct", pool[2]["total_lines"] == 9)

    print("=== test_pool_upsert ===")
    files2 = [
        {"filename": "chat1.txt", "total_lines": 20},
        {"filename": "chat4.txt", "total_lines": 7},
    ]
    await db.upsert_file_pool("/folder1", files2)
    pool = await db.get_file_pool("/folder1")
    check("pool now has 4 files", len(pool) == 4)
    chat1 = [p for p in pool if p["filename"] == "chat1.txt"][0]
    check("chat1 lines updated", chat1["total_lines"] == 20)

    print("=== test_distinct_sessions ===")
    await db.clear_folder_assignments("/folder1")
    for i in range(4):
        await db.set_session_assignment("joingy", f"u{i}", "/folder1", f"chat{i+1}.txt", 0)
    rows = await db.get_folder_assignments("/folder1")
    files_used = set(r["assigned_file"] for r in rows)
    check("4 distinct files", len(files_used) == 4)

    await db.close()

    print(f"\n{'='*40}")
    print(f"  Results: {passed} passed, {failed} failed")
    print(f"{'='*40}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())
