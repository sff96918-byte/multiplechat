"""EVA Bot — Professional Desktop Dashboard (PyQt6).

Same dark professional style as the user's original EVA project
(sidebar + group boxes + live log), upgraded with the capture-backed
WebSocket bot and the CDP browser login flow.

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
QLabel#brand {{ font-size: 20px; font-weight: 800; }}
QLabel#hdr {{ font-size: 22px; font-weight: 700; }}
QLabel#dim {{ color: {C_TEXT_DIM}; font-size: 12px; }}
QLabel#statVal {{ font-size: 17px; font-weight: 700; }}
QLabel#statLbl {{ color: {C_TEXT_DIM}; font-size: 11px; }}
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
    """Runs the asyncio bot in a background thread; state read via snapshot()."""

    def __init__(self) -> None:
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.chat_loop = None          # WsChatLoop
        self.api = None
        self.thread: Optional[threading.Thread] = None
        self.error: str = ""

    @property
    def running(self) -> bool:
        return bool(self.chat_loop and self.chat_loop._running)

    def start(self, on_ready=None, on_error=None) -> None:
        cfg = _load_config()
        if not SESSION_PATH.exists():
            raise RuntimeError("configs/session.json নেই — আগে Launch Browser → Login → Pull Session করো")
        session = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
        cookies = session.get("cookies") or {}
        if "token" not in cookies:
            raise RuntimeError("session.json-এ cookies.token নেই — আবার Pull Session করো")
        ua = session.get("user_agent") or ""
        snap = [s.strip() for s in (cfg.get("snap_usernames") or []) if s and s.strip()]
        if cfg.get("engine", "flow") == "flow" and not snap:
            raise RuntimeError("Flow engine-এর জন্য Snap Username দাও (Settings ট্যাব)")

        def runner() -> None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            try:
                self.loop.run_until_complete(self._run(cfg, cookies, ua, on_ready))
            except Exception as exc:  # noqa: BLE001
                self.error = f"{type(exc).__name__}: {exc}"
                if on_error:
                    on_error(self.error)

        self.thread = threading.Thread(target=runner, daemon=True, name="eva-bot")
        self.thread.start()

    async def _run(self, cfg: dict, cookies: dict, ua: str, on_ready) -> None:
        from ..transport.chitchat_api import ChitchatApi
        from ..transport.chitchat_socket import ChitchatSocket
        from ..transport.protocol import DEFAULT_UA
        from ..transport.ws_chat_loop import LoopConfig, WsChatLoop

        persona_cfg = cfg.get("persona") or {}
        loop_cfg = LoopConfig(**{k: tuple(v) if isinstance(v, list) else v
                                 for k, v in (cfg.get("loop") or {}).items()})
        self.api = ChitchatApi(cookies, user_agent=ua or DEFAULT_UA,
                               message_body_format=cfg.get("message_body_format", "multipart"))
        me = await self.api.me()
        socket = ChitchatSocket(cookies, user_agent=ua or DEFAULT_UA)

        engine_name = (cfg.get("engine") or "flow").lower()
        if engine_name == "flow":
            from ..brain.flow_reply_engine import FlowReplyEngine
            engine = FlowReplyEngine(snap_usernames=cfg.get("snap_usernames"))
        else:
            from ..replies import Persona, ReplyEngine
            persona = Persona(**{k: v for k, v in persona_cfg.items()})
            engine = ReplyEngine(persona=persona, config=cfg.get("replies"))

        self.chat_loop = WsChatLoop(self.api, socket, engine, loop_cfg)
        await self.chat_loop.start()
        if on_ready:
            on_ready(me.get("username", "?"))
        while self.chat_loop._running:
            await asyncio.sleep(0.5)

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
                                 QLineEdit, QSpinBox, QDoubleSpinBox, QMessageBox)

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
    win.setWindowTitle("EVA Bot — Chitchat Live Dashboard")
    win.resize(1120, 760)

    central = QWidget()
    win.setCentralWidget(central)
    layout = QHBoxLayout(central)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    # ---------------------------------------------------------- sidebar
    sidebar = QFrame()
    sidebar.setObjectName("sidebar")
    sidebar.setFixedWidth(210)
    sb = QVBoxLayout(sidebar)
    sb.setContentsMargins(15, 20, 15, 20)

    brand = QLabel("🤖 EVA BOT")
    brand.setObjectName("brand")
    sb.addWidget(brand)
    ver = QLabel("chitchat.gg • WS live")
    ver.setObjectName("dim")
    sb.addWidget(ver)
    sb.addSpacing(12)

    sess_group = QGroupBox("SESSION")
    sl = QVBoxLayout(sess_group)
    sess_status = QLabel("checking…")
    sess_status.setWordWrap(True)
    sl.addWidget(sess_status)
    btn_launch = QPushButton("🚀 Launch Browser & Login")
    btn_launch.setObjectName("launchBtn")
    sl.addWidget(btn_launch)
    btn_pull = QPushButton("💾 Pull Session")
    sl.addWidget(btn_pull)
    sb.addWidget(sess_group)
    sb.addStretch()

    cpu_lbl = QLabel("CPU: –")
    ram_lbl = QLabel("RAM: –")
    for w, c in ((cpu_lbl, "#FB923C"), (ram_lbl, C_BLUE)):
        w.setStyleSheet(f"font-size: 11px; color: {c};")
        sb.addWidget(w)
    sb.addSpacing(8)

    start_btn = QPushButton("▶ START")
    start_btn.setObjectName("startBtn")
    stop_btn = QPushButton("■ STOP")
    stop_btn.setObjectName("stopBtn")
    stop_btn.setEnabled(False)
    sb.addWidget(start_btn)
    sb.addWidget(stop_btn)

    layout.addWidget(sidebar)

    # ---------------------------------------------------------- content
    content = QWidget()
    cl = QVBoxLayout(content)
    cl.setContentsMargins(20, 18, 20, 18)
    cl.setSpacing(12)

    header = QLabel("Dashboard")
    header.setObjectName("hdr")
    cl.addWidget(header)
    status_lbl = QLabel("● Ready — session সেটআপ করো, তারপর START")
    status_lbl.setStyleSheet(f"color: {C_GREEN}; font-size: 14px;")
    cl.addWidget(status_lbl)

    # ---- session + engine row
    eng_row = QHBoxLayout()
    eng_group = QGroupBox("ENGINE & SNAP")
    eg = QGridLayout(eng_group)
    engine_combo = QComboBox()
    engine_combo.addItems(["flow — txt banks (greeting→age→country→flirty→snap)",
                           "simple — persona templates"])
    eg.addWidget(QLabel("Engine:"), 0, 0)
    eg.addWidget(engine_combo, 0, 1, 1, 3)
    snap_edit = QLineEdit()
    snap_edit.setPlaceholderText("snap username (%username% এ যাবে, কমা দিলে rotate)")
    eg.addWidget(QLabel("Snap:"), 1, 0)
    eg.addWidget(snap_edit, 1, 1, 1, 3)
    eng_row.addWidget(eng_group, 2)

    persona_group = QGroupBox("PERSONA")
    pg = QGridLayout(persona_group)
    p_name = QLineEdit(); p_age = QSpinBox(); p_age.setRange(18, 60); p_age.setValue(21)
    p_gender = QComboBox(); p_gender.addItems(["f", "m"])
    p_country = QLineEdit(); p_country.setText("Germany")
    pg.addWidget(QLabel("Name"), 0, 0); pg.addWidget(p_name, 0, 1)
    pg.addWidget(QLabel("Age"), 0, 2); pg.addWidget(p_age, 0, 3)
    pg.addWidget(QLabel("Gender"), 1, 0); pg.addWidget(p_gender, 1, 1)
    pg.addWidget(QLabel("Country"), 1, 2); pg.addWidget(p_country, 1, 3)
    eng_row.addWidget(persona_group, 1)
    cl.addLayout(eng_row)

    # ---- loop settings row
    loop_row = QHBoxLayout()
    loop_group = QGroupBox("LOOP SETTINGS")
    lg = QGridLayout(loop_group)
    idle_spin = QSpinBox(); idle_spin.setRange(15, 600); idle_spin.setValue(90)
    typing_cb = QCheckBox("Typing indicator"); typing_cb.setChecked(True)
    autonext_cb = QCheckBox("Auto next match"); autonext_cb.setChecked(True)
    maxm_spin = QSpinBox(); maxm_spin.setRange(0, 999); maxm_spin.setValue(0)
    lg.addWidget(QLabel("Skip idle (sec)"), 0, 0); lg.addWidget(idle_spin, 0, 1)
    lg.addWidget(typing_cb, 0, 2); lg.addWidget(autonext_cb, 0, 3)
    lg.addWidget(QLabel("Max matches (0=∞)"), 1, 0); lg.addWidget(maxm_spin, 1, 1)
    btn_save_cfg = QPushButton("💾 Save Settings")
    lg.addWidget(btn_save_cfg, 1, 2, 1, 2)
    loop_row.addWidget(loop_group)

    match_group = QGroupBox("CURRENT MATCH")
    mg = QGridLayout(match_group)
    m_state = QLabel("—"); m_state.setStyleSheet(f"color:{C_AMBER}; font-size:16px; font-weight:800;")
    m_partner = QLabel("—"); m_partner.setStyleSheet(f"color:{C_BLUE}; font-size:15px; font-weight:700;")
    m_stage = QLabel("—"); m_stage.setObjectName("dim"); m_stage.setWordWrap(True)
    mg.addWidget(QLabel("State"), 0, 0); mg.addWidget(m_state, 0, 1)
    mg.addWidget(QLabel("Partner"), 1, 0); mg.addWidget(m_partner, 1, 1)
    mg.addWidget(QLabel("Flow"), 2, 0); mg.addWidget(m_stage, 2, 1)
    loop_row.addWidget(match_group, 1)
    cl.addLayout(loop_row)

    # ---- stats row
    stats_group = QGroupBox("STATS")
    sg = QGridLayout(stats_group)
    stat_vals: Dict[str, QLabel] = {}
    for i, key in enumerate(["Matches", "Sent", "Recv", "Skips T/U", "WS in/out", "Uptime"]):
        val = QLabel("0"); val.setObjectName("statVal")
        lbl = QLabel(key); lbl.setObjectName("statLbl")
        val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sg.addWidget(val, 0, i); sg.addWidget(lbl, 1, i)
        stat_vals[key] = val
    cl.addWidget(stats_group)

    # ---- log
    log_group = QGroupBox("LIVE LOG")
    ll = QVBoxLayout(log_group)
    log_text = QTextEdit()
    log_text.setReadOnly(True)
    log_text.setMinimumHeight(170)
    ll.addWidget(log_text)
    cl.addWidget(log_group, 1)

    layout.addWidget(content, 1)

    worker = BotWorker()

    # ---------------------------------------------------------- actions

    def do_launch() -> None:
        btn_launch.setEnabled(False)
        status_lbl.setText("● Browser launch হচ্ছে…")
        def work() -> None:
            try:
                res = cdp_launch_blocking()
            except Exception as exc:  # noqa: BLE001
                res = {"status": f"error: {exc}"}
            QTimer.singleShot(0, lambda: _after_launch(res))
        threading.Thread(target=work, daemon=True).start()

    def _after_launch(res: dict) -> None:
        btn_launch.setEnabled(True)
        ok = res.get("status") in ("launched", "already-running")
        status_lbl.setText(("● Browser খোলা — এখন chitchat.gg-তে LOGIN করো, তারপর Pull Session"
                            if ok else f"● Launch সমস্যা: {res.get('status')} {res.get('hint','')}"))
        if not ok:
            status_lbl.setStyleSheet(f"color: {C_RED}; font-size: 14px;")

    def do_pull() -> None:
        btn_pull.setEnabled(False)
        status_lbl.setText("● Cookies আনা হচ্ছে (browser-এ login করেছো তো?)…")
        def work() -> None:
            try:
                res = cdp_pull_blocking()
            except Exception as exc:  # noqa: BLE001
                res = {"saved": False, "error": str(exc)}
            QTimer.singleShot(0, lambda: _after_pull(res))
        threading.Thread(work, daemon=True).start()

    def _after_pull(res: dict) -> None:
        btn_pull.setEnabled(True)
        if res.get("saved"):
            who = res.get("username")
            status_lbl.setText(f"● Session saved ✓ {('— ' + who) if who else '(verify skip)'} — এবার START")
            status_lbl.setStyleSheet(f"color: {C_GREEN}; font-size: 14px;")
            refresh_session()
        else:
            status_lbl.setText(f"● Save fail: {res.get('error','?')}")
            status_lbl.setStyleSheet(f"color: {C_RED}; font-size: 14px;")

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
            sess_status.setText(f"✓ {res.get('username','?')}")
            sess_status.setStyleSheet(f"color: {C_GREEN}; font-weight:700;")
        elif res.get("exists"):
            sess_status.setText("saved (unverified)")
            sess_status.setStyleSheet(f"color: {C_AMBER};")
        else:
            sess_status.setText("✗ নেই — Browser চালু করে Pull করো")
            sess_status.setStyleSheet(f"color: {C_RED};")

    def save_settings() -> None:
        cfg = _load_config()
        engine = "flow" if engine_combo.currentIndex() == 0 else "simple"
        cfg["engine"] = engine
        cfg["snap_usernames"] = [s.strip() for s in snap_edit.text().split(",") if s.strip()]
        cfg.setdefault("persona", {}).update({
            "name": p_name.text() or "Alex", "age": p_age.value(),
            "gender": p_gender.currentText(), "country": p_country.text() or "Germany",
        })
        cfg.setdefault("loop", {}).update({
            "skip_idle_s": idle_spin.value(),
            "typing_indicator": typing_cb.isChecked(),
            "auto_next": autonext_cb.isChecked(),
        })
        _save_config(cfg)
        status_lbl.setText("● Settings saved ✓")

    def do_start() -> None:
        save_settings()
        try:
            maxm = maxm_spin.value()
            worker.start(on_ready=lambda u: QTimer.singleShot(0, lambda: status_lbl.setText(f"● LIVE — {u} হিসেবে চলছে")),
                         on_error=lambda e: QTimer.singleShot(0, lambda: _bot_err(e)))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(win, "START সমস্যা", str(exc))
            return
        start_btn.setEnabled(False)
        stop_btn.setEnabled(True)
        status_lbl.setText("● চালু হচ্ছে…")
        worker.max_matches = maxm

    def _bot_err(e: str) -> None:
        status_lbl.setText(f"● সমস্যা: {e[:120]}")
        status_lbl.setStyleSheet(f"color: {C_RED}; font-size: 14px;")
        start_btn.setEnabled(True)
        stop_btn.setEnabled(False)

    def do_stop() -> None:
        worker.stop()
        start_btn.setEnabled(True)
        stop_btn.setEnabled(False)
        status_lbl.setText("● বন্ধ করা হলো")

    btn_launch.clicked.connect(do_launch)
    btn_pull.clicked.connect(do_pull)
    btn_save_cfg.clicked.connect(save_settings)
    start_btn.clicked.connect(do_start)
    stop_btn.clicked.connect(do_stop)

    # ---------------------------------------------------------- timers

    def poll_stats() -> None:
        s = worker.snapshot()
        m_state.setText(s.get("state", "—") if s.get("running") else ("ERROR" if s.get("error") else "IDLE"))
        m_partner.setText(s.get("partner") or "—")
        stage_txt = s.get("flow_stage") or ""
        reason = s.get("flow_reason") or ""
        m_stage.setText((stage_txt + (" · " + reason if reason else "")) or "—")
        stat_vals["Matches"].setText(str(s.get("matches", 0)))
        stat_vals["Sent"].setText(str(s.get("sent", 0)))
        stat_vals["Recv"].setText(str(s.get("recv", 0)))
        stat_vals["Skips T/U"].setText(f"{s.get('skips_partner',0)}/{s.get('skips_ours',0)}")
        stat_vals["WS in/out"].setText(f"{s.get('ws_in',0)}/{s.get('ws_out',0)}")
        up = int(s.get("uptime_s", 0) or 0)
        stat_vals["Uptime"].setText(f"{up//60}m{up%60:02d}s")
        # drain log queue
        lines = []
        try:
            while True:
                lines.append(log_q.get_nowait())
        except queue.Empty:
            pass
        if lines:
            log_text.append("\n".join(lines[-200:]))

    def poll_sys() -> None:
        try:
            import psutil
            cpu_lbl.setText(f"CPU: {psutil.cpu_percent():.0f}%")
            ram_lbl.setText(f"RAM: {psutil.virtual_memory().percent:.0f}%")
        except Exception:
            cpu_lbl.setText("CPU: n/a")
            ram_lbl.setText("RAM: n/a")

    t_stats = QTimer()
    t_stats.timeout.connect(poll_stats)
    t_stats.start(1000)
    t_sys = QTimer()
    t_sys.timeout.connect(poll_sys)
    t_sys.start(2500)

    refresh_session()
    cfg = _load_config()
    engine_combo.setCurrentIndex(0 if (cfg.get("engine", "flow") == "flow") else 1)
    snap_edit.setText(", ".join(cfg.get("snap_usernames") or []))
    pr = cfg.get("persona") or {}
    p_name.setText(pr.get("name", "Alex")); p_age.setValue(int(pr.get("age", 21)))
    p_gender.setCurrentText(pr.get("gender", "f")); p_country.setText(pr.get("country", "Germany"))
    lp = cfg.get("loop") or {}
    idle_spin.setValue(int(lp.get("skip_idle_s", 90)))
    typing_cb.setChecked(bool(lp.get("typing_indicator", True)))
    autonext_cb.setChecked(bool(lp.get("auto_next", True)))

    logging.getLogger("eva").info("Dashboard চালু — root: %s", ROOT)
    win.show()
    return app.exec()


def main() -> None:
    sys.exit(run_gui())


if __name__ == "__main__":
    main()
