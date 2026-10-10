"""EVA Bot — Mood-based Professional Desktop Dashboard (PyQt6).

HOME-এ ২টা MOOD — যেটা select করবে সেটার জন্য সম্পূর্ণ আলাদা dashboard খুলবে:

  🌐 LIVE BROWSER MOOD  — ব্রাউজার চোখের সামনে চলবে, বট লাইভ auto-reply করবে,
                          browser-এর session auto-save হবে (প্রতি 60s)।
  🔑 SESSION CHAT MOOD  — Session পেজে ২টা অপশন:
                          (1) লাইভ ব্রাউজার চালু করে session collect
                          (2) পুরনো saved session দিয়ে চ্যাট শুরু

Runs standalone:   python -m eva.gui.dashboard
Frozen exe:        built by build_exe.bat (PyInstaller, EVA_Dashboard.spec)
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ..paths import project_root

ROOT = project_root()
sys.path.insert(0, str(ROOT))

CONFIG_PATH = ROOT / "configs" / "chitchat_bot.json"
CONFIG_EXAMPLE = ROOT / "configs" / "chitchat_bot.example.json"
SESSION_PATH = ROOT / "configs" / "session.json"
ICON_PATH = ROOT / "eva" / "brain" / "data" / "chitchat-bot.ico"
DATA_DIR = ROOT / "eva" / "brain" / "data"

# ----------------------------------------------------------------- theme
C_BG = "#0B0E14"
C_PANEL = "#11151F"
C_PANEL_2 = "#161B28"
C_BORDER = "#232B3A"
C_TEXT = "#E6EAF2"
C_TEXT_DIM = "#8A93A6"
C_ACCENT = "#8B5CF6"
C_GREEN = "#00D68F"
C_RED = "#FF5555"
C_AMBER = "#FFC107"
C_BLUE = "#4DA3FF"
C_ORANGE = "#FB923C"

QSS = f"""
* {{ font-family: 'Segoe UI', sans-serif; }}
QMainWindow, QWidget {{ background-color: {C_BG}; color: {C_TEXT}; }}
QLabel {{ color: {C_TEXT}; background: transparent; }}
QGroupBox {{
    font-size: 13px; font-weight: 700; color: {C_TEXT};
    border: 1px solid {C_BORDER}; border-radius: 14px;
    margin-top: 14px; padding: 14px;
    background-color: {C_PANEL};
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    padding: 0 10px; color: {C_TEXT_DIM};
}}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: #1A2130; border: 1px solid {C_BORDER};
    border-radius: 9px; padding: 7px; color: {C_TEXT};
    selection-background-color: {C_ACCENT};
}}
QComboBox QAbstractItemView {{ background: {C_PANEL_2}; color: {C_TEXT};
    selection-background-color: {C_ACCENT}; }}
