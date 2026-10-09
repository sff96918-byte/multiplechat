# -*- coding: utf-8 -*-
"""
SQLite handler — tracks users, messages, snap leads, and per-site stats.
All operations are async (uses aiosqlite).
"""
import aiosqlite
import time
import json
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site TEXT NOT NULL,
    site_user_id TEXT,
    nickname TEXT,
    gender TEXT,
    country TEXT,
    msg_count INTEGER DEFAULT 0,
    snap_shared INTEGER DEFAULT 0,
    priority TEXT DEFAULT 'normal',
    first_seen REAL,
    last_seen REAL,
    UNIQUE(site, site_user_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site TEXT NOT NULL,
    conversation_id TEXT,
    direction TEXT NOT NULL,
    nickname TEXT,
    text TEXT,
    category TEXT,
    timestamp REAL
);

CREATE TABLE IF NOT EXISTS snap_leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site TEXT NOT NULL,
    nickname TEXT,
    conversation_id TEXT,
    messages_exchanged INTEGER,
    timestamp REAL
);

CREATE TABLE IF NOT EXISTS site_stats (
    site TEXT PRIMARY KEY,
    enabled INTEGER DEFAULT 0,
    running INTEGER DEFAULT 0,
    messages_sent INTEGER DEFAULT 0,
    messages_received INTEGER DEFAULT 0,
    conversations_started INTEGER DEFAULT 0,
    snap_shares INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,
    last_error TEXT,
    started_at REAL,
    updated_at REAL
);

CREATE TABLE IF NOT EXISTS site_settings (
    site TEXT PRIMARY KEY,
    max_sessions INTEGER DEFAULT 5,
    reply_delay_min REAL DEFAULT 2,
    reply_delay_max REAL DEFAULT 6,
    snap_after_n INTEGER DEFAULT 3,
    headless INTEGER DEFAULT 1,
    enabled INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS live_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site TEXT NOT NULL,
    conversation_id TEXT,
    direction TEXT NOT NULL,
    nickname TEXT,
    text TEXT,
    timestamp REAL
);

CREATE TABLE IF NOT EXISTS fixed_sms_state (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    site TEXT NOT NULL,
    session_id TEXT NOT NULL,
    folder_path TEXT NOT NULL,
    assigned_file TEXT NOT NULL,
    current_line INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(site, session_id, folder_path)
);

