# -*- coding: utf-8 -*-
"""
DB Reply Engine — two engines in one file.

1. DbReplyEngine — async wrapper around ReplyEngine that persists conversation
   state (GREETING, AGE_GENDER, etc.) in `db_reply_state` table. Survives restarts.

2. DBReplyEngine — sync SQLite reply bank. Stores mood+stage+trigger+reply rows
   in `reply_bank` table. Weighted lookup: exact match → LIKE → random weighted →
   fallback_engine. No async, plain sqlite3.
"""
import asyncio
import sqlite3
import random
import logging
import os
from reply_engine import ReplyEngine, GREETING, AGE_GENDER, COUNTRY, COUNTRY_REPLY, MIDDLE_CHAT, SHARE_SNAP, END

logger = logging.getLogger("db_reply_engine")

# ═══════════════════════════════════════════════════════════════════════════════
# 1. DbReplyEngine (async, wraps ReplyEngine — existing, preserved)
# ═══════════════════════════════════════════════════════════════════════════════

DB_REPLY_STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS db_reply_state (
    site TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    state TEXT DEFAULT 'GREETING',
    msg_count INTEGER DEFAULT 0,
    middle_count INTEGER DEFAULT 0,
    updated_at REAL,
    PRIMARY KEY (site, conversation_id)
);

