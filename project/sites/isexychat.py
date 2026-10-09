# -*- coding: utf-8 -*-
"""
iSexyChat bot — Playwright browser automation.
KiwiIRC web client at chat.isexychat.com.
IRC over WebSocket gateway (browser handles WebSocket naturally).
"""
import asyncio
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

logger = logging.getLogger("isexychat")
dlog = DebugLogger("isexychat")
trace = get_trace_capture()
crash = get_crash_tracker()
inspector = get_state_inspector()


def rand_nick(n=5):
    return "Guest" + "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


class IsexychatSession:
    """One Playwright browser session for iSexyChat."""

    def __init__(self, session_id, url, reply_engine, db, channel, headless=True,
                 snap_username="username", snap_after_n=3, reply_delay=(2, 6), fixed_engine=None,
                 proxy_mgr=None, use_proxy=True):
        self.id = session_id
        self.url = url
        self.reply_engine = reply_engine
        self.db = db
        self.channel = channel
        self.headless = headless
        self.snap_username = snap_username
        self.snap_after_n = snap_after_n
        self.reply_delay = reply_delay
        self.fixed_engine = fixed_engine
        self.proxy_mgr = proxy_mgr
        self.use_proxy = use_proxy

        self.conv_id = f"isexychat_{session_id}"
        self.messages_sent = 0
        self.messages_received = 0
        self.running = False
        self.browser = None
        self.context = None
        self.page = None
        self.proxy = None
        self._last_messages = set()
        self._nick = None

    async def start(self):
        from playwright.async_api import async_playwright

        await self.db.init_site_stats("isexychat")
        await self.db.increment_stat("isexychat", "conversations_started")

        await inspector.update("isexychat", str(self.id), {
            "state": "launching", "sent": 0, "recv": 0,
        })
        dlog.info("session_starting", session_id=str(self.id), url=self.url[:50])

        try:
            async with async_playwright() as p:
                t0 = time.monotonic()

                proxy_config = None
                if self.use_proxy and self.proxy_mgr:
                    self.proxy = await self.proxy_mgr.get()
                    if self.proxy:
                        proxy_config = {
                            "server": f"{self.proxy.protocol}://{self.proxy.host}:{self.proxy.port}",
                        }
                        if self.proxy.username:
                            proxy_config["username"] = self.proxy.username
                        if self.proxy.password:
                            proxy_config["password"] = self.proxy.password
                        dlog.info("using_proxy", session_id=str(self.id),
                                  server=proxy_config["server"])

                self.browser = await p.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
                )
                context_kwargs = {
                    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "viewport": {"width": 1280, "height": 720},
                    "ignore_https_errors": True,
                }
                if proxy_config:
                    context_kwargs["proxy"] = proxy_config
                self.context = await self.browser.new_context(**context_kwargs)
                await self.context.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                )
                self.page = await self.context.new_page()
                launch_ms = (time.monotonic() - t0) * 1000
                dlog.info("browser_launched", session_id=str(self.id),
                          headless=self.headless, launch_ms=round(launch_ms, 1))

                self.running = True
                try:
                    await self._connect()
                    await inspector.update("isexychat", str(self.id), {
                        "state": "chatting", "sent": self.messages_sent,
                        "recv": self.messages_received,
                    })
                    await self._chat_loop()
                except Exception as e:
                    logger.error(f"Session {self.id}: {e}")
                    dlog.error("session_crash", exc=e, session_id=str(self.id),
                               sent=self.messages_sent, recv=self.messages_received)
                    await crash.record("isexychat", str(self.id), e)
                    await self.db.set_site_error("isexychat", str(e))
                finally:
                    await self._cleanup()
        except Exception as e:
            dlog.error("playwright_init_crash", exc=e)
            await crash.record("isexychat", str(self.id), e)
            await self.db.set_site_error("isexychat", str(e))
        finally:
            await inspector.remove("isexychat", str(self.id))

    async def _connect(self):
        """Navigate to KiwiIRC, fill nick, click Start."""
        logger.info(f"Session {self.id}: navigating to {self.url}")
        await self.page.goto(self.url, wait_until="networkidle", timeout=45000)
        await asyncio.sleep(3)

        self._nick = rand_nick()
        logger.info(f"Session {self.id}: using nick {self._nick}")

        # Fill nickname — KiwiIRC uses first text input
        inputs = await self.page.query_selector_all("input[type='text']")
        if inputs:
            await inputs[0].click()
            await inputs[0].fill("")
            await asyncio.sleep(0.5)
            await inputs[0].type(self._nick, delay=50)
            await asyncio.sleep(1)

        # Fill channel if there's a second text input
        if len(inputs) >= 2:
            await inputs[1].click()
            await inputs[1].fill("")
            await asyncio.sleep(0.3)
            await inputs[1].type(self.channel, delay=30)
            await asyncio.sleep(0.5)

        # Click Start button — wait for it to be enabled
        logger.info(f"Session {self.id}: clicking Start...")
        try:
            start_btn = await self.page.wait_for_selector(
                "button[type='submit']:not([disabled])", timeout=15000
            )
            await start_btn.click()
        except Exception:
            # Fallback: try clicking by class
            try:
                await self.page.click(".u-button.u-button-primary", timeout=5000)
            except:
                logger.warning(f"Session {self.id}: could not click Start button")

        # Wait for chat to load
        logger.info(f"Session {self.id}: waiting for chat to load...")
        for _ in range(30):
            await asyncio.sleep(2)
            msg_input = await self.page.query_selector(
                ".kiwi-inputbar-input, textarea.kiwi-inputbar-input, "
                ".kiwi-controlinput-inner input, .kiwi-inputbar textarea"
            )
            if msg_input:
                logger.info(f"Session {self.id}: chat loaded!")
                return

        logger.warning(f"Session {self.id}: chat did not load in time")

    async def _chat_loop(self):
        """Read messages from DOM, reply via input."""
        poll_count = 0
        max_polls = 600  # ~20 min max

        while self.running and poll_count < max_polls:
            try:
                # Read latest messages from DOM
                messages = await self.page.evaluate("""() => {
                    const msgs = document.querySelectorAll(
                        '.kiwi-messagelist-message, .kiwi-messagelist-body'
                    );
                    const result = [];
                    msgs.forEach(m => {
                        const nickEl = m.querySelector('.kiwi-messagelist-nick');
                        const bodyEl = m.querySelector('.kiwi-messagelist-body') || m;
                        const nick = nickEl ? nickEl.textContent.trim() : '';
                        const text = bodyEl ? bodyEl.textContent.trim() : '';
                        if (nick && text) result.push({nick, text});
                    });
                    return result.slice(-20);
                }""")

                for msg in messages:
                    nick = msg.get("nick", "")
                    text = msg.get("text", "")
                    msg_key = f"{nick}:{text}"

                    # Skip our own messages
                    if nick == self._nick:
                        continue

                    # Skip already processed
                    if msg_key in self._last_messages:
                        continue

                    # Skip server messages
                    if not text or len(text) < 1:
                        continue

                    self._last_messages.add(msg_key)
                    self.messages_received += 1
                    logger.info(f"Session {self.id}: <- {nick}: {text[:80]}")
                    await self.db.log_message("isexychat", self.conv_id, "in", nick, text)
                    await self.db.add_live_log("isexychat", self.conv_id, "in", nick, text)
                    await self.db.increment_stat("isexychat", "messages_received")

                    # Reply
                    await asyncio.sleep(random.uniform(*self.reply_delay))
                    replies = None
                    if self.fixed_engine and self.fixed_engine.is_enabled():
                        fixed_reply = await self.fixed_engine.get_reply("isexychat", self.conv_id)
                        if fixed_reply is not None:
                            fixed_reply = self.fixed_engine.replace_username(fixed_reply)
                            replies = [(fixed_reply, "fixed_sms")]
                            logger.debug(f"Session {self.id}: fixed_sms reply")
                    if replies is None:
                        replies = self.reply_engine.reply(text, conversation_id=self.conv_id)
                    for i, (r_msg, r_cat) in enumerate(replies):
                        if i > 0:
                            await asyncio.sleep(random.uniform(*self.reply_delay))
                        await self._send(r_msg)
                    if self.reply_engine.get_state(self.conv_id) == "END":
                        logger.info(f"Session {self.id}: conversation ended (state=END)")
                        self.running = False

            except Exception as e:
                logger.debug(f"Session {self.id}: poll error: {e}")

            poll_count += 1
            await asyncio.sleep(1)

    async def _send(self, msg):
        """Type and send a message in the chat input."""
        try:
            msg_input = await self.page.query_selector(
                ".kiwi-inputbar-input, textarea.kiwi-inputbar-input, "
                ".kiwi-controlinput-inner input, .kiwi-inputbar textarea"
            )
            if msg_input:
                await msg_input.fill(msg)
                await msg_input.press("Enter")
                self.messages_sent += 1
                await self.db.log_message("isexychat", self.conv_id, "out", self._nick, msg)
                await self.db.add_live_log("isexychat", self.conv_id, "out", self._nick, msg)
                await self.db.increment_stat("isexychat", "messages_sent")
                logger.info(f"Session {self.id}: -> {msg[:80]}")

                if self.snap_username in msg:
                    await self.db.log_snap_lead("isexychat", "", self.conv_id, self.messages_sent)
                    await self.db.increment_stat("isexychat", "snap_shares")
                    logger.info(f"Session {self.id}: SNAP SHARED!")
        except Exception as e:
            logger.error(f"Session {self.id}: send error: {e}")

    async def _cleanup(self):
        self.running = False
        self.reply_engine.reset(self.conv_id)
        if self.proxy and self.proxy_mgr:
            await self.proxy_mgr.release(self.proxy, self.messages_received > 0)
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
        except:
            pass
        logger.info(f"Session {self.id}: cleaned up")


