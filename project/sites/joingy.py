# -*- coding: utf-8 -*-
"""
Joingy bot — pure HTTP API, no browser needed.
Confirmed working: had real conversation with stranger.

Protocol:
  POST /start  -> {"randid":"xxx","vid":false,"hash":"xxx"} -> returns UID
  POST /event  -> uid=xxx&vid=false -> {"event":"connected|message|typing|disconnected"}
  POST /boop   -> uid=xxx&msg=text&vid=false -> send message
  POST /disconnect -> uid=xxx&vid=false
"""
import asyncio
import json
import time
import random
import string
import logging
import traceback
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from debug_utils import (
    DebugLogger,
    get_trace_capture,
    get_crash_tracker,
    get_state_inspector,
)

logger = logging.getLogger("joingy")
dlog = DebugLogger("joingy")
trace = get_trace_capture()
crash = get_crash_tracker()
inspector = get_state_inspector()


def rand_id(n=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def rand_hash(n=32):
    return "".join(random.choices("abcdef0123456789", k=n))


class JoingySession:
    """One Joingy conversation session."""

    def __init__(self, session_id, api_base, reply_engine, db, proxy_mgr, snap_username,
                 snap_after_n=3, poll_interval=1.0, reply_delay=(2, 6), fixed_engine=None,
                 use_proxy=True):
        self.id = session_id
        self.api_base = api_base
        self.reply_engine = reply_engine
        self.db = db
        self.proxy_mgr = proxy_mgr
        self.snap_username = snap_username
        self.snap_after_n = snap_after_n
        self.poll_interval = poll_interval
        self.reply_delay = reply_delay
        self.fixed_engine = fixed_engine
        self.use_proxy = use_proxy

        self.uid = None
        self.conv_id = f"joingy_{session_id}"
        self.messages_sent = 0
        self.messages_received = 0
        self.partner_connected = False
        self.running = False
        self.proxy = None
        self.connector = None
        self.session = None
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": "https://joingy.com/",
            "Origin": "https://joingy.com",
        }

    async def start(self):
        """Start a session: get UID from /start, then poll events."""
        import aiohttp
        if self.use_proxy and self.proxy_mgr:
            self.proxy = await self.proxy_mgr.get()
            self.connector = self.proxy_mgr.get_aiohttp_connector(self.proxy)
        else:
            self.proxy = None
            self.connector = None
        timeout = aiohttp.ClientTimeout(total=120)
        self.session = aiohttp.ClientSession(connector=self.connector, timeout=timeout)

        try:
            await self.db.init_site_stats("joingy")
            await self.db.increment_stat("joingy", "conversations_started")

            await inspector.update("joingy", str(self.id), {
                "state": "starting", "sent": 0, "recv": 0,
            })

            # Step 1: Start
            payload = {"randid": rand_id(), "vid": False, "hash": rand_hash()}
            t0 = time.monotonic()
            async with self.session.post(
                f"{self.api_base}/start",
                json=payload,
                headers={**self.headers, "Content-Type": "application/json"},
            ) as resp:
                text = await resp.text()
                elapsed = (time.monotonic() - t0) * 1000
                self.uid = text.strip().strip('"')
                trace.record("joingy", str(self.id), "req",
                             "/start", resp.status, elapsed,
                             f"uid={self.uid[:20]}")
                dlog.info("start_session", uid=self.uid[:20], status=resp.status,
                          latency_ms=round(elapsed, 1), proxy=str(self.proxy)[:80] if self.proxy else "none")

            if not self.uid or self.uid in ("ratelimit", "ban"):
                dlog.warning("start_failed", uid=self.uid, reason=self.uid)
                await self.db.set_site_error("joingy", f"Start failed: {self.uid}")
                await inspector.remove("joingy", str(self.id))
                return False

            dlog.info("session_active", uid=self.uid[:20])
            self.running = True
            await self._event_loop()
            return True

        except Exception as e:
            dlog.error("start_crash", exc=e, uid=getattr(self, 'uid', None))
            trace.record("joingy", str(self.id), "req",
                         "/start", 0, 0, error=str(e)[:200])
            await crash.record("joingy", str(self.id), e)
            await self.db.set_site_error("joingy", str(e))
            return False
        finally:
            if not self.running:
                await inspector.remove("joingy", str(self.id))
            await self.stop()

    async def _event_loop(self):
        """Poll for events and respond to messages."""
        poll_count = 0
        max_polls = 300  # ~5 min max conversation
        error_streak = 0

        while self.running and poll_count < max_polls:
            try:
                t0 = time.monotonic()
                async with self.session.post(
                    f"{self.api_base}/event",
                    data={"uid": self.uid, "vid": "false"},
                    headers=self.headers,
                ) as resp:
                    text = await resp.text()
                    elapsed = (time.monotonic() - t0) * 1000
                    if resp.status != 200:
                        trace.record("joingy", str(self.id), "poll",
                                     "/event", resp.status, elapsed,
                                     error=f"HTTP {resp.status}")
                        error_streak += 1
                    else:
                        error_streak = 0

                    if not text:
                        await asyncio.sleep(self.poll_interval)
                        poll_count += 1
                        continue

                    try:
                        event = json.loads(text)
                    except json.JSONDecodeError:
                        await asyncio.sleep(self.poll_interval)
                        poll_count += 1
                        continue

                    evt = event.get("event", "")

                    if evt == "connected":
                        self.partner_connected = True
                        dlog.info("partner_connected", uid=self.uid[:20])
                        logger.info(f"Session {self.id}: partner connected!")
                        await self.db.increment_stat("joingy", "messages_received")
                        await inspector.update("joingy", str(self.id), {
                            "state": "connected", "sent": self.messages_sent,
                            "recv": self.messages_received,
                        })
                        await asyncio.sleep(random.uniform(*self.reply_delay))
                        await self._send_opening()

                    elif evt == "message":
                        msg = event.get("val", "")
                        self.messages_received += 1
                        logger.info(f"Session {self.id}: <- {msg[:80]}")
                        await self.db.log_message("joingy", self.conv_id, "in", "", msg)
                        await self.db.add_live_log("joingy", self.conv_id, "in", "", msg)
                        await self.db.increment_stat("joingy", "messages_received")
                        await inspector.update("joingy", str(self.id), {
                            "state": "chatting", "sent": self.messages_sent,
                            "recv": self.messages_received,
                        })

                        # Reply
                        await asyncio.sleep(random.uniform(*self.reply_delay))
                        await self._reply(msg)

                    elif evt == "typing":
                        pass

                    elif evt == "disconnected":
                        logger.info(f"Session {self.id}: partner disconnected")
                        await self.db.increment_stat("joingy", "conversations_started")
                        self.reply_engine.reset(self.conv_id)
                        dlog.info("partner_disconnected", uid=self.uid[:20],
                                  sent=self.messages_sent, recv=self.messages_received)
                        break

            except asyncio.TimeoutError:
                error_streak += 1
                pass
            except Exception as e:
                error_streak += 1
                logger.debug(f"Session {self.id}: poll error: {e}")
                if error_streak >= 10:
                    dlog.warning("poll_error_streak", uid=self.uid[:20],
                                 streak=error_streak, error=str(e)[:200])
                    trace.record("joingy", str(self.id), "poll",
                                 "/event", 0, 0, error=f"streak={error_streak}: {str(e)[:200]}")
                if error_streak >= 30:
                    dlog.error("poll_abort", uid=self.uid[:20], streak=error_streak)
                    break

            poll_count += 1
            await asyncio.sleep(self.poll_interval)

    async def _send_opening(self):
        """Send the first message to start conversation."""
        replies = self.reply_engine.reply("hi", conversation_id=self.conv_id)
        for msg, cat in replies:
            await self._send(msg)
            await asyncio.sleep(random.uniform(*self.reply_delay))

    async def _reply(self, incoming_text):
        """Generate reply from fixed engine or state machine and send."""
        replies = None
        if self.fixed_engine and self.fixed_engine.is_enabled():
            fixed_reply = await self.fixed_engine.get_reply("joingy", self.uid)
            if fixed_reply is not None:
                fixed_reply = self.fixed_engine.replace_username(fixed_reply)
                replies = [(fixed_reply, "fixed_sms")]
                logger.debug(f"Session {self.id}: fixed_sms reply (uid={self.uid})")
        if replies is None:
            replies = self.reply_engine.reply(incoming_text, conversation_id=self.conv_id)
        for i, (msg, cat) in enumerate(replies):
            if i > 0:
                await asyncio.sleep(random.uniform(*self.reply_delay))
            await self._send(msg)
        if self.reply_engine.get_state(self.conv_id) == "END":
            logger.info(f"Session {self.id}: conversation ended (state=END), disconnecting")
            self.running = False
            await self._disconnect()

    async def _send(self, msg):
        """Send a message via /boop."""
        try:
            t0 = time.monotonic()
            async with self.session.post(
                f"{self.api_base}/boop",
                data={"uid": self.uid, "msg": msg, "vid": "false"},
                headers=self.headers,
            ) as resp:
                elapsed = (time.monotonic() - t0) * 1000
                if resp.status == 201:
                    self.messages_sent += 1
                    await self.db.log_message("joingy", self.conv_id, "out", "", msg)
                    await self.db.add_live_log("joingy", self.conv_id, "out", "", msg)
                    await self.db.increment_stat("joingy", "messages_sent")
                    logger.info(f"Session {self.id}: -> {msg[:80]}")
                    trace.record("joingy", str(self.id), "send",
                                 "/boop", resp.status, elapsed, msg[:80])

                    # Check if snap username was shared
                    if self.snap_username in msg:
                        await self.db.log_snap_lead("joingy", "", self.conv_id, self.messages_sent)
                        await self.db.increment_stat("joingy", "snap_shares")
                        logger.info(f"Session {self.id}: SNAP SHARED! (msg #{self.messages_sent})")
        except Exception as e:
            logger.error(f"Session {self.id}: send error: {e}")

    async def _disconnect(self):
        """Send disconnect to Joingy API."""
        if self.uid and self.session:
            try:
                async with self.session.post(
                    f"{self.api_base}/disconnect",
                    data={"uid": self.uid, "vid": "false"},
                    headers=self.headers,
                ) as r:
                    pass
            except:
                pass

    async def stop(self):
        """Disconnect and cleanup."""
        self.running = False
        if self.uid and self.session:
            try:
                async with self.session.post(
                    f"{self.api_base}/disconnect",
                    data={"uid": self.uid, "vid": "false"},
                    headers=self.headers,
                ) as r:
                    pass
            except:
                pass
        if self.proxy:
            await self.proxy_mgr.release(self.proxy, self.messages_received > 0)
        if self.session:
            await self.session.close()


