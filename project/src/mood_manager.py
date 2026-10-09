# -*- coding: utf-8 -*-
"""
Mood Manager — tone/sentiment control for bot replies.

Tracks a per-site "mood" that influences reply style:
  - FLIRTY  → playful, teasing, suggestive
  - DIRECT  → straightforward, no games
  - SHY     → hesitant, blushing, soft
  - AGGRESSIVE → dominant, provocative
  - RANDOM  → picks randomly each reply

Moods can be auto-cycled or locked. The mood is used by reply engines
to filter/pick appropriate templates. Persisted in `mood_state` table.
"""
import asyncio
import random
import logging
from enum import Enum

logger = logging.getLogger("mood_manager")


class Mood(str, Enum):
    FLIRTY = "FLIRTY"
    DIRECT = "DIRECT"
    SHY = "SHY"
    AGGRESSIVE = "AGGRESSIVE"
    RANDOM = "RANDOM"


MOOD_CYCLE = [Mood.FLIRTY, Mood.DIRECT, Mood.SHY, Mood.AGGRESSIVE]
NON_RANDOM_MOODS = [Mood.FLIRTY, Mood.DIRECT, Mood.SHY, Mood.AGGRESSIVE]

MOOD_SCHEMA = """
CREATE TABLE IF NOT EXISTS mood_state (
    site TEXT PRIMARY KEY,
    current_mood TEXT DEFAULT 'RANDOM',
    auto_cycle INTEGER DEFAULT 1,
    cycle_interval INTEGER DEFAULT 5,
    updated_at REAL
);
"""


class MoodManager:
    def __init__(self, db):
        self.db = db
        self._lock = asyncio.Lock()
        self._cache: dict[str, dict] = {}

    async def init(self):
        for stmt in MOOD_SCHEMA.split(";"):
            s = stmt.strip()
            if s:
                await self.db.conn.execute(s)
        await self.db.conn.commit()

        cursor = await self.db.conn.execute("SELECT * FROM mood_state")
        rows = await cursor.fetchall()
        for r in rows:
            self._cache[r["site"]] = {
                "current_mood": r["current_mood"],
                "auto_cycle": bool(r["auto_cycle"]),
                "cycle_interval": r["cycle_interval"],
            }
        logger.info(f"MoodManager: loaded {len(self._cache)} site moods")

    async def get_mood(self, site: str) -> str:
        if site not in self._cache:
            await self._init_site(site)

        info = self._cache[site]
        mood = info["current_mood"]
        if mood == Mood.RANDOM:
            return random.choice(NON_RANDOM_MOODS)
        return mood

    async def set_mood(self, site: str, mood: str) -> None:
        import time
        mood = mood.upper()
        if mood not in [m.value for m in Mood]:
            raise ValueError(f"Invalid mood: {mood}. Valid: {[m.value for m in Mood]}")

        now = time.time()
        await self.db.conn.execute(
            """INSERT INTO mood_state (site, current_mood, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(site) DO UPDATE SET current_mood=?, updated_at=?""",
            (site, mood, now, mood, now),
        )
        await self.db.conn.commit()
        self._cache.setdefault(site, {})["current_mood"] = mood
        logger.info(f"Mood: {site} → {mood}")

    async def set_auto_cycle(self, site: str, enabled: bool, interval: int = 5) -> None:
        import time
        now = time.time()
        await self.db.conn.execute(
            """INSERT INTO mood_state (site, auto_cycle, cycle_interval, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(site) DO UPDATE SET auto_cycle=?, cycle_interval=?, updated_at=?""",
            (site, int(enabled), interval, now, int(enabled), interval, now),
        )
        await self.db.conn.commit()
        info = self._cache.setdefault(site, {})
        info["auto_cycle"] = enabled
        info["cycle_interval"] = interval
        logger.info(f"Mood auto-cycle: {site} → {'ON' if enabled else 'OFF'} (interval={interval})")

    async def cycle(self, site: str) -> str:
        async with self._lock:
            if site not in self._cache:
                await self._init_site(site)

            info = self._cache[site]
            if not info.get("auto_cycle"):
                return info.get("current_mood", Mood.RANDOM)

            current = info.get("current_mood", Mood.RANDOM)
            if current == Mood.RANDOM:
                next_mood = random.choice(NON_RANDOM_MOODS)
            else:
                try:
                    idx = MOOD_CYCLE.index(Mood(current))
                    next_mood = MOOD_CYCLE[(idx + 1) % len(MOOD_CYCLE)]
                except (ValueError, IndexError):
                    next_mood = Mood.FLIRTY

            await self.set_mood(site, next_mood.value)
            return next_mood.value

    async def get_all_moods(self) -> dict:
        result = {}
        for site, info in self._cache.items():
            result[site] = {
                "mood": info.get("current_mood", Mood.RANDOM),
                "auto_cycle": info.get("auto_cycle", True),
                "cycle_interval": info.get("cycle_interval", 5),
            }
        return result

    async def _init_site(self, site: str):
        import time
        await self.db.conn.execute(
            "INSERT OR IGNORE INTO mood_state (site, current_mood, auto_cycle, cycle_interval, updated_at) VALUES (?, ?, ?, ?, ?)",
            (site, Mood.RANDOM, 1, 5, time.time()),
        )
        await self.db.conn.commit()
        self._cache[site] = {"current_mood": Mood.RANDOM, "auto_cycle": True, "cycle_interval": 5}


if __name__ == "__main__":
    import tempfile
    from db import Database

    async def _smoke():
        tmp = tempfile.mkdtemp(prefix="mood_")
        db_path = f"{tmp}/test.db"
        db = Database(db_path)
        await db.init()

        mm = MoodManager(db)
        await mm.init()

        mood = await mm.get_mood("joingy")
        assert mood in NON_RANDOM_MOODS, f"Invalid mood: {mood}"
        print(f"  Default mood (joingy): {mood}")

        await mm.set_mood("joingy", "SHY")
        assert await mm.get_mood("joingy") == "SHY"
        print("  Set SHY OK")

        await mm.set_auto_cycle("joingy", True, 1)
        mood2 = await mm.cycle("joingy")
        assert mood2 != "SHY", f"Expected cycled mood, got {mood2}"
        print(f"  Cycled: {mood2}")

        await mm.set_mood("isexychat", "AGGRESSIVE")
        moods = await mm.get_all_moods()
        assert "joingy" in moods and "isexychat" in moods
        print(f"  All moods: {moods}")

        await db.close()
        print("\n  ALL SMOKE TESTS PASSED")

    asyncio.run(_smoke())