class IsexychatBot:
    """Manages multiple iSexyChat Playwright sessions."""

    def __init__(self, config, reply_engine, db, proxy_mgr=None, fixed_engine=None):
        self.config = config
        self.reply_engine = reply_engine
        self.db = db
        self.fixed_engine = fixed_engine
        self.url = config.get("url", "https://chat.isexychat.com/")
        self.max_sessions = config.get("max_sessions", 5)
        self.channel = config.get("channel", "#ifap")
        self.headless = config.get("headless", True)
        self.use_proxy = config.get("use_proxy", True)
        self.proxy_mgr = proxy_mgr
        self.snap_username = config.get("snap_username", "username")
        self.snap_after_n = config.get("snap_share_after_n_messages", 3)
        self.reply_delay = (
            config.get("reply_delay_min_sec", 2),
            config.get("reply_delay_max_sec", 6),
        )

        self.sessions: dict[int, IsexychatSession] = {}
        self.running = False
        self._next_id = 0
        self._tasks: dict[int, asyncio.Task] = {}

    async def start(self):
        self.running = True
        await self.db.set_site_running("isexychat", 1)
        logger.info(f"IsexychatBot starting with max_sessions={self.max_sessions}")

        while self.running:
            active = sum(1 for s in self.sessions.values() if s.running)
            if active < self.max_sessions:
                self._next_id += 1
                sid = self._next_id
                session = IsexychatSession(
                    sid, self.url, self.reply_engine, self.db,
                    self.channel, self.headless, self.snap_username,
                    self.snap_after_n, self.reply_delay,
                    fixed_engine=self.fixed_engine,
                    proxy_mgr=self.proxy_mgr,
                    use_proxy=self.use_proxy,
                )
                self.sessions[sid] = session
                task = asyncio.create_task(self._run_session(sid, session))
                self._tasks[sid] = task
            await asyncio.sleep(5)

    async def _run_session(self, sid, session):
        max_retries = 2
        try:
            for attempt in range(max_retries):
                try:
                    await session.start()
                    break
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    should_retry, backoff = await crash.can_retry("isexychat", str(sid))
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
            await inspector.remove("isexychat", str(sid))

    async def health_check(self):
        """Remove dead sessions and report health."""
        dead = []
        for sid, session in list(self.sessions.items()):
            if not session.running:
                dead.append(sid)
            elif getattr(session, '_last_messages', None) and len(session._last_messages) > 200:
                session._last_messages = set(list(session._last_messages)[-50:])
        for sid in dead:
            sess = self.sessions.pop(sid, None)
            if sess:
                session.running = False
                await inspector.remove("isexychat", str(sid))
        return {"active": sum(1 for s in self.sessions.values() if s.running),
                "dead": len(dead)}

    async def stop(self):
        self.running = False
        await self.db.set_site_running("isexychat", 0)
        for session in list(self.sessions.values()):
            session.running = False
        for task in list(self._tasks.values()):
            task.cancel()
        logger.info("IsexychatBot stopped")

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
        if "headless" in settings:
            self.headless = bool(int(settings["headless"]))
        logger.info(f"IsexychatBot config updated: max_sessions={self.max_sessions}, reply_delay={self.reply_delay}, snap_after_n={self.snap_after_n}, headless={self.headless}")