class JoingyBot:
    """Manages multiple Joingy sessions."""

    def __init__(self, config, reply_engine, db, proxy_mgr, fixed_engine=None):
        self.config = config
        self.reply_engine = reply_engine
        self.db = db
        self.proxy_mgr = proxy_mgr
        self.fixed_engine = fixed_engine
        self.api_base = config.get("api_base", "https://back.joingy.com")
        self.max_sessions = config.get("max_sessions", 20)
        self.poll_interval = config.get("poll_interval_sec", 1)
        self.auto_reconnect = config.get("auto_reconnect", True)
        self.snap_username = config.get("snap_username", "username")
        self.snap_after_n = config.get("snap_share_after_n_messages", 3)
        self.use_proxy = config.get("use_proxy", True)
        self.reply_delay = (
            config.get("reply_delay_min_sec", 2),
            config.get("reply_delay_max_sec", 6),
        )

        self.sessions: dict[int, JoingySession] = {}
        self.running = False
        self._next_id = 0
        self._tasks: dict[int, asyncio.Task] = {}

    async def start(self):
        self.running = True
        await self.db.set_site_running("joingy", 1)
        logger.info(f"JoingyBot starting with max_sessions={self.max_sessions}")

        while self.running:
            active = sum(1 for s in self.sessions.values() if s.running)
            if active < self.max_sessions:
                self._next_id += 1
                sid = self._next_id
                session = JoingySession(
                    sid, self.api_base, self.reply_engine, self.db, self.proxy_mgr,
                    self.snap_username, self.snap_after_n, self.poll_interval, self.reply_delay,
                    fixed_engine=self.fixed_engine, use_proxy=self.use_proxy,
                )
                self.sessions[sid] = session
                task = asyncio.create_task(self._run_session(sid, session))
                self._tasks[sid] = task
            await asyncio.sleep(2)

    async def _run_session(self, sid, session):
        max_retries = 3
        try:
            for attempt in range(max_retries):
                try:
                    await session.start()
                    break
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    should_retry, backoff = await crash.can_retry("joingy", str(sid))
                    if attempt < max_retries - 1 and should_retry:
                        logger.warning(
                            f"Session {sid}: crash (attempt {attempt+1}/{max_retries}), "
                            f"retrying in {backoff:.0f}s: {e}"
                        )
                        if backoff > 0:
                            await asyncio.sleep(backoff)
                    else:
                        logger.error(f"Session {sid}: fatal after {attempt+1} attempts: {e}")
                        break
        finally:
            self.sessions.pop(sid, None)
            self._tasks.pop(sid, None)
            await inspector.remove("joingy", str(sid))

    async def health_check(self):
        """Remove dead sessions and report health."""
        now = time.time()
        dead = []
        for sid, session in list(self.sessions.items()):
            if not session.running:
                dead.append(sid)
            elif session.partner_connected and session.messages_received == 0:
                session.last_activity = getattr(session, 'last_activity', now)
                if now - getattr(session, 'last_activity', now) > 180:
                    logger.info(f"Health: stale session {sid} (no msgs in 3min), cleaning")
                    session.running = False
                    dead.append(sid)
        for sid in dead:
            sess = self.sessions.pop(sid, None)
            if sess:
                await sess.stop()
                await inspector.remove("joingy", str(sid))
        return {"active": sum(1 for s in self.sessions.values() if s.running),
                "dead": len(dead)}

    async def stop(self):
        self.running = False
        await self.db.set_site_running("joingy", 0)
        for session in list(self.sessions.values()):
            await session.stop()
        for task in list(self._tasks.values()):
            task.cancel()
        logger.info("JoingyBot stopped")

    def stats(self):
        return {
            "active_sessions": sum(1 for s in self.sessions.values() if s.running),
            "max_sessions": self.max_sessions,
            "total_sent": sum(s.messages_sent for s in self.sessions.values()),
            "total_received": sum(s.messages_received for s in self.sessions.values()),
        }

    def update_config(self, settings):
        if "max_sessions" in settings:
            self.max_sessions = int(settings["max_sessions"])
        if "reply_delay_min_sec" in settings and "reply_delay_max_sec" in settings:
            self.reply_delay = (float(settings["reply_delay_min_sec"]), float(settings["reply_delay_max_sec"]))
        elif "reply_delay_min" in settings and "reply_delay_max" in settings:
            self.reply_delay = (float(settings["reply_delay_min"]), float(settings["reply_delay_max"]))
        if "snap_after_n" in settings:
            self.snap_after_n = int(settings["snap_after_n"])
        if "snap_share_after_n_messages" in settings:
            self.snap_after_n = int(settings["snap_share_after_n_messages"])
        if "snap_username" in settings:
            self.snap_username = settings["snap_username"]
        if "use_proxy" in settings:
            self.use_proxy = bool(settings["use_proxy"])
        logger.info(f"JoingyBot config updated: max_sessions={self.max_sessions}, reply_delay={self.reply_delay}, snap_after_n={self.snap_after_n}")