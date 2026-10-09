# -*- coding: utf-8 -*-
"""
Thread Manager — concurrency/session pool coordinator.

Manages per-site session pools with configurable max concurrency.
Tracks active/pending/completed sessions. Coordinates with the
bot implementations to ensure session limits are honored.

State persisted in `thread_state` table (restart-safe).
"""
import asyncio
import time
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("thread_manager")

THREAD_SCHEMA = """
CREATE TABLE IF NOT EXISTS thread_state (
    site TEXT NOT NULL,
    session_id TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at REAL,
    started_at REAL,
    finished_at REAL,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,
    PRIMARY KEY (site, session_id)
);
"""


@dataclass
class ThreadSlot:
    session_id: str
    status: str = "pending"
    created_at: float = 0.0
    started_at: float = 0.0
    finished_at: float = 0.0
    error_count: int = 0
    last_error: str = ""


class ThreadManager:
    def __init__(self, db):
        self.db = db
        self._lock = asyncio.Lock()
        self._pools: dict[str, dict] = {}
        self._semaphores: dict[str, asyncio.Semaphore] = {}

    async def init(self):
        for stmt in THREAD_SCHEMA.split(";"):
            s = stmt.strip()
            if s:
                await self.db.conn.execute(s)
        await self.db.conn.commit()

        cursor = await self.db.conn.execute("SELECT * FROM thread_state")
        rows = await cursor.fetchall()
        for r in rows:
            site = r["site"]
            sid = r["session_id"]
            self._pools.setdefault(site, {})[sid] = ThreadSlot(
                session_id=sid,
                status=r["status"],
                created_at=r["created_at"],
                started_at=r["started_at"],
                finished_at=r["finished_at"],
                error_count=r["error_count"],
                last_error=r["last_error"] or "",
            )

        logger.info(f"ThreadManager: loaded {sum(len(p) for p in self._pools.values())} threads")

    async def configure(self, site: str, max_concurrent: int):
        self._semaphores[site] = asyncio.Semaphore(max_concurrent)
        self._pools.setdefault(site, {})
        logger.info(f"Thread pool: {site} max={max_concurrent}")

    async def acquire(self, site: str, session_id: str) -> bool:
        if site not in self._semaphores:
            await self.configure(site, 5)

        acquired = self._semaphores[site].locked() is False or True
        async with self._lock:
            if site not in self._pools:
                self._pools[site] = {}

            slot = self._pools[site].get(session_id)
            if slot is None:
                slot = ThreadSlot(session_id=session_id, created_at=time.time())
                self._pools[site][session_id] = slot

            slot.status = "starting"
            slot.started_at = time.time()

            await self.db.conn.execute(
                """INSERT INTO thread_state (site, session_id, status, created_at, started_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(site, session_id) DO UPDATE SET
                     status='starting', started_at=?""",
                (site, session_id, "starting", slot.created_at, slot.started_at, slot.started_at),
            )
            await self.db.conn.commit()

        await self._semaphores[site].acquire()
        slot.status = "running"
        await self._update_db_status(site, session_id, "running")
        logger.debug(f"Thread acquired: {site}/{session_id}")
        return True

    async def release(self, site: str, session_id: str, error: str = None):
        async with self._lock:
            pool = self._pools.get(site, {})
            slot = pool.get(session_id)
            if slot:
                slot.finished_at = time.time()
                if error:
                    slot.error_count += 1
                    slot.last_error = error
                    slot.status = "error"
                else:
                    slot.status = "completed"

                await self.db.conn.execute(
                    """UPDATE thread_state SET status=?, finished_at=?, error_count=?, last_error=?
                       WHERE site=? AND session_id=?""",
                    (slot.status, slot.finished_at, slot.error_count, slot.last_error or "", site, session_id),
                )
                await self.db.conn.commit()

            if site in self._semaphores:
                try:
                    self._semaphores[site].release()
                except ValueError:
                    pass

            logger.debug(f"Thread released: {site}/{session_id} status={slot.status if slot else '?'}")

    async def _update_db_status(self, site: str, session_id: str, status: str):
        await self.db.conn.execute(
            "UPDATE thread_state SET status=? WHERE site=? AND session_id=?",
            (status, site, session_id),
        )
        await self.db.conn.commit()

    async def get_pool_stats(self, site: str = None) -> dict:
        stats = {}
        for s, pool in self._pools.items():
            if site and s != site:
                continue
            counts = {"pending": 0, "starting": 0, "running": 0, "completed": 0, "error": 0}
            for slot in pool.values():
                counts[slot.status] = counts.get(slot.status, 0) + 1
            sem = self._semaphores.get(s)
            max_conc = getattr(sem, '_value', 0) if sem else 0
            stats[s] = {
                "active": counts["running"] + counts["starting"],
                "pending": counts["pending"],
                "completed": counts["completed"],
                "errors": counts["error"],
                "max_concurrent": max_conc,
            }
        return stats if site is None else stats.get(site, {})

    async def get_active_threads(self, site: str = None) -> list[dict]:
        result = []
        for s, pool in self._pools.items():
            if site and s != site:
                continue
            for sid, slot in pool.items():
                if slot.status in ("running", "starting"):
                    result.append({
                        "site": s,
                        "session_id": sid,
                        "status": slot.status,
                        "started_at": slot.started_at,
                        "errors": slot.error_count,
                        "last_error": slot.last_error,
                    })
        result.sort(key=lambda x: x["started_at"] or 0, reverse=True)
        return result

    async def cleanup(self, site: str = None):
        async with self._lock:
            for s, pool in list(self._pools.items()):
                if site and s != site:
                    continue
                for sid, slot in list(pool.items()):
                    if slot.status in ("completed", "error"):
                        del pool[sid]
                        await self.db.conn.execute(
                            "DELETE FROM thread_state WHERE site=? AND session_id=?",
                            (s, sid),
                        )
            await self.db.conn.commit()
        logger.info(f"ThreadManager: cleanup {'all' if site is None else site}")


if __name__ == "__main__":
    import tempfile
    from db import Database

    async def _smoke():
        tmp = tempfile.mkdtemp(prefix="thread_")
        db_path = f"{tmp}/test.db"
        db = Database(db_path)
        await db.init()

        tm = ThreadManager(db)
        await tm.init()
        await tm.configure("joingy", 3)

        acquired = await tm.acquire("joingy", "sess_1")
        assert acquired
        print("  Acquired sess_1 OK")

        stats = await tm.get_pool_stats("joingy")
        assert stats["active"] == 1, f"Expected 1 active, got {stats}"
        print(f"  Stats: {stats}")

        await tm.release("joingy", "sess_1")
        stats2 = await tm.get_pool_stats("joingy")
        assert stats2["completed"] == 1, f"Expected 1 completed, got {stats2}"
        print(f"  After release: {stats2}")

        await tm.acquire("isexychat", "browser_1")
        await tm.release("isexychat", "browser_1", error="timeout")
        active = await tm.get_active_threads()
        assert len(active) == 0
        print(f"  Active threads: {len(active)}")

        stats3 = await tm.get_pool_stats()
        assert "joingy" in stats3 and "isexychat" in stats3
        print(f"  All pools: {stats3}")

        await tm.cleanup()
        stats4 = await tm.get_pool_stats()
        all_done = all(
            pool["active"] == 0 and pool["pending"] == 0
            for pool in stats4.values()
        )
        print(f"  After cleanup all done: {all_done}")

        await db.close()
        print("\n  ALL SMOKE TESTS PASSED")

    asyncio.run(_smoke())
