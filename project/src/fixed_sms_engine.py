# -*- coding: utf-8 -*-
"""
FixedSmsEngine — random txt file per chat session, line-by-line reply.

Each new chat session gets a random txt file from a configured folder.
No two sessions share a file until the pool is exhausted (least-used-random).
Replies are sent line-by-line from the assigned file.
State is persisted in SQLite (restart-safe).
%username% is replaced with snap username loaded from a desktop txt file.

Fallback chain: FixedSmsEngine → ReplyEngine → silent log.
"""
import os
import random
import asyncio
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger("fixed_sms")


class FixedSmsEngine:
    """Core engine for Fixed SMS Mode."""

    def __init__(self, db, config: dict):
        self.db = db
        self.config = config
        self._folder_path: Optional[str] = None
        self._file_cache: dict[str, list[str]] = {}
        self._lock = asyncio.Lock()
        fsm = config.get("fixed_sms", {})
        self._enabled = fsm.get("enabled", False)
        self._loop = fsm.get("loop", True)
        self._pick_mode = fsm.get("pick_mode", "least_used_random")
        self._recursive = fsm.get("recursive", False)
        self._snap_username: Optional[str] = None
        self._snap_file_mtime: float = 0
        self._snap_file: str = fsm.get(
            "snap_username_file", "C:\\Users\\papi\\Desktop\\snap_username.txt"
        )

    # ═══ Public API ═══
    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    async def set_folder(self, path: str) -> dict:
        """Validate folder, scan txt files, persist to DB, clear old assignments."""
        if not os.path.isdir(path):
            return {"ok": False, "error": f"Not a directory: {path}"}

        files_info = []
        if self._recursive:
            txt_files = list(Path(path).rglob("*.txt"))
        else:
            txt_files = list(Path(path).glob("*.txt"))

        for fp in sorted(txt_files):
            name = fp.name
            if name.startswith("."):
                continue
            try:
                lines = self._read_lines(str(fp))
                usable = [l for l in lines if l.strip() and not l.strip().startswith("#")]
                if usable:
                    files_info.append({"filename": name, "total_lines": len(usable)})
            except Exception as e:
                logger.warning(f"Skipping {name}: {e}")
                continue

        if not files_info:
            return {"ok": False, "error": "No usable txt files found"}

        if self._folder_path and self._folder_path != path:
            await self.db.clear_folder_assignments(self._folder_path)
        await self.db.upsert_file_pool(path, files_info)
        await self.db.clear_folder_assignments(path)
        self._folder_path = path
        self._file_cache.clear()
        total = sum(f["total_lines"] for f in files_info)
        logger.info(f"FixedSms folder set: {path} ({len(files_info)} files, {total} lines)")
        return {"ok": True, "folder": path, "files": files_info, "total_lines": total}

    async def get_reply(self, site: str, session_id: str) -> Optional[str]:
        """Get the next line for a session. Returns None if not available."""
        if not self._enabled:
            return None
        if not self._folder_path:
            logger.debug("FixedSms: no folder set")
            return None

        async with self._lock:
            pool = await self.db.get_file_pool(self._folder_path)
            if not pool:
                logger.warning("FixedSms: file pool empty")
                return None

            assignment = await self.db.get_session_assignment(site, session_id, self._folder_path)

            if assignment is None:
                chosen = await self._pick_file(pool)
                await self.db.set_session_assignment(
                    site, session_id, self._folder_path, chosen, 0
                )
                assigned_file = chosen
                current_line = 0
                logger.info(f"FixedSms: assigned {chosen} to {site}/{session_id}")
            else:
                assigned_file = assignment["assigned_file"]
                current_line = assignment["current_line"]

            lines = await self._load_lines(assigned_file)
            if not lines:
                retry_count = 0
                max_retries = min(len(pool), 5)
                while retry_count < max_retries:
                    retry_count += 1
                    chosen = await self._pick_file(pool)
                    lines = await self._load_lines(chosen)
                    if lines:
                        assigned_file = chosen
                        current_line = 0
                        await self.db.set_session_assignment(
                            site, session_id, self._folder_path, chosen, 0
                        )
                        logger.info(f"FixedSms: retry assigned {chosen} to {site}/{session_id}")
                        break
                if not lines:
                    logger.error("FixedSms: all files empty")
                    return None

            if current_line >= len(lines):
                if self._loop:
                    current_line = current_line % len(lines)
                else:
                    logger.info(f"FixedSms: {site}/{session_id} exhausted file {assigned_file}")
                    return None

            reply = lines[current_line]
            await self.db.update_session_line(
                site, session_id, self._folder_path, current_line + 1
            )
            return reply

    async def peek_reply(self, site: str, session_id: str) -> Optional[dict]:
        """Preview next line without advancing pointer."""
        if not self._enabled or not self._folder_path:
            return None

        assignment = await self.db.get_session_assignment(site, session_id, self._folder_path)
        if assignment is None:
            pool = await self.db.get_file_pool(self._folder_path)
            if not pool:
                return None
            chosen = await self._pick_file(pool)
            return {"assigned_file": chosen, "next_line": "(not yet assigned)", "next_line_no": 0}

        assigned_file = assignment["assigned_file"]
        current_line = assignment["current_line"]
        lines = await self._load_lines(assigned_file)
        if not lines:
            return {"assigned_file": assigned_file, "next_line": "(file empty)", "next_line_no": current_line}

        idx = current_line % len(lines) if self._loop else current_line
        if idx >= len(lines):
            next_line = "(exhausted)"
        else:
            next_line = lines[idx]

        return {
            "assigned_file": assigned_file,
            "next_line": next_line,
            "next_line_no": current_line + 1,
        }

    async def load_snap_username(self) -> Optional[str]:
        """Load snap username from configured txt file (with mtime cache)."""
        snap_file = self.config.get("fixed_sms", {}).get(
            "snap_username_file", self._snap_file
        )
        self._snap_file = snap_file

        if not snap_file or not os.path.isfile(snap_file):
            logger.warning(f"FixedSms: snap file not found: {snap_file}")
            fallback = self.config.get("snap_username", "")
            self._snap_username = fallback
            return fallback

        try:
            mtime = os.path.getmtime(snap_file)
            if mtime == self._snap_file_mtime and self._snap_username:
                return self._snap_username

            with open(snap_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self._snap_username = line
                        self._snap_file_mtime = mtime
                        logger.info(f"FixedSms: snap username loaded: {line}")
                        return line
            logger.warning("FixedSms: snap file has no usable lines")
            self._snap_username = self.config.get("snap_username", "")
            return self._snap_username
        except Exception as e:
            logger.warning(f"FixedSms: error reading snap file: {e}")
            self._snap_username = self.config.get("snap_username", "")
            return self._snap_username

    def replace_username(self, text: str) -> str:
        """Replace %username% with loaded snap username."""
        snap = self._snap_username or self.config.get("snap_username", "")
        return text.replace("%username%", snap)

    async def get_status(self) -> dict:
        """Return current engine status for dashboard."""
        files = []
        assignment_count = 0
        if self._folder_path:
            pool = await self.db.get_file_pool(self._folder_path)
            for p in pool:
                files.append({"name": p["filename"], "lines": p["total_lines"]})
            assignments = await self.db.get_folder_assignments(self._folder_path)
            assignment_count = len(assignments)

        return {
            "enabled": self._enabled,
            "folder": self._folder_path or "",
            "files": files,
            "assignment_count": assignment_count,
            "snap_username": self._snap_username or "",
            "snap_file": self._snap_file,
            "loop": self._loop,
        }

    async def get_assignments(self) -> list[dict]:
        """Return all active assignments for dashboard table."""
        if not self._folder_path:
            return []
        rows = await self.db.get_folder_assignments(self._folder_path)
        return [
            {
                "site": r["site"],
                "session_id": r["session_id"],
                "assigned_file": r["assigned_file"],
                "current_line": r["current_line"],
            }
            for r in rows
        ]

    # ═══ Internal ═══
    async def _pick_file(self, pool: list[dict]) -> str:
        """Least-used-then-random file selection."""
        if self._pick_mode == "random":
            return random.choice(pool)["filename"]

        assignments = await self.db.get_folder_assignments(self._folder_path)
        counts: dict[str, int] = {}
        for p in pool:
            counts[p["filename"]] = 0
        for a in assignments:
            fn = a["assigned_file"]
            if fn in counts:
                counts[fn] += 1

        min_count = min(counts.values()) if counts else 0
        candidates = [fn for fn, c in counts.items() if c == min_count]
        return random.choice(candidates)

    async def _load_lines(self, filename: str) -> list[str]:
        """Load usable lines from a file (with cache)."""
        if filename in self._file_cache:
            return self._file_cache[filename]

        if not self._folder_path:
            return []

        filepath = os.path.join(self._folder_path, filename)
        if not os.path.isfile(filepath):
            logger.warning(f"FixedSms: file missing: {filepath}")
            return []

        lines = self._read_lines(filepath)
        usable = [l for l in lines if l.strip() and not l.strip().startswith("#")]
        self._file_cache[filename] = usable
        return usable

    @staticmethod
    def _read_lines(filepath: str) -> list[str]:
        """Read file lines with utf-8 → latin-1 fallback."""
        for encoding in ("utf-8", "latin-1"):
            try:
                with open(filepath, "r", encoding=encoding) as f:
                    return f.readlines()
            except UnicodeDecodeError:
                continue
            except Exception:
                return []
        return []


# ═══ Smoke Test ═══
if __name__ == "__main__":
    import tempfile
    import aiosqlite
    from db import Database

    async def _smoke():
        tmpdir = tempfile.mkdtemp(prefix="fixed_sms_")
        snap_dir = tempfile.mkdtemp(prefix="fixed_sms_snap_")
        for i in range(1, 4):
            with open(os.path.join(tmpdir, f"chat{i}.txt"), "w") as f:
                for j in range(1, 6):
                    f.write(f"chat{i}_line{j}\n")

        snap_file = os.path.join(snap_dir, "snap.txt")
        with open(snap_file, "w") as f:
            f.write("testuser123\n")

        db_path = os.path.join(tmpdir, "test.db")
        db = Database(db_path)
        await db.init()

        config = {
            "snap_username": "fallback_snap",
            "fixed_sms": {
                "enabled": True,
                "folder": tmpdir,
                "loop": True,
                "snap_username_file": snap_file,
            },
        }
        engine = FixedSmsEngine(db, config)
        await engine.load_snap_username()

        result = await engine.set_folder(tmpdir)
        assert result["ok"], f"set_folder failed: {result}"
        assert len(result["files"]) == 3, f"Expected 3 files, got {len(result['files'])}"
        print(f"  set_folder: {result['files']}")

        assigned = set()
        for i in range(1, 5):
            reply = await engine.get_reply("test", f"session_{i}")
            assert reply is not None, f"Session {i} got None"
            file_line = reply.strip()
            fname = file_line.split("_line")[0]
            assigned.add(fname)
            print(f"  Session {i}: {reply.strip()}")

        assert len(assigned) == 3, f"Expected 3 distinct files, got {len(assigned)}: {assigned}"
        print(f"  DISTINCT FILES: {assigned} OK")

        r1 = await engine.get_reply("test", "session_linebyline")
        r2 = await engine.get_reply("test", "session_linebyline")
        assert "line1" in r1, f"Expected line1, got {r1}"
        assert "line2" in r2, f"Expected line2, got {r2}"
        print(f"  Line-by-line: r1={r1.strip()}, r2={r2.strip()} OK")

        engine2 = FixedSmsEngine(db, config)
        engine2._folder_path = tmpdir
        r3 = await engine2.get_reply("test", "session_linebyline")
        assert "line3" in r3, f"Expected line3 after reload, got {r3}"
        print(f"  Resume after reload: r3={r3.strip()} OK")

        replaced = engine.replace_username("hi %username%")
        assert replaced == "hi testuser123", f"Expected 'hi testuser123', got '{replaced}'"
        print(f"  Snap replace: {replaced} OK")

        os.remove(snap_file)
        await engine.load_snap_username()
        replaced2 = engine.replace_username("hi %username%")
        assert "fallback_snap" in replaced2, f"Expected fallback, got '{replaced2}'"
        print(f"  Snap fallback: {replaced2} OK")

        await db.close()
        print("\n  ALL SMOKE TESTS PASSED OK")

    asyncio.run(_smoke())