CREATE TABLE IF NOT EXISTS fixed_sms_file_pool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folder_path TEXT NOT NULL,
    filename TEXT NOT NULL,
    total_lines INTEGER DEFAULT 0,
    last_scanned TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(folder_path, filename)
);
"""


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def init(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        for stmt in SCHEMA.split(";"):
            s = stmt.strip()
            if s:
                await self._conn.execute(s)
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()

    @property
    def conn(self):
        if self._conn is None:
            raise RuntimeError("Database not initialized")
        return self._conn

    async def upsert_user(self, site, site_user_id, nickname="", gender="", country=""):
        now = time.time()
        await self.conn.execute(
            """INSERT INTO users (site, site_user_id, nickname, gender, country, first_seen, last_seen)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(site, site_user_id) DO UPDATE SET
                 nickname=excluded.nickname, last_seen=?""",
            (site, site_user_id, nickname, gender, country, now, now, now),
        )
        await self.conn.commit()

    async def increment_user_msg(self, site, site_user_id):
        await self.conn.execute(
            "UPDATE users SET msg_count=msg_count+1, last_seen=? WHERE site=? AND site_user_id=?",
            (time.time(), site, site_user_id),
        )
        await self.conn.commit()

    async def mark_snap_shared(self, site, site_user_id):
        await self.conn.execute(
            "UPDATE users SET snap_shared=1 WHERE site=? AND site_user_id=?",
            (site, site_user_id),
        )
        await self.conn.commit()

    async def log_message(self, site, conversation_id, direction, nickname, text, category=""):
        await self.conn.execute(
            """INSERT INTO messages (site, conversation_id, direction, nickname, text, category, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (site, conversation_id, direction, nickname, text, category, time.time()),
        )
        await self.conn.commit()

    async def log_snap_lead(self, site, nickname, conversation_id, messages_exchanged):
        await self.conn.execute(
            "INSERT INTO snap_leads (site, nickname, conversation_id, messages_exchanged, timestamp) VALUES (?, ?, ?, ?, ?)",
            (site, nickname, conversation_id, messages_exchanged, time.time()),
        )
        await self.conn.commit()

    async def get_message_count(self, site, conversation_id):
        cursor = await self.conn.execute(
            "SELECT COUNT(*) as c FROM messages WHERE site=? AND conversation_id=?",
            (site, conversation_id),
        )
        row = await cursor.fetchone()
        return row["c"] if row else 0

    async def init_site_stats(self, site):
        await self.conn.execute(
            "INSERT OR IGNORE INTO site_stats (site) VALUES (?)",
            (site,),
        )
        await self.conn.commit()

    async def set_site_running(self, site, running):
        now = time.time()
        await self.conn.execute(
            "UPDATE site_stats SET running=?, started_at=CASE WHEN ?=1 THEN ? ELSE started_at END, updated_at=? WHERE site=?",
            (running, running, now, now, site),
        )
        await self.conn.commit()

    async def increment_stat(self, site, stat_name, amount=1):
        await self.conn.execute(
            f"UPDATE site_stats SET {stat_name}={stat_name}+?, updated_at=? WHERE site=?",
            (amount, time.time(), site),
        )
        await self.conn.commit()

    async def set_site_error(self, site, error):
        await self.conn.execute(
            "UPDATE site_stats SET errors=errors+1, last_error=?, updated_at=? WHERE site=?",
            (error[:200], time.time(), site),
        )
        await self.conn.commit()

    async def get_all_stats(self):
        cursor = await self.conn.execute("SELECT * FROM site_stats")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_recent_leads(self, limit=20):
        cursor = await self.conn.execute(
            "SELECT * FROM snap_leads ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_total_leads(self):
        cursor = await self.conn.execute("SELECT COUNT(*) as c FROM snap_leads")
        row = await cursor.fetchone()
        return row["c"] if row else 0

    async def get_total_messages(self):
        cursor = await self.conn.execute("SELECT COUNT(*) as c FROM messages")
        row = await cursor.fetchone()
        return row["c"] if row else 0

    async def get_recent_messages(self, limit=50):
        cursor = await self.conn.execute(
            "SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_messages_by_site(self, site, limit=100):
        cursor = await self.conn.execute(
            "SELECT * FROM messages WHERE site=? ORDER BY timestamp DESC LIMIT ?", (site, limit)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_leads_by_site(self, site, limit=50):
        cursor = await self.conn.execute(
            "SELECT * FROM snap_leads WHERE site=? ORDER BY timestamp DESC LIMIT ?", (site, limit)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_total_leads_by_site(self, site):
        cursor = await self.conn.execute(
            "SELECT COUNT(*) as c FROM snap_leads WHERE site=?", (site,)
        )
        row = await cursor.fetchone()
        return row["c"] if row else 0

    async def get_total_messages_by_site(self, site):
        cursor = await self.conn.execute(
            "SELECT COUNT(*) as c FROM messages WHERE site=?", (site,)
        )
        row = await cursor.fetchone()
        return row["c"] if row else 0

    async def get_total_users_by_site(self, site):
        cursor = await self.conn.execute(
            "SELECT COUNT(*) as c FROM users WHERE site=?", (site,)
        )
        row = await cursor.fetchone()
        return row["c"] if row else 0

    async def get_conversation_count_by_site(self, site):
        cursor = await self.conn.execute(
            "SELECT COUNT(DISTINCT conversation_id) as c FROM messages WHERE site=?", (site,)
        )
        row = await cursor.fetchone()
        return row["c"] if row else 0

    async def get_all_sites_summary(self):
        cursor = await self.conn.execute("SELECT DISTINCT site FROM site_stats")
        rows = await cursor.fetchall()
        sites = [r["site"] for r in rows]
        summary = {}
        for site in sites:
            cursor = await self.conn.execute(
                "SELECT * FROM site_stats WHERE site=?", (site,)
            )
            row = await cursor.fetchone()
            stats = dict(row) if row else {}
            stats["total_leads"] = await self.get_total_leads_by_site(site)
            stats["total_messages"] = await self.get_total_messages_by_site(site)
            stats["total_users"] = await self.get_total_users_by_site(site)
            stats["total_conversations"] = await self.get_conversation_count_by_site(site)
            summary[site] = stats
        return summary

    async def init_site_settings(self, site, defaults=None):
        if defaults is None:
            defaults = {}
        await self.conn.execute(
            """INSERT OR IGNORE INTO site_settings (site, max_sessions, reply_delay_min, reply_delay_max, snap_after_n, headless, enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (site, defaults.get("max_sessions", 5), defaults.get("reply_delay_min", 2),
             defaults.get("reply_delay_max", 6), defaults.get("snap_after_n", 3),
             defaults.get("headless", 1), defaults.get("enabled", 1)),
        )
        await self.conn.commit()

    async def get_site_settings(self, site):
        cursor = await self.conn.execute(
            "SELECT * FROM site_settings WHERE site=?", (site,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_all_site_settings(self):
        cursor = await self.conn.execute("SELECT * FROM site_settings")
        rows = await cursor.fetchall()
        return {r["site"]: dict(r) for r in rows}

    async def update_site_settings(self, site, settings):
        fields = []
        values = []
        for k in ("max_sessions", "reply_delay_min", "reply_delay_max", "snap_after_n", "headless", "enabled"):
            if k in settings:
                fields.append(f"{k}=?")
                values.append(settings[k])
        if not fields:
            return
        values.append(site)
        await self.conn.execute(
            f"UPDATE site_settings SET {','.join(fields)} WHERE site=?", values
        )
        await self.conn.commit()

    async def add_live_log(self, site, conversation_id, direction, nickname, text):
        await self.conn.execute(
            """INSERT INTO live_logs (site, conversation_id, direction, nickname, text, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (site, conversation_id, direction, nickname, text, time.time()),
        )
        await self.conn.commit()

    async def get_live_logs(self, site=None, limit=100):
        if site:
            cursor = await self.conn.execute(
                "SELECT * FROM live_logs WHERE site=? ORDER BY id DESC LIMIT ?", (site, limit)
            )
        else:
            cursor = await self.conn.execute(
                "SELECT * FROM live_logs ORDER BY id DESC LIMIT ?", (limit,)
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_live_logs_since(self, site, last_id, limit=100):
        if site and site != "all":
            cursor = await self.conn.execute(
                "SELECT * FROM live_logs WHERE site=? AND id>? ORDER BY id ASC LIMIT ?", (site, last_id, limit)
            )
        else:
            cursor = await self.conn.execute(
                "SELECT * FROM live_logs WHERE id>? ORDER BY id ASC LIMIT ?", (last_id, limit)
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def clear_live_logs(self, site=None):
        if site:
            await self.conn.execute("DELETE FROM live_logs WHERE site=?", (site,))
        else:
            await self.conn.execute("DELETE FROM live_logs")
        await self.conn.commit()

    async def get_global_settings(self):
        cursor = await self.conn.execute("SELECT * FROM site_settings")
        rows = await cursor.fetchall()
        return {r["site"]: dict(r) for r in rows}

    # ═══ Fixed SMS State ═══
    async def get_session_assignment(self, site: str, session_id: str, folder_path: str) -> dict | None:
        """Get the file assignment + current line for a session."""
        cursor = await self.conn.execute(
            "SELECT * FROM fixed_sms_state WHERE site=? AND session_id=? AND folder_path=?",
            (site, session_id, folder_path),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def set_session_assignment(self, site: str, session_id: str, folder_path: str,
                                     assigned_file: str, current_line: int = 0) -> None:
        """Upsert a session-to-file assignment."""
        await self.conn.execute(
            """INSERT INTO fixed_sms_state (site, session_id, folder_path, assigned_file, current_line, created_at, last_updated)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
               ON CONFLICT(site, session_id, folder_path) DO UPDATE SET
                 assigned_file=excluded.assigned_file,
                 current_line=excluded.current_line,
                 last_updated=CURRENT_TIMESTAMP""",
            (site, session_id, folder_path, assigned_file, current_line),
        )
        await self.conn.commit()

    async def update_session_line(self, site: str, session_id: str, folder_path: str, line_no: int) -> None:
        """Advance the line pointer for a session."""
        await self.conn.execute(
            "UPDATE fixed_sms_state SET current_line=?, last_updated=CURRENT_TIMESTAMP WHERE site=? AND session_id=? AND folder_path=?",
            (line_no, site, session_id, folder_path),
        )
        await self.conn.commit()

    async def get_folder_assignments(self, folder_path: str) -> list[dict]:
        """Get all session assignments for a folder."""
        cursor = await self.conn.execute(
            "SELECT * FROM fixed_sms_state WHERE folder_path=?",
            (folder_path,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def clear_folder_assignments(self, folder_path: str) -> None:
        """Clear all session assignments for a folder (used on folder change)."""
        await self.conn.execute(
            "DELETE FROM fixed_sms_state WHERE folder_path=?",
            (folder_path,),
        )
        await self.conn.commit()

    async def upsert_file_pool(self, folder_path: str, files: list[dict]) -> None:
        """Bulk upsert file pool entries. files = [{"filename": ..., "total_lines": ...}, ...]."""
        for f in files:
            await self.conn.execute(
                """INSERT INTO fixed_sms_file_pool (folder_path, filename, total_lines, last_scanned)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(folder_path, filename) DO UPDATE SET
                     total_lines=excluded.total_lines,
                     last_scanned=CURRENT_TIMESTAMP""",
                (folder_path, f["filename"], f["total_lines"]),
            )
        await self.conn.commit()

    async def get_file_pool(self, folder_path: str) -> list[dict]:
        """Get all files in the pool for a folder."""
        cursor = await self.conn.execute(
            "SELECT * FROM fixed_sms_file_pool WHERE folder_path=? ORDER BY filename",
            (folder_path,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]