CREATE TABLE IF NOT EXISTS db_reply_used (
    site TEXT NOT NULL,
    conversation_id TEXT NOT NULL,
    reply_hash TEXT NOT NULL,
    PRIMARY KEY (site, conversation_id, reply_hash)
);
"""


class DbReplyEngine:
    def __init__(self, db, reply_engine: ReplyEngine):
        self.db = db
        self._engine = reply_engine
        self._lock = asyncio.Lock()
        self._cache: dict[str, dict] = {}

    async def init(self):
        for stmt in DB_REPLY_STATE_SCHEMA.split(";"):
            s = stmt.strip()
            if s:
                await self.db.conn.execute(s)
        await self.db.conn.commit()

    async def reply(self, site: str, text: str, conversation_id: str = None):
        async with self._lock:
            if conversation_id is None:
                conversation_id = "default"

            key = f"{site}:{conversation_id}"
            if key not in self._cache:
                await self._load_state(site, conversation_id)

            state_info = self._cache.get(key, {})
            self._engine.conv_state[conversation_id] = state_info.get("state", GREETING)
            self._engine.conv_msg_count[conversation_id] = state_info.get("msg_count", 0)
            self._engine.conv_middle_count[conversation_id] = state_info.get("middle_count", 0)

            if conversation_id not in self._engine.conv_used:
                self._engine.conv_used[conversation_id] = set()

            result = self._engine.reply(text, conversation_id)

            await self._save_state(site, conversation_id)
            return result

    async def _load_state(self, site: str, conversation_id: str):
        cursor = await self.db.conn.execute(
            "SELECT state, msg_count, middle_count FROM db_reply_state WHERE site=? AND conversation_id=?",
            (site, conversation_id),
        )
        row = await cursor.fetchone()
        if row:
            self._cache[f"{site}:{conversation_id}"] = {
                "state": row["state"],
                "msg_count": row["msg_count"],
                "middle_count": row["middle_count"],
            }
        else:
            self._cache[f"{site}:{conversation_id}"] = {
                "state": GREETING,
                "msg_count": 0,
                "middle_count": 0,
            }

    async def _save_state(self, site: str, conversation_id: str):
        import time
        state = self._engine.conv_state.get(conversation_id, GREETING)
        msg_count = self._engine.conv_msg_count.get(conversation_id, 0)
        middle_count = self._engine.conv_middle_count.get(conversation_id, 0)
        now = time.time()

        await self.db.conn.execute(
            """INSERT INTO db_reply_state (site, conversation_id, state, msg_count, middle_count, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(site, conversation_id) DO UPDATE SET
                 state=excluded.state, msg_count=excluded.msg_count,
                 middle_count=excluded.middle_count, updated_at=?""",
            (site, conversation_id, state, msg_count, middle_count, now, now),
        )
        await self.db.conn.commit()

        key = f"{site}:{conversation_id}"
        self._cache[key] = {"state": state, "msg_count": msg_count, "middle_count": middle_count}

    def reset(self, site: str = None, conversation_id: str = None):
        if site is None:
            self._cache.clear()
            self._engine.reset(None)
            return
        if conversation_id is None:
            keys = [k for k in self._cache if k.startswith(f"{site}:")]
            for k in keys:
                del self._cache[k]
        else:
            self._cache.pop(f"{site}:{conversation_id}", None)
        self._engine.reset(conversation_id)

    async def get_stats(self) -> dict:
        cursor = await self.db.conn.execute(
            "SELECT site, state, COUNT(*) as count FROM db_reply_state GROUP BY site, state"
        )
        rows = await cursor.fetchall()
        breakdown = {}
        for r in rows:
            breakdown.setdefault(r["site"], {})[r["state"]] = r["count"]

        cursor = await self.db.conn.execute("SELECT COUNT(*) as c FROM db_reply_state")
        total = (await cursor.fetchone())["c"]
        return {"total_conversations": total, "by_site_state": breakdown}

    async def get_conversations(self, site: str = None, limit: int = 50) -> list[dict]:
        if site:
            cursor = await self.db.conn.execute(
                "SELECT * FROM db_reply_state WHERE site=? ORDER BY updated_at DESC LIMIT ?",
                (site, limit),
            )
        else:
            cursor = await self.db.conn.execute(
                "SELECT * FROM db_reply_state ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DBReplyEngine (sync, standalone reply bank — NEW)
# ═══════════════════════════════════════════════════════════════════════════════

REPLY_BANK_SCHEMA = """
CREATE TABLE IF NOT EXISTS reply_bank (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mood TEXT NOT NULL DEFAULT 'normal',
    stage TEXT NOT NULL,
    trigger TEXT NOT NULL,
    reply TEXT NOT NULL,
    weight REAL DEFAULT 1.0
);
CREATE INDEX IF NOT EXISTS idx_reply_bank_mood ON reply_bank(mood);
CREATE INDEX IF NOT EXISTS idx_reply_bank_stage ON reply_bank(stage);
CREATE INDEX IF NOT EXISTS idx_reply_bank_mood_stage ON reply_bank(mood, stage);
"""


class DBReplyEngine:
    def __init__(self, db_path: str, fallback_engine=None):
        self.db_path = db_path
        self.fallback_engine = fallback_engine
        self._rows: list[dict] = []
        self._moods: set = set()
        self._triggers: set = set()

    def ensure_schema(self):
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(REPLY_BANK_SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def reload(self):
        if not os.path.exists(self.db_path):
            self._rows = []
            self._moods = set()
            self._triggers = set()
            return

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute("SELECT id, mood, stage, trigger, reply, weight FROM reply_bank")
            self._rows = [dict(r) for r in cursor.fetchall()]
            self._moods = set(r["mood"] for r in self._rows)
            self._triggers = set(r["trigger"] for r in self._rows)
        finally:
            conn.close()

    def get_reply(self, mood: str, stage: str, incoming_msg: str) -> str | None:
        if not self._rows or not incoming_msg:
            if self.fallback_engine:
                return self.fallback_engine
            return None

        msg_lower = incoming_msg.lower().strip()

        candidates = [r for r in self._rows if r["mood"] == mood and r["stage"] == stage]
        if not candidates:
            candidates = [r for r in self._rows if r["mood"] == mood]

        if not candidates:
            if self.fallback_engine:
                return self.fallback_engine
            return None

        exact = [r for r in candidates if r["trigger"].lower().strip() == msg_lower]
        if exact:
            return self._weighted_pick(exact)

        like = [r for r in candidates if r["trigger"].lower() in msg_lower]
        if like:
            return self._weighted_pick(like)

        if self.fallback_engine:
            return self.fallback_engine

        return self._weighted_pick(candidates)

    def _weighted_pick(self, rows: list[dict]) -> str:
        if not rows:
            return None
        if len(rows) == 1:
            return rows[0]["reply"]

        total_weight = sum(r.get("weight", 1.0) for r in rows)
        if total_weight <= 0:
            return random.choice(rows)["reply"]

        r = random.uniform(0, total_weight)
        cumulative = 0.0
        for row in rows:
            cumulative += row.get("weight", 1.0)
            if r <= cumulative:
                return row["reply"]

        return rows[-1]["reply"]

    def add_row(self, mood: str, stage: str, trigger: str, reply: str, weight: float = 1.0) -> int:
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(REPLY_BANK_SCHEMA)
            cursor = conn.execute(
                "INSERT INTO reply_bank (mood, stage, trigger, reply, weight) VALUES (?, ?, ?, ?, ?)",
                (mood, stage, trigger, reply, weight),
            )
            conn.commit()
            row_id = cursor.lastrowid

            self._rows.append({
                "id": row_id,
                "mood": mood,
                "stage": stage,
                "trigger": trigger,
                "reply": reply,
                "weight": weight,
            })
            self._moods.add(mood)
            self._triggers.add(trigger)
            return row_id
        finally:
            conn.close()

    def stats(self) -> dict:
        return {
            "rows": len(self._rows),
            "moods": sorted(self._moods),
            "triggers": len(self._triggers),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Smoke test for DBReplyEngine
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import tempfile

    tmp = tempfile.mkdtemp(prefix="dbreply_")
    db_path = os.path.join(tmp, "reply_bank.db")

    engine = DBReplyEngine(db_path)
    engine.ensure_schema()

    engine.add_row("normal", "GREETING", "hi", "hello there", 2.0)
    engine.add_row("normal", "GREETING", "hey", "heyy you", 1.0)
    engine.add_row("flirty", "GREETING", "hi", "heyy cutie", 3.0)
    engine.add_row("normal", "MIDDLE_CHAT", "how are you", "im good wbu", 2.0)
    engine.add_row("normal", "MIDDLE_CHAT", "good", "niceee", 1.0)
    engine.add_row("shy", "GREETING", "hi", "h-hi...", 1.0)

    engine.reload()
    stats = engine.stats()
    assert stats["rows"] == 6
    assert len(stats["moods"]) == 3
    print(f"  Stats: {stats}")

    r = engine.get_reply("normal", "GREETING", "hi")
    assert r in ("hello there", "heyy you"), f"Got: {r}"
    print(f"  normal+GREETING+hi → {r}")

    r2 = engine.get_reply("flirty", "GREETING", "hi")
    assert r2 == "heyy cutie", f"Got: {r2}"
    print(f"  flirty+GREETING+hi → {r2}")

    r3 = engine.get_reply("shy", "GREETING", "hi")
    assert r3 == "h-hi...", f"Got: {r3}"
    print(f"  shy+GREETING+hi → {r3}")

    r4 = engine.get_reply("normal", "MIDDLE_CHAT", "hey how are you doing")
    print(f"  normal+MIDDLE_CHAT+LIKE 'how are you' → {r4}")
    assert r4 in ("im good wbu", "niceee")

    r5 = engine.get_reply("aggressive", "GREETING", "hi")
    assert r5 is None, f"Should be None (no aggressive mood), got: {r5}"
    print(f"  aggressive+GREETING+hi → None (correct)")

    row_id = engine.add_row("normal", "END", "bye", "cya bye", 1.5)
    assert row_id == 7
    print(f"  add_row returned id={row_id}")

    engine2 = DBReplyEngine(db_path)
    engine2.ensure_schema()
    engine2.reload()
    assert engine2.stats()["rows"] == 7
    print(f"  Reload from disk: {engine2.stats()['rows']} rows (OK)")

    engine3 = DBReplyEngine(":memory:", fallback_engine="FALLBACK_MSG")
    engine3.ensure_schema()
    engine3.reload()
    r6 = engine3.get_reply("normal", "GREETING", "hi")
    assert r6 == "FALLBACK_MSG", f"Got: {r6}"
    print(f"  Fallback engine: {r6}")

    print("\n  ALL DBReplyEngine SMOKE TESTS PASSED")