QPushButton {{
    background-color: {C_PANEL_2}; color: {C_TEXT}; border: 1px solid {C_BORDER};
    border-radius: 9px; padding: 9px 16px; font-size: 13px; font-weight: 600;
}}
QPushButton:hover {{ background-color: #1D2434; border-color: {C_ACCENT}; }}
QPushButton:disabled {{ color: {C_TEXT_DIM}; }}
QPushButton#startBtn {{
    background-color: {C_GREEN}; color: #04140E; border: none;
    font-size: 15px; font-weight: 800; padding: 12px;
}}
QPushButton#startBtn:hover {{ background-color: #22e6a5; }}
QPushButton#stopBtn {{
    background-color: {C_RED}; color: #fff; border: none;
    font-size: 15px; font-weight: 800; padding: 12px;
}}
QPushButton#stopBtn:hover {{ background-color: #ff7070; }}
QPushButton#launchBtn {{ border-color: {C_ACCENT}; color: {C_ACCENT}; }}
QPushButton#moodCard {{
    background-color: {C_PANEL}; border: 2px solid {C_BORDER};
    border-radius: 18px; padding: 24px; text-align: left;
    font-size: 18px; font-weight: 800;
}}
QPushButton#moodCard:hover {{ border-color: {C_ACCENT}; background-color: {C_PANEL_2}; }}
QPushButton#backBtn {{ color: {C_TEXT_DIM}; border: none; font-weight: 700; padding: 6px 12px; }}
QPushButton#backBtn:hover {{ color: {C_ACCENT}; }}
QTextEdit {{
    background-color: #0A0D13; border: 1px solid {C_BORDER};
    border-radius: 10px; padding: 8px; color: #9FB3C8;
    font-family: 'Consolas', monospace; font-size: 12px;
}}
QCheckBox {{ spacing: 7px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px; border-radius: 4px;
    border: 1px solid {C_BORDER}; background: #1A2130;
}}
QCheckBox::indicator:checked {{ background: {C_ACCENT}; border-color: {C_ACCENT}; }}
QFrame#sidebar {{ background: {C_PANEL}; border-right: 1px solid {C_BORDER}; }}
QLabel#brand {{ font-size: 26px; font-weight: 800; }}
QLabel#hdr {{ font-size: 22px; font-weight: 700; }}
QLabel#dim {{ color: {C_TEXT_DIM}; font-size: 12px; }}
QLabel#statVal {{ font-size: 17px; font-weight: 700; }}
QLabel#statLbl {{ color: {C_TEXT_DIM}; font-size: 11px; }}
QLabel#homeSub {{ color: {C_TEXT_DIM}; font-size: 14px; }}
"""


# ------------------------------------------------------------- logging → GUI

class QueueLogHandler(logging.Handler):
    def __init__(self, q: "queue.Queue[str]") -> None:
        super().__init__()
        self.q = q
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s",
                                            datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.q.put_nowait(self.format(record))
        except Exception:
            pass


# ------------------------------------------------------------- bot worker

class BotWorker:
    """Runs the asyncio bot in a background thread; state read via snapshot().

    mode: "session" = configs/session.json → headless WS chat
          "browser" = লাইভ CDP browser থেকে cookies → session auto-save সহ চ্যাট
    """

    def __init__(self) -> None:
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.chat_loop = None          # WsChatLoop
        self.api = None
        self.thread: Optional[threading.Thread] = None
        self.error: str = ""
        self.mode: str = "session"

    @property
    def running(self) -> bool:
        return bool(self.chat_loop and self.chat_loop._running)

    def start(self, mode: str = "session", on_ready=None, on_error=None) -> None:
        self.mode = mode
        self.error = ""
        cfg = _load_config()
        cookies: Dict[str, str] = {}
        ua = ""
        if mode == "session":
            if not SESSION_PATH.exists():
                raise RuntimeError("configs/session.json নেই — Session mood-এর Option 1 "
                                   "(লাইভ ব্রাউজার থেকে session collect) দিয়ে আগে session বানাও")
            session = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
            cookies = session.get("cookies") or {}
            if "token" not in cookies:
                raise RuntimeError("session.json-এ cookies.token নেই — আবার Pull Session করো")
            ua = session.get("user_agent") or ""
        snap = [s.strip() for s in (cfg.get("snap_usernames") or []) if s and s.strip()]
        if cfg.get("engine", "flow") == "flow" and not snap:
            raise RuntimeError("Flow engine-এর জন্য Snap Username দাও (Engine & Snap সেকশন)")

        def runner() -> None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            try:
                if mode == "browser":
                    coro = self._run_browser(cfg, on_ready)
                else:
                    coro = self._run(cfg, cookies, ua, on_ready)
                self.loop.run_until_complete(coro)
            except Exception as exc:  # noqa: BLE001
                self.error = f"{type(exc).__name__}: {exc}"
                if "SessionExpired" in self.error:
                    self.error = ("SESSION মেয়াদ শেষ (401) — browser-এ chitchat.gg আবার "
                                  "login করে session রিফ্রেশ করো")
                if on_error:
                    on_error(self.error)

        self.thread = threading.Thread(target=runner, daemon=True, name="eva-bot")
        self.thread.start()

    async def _run_browser(self, cfg: dict, on_ready) -> None:
        """LIVE BROWSER mood: CDP browser থেকে cookies নিয়ে চ্যাট + auto-save."""
        from ..dashboard.cdp_session import CdpSessionManager

        log = logging.getLogger("eva")
        mgr = CdpSessionManager()
        log.info("browser mood: লাইভ browser থেকে cookies আনা হচ্ছে…")
        res = await mgr.pull_and_save()
        if not res.get("saved"):
            raise RuntimeError(f"browser থেকে session আনা গেল না: {res}")
        who = res.get("username") or "(unverified)"
        log.info("live browser session saved ✓ — %s", who)
        session = json.loads(mgr.session_path.read_text(encoding="utf-8"))
        cookies = session.get("cookies") or {}
        ua = session.get("user_agent") or ""
        await self._run(cfg, cookies, ua, on_ready, auto_save=bool(cfg.get("browser_autosave", True)))

    @staticmethod
    async def _auto_save_session(interval_s: int = 60) -> None:
        """বট চলা অবস্থায় প্রতি interval-এ লাইভ browser থেকে session সেভ করে।"""
        from ..dashboard.cdp_session import CdpSessionManager

        log = logging.getLogger("eva")
        mgr = CdpSessionManager()
        while True:
            await asyncio.sleep(interval_s)
            try:
                await mgr.pull_and_save()
                log.info("session auto-save ✓ (live browser)")
            except Exception as exc:  # noqa: BLE001
                log.warning("session auto-save skip: %s", exc)

    async def _run(self, cfg: dict, cookies: dict, ua: str, on_ready,
                   auto_save: bool = False) -> None:
        from ..transport.chitchat_api import ChitchatApi
        from ..transport.chitchat_socket import ChitchatSocket
        from ..transport.protocol import DEFAULT_UA
        from ..transport.ws_chat_loop import LoopConfig, WsChatLoop

        loop_cfg = LoopConfig(**{k: tuple(v) if isinstance(v, list) else v
                                 for k, v in (cfg.get("loop") or {}).items()})
        self.api = ChitchatApi(cookies, user_agent=ua or DEFAULT_UA,
                               message_body_format=cfg.get("message_body_format", "multipart"))
        me = await self.api.me()
        socket = ChitchatSocket(cookies, user_agent=ua or DEFAULT_UA)

        engine_name = (cfg.get("engine") or "flow").lower()
        if engine_name == "fixed":
            from ..brain.fixed_reply_engine import FixedReplyEngine
            engine = FixedReplyEngine(script_path=cfg.get("fixed_file"),
                                      timing=cfg.get("timing"))
        else:
            from ..brain.flow_reply_engine import FlowReplyEngine
            engine = FlowReplyEngine(snap_usernames=cfg.get("snap_usernames"),
                                     timing=cfg.get("timing"))

        self.chat_loop = WsChatLoop(self.api, socket, engine, loop_cfg)
        await self.chat_loop.start()
        if on_ready:
            on_ready(me.get("username", "?"))
        save_task = None
        if auto_save:
            save_task = asyncio.ensure_future(self._auto_save_session())
        try:
            while self.chat_loop._running:
                await asyncio.sleep(0.5)
        finally:
            if save_task:
                save_task.cancel()
                try:
                    await save_task
                except asyncio.CancelledError:
                    pass

    def stop(self) -> None:
        async def _stop() -> None:
            if self.chat_loop:
                await self.chat_loop.stop("dashboard stop")
            if self.api:
                await self.api.close()
        if self.loop and self.running:
            asyncio.run_coroutine_threadsafe(_stop(), self.loop)

    def snapshot(self) -> dict:
        if not self.chat_loop:
            return {"running": self.running, "error": self.error}
        lp = self.chat_loop
        st = lp.stats.snapshot()
        ws = lp.socket.stats.snapshot()
        extra = {}
        eng = getattr(lp, "engine", None)
        if hasattr(eng, "stage") and lp.partner:
            extra["flow_stage"] = eng.stage(lp.partner.id)
            extra["flow_reason"] = eng.last_reason()
        return {
            "running": self.running,
            "error": self.error,
            "state": getattr(lp.state, "value", str(lp.state)),
            "partner": lp.partner.display() if lp.partner else None,
            "conversationId": lp.conversation_id or None,
            "matches": st.get("matches", 0),
            "sent": st.get("messages_sent", 0),
            "recv": st.get("messages_received", 0),
            "skips_partner": st.get("partner_skips", 0),
            "skips_ours": st.get("our_skips", 0),
            "flagged": st.get("flagged_403", 0),
            "uptime_s": st.get("uptime_s", 0),
            "ws_in": ws.get("frames_in", 0),
            "ws_out": ws.get("frames_out", 0),
            "reconnects": ws.get("reconnects", 0),
            **extra,
        }


# ------------------------------------------------------------- helpers

def _load_config() -> dict:
    for p in (CONFIG_PATH, CONFIG_EXAMPLE):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def _save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def cdp_launch_blocking(browser_path: str = "") -> dict:
    from ..dashboard.cdp_session import CdpSessionManager

    async def _go() -> dict:
        mgr = CdpSessionManager(browser_path=browser_path or None)
        return await mgr.launch()

    return asyncio.run(_go())


def cdp_pull_blocking() -> dict:
    from ..dashboard.cdp_session import CdpSessionManager

    async def _go() -> dict:
        mgr = CdpSessionManager()
        return await mgr.pull_and_save()

    return asyncio.run(_go())


def session_status_blocking() -> dict:
    from ..dashboard.cdp_session import CdpSessionManager
    mgr = CdpSessionManager()
    out = mgr.session_status()
    if out.get("exists"):
        try:
            me = asyncio.run(mgr.verify(_session_cookies(), _session_ua()))
            out["username"] = (me or {}).get("username")
            out["verified"] = bool(me)
        except Exception:
            out["verified"] = False
    return out


def _session_cookies() -> dict:
    try:
        return json.loads(SESSION_PATH.read_text(encoding="utf-8")).get("cookies") or {}
    except Exception:
        return {}


def _session_ua() -> str:
    try:
        return json.loads(SESSION_PATH.read_text(encoding="utf-8")).get("user_agent") or ""
    except Exception:
        return ""


# ================================================================ GUI

def run_gui() -> int:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                                 QHBoxLayout, QGridLayout, QPushButton, QTextEdit,
                                 QLabel, QGroupBox, QCheckBox, QComboBox, QFrame,
                                 QLineEdit, QSpinBox, QDoubleSpinBox, QMessageBox,
                                 QFileDialog, QStackedWidget)

    log_q: "queue.Queue[str]" = queue.Queue()
    qh = QueueLogHandler(log_q)
    logging.getLogger("eva").addHandler(qh)
    logging.getLogger("eva").setLevel(logging.INFO)
    if not logging.getLogger("eva").handlers:
        logging.getLogger("eva").addHandler(logging.NullHandler())

    app = QApplication(sys.argv)
    app.setStyleSheet(QSS)
    if ICON_PATH.exists():
        from PyQt6.QtGui import QIcon
        app.setWindowIcon(QIcon(str(ICON_PATH)))

    win = QMainWindow()
    win.setWindowTitle("EVA Bot — Mood Dashboard")
    win.resize(1120, 760)

    stacked = QStackedWidget()
    win.setCentralWidget(stacked)

    worker = BotWorker()
    status_colors = {"ok": C_GREEN, "warn": C_AMBER, "err": C_RED, "info": C_BLUE}

    # shared engine-widgets per page (Qt-তে এক widget দুই parent-এ থাকতে পারে না)
    engine_sets: Dict[str, dict] = {}

    def make_engine_set() -> dict:
        w: dict = {}
        row = QHBoxLayout()
        eng_group = QGroupBox("ENGINE & SNAP")
        eg = QGridLayout(eng_group)
        w["engine_combo"] = QComboBox()
        w["engine_combo"].addItems([
            "flow — SMS detect → input/output matching reply (funnel logic)",
            "fixed — একটা fixed txt ফাইল, line-by-line reply",
        ])
        eg.addWidget(QLabel("Engine:"), 0, 0)
        eg.addWidget(w["engine_combo"], 0, 1, 1, 3)
        w["snap_edit"] = QLineEdit()
        w["snap_edit"].setPlaceholderText("snap username (%username% এ যাবে, কমা দিলে rotate)")
        eg.addWidget(QLabel("Snap:"), 1, 0)
        eg.addWidget(w["snap_edit"], 1, 1, 1, 3)
        w["group"] = eng_group
        row.addWidget(eng_group, 2)

        fixed_group = QGroupBox("FIXED SCRIPT (engine=fixed হলে)")
        fg = QGridLayout(fixed_group)
        w["fixed_edit"] = QLineEdit()
        w["fixed_edit"].setPlaceholderText("configs/fixed_script.txt (প্রতি লাইনে একটা reply, ক্রম অনুযায়ী)")
        btn_browse = QPushButton("Browse…")
        fg.addWidget(QLabel("File:"), 0, 0)
        fg.addWidget(w["fixed_edit"], 0, 1)
        fg.addWidget(btn_browse, 0, 2)
        fixed_hint = QLabel("line শেষ হলে bot match skip করে next-এ যাবে")
        fixed_hint.setObjectName("dim")
        fixed_hint.setWordWrap(True)
        fg.addWidget(fixed_hint, 1, 0, 1, 3)

        def browse_fixed() -> None:
            path, _ = QFileDialog.getOpenFileName(win, "Fixed script বাছাই করো", "",
                                                  "Text files (*.txt);;All files (*)")
            if path:
                w["fixed_edit"].setText(path)
        btn_browse.clicked.connect(browse_fixed)
        w["fixed_group"] = fixed_group
        row.addWidget(fixed_group, 1)
        w["row"] = row

        # ---- LOOP SETTINGS (প্রতি পেজে আলাদা instance)
        loop_group = QGroupBox("LOOP SETTINGS")
        lg = QGridLayout(loop_group)
        w["idle_spin"] = QSpinBox()
        w["idle_spin"].setRange(15, 600)
        w["idle_spin"].setValue(90)
        w["typing_cb"] = QCheckBox("Typing indicator")
        w["typing_cb"].setChecked(True)
        w["autonext_cb"] = QCheckBox("Auto next match")
        w["autonext_cb"].setChecked(True)
        lg.addWidget(QLabel("Skip idle (sec)"), 0, 0)
        lg.addWidget(w["idle_spin"], 0, 1)
        lg.addWidget(w["typing_cb"], 0, 2)
        lg.addWidget(w["autonext_cb"], 0, 3)
        lg.addWidget(QLabel("partner এত সেকেন্ড চুপ থাকলে next match-এ যাবে"), 1, 0, 1, 4)
        lg.itemAt(1).widget().setObjectName("dim")
        w["loop_group"] = loop_group
        return w

    def collect_engine(w: dict) -> None:
        """এই পেজের widget থেকে config সেভ + অন্য পেজের widget-ও sync করে।"""
        cfg = _load_config()
        cfg["engine"] = "flow" if w["engine_combo"].currentIndex() == 0 else "fixed"
        cfg["snap_usernames"] = [s.strip() for s in w["snap_edit"].text().split(",") if s.strip()]
        cfg["fixed_file"] = w["fixed_edit"].text().strip() or "configs/fixed_script.txt"
        cfg.setdefault("loop", {}).update({
            "skip_idle_s": w["idle_spin"].value(),
            "typing_indicator": w["typing_cb"].isChecked(),
            "auto_next": w["autonext_cb"].isChecked(),
        })
        _save_config(cfg)
        apply_engine_all(cfg)

    def apply_engine_all(cfg: dict) -> None:
        lp = cfg.get("loop") or {}
        for w in engine_sets.values():
            w["engine_combo"].setCurrentIndex(0 if (cfg.get("engine", "flow") == "flow") else 1)
            w["snap_edit"].setText(", ".join(cfg.get("snap_usernames") or []))
            w["fixed_edit"].setText(cfg.get("fixed_file", "configs/fixed_script.txt"))
            w["idle_spin"].setValue(int(lp.get("skip_idle_s", 90)))
            w["typing_cb"].setChecked(bool(lp.get("typing_indicator", True)))
            w["autonext_cb"].setChecked(bool(lp.get("auto_next", True)))

    def make_stats_and_log() -> dict:
        out: dict = {}
        stats_group = QGroupBox("STATS")
        sg = QGridLayout(stats_group)
        vals: Dict[str, QLabel] = {}
        for i, key in enumerate(["Matches", "Sent", "Recv", "Skips T/U", "WS in/out", "Uptime"]):
            val = QLabel("0")
            val.setObjectName("statVal")
            lbl = QLabel(key)
            lbl.setObjectName("statLbl")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sg.addWidget(val, 0, i)
            sg.addWidget(lbl, 1, i)
            vals[key] = val
        out["stats_group"] = stats_group
        out["stat_vals"] = vals

        match_group = QGroupBox("CURRENT MATCH")
        mg = QGridLayout(match_group)
        m_state = QLabel("—")
        m_state.setStyleSheet(f"color:{C_AMBER}; font-size:16px; font-weight:800;")
        m_partner = QLabel("—")
        m_partner.setStyleSheet(f"color:{C_BLUE}; font-size:15px; font-weight:700;")
        m_stage = QLabel("—")
        m_stage.setObjectName("dim")
        m_stage.setWordWrap(True)
        mg.addWidget(QLabel("State"), 0, 0)
        mg.addWidget(m_state, 0, 1)
        mg.addWidget(QLabel("Partner"), 1, 0)
        mg.addWidget(m_partner, 1, 1)
        mg.addWidget(QLabel("Flow"), 2, 0)
        mg.addWidget(m_stage, 2, 1)
        match_group.setParent(None)
        out["m_state"] = m_state
        out["m_partner"] = m_partner
        out["m_stage"] = m_stage
        out["match_group"] = match_group

        log_group = QGroupBox("LIVE LOG")
        ll = QVBoxLayout(log_group)
        log_text = QTextEdit()
        log_text.setReadOnly(True)
        log_text.setMinimumHeight(150)
        ll.addWidget(log_text)
        out["log_text"] = log_text
        out["log_group"] = log_group
        return out

    def make_header(title: str) -> tuple:
        bar = QHBoxLayout()
        back = QPushButton("←  Home")
        back.setObjectName("backBtn")
        hdr = QLabel(title)
        hdr.setObjectName("hdr")
        bar.addWidget(back)
        bar.addWidget(hdr)
        bar.addStretch()
        return bar, back

    def make_status_strip() -> QLabel:
        lbl = QLabel("● Ready")
        lbl.setStyleSheet(f"color: {C_GREEN}; font-size: 14px;")
        return lbl

    def make_cpu_ram() -> tuple:
        cpu_lbl = QLabel("CPU: –")
        ram_lbl = QLabel("RAM: –")
        for w, c in ((cpu_lbl, C_ORANGE), (ram_lbl, C_BLUE)):
            w.setStyleSheet(f"font-size: 11px; color: {c};")
        return cpu_lbl, ram_lbl

    # ================================================== PAGE 0 — HOME (mood select)
    page_home = QWidget()
    hl = QVBoxLayout(page_home)
    hl.setContentsMargins(60, 50, 60, 40)
    hl.setSpacing(18)

    brand = QLabel("🤖  EVA BOT")
    brand.setObjectName("brand")
    brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
    hl.addWidget(brand)
    home_sub = QLabel("কোন MOOD-এ চালাবে? — বাছাই করলে সেই mood-এর নিজের dashboard খুলবে")
    home_sub.setObjectName("homeSub")
    home_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
    hl.addWidget(home_sub)
    hl.addSpacing(14)

    card_browser = QPushButton(
        "🌐   LIVE BROWSER MOOD\n\n"
        "ব্রাউজার চোখের সামনে চলবে — বট লাইভ auto-reply করবে (পুরনো মোডের মতো)\n"
        "+ ব্রাউজারের session auto-save হবে")
    card_browser.setObjectName("moodCard")
    hl.addWidget(card_browser)

    card_session = QPushButton(
        "🔑   SESSION CHAT MOOD\n\n"
        "Session পেজ — ২টা অপশন: লাইভ ব্রাউজার চালু করে session collect,\n"
        "অথবা পুরনো saved session দিয়ে headless চ্যাট শুরু")
    card_session.setObjectName("moodCard")
    hl.addWidget(card_session)

    hl.addStretch()
    ver_lbl = QLabel("chitchat.gg • WS live • mood dashboards")
    ver_lbl.setObjectName("dim")
    ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    hl.addWidget(ver_lbl)
    stacked.addWidget(page_home)

    # shared ui-state
    pages: Dict[str, dict] = {}

    def goto(page_key: str) -> None:
        stacked.setCurrentWidget(pages[page_key]["widget"])

    # start/stop enable across pages
    start_btns = []
    stop_btns = []

    def set_running_ui(running: bool) -> None:
        for b in start_btns:
            b.setEnabled(not running)
        for b in stop_btns:
            b.setEnabled(running)

    def _bot_err_common(e: str, status_lbl: QLabel) -> None:
        status_lbl.setText(f"● সমস্যা: {e[:140]}")
        status_lbl.setStyleSheet(f"color: {C_RED}; font-size: 14px;")
        set_running_ui(False)

    # ================================================== PAGE 1 — LIVE BROWSER MOOD
    page_browser = QWidget()
    bl = QVBoxLayout(page_browser)
    bl.setContentsMargins(20, 18, 20, 14)
    bl.setSpacing(10)

    bar, back_b = make_header("🌐  LIVE BROWSER MOOD")
    bl.addLayout(bar)
    status_browser = make_status_strip()
    bl.addWidget(status_browser)

    browser_group = QGroupBox("LIVE BROWSER (চোখের সামনে চলবে)")
    bg = QGridLayout(browser_group)
    btn_open_live = QPushButton("🚀 Browser খোলো (live)")
    btn_open_live.setObjectName("launchBtn")
    btn_save_now = QPushButton("💾 Session Save now")
    auto_save_cb = QCheckBox("Session auto-save (বট চলাকালীন প্রতি 60s)")
    auto_save_cb.setChecked(True)
    live_info = QLabel("browser খুলে chitchat.gg-তে login থাকলে বট এই ব্রাউজারের cookies-ই ব্যবহার করবে")
    live_info.setObjectName("dim")
    live_info.setWordWrap(True)
    bg.addWidget(btn_open_live, 0, 0)
    bg.addWidget(btn_save_now, 0, 1)
    bg.addWidget(auto_save_cb, 0, 2)
    bg.addWidget(live_info, 1, 0, 1, 3)
    bl.addWidget(browser_group)

    eng_b = make_engine_set()
    engine_sets["browser"] = eng_b
    bl.addLayout(eng_b["row"])
    bl.addWidget(eng_b["loop_group"])

    run_row_b = QHBoxLayout()
    start_b = QPushButton("▶  START — LIVE BROWSER MOOD")
    start_b.setObjectName("startBtn")
    stop_b = QPushButton("■  STOP")
    stop_b.setObjectName("stopBtn")
    stop_b.setEnabled(False)
    run_row_b.addWidget(start_b, 2)
    run_row_b.addWidget(stop_b, 1)
    bl.addLayout(run_row_b)

    ui_b = make_stats_and_log()
    loop_row_b = QHBoxLayout()
    loop_row_b.addWidget(ui_b["stats_group"], 2)
    loop_row_b.addWidget(ui_b["match_group"], 1)
    bl.addLayout(loop_row_b)
    bl.addWidget(ui_b["log_group"], 1)

    cpu_b, ram_b = make_cpu_ram()
    foot_b = QHBoxLayout()
    foot_b.addWidget(cpu_b)
    foot_b.addWidget(ram_b)
    foot_b.addStretch()
    bl.addLayout(foot_b)
    stacked.addWidget(page_browser)
    pages["browser"] = {"widget": page_browser, **ui_b, "status": status_browser,
                        "cpu": cpu_b, "ram": ram_b}

    # ================================================== PAGE 2 — SESSION CHAT MOOD
    page_session = QWidget()
    sl2 = QVBoxLayout(page_session)
    sl2.setContentsMargins(20, 18, 20, 14)
    sl2.setSpacing(10)

    bar2, back_s = make_header("🔑  SESSION CHAT MOOD")
    sl2.addLayout(bar2)
    status_session = make_status_strip()
    sl2.addWidget(status_session)

    sess_pick = QGroupBox("SESSION — ২টা অপশন (যেটা চাও)")
    spl = QGridLayout(sess_pick)

    # ---- Option 1: live browser → session collect
    opt1 = QGroupBox("🆕  Option 1 — লাইভ ব্রাউজার চালু করে session collect")
    o1 = QGridLayout(opt1)
    btn_launch_s = QPushButton("🚀 Browser খোলো")
    btn_launch_s.setObjectName("launchBtn")
    btn_pull_s = QPushButton("💾 Pull Session")
    opt1_status = QLabel("browser খুলে chitchat.gg-তে LOGIN করো → তারপর Pull Session")
    opt1_status.setObjectName("dim")
    opt1_status.setWordWrap(True)
    o1.addWidget(btn_launch_s, 0, 0)
    o1.addWidget(btn_pull_s, 0, 1)
    o1.addWidget(opt1_status, 1, 0, 1, 2)
    spl.addWidget(opt1, 0, 0)

    # ---- Option 2: old saved session → chat
    opt2 = QGroupBox("💾  Option 2 — পুরনো saved session দিয়ে চ্যাট শুরু")
    o2 = QGridLayout(opt2)
    old_status = QLabel("checking…")
    old_status.setWordWrap(True)
    btn_refresh_sess = QPushButton("🔄 চেক করো")
    o2.addWidget(old_status, 0, 0)
    o2.addWidget(btn_refresh_sess, 0, 1)
    o2.addWidget(QLabel("configs/session.json থেকে সরাসরি চ্যাট শুরু হবে (browser লাগবে না)"),
                 1, 0, 1, 2)
    spl.addWidget(opt2, 0, 1)
    sl2.addWidget(sess_pick)

    eng_s = make_engine_set()
    engine_sets["session"] = eng_s
    sl2.addLayout(eng_s["row"])
    sl2.addWidget(eng_s["loop_group"])

    run_row_s = QHBoxLayout()
    start_s = QPushButton("▶  START — SESSION MOOD")
    start_s.setObjectName("startBtn")
    stop_s = QPushButton("■  STOP")
    stop_s.setObjectName("stopBtn")
    stop_s.setEnabled(False)
    run_row_s.addWidget(start_s, 2)
    run_row_s.addWidget(stop_s, 1)
    sl2.addLayout(run_row_s)

    ui_s = make_stats_and_log()
    loop_row_s = QHBoxLayout()
    loop_row_s.addWidget(ui_s["stats_group"], 2)
    loop_row_s.addWidget(ui_s["match_group"], 1)
    sl2.addLayout(loop_row_s)
    sl2.addWidget(ui_s["log_group"], 1)

    cpu_s, ram_s = make_cpu_ram()
    foot_s = QHBoxLayout()
    foot_s.addWidget(cpu_s)
    foot_s.addWidget(ram_s)
    foot_s.addStretch()
    sl2.addLayout(foot_s)
    stacked.addWidget(page_session)
    pages["session"] = {"widget": page_session, **ui_s, "status": status_session,
                        "cpu": cpu_s, "ram": ram_s}

    start_btns = [start_b, start_s]
    stop_btns = [stop_b, stop_s]

    # ---------------------------------------------------------- navigation
    card_browser.clicked.connect(lambda: goto("browser"))
    card_session.clicked.connect(lambda: goto("session"))
    back_b.clicked.connect(lambda: stacked.setCurrentWidget(page_home))
    back_s.clicked.connect(lambda: stacked.setCurrentWidget(page_home))

    # ---------------------------------------------------------- actions

    def set_status(page: str, text: str, color: str = "ok") -> None:
        lbl = pages[page]["status"]
        lbl.setText(text)
        lbl.setStyleSheet(f"color: {status_colors[color]}; font-size: 14px;")

    def _launch_done(page: str, res: dict) -> None:
        ok = res.get("status") in ("launched", "already-running")
        if page == "browser":
            set_status("browser",
                       ("● Browser খোলা ✓ — login থাকলেই START চাপো (session auto-save চালু)"
                        if ok else f"● Launch সমস্যা: {res.get('status')} {res.get('hint','')}"),
                       "ok" if ok else "err")
        else:
            opt1_status.setText(("Browser খোলা ✓ — এখন chitchat.gg-তে LOGIN করো → Pull Session"
                                 if ok else f"Launch সমস্যা: {res.get('status')} {res.get('hint','')}"))

    def do_launch(page: str, btn) -> None:
        btn.setEnabled(False)
        if page == "browser":
            set_status("browser", "● Browser launch হচ্ছে…", "info")
        else:
            opt1_status.setText("Browser launch হচ্ছে…")

        def work() -> None:
            try:
                res = cdp_launch_blocking()
            except Exception as exc:  # noqa: BLE001
                res = {"status": f"error: {exc}"}
            QTimer.singleShot(0, lambda: (_launch_done(page, res), btn.setEnabled(True)))
        threading.Thread(target=work, daemon=True).start()

    def do_pull(btn, done) -> None:
        btn.setEnabled(False)

        def work() -> None:
            try:
                res = cdp_pull_blocking()
            except Exception as exc:  # noqa: BLE001
                res = {"saved": False, "error": str(exc)}
            QTimer.singleShot(0, lambda: (btn.setEnabled(True), done(res)))
        threading.Thread(work, daemon=True).start()

    def _after_pull_session_mode(res: dict) -> None:
        if res.get("saved"):
            who = res.get("username")
            opt1_status.setText(f"Session saved ✓ {('— ' + who) if who else '(verify skip)'} — "
                                f"এবার Option 2 দিয়ে বা সরাসরি START চাপো")
            set_status("session", "● Session ready ✓ — START চাপলেই চ্যাট শুরু", "ok")
            refresh_session()
        else:
            opt1_status.setText(f"Save fail: {res.get('error', '?')}")

    def _after_pull_browser_mode(res: dict) -> None:
        if res.get("saved"):
            set_status("browser", f"● Session saved ✓ {res.get('username') or ''} — START রেডি", "ok")
            refresh_session()
        else:
            set_status("browser", f"● Save fail: {res.get('error', '?')}", "err")

    btn_open_live.clicked.connect(lambda: do_launch("browser", btn_open_live))
    btn_save_now.clicked.connect(lambda: do_pull(btn_save_now, _after_pull_browser_mode))
    btn_launch_s.clicked.connect(lambda: do_launch("session", btn_launch_s))
    btn_pull_s.clicked.connect(lambda: do_pull(btn_pull_s, _after_pull_session_mode))

    def refresh_session() -> None:
        def work() -> None:
            try:
                res = session_status_blocking()
            except Exception:
                res = {}
            QTimer.singleShot(0, lambda: _paint_session(res))
        threading.Thread(target=work, daemon=True).start()

    def _paint_session(res: dict) -> None:
        if res.get("exists") and res.get("verified"):
            old_status.setText(f"✓ saved session পাওয়া গেছে — user: {res.get('username', '?')}  "
                               f"(START চাপলেই চ্যাট শুরু)")
            old_status.setStyleSheet(f"color: {C_GREEN}; font-weight:700;")
        elif res.get("exists"):
            old_status.setText("saved session আছে (unverified) — START চেষ্টা করা যায়")
            old_status.setStyleSheet(f"color: {C_AMBER};")
        else:
            old_status.setText("✗ কোনো saved session নেই — আগে Option 1 দিয়ে session বানাও")
            old_status.setStyleSheet(f"color: {C_RED};")

    btn_refresh_sess.clicked.connect(refresh_session)

    def do_start(mode: str, page: str) -> None:
        collect_engine(engine_sets[page])
        cfg = _load_config()
        cfg["browser_autosave"] = auto_save_cb.isChecked()
        _save_config(cfg)
        try:
            worker.start(mode=mode,
                         on_ready=lambda u: QTimer.singleShot(
                             0, lambda: set_status(page, f"● LIVE — {u} হিসেবে চলছে", "ok")),
                         on_error=lambda e: QTimer.singleShot(
                             0, lambda: _bot_err_common(e, pages[page]["status"])))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(win, "START সমস্যা", str(exc))
            return
        set_running_ui(True)
        set_status(page, "● চালু হচ্ছে…", "info")

    def do_stop() -> None:
        worker.stop()
        set_running_ui(False)
        set_status("browser", "● বন্ধ করা হলো", "warn")
        set_status("session", "● বন্ধ করা হলো", "warn")

    start_b.clicked.connect(lambda: do_start("browser", "browser"))
    start_s.clicked.connect(lambda: do_start("session", "session"))
    stop_b.clicked.connect(do_stop)
    stop_s.clicked.connect(do_stop)

    # ---------------------------------------------------------- timers

    def poll_stats() -> None:
        s = worker.snapshot()
        running = bool(s.get("running"))
        err = s.get("error") or ""
        state_txt = (s.get("state", "—") if running else ("ERROR" if err else "IDLE"))
        partner_txt = s.get("partner") or "—"
        stage_txt = (s.get("flow_stage") or "") + ((" · " + s["flow_reason"]) if s.get("flow_reason") else "")
        up = int(s.get("uptime_s", 0) or 0)
        vals_txt = {
            "Matches": str(s.get("matches", 0)),
            "Sent": str(s.get("sent", 0)),
            "Recv": str(s.get("recv", 0)),
            "Skips T/U": f"{s.get('skips_partner', 0)}/{s.get('skips_ours', 0)}",
            "WS in/out": f"{s.get('ws_in', 0)}/{s.get('ws_out', 0)}",
            "Uptime": f"{up // 60}m{up % 60:02d}s",
        }
        for key in pages:
            pg = pages[key]
            pg["m_state"].setText(state_txt)
            pg["m_partner"].setText(partner_txt)
            pg["m_stage"].setText(stage_txt or "—")
            for k, v in vals_txt.items():
                pg["stat_vals"][k].setText(v)
        # drain log queue → সব পেজের log-এ
        lines = []
        try:
            while True:
                lines.append(log_q.get_nowait())
        except queue.Empty:
            pass
        if lines:
            chunk = "\n".join(lines[-200:])
            for key in pages:
                pages[key]["log_text"].append(chunk)

    def poll_sys() -> None:
        try:
            import psutil
            cpu_txt = f"CPU: {psutil.cpu_percent():.0f}%"
            ram_txt = f"RAM: {psutil.virtual_memory().percent:.0f}%"
        except Exception:
            cpu_txt, ram_txt = "CPU: n/a", "RAM: n/a"
        cpu_b.setText(cpu_txt)
        ram_b.setText(ram_txt)
        cpu_s.setText(cpu_txt)
        ram_s.setText(ram_txt)

    def poll_autosave() -> None:
        """BROWSER page-এ, বট বন্ধ থাকলেও লাইভ browser-এর session মাঝে মাঝে সেভ হয়।"""
        if stacked.currentWidget() is not page_browser or worker.running \
                or not auto_save_cb.isChecked():
            return

        def work() -> None:
            try:
                res = cdp_pull_blocking()
                saved = bool(res.get("saved"))
            except Exception:
                saved = False
            if saved:
                QTimer.singleShot(0, lambda: set_status(
                    "browser", "● browser খোলা — session auto-saved ✓ (START রেডি)", "ok"))
        threading.Thread(target=work, daemon=True).start()

    t_stats = QTimer()
    t_stats.timeout.connect(poll_stats)
    t_stats.start(1000)
    t_sys = QTimer()
    t_sys.timeout.connect(poll_sys)
    t_sys.start(2500)
    t_auto = QTimer()
    t_auto.timeout.connect(poll_autosave)
    t_auto.start(60_000)

    refresh_session()
    apply_engine_all(_load_config())
    lp = _load_config().get("loop") or {}
    auto_save_cb.setChecked(True)

    logging.getLogger("eva").info("Mood Dashboard চালু — root: %s", ROOT)
    win.show()
    return app.exec()


def main() -> None:
    sys.exit(run_gui())


if __name__ == "__main__":
    main()
