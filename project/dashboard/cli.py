# -*- coding: utf-8 -*-
"""
Native Textual TUI Dashboard.
Tabs: Overview | Control | Settings | Logs | Fixed SMS | Debug | Leads
"""
import asyncio
import json
import time
import os
import sys
import logging
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll, Container
from textual.widgets import (
    TabbedContent,
    TabPane,
    DataTable,
    Static,
    Button,
    Input,
    Select,
    Label,
    RichLog,
    Switch,
)
from textual.binding import Binding

logger = logging.getLogger("cli_dashboard")

HERE = Path(__file__).resolve().parent


def _ts(ts):
    if not ts:
        return "-"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%H:%M:%S")
    except Exception:
        return "-"


class BotDashboard(App):
    CSS = """
    Screen { background: $surface; }
    #header { dock: top; height: 3; background: $boost; border-bottom: solid $primary; padding: 0 1; }
    .stat-box { border: round $primary; padding: 0 1; width: 1fr; height: 5; content-align: center middle; }
    .stats-row { height: 5; margin: 0 0 1 0; }
    .site-card { border: round $accent; padding: 0 1; width: 1fr; height: auto; margin: 0 0 1 0; }
    .site-card-title { text-style: bold; color: $text; }
    .site-card-stats { color: $text-muted; }
    .btn-row { height: 3; margin: 0 0 1 0; }
    .btn-row Button { margin-right: 1; }
    .settings-group { height: 3; margin: 0 0 1 0; }
    .settings-group Label { width: 20; padding: 1 1 0 0; color: $text-muted; }
    .settings-group Input, .settings-group Select { width: 35; }
    .settings-switch { height: 3; margin: 0 0 1 0; }
    .settings-switch Label { width: 20; padding: 1 1 0 0; color: $text-muted; }
    .section-title { text-style: bold; color: $primary; margin: 1 0 0 0; }
    RichLog { border: round $accent; }
    """

    TITLE = "Multi-Site Bot Dashboard"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, bots, db, proxy_mgr, reply_engine, config, config_path=None, fixed_engine=None,
                 db_reply_engine=None, mood_manager=None, thread_manager=None):
        super().__init__()
        self.bots = bots
        self.db = db
        self.proxy_mgr = proxy_mgr
        self.reply_engine = reply_engine
        self.config = config
        self.config_path = config_path
        self.fixed_engine = fixed_engine
        self.db_reply_engine = db_reply_engine
        self.mood_manager = mood_manager
        self.thread_manager = thread_manager
        self._start_time = time.time()
        self._last_log_id = 0
        self._log_site = "all"
        self._fsm_path_locked = False

    # ═══ Layout ═══
    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]Multi-Site Bot Dashboard[/]  |  Loading...",
            id="header",
        )
        with TabbedContent():
            # ── OVERVIEW ──
            with TabPane("Overview", id="tab-overview"):
                with VerticalScroll():
                    with Horizontal(classes="stats-row"):
                        yield Static("Leads\n0", id="stat-leads", classes="stat-box")
                        yield Static("Sent\n0", id="stat-sent", classes="stat-box")
                        yield Static("Recv\n0", id="stat-recv", classes="stat-box")
                        yield Static("Convos\n0", id="stat-convos", classes="stat-box")
                        yield Static("Users\n0", id="stat-users", classes="stat-box")
                        yield Static("Proxy\n0/0", id="stat-proxy", classes="stat-box")
                    yield Static("[bold]Sites[/]", classes="section-title")
                    yield Vertical(id="overview-sites")
                    yield Static("[bold]Recent Leads[/]", classes="section-title")
                    yield DataTable(id="overview-leads")
                    yield Static("[bold]Recent Messages[/]", classes="section-title")
                    yield DataTable(id="overview-msgs")

            # ── CONTROL ──
            with TabPane("Control", id="tab-control"):
                with Horizontal(classes="btn-row"):
                    yield Button("START ALL", id="btn-start-all", variant="success")
                    yield Button("STOP ALL", id="btn-stop-all", variant="error")
                    yield Label("", id="control-status")
                yield Static("[bold]Autostart[/]", classes="section-title")
                with Horizontal(classes="settings-switch"):
                    yield Label("Auto-start on launch")
                    yield Switch(value=self.config.get("autostart", False), id="ctrl-autostart")
                yield Vertical(id="control-sites")

            # ── SETTINGS ──
            with TabPane("Settings", id="tab-settings"):
                with VerticalScroll():
                    yield Static("[bold]Global Settings[/]", classes="section-title")
                    with Horizontal(classes="settings-group"):
                        yield Label("Data Dir (input/output)")
                        yield Input(value=self.config.get("data_dir", ""), id="g-data-dir", placeholder="../path/to/data")
                    with Horizontal(classes="settings-group"):
                        yield Label("Proxy File")
                        yield Input(value=self.config.get("proxy_file", "proxy.txt"), id="g-proxy-file")
                    with Horizontal(classes="settings-group"):
                        yield Label("Reply Delay Min (s)")
                        yield Input(value=str(self.config.get("reply_delay_min_sec", 2)), id="g-delay-min")
                    with Horizontal(classes="settings-group"):
                        yield Label("Reply Delay Max (s)")
                        yield Input(value=str(self.config.get("reply_delay_max_sec", 6)), id="g-delay-max")
                    with Horizontal(classes="settings-group"):
                        yield Label("Snap After N Msgs")
                        yield Input(value=str(self.config.get("snap_share_after_n_messages", 3)), id="g-snap-n")
                    with Horizontal(classes="settings-switch"):
                        yield Label("Use Proxy")
                        yield Switch(value=self.config.get("use_proxy", True), id="g-proxy")
                    with Horizontal(classes="settings-switch"):
                        yield Label("Autostart")
                        yield Switch(value=self.config.get("autostart", False), id="g-autostart")
                    with Horizontal(classes="btn-row"):
                        yield Button("Save Global", id="btn-save-global", variant="primary")
                    yield Static("[bold]Per-Site Settings[/]", classes="section-title")
                    yield Vertical(id="per-site-settings")
                    with Horizontal(classes="btn-row"):
                        yield Button("Save Config to Disk", id="btn-save-config", variant="primary")

            # ── LOGS ──
            with TabPane("Logs", id="tab-logs"):
                with Horizontal(classes="btn-row"):
                    yield Label("Site:")
                    yield Select(
                        [("All", "all"), ("Joingy", "joingy"), ("iSexyChat", "isexychat")],
                        value="all",
                        id="log-site-select",
                    )
                    yield Button("Clear", id="btn-clear-logs", variant="warning")
                    yield Label("0 logs", id="log-count")
                yield RichLog(id="log-view", highlight=True, markup=True)

            # ── FIXED SMS ──
            with TabPane("Fixed SMS", id="tab-fixedsms"):
                with VerticalScroll():
                    yield Static("[bold]Mode[/]", classes="section-title")
                    with Horizontal(classes="settings-switch"):
                        yield Label("Fixed SMS Mode")
                        yield Switch(value=False, id="fsm-toggle")
                    with Horizontal(classes="btn-row"):
                        yield Button("Apply", id="btn-fsm-toggle", variant="primary")
                    yield Static("[bold]Script Folder[/]", classes="section-title")
                    with Horizontal(classes="settings-group"):
                        yield Label("Folder Path")
                        yield Input(value="", id="fsm-folder", placeholder="D:\\chat_scripts")
                        yield Button("Browse", id="btn-fsm-browse-folder", variant="default")
                    with Horizontal(classes="btn-row"):
                        yield Button("Set Folder", id="btn-fsm-folder", variant="success")
                    yield Static("", id="fsm-files")
                    yield Static("[bold]Snap Username File[/]", classes="section-title")
                    with Horizontal(classes="settings-group"):
                        yield Label("File Path")
                        yield Input(value=self.config.get("fixed_sms", {}).get("snap_username_file", ""), id="fsm-snap-file")
                        yield Button("Browse", id="btn-fsm-browse-snap", variant="default")
                    with Horizontal(classes="btn-row"):
                        yield Button("Load Snap File", id="btn-fsm-snap", variant="primary")
                    yield Static("", id="fsm-snap-status")
                    yield Static("[bold]Active Assignments[/]", classes="section-title")
                    yield DataTable(id="fsm-assignments-table")

            # ── MODE ──
            with TabPane("MODE", id="tab-mode"):
                with VerticalScroll():
                    yield Static("[bold]Bot Mode[/]", classes="section-title")
                    with Horizontal(classes="settings-switch"):
                        yield Label("Template Engine Mode")
                        yield Switch(value=True, id="mode-template")
                    with Horizontal(classes="settings-switch"):
                        yield Label("Fixed SMS Mode")
                        yield Switch(value=False, id="mode-fixedsms")
                    with Horizontal(classes="settings-switch"):
                        yield Label("DB Reply Engine Mode")
                        yield Switch(value=False, id="mode-dbreply")
                    with Horizontal(classes="btn-row"):
                        yield Button("Apply Mode", id="btn-apply-mode", variant="primary")
                        yield Label("", id="mode-status")
                    yield Static("[bold]Mood Selector[/]", classes="section-title")
                    yield Static("Site Moods:", classes="site-card-title")
                    yield DataTable(id="mode-moods-table")
                    with Horizontal(classes="settings-group"):
                        yield Label("Site")
                        yield Select([], id="mood-site-select")
                        yield Label("Mood")
                        yield Select(
                            [("FLIRTY", "FLIRTY"), ("DIRECT", "DIRECT"), ("SHY", "SHY"),
                             ("AGGRESSIVE", "AGGRESSIVE"), ("RANDOM", "RANDOM")],
                            value="RANDOM",
                            id="mood-select",
                        )
                    with Horizontal(classes="settings-switch"):
                        yield Label("Auto Cycle")
                        yield Switch(value=True, id="mood-autocycle")
                    with Horizontal(classes="settings-group"):
                        yield Label("Cycle Interval (msgs)")
                        yield Input(value="5", id="mood-cycle-interval")
                    with Horizontal(classes="btn-row"):
                        yield Button("Set Mood", id="btn-set-mood", variant="primary")
                        yield Button("Cycle Now", id="btn-cycle-mood", variant="default")
                        yield Label("", id="mood-status-label")

            # ── DB BANK ──
            with TabPane("DB BANK", id="tab-dbbank"):
                with VerticalScroll():
                    yield Static("[bold]DB Reply Engine — Conversation State[/]", classes="section-title")
                    yield Static("", id="dbbank-stats")
                    yield Static("[bold]Active Conversations[/]", classes="section-title")
                    yield DataTable(id="dbbank-convos")
                    with Horizontal(classes="btn-row"):
                        yield Button("Refresh", id="btn-dbbank-refresh", variant="primary")
                        yield Button("Reset All", id="btn-dbbank-reset", variant="error")
                        yield Label("", id="dbbank-status")

            # ── THREADS ──
            with TabPane("THREADS", id="tab-threads"):
                with VerticalScroll():
                    yield Static("[bold]Thread Pool Status[/]", classes="section-title")
                    yield DataTable(id="threads-pool-table")
                    yield Static("[bold]Active Threads[/]", classes="section-title")
                    yield DataTable(id="threads-active-table")
                    with Horizontal(classes="btn-row"):
                        yield Button("Refresh", id="btn-threads-refresh", variant="primary")
                        yield Button("Cleanup", id="btn-threads-cleanup", variant="warning")
                        yield Label("", id="threads-status")

            # ── PROXY ──
            with TabPane("PROXY", id="tab-proxy"):
                with VerticalScroll():
                    yield Static("[bold]Proxy Pool[/]", classes="section-title")
                    yield Static("", id="proxy-stats-header")
                    yield DataTable(id="proxy-pool-table")
                    with Horizontal(classes="btn-row"):
                        yield Button("Refresh", id="btn-proxy-refresh", variant="primary")
                        yield Button("Reload Proxies", id="btn-proxy-reload", variant="warning")
                        yield Label("", id="proxy-status")

            # ── SNAP ──
            with TabPane("SNAP", id="tab-snap"):
                with VerticalScroll():
                    yield Static("[bold]Snapchat Management[/]", classes="section-title")
                    with Horizontal(classes="settings-group"):
                        yield Label("Snap Username")
                        yield Input(value="", id="snap-username-input", placeholder="your_snap_username")
                    with Horizontal(classes="settings-group"):
                        yield Label("Share After N Msgs")
                        yield Input(value="3", id="snap-after-n-input")
                    with Horizontal(classes="btn-row"):
                        yield Button("Apply", id="btn-snap-apply", variant="primary")
                        yield Label("", id="snap-status")
                    yield Static("[bold]Snap Leads[/]", classes="section-title")
                    yield DataTable(id="snap-leads-table")
                    yield Static("[bold]Snap Share Stats[/]", classes="section-title")
                    yield DataTable(id="snap-stats-table")

            # ── SMS ──
            with TabPane("SMS", id="tab-sms"):
                with VerticalScroll():
                    yield Static("[bold]SMS Engine Status[/]", classes="section-title")
                    with Horizontal(classes="settings-switch"):
                        yield Label("SMS Engine Enabled")
                        yield Switch(value=False, id="sms-engine-toggle")
                    with Horizontal(classes="btn-row"):
                        yield Button("Apply", id="btn-sms-apply", variant="primary")
                        yield Label("", id="sms-status")
                    yield Static("[bold]SMS Line Pool[/]", classes="section-title")
                    yield DataTable(id="sms-pool-table")
                    yield Static("[bold]SMS Session Assignments[/]", classes="section-title")
                    yield DataTable(id="sms-assignments-table")
                    with Horizontal(classes="btn-row"):
                        yield Button("Refresh", id="btn-sms-refresh", variant="primary")

            # ── DEBUG ──
            with TabPane("Debug", id="tab-debug"):
                with VerticalScroll():
                    with Horizontal(classes="btn-row"):
                        yield Label("Log Level:")
                        yield Select(
                            [("INFO", "INFO"), ("DEBUG", "DEBUG"),
                             ("WARNING", "WARNING"), ("CRITICAL", "CRITICAL")],
                            value=self.config.get("debug_level", "INFO"),
                            id="debug-level-select",
                        )
                    yield Static("[bold]Session States[/]", classes="section-title")
                    yield DataTable(id="debug-sessions")
                    yield Static("[bold]Recent Crashes[/]", classes="section-title")
                    yield DataTable(id="debug-crashes")
                    with Horizontal(classes="btn-row"):
                        yield Label("Trace Filter:")
                        yield Select(
                            [("All", "all"), ("Joingy", "joingy"), ("iSexyChat", "isexychat")],
                            value="all",
                            id="debug-trace-filter",
                        )
                    yield Static("[bold]Live Trace[/]", classes="section-title")
                    yield DataTable(id="debug-trace-live")
                    yield Static("[bold]Trace Errors[/]", classes="section-title")
                    yield DataTable(id="debug-trace-errors")
                    yield Static("[bold]Proxy Health[/]", classes="section-title")
                    yield Static("", id="debug-proxy")
                    with Horizontal(classes="btn-row"):
                        yield Button("Health Check", id="btn-health-check", variant="primary")
                        yield Button("Force GC", id="btn-force-gc", variant="warning")
                        yield Button("Clear Crashes", id="btn-clear-crashes", variant="default")
                        yield Button("Export Debug", id="btn-export-debug", variant="success")
                        yield Label("", id="debug-status")
                    yield Static("", id="debug-summary")

            # ── LEADS ──
            with TabPane("Leads", id="tab-leads"):
                with VerticalScroll():
                    yield Static("[bold]All Leads[/]", classes="section-title")
                    yield DataTable(id="leads-table")
                    yield Static("[bold]Per-Site Breakdown[/]", classes="section-title")
                    yield DataTable(id="breakdown-table")

    # ═══ Init ═══
    def on_mount(self) -> None:
        for table_id, cols in [
            ("overview-leads", ["Site", "Nick", "Conv", "Msgs", "Time"]),
            ("overview-msgs", ["Site", "Dir", "Nick", "Text", "Time"]),
            ("leads-table", ["Site", "Nick", "Conv", "Msgs", "Time"]),
            ("breakdown-table", ["Site", "Leads", "Msgs", "Users", "Convos", "Snaps"]),
            ("fsm-assignments-table", ["Site", "Session", "File", "Line"]),
            ("mode-moods-table", ["Site", "Mood", "Auto Cycle", "Interval"]),
            ("dbbank-convos", ["Site", "Conv ID", "State", "Msgs", "Middle", "Updated"]),
            ("threads-pool-table", ["Site", "Active", "Pending", "Completed", "Errors", "Max"]),
            ("threads-active-table", ["Site", "Session", "Status", "Started", "Errors", "Last Error"]),
            ("proxy-pool-table", ["Host:Port", "Protocol", "Status", "Uses", "Fails", "Successes", "Last Used"]),
            ("snap-leads-table", ["Site", "Nick", "Conv", "Msgs", "Time"]),
            ("snap-stats-table", ["Site", "Leads", "Snap Shares", "Total Msgs"]),
            ("sms-pool-table", ["Filename", "Lines", "Assignments"]),
            ("sms-assignments-table", ["Site", "Session", "File", "Line"]),
            ("debug-sessions", ["Site", "Session", "State", "Sent", "Recv", "Last Active"]),
            ("debug-crashes", ["Time", "Site", "Session", "Exception", "Msg"]),
            ("debug-trace-live", ["Time", "Site", "Session", "Dir", "Endpoint", "Status", "Ms", "Data"]),
            ("debug-trace-errors", ["Time", "Site", "Session", "Endpoint", "Status", "Error"]),
        ]:
            try:
                tbl = self.query_one(f"#{table_id}", DataTable)
                tbl.add_columns(*cols)
            except Exception:
                pass

        self._init_mood_site_select()
        self._build_site_cards()
        self.set_interval(2.0, self._refresh)
        self.set_interval(1.5, self._refresh_logs)
        self.set_interval(5.0, self._refresh_leads)
        self.set_interval(5.0, self._refresh_fsm)
        self.set_interval(5.0, self._refresh_mode)
        self.set_interval(4.0, self._refresh_dbbank)
        self.set_interval(3.0, self._refresh_threads)
        self.set_interval(4.0, self._refresh_proxy_tab)
        self.set_interval(5.0, self._refresh_snap_tab)
        self.set_interval(5.0, self._refresh_sms_tab)
        self.set_interval(3.0, self._refresh_debug)
        self.run_worker(self._async_init())

    async def _async_init(self):
        await self._build_per_site_settings()
        await self._refresh()
        await self._refresh_leads()

    # ═══ Build dynamic widgets ═══
    def _build_site_cards(self):
        try:
            ov = self.query_one("#overview-sites")
            ct = self.query_one("#control-sites")
            ov.remove_children()
            ct.remove_children()
        except Exception:
            return

        for name in self.bots:
            ov.mount(Static(
                f"[bold]{name}[/]  STOPPED\n"
                f"Sent: 0 | Recv: 0 | Leads: 0 | Convos: 0 | Users: 0 | Errors: 0 | Sessions: 0/0",
                id=f"ov-{name}",
                classes="site-card",
            ))
            card = Vertical(
                Static(f"[bold]{name}[/]  STOPPED", id=f"ctrl-title-{name}", classes="site-card-title"),
                Static("Sessions: 0/0 | Sent: 0 | Recv: 0 | Errors: 0", id=f"ctrl-stats-{name}", classes="site-card-stats"),
                Static("", id=f"ctrl-err-{name}"),
                Horizontal(
                    Button("START", id=f"btn-start-{name}", variant="success"),
                    Button("STOP", id=f"btn-stop-{name}", variant="error"),
                    Button("RESTART", id=f"btn-restart-{name}", variant="warning"),
                    classes="btn-row",
                ),
                classes="site-card",
            )
            ct.mount(card)

    async def _build_per_site_settings(self):
        try:
            container = self.query_one("#per-site-settings")
        except Exception:
            return
        container.remove_children()
        settings = await self.db.get_all_site_settings()

        for name in self.bots:
            s = settings.get(name, {})
            group = Vertical(
                Static(f"[bold]{name}[/]", classes="site-card-title"),
                Horizontal(
                    Label("Max Sessions"),
                    Input(value=str(s.get("max_sessions", 5)), id=f"ss-{name}-max"),
                    classes="settings-group",
                ),
                Horizontal(
                    Label("Delay Min (s)"),
                    Input(value=str(s.get("reply_delay_min", 2)), id=f"ss-{name}-dmin"),
                    classes="settings-group",
                ),
                Horizontal(
                    Label("Delay Max (s)"),
                    Input(value=str(s.get("reply_delay_max", 6)), id=f"ss-{name}-dmax"),
                    classes="settings-group",
                ),
                Horizontal(
                    Label("Snap After N"),
                    Input(value=str(s.get("snap_after_n", 3)), id=f"ss-{name}-snapn"),
                    classes="settings-group",
                ),
                Horizontal(
                    Label("Headless"),
                    Switch(value=bool(s.get("headless", 1)), id=f"ss-{name}-headless"),
                    classes="settings-switch",
                ),
                Horizontal(
                    Button(f"Save {name}", id=f"btn-save-{name}", variant="primary"),
                    classes="btn-row",
                ),
                classes="site-card",
            )
            container.mount(group)

    # ═══ Refresh ═══
    async def _refresh(self):
        try:
            stats = await self._gather_stats()
            self._update_header(stats)
            self._update_overview(stats)
            self._update_control(stats)
            self._update_breakdown(stats)
        except Exception as e:
            logger.debug(f"refresh error: {e}")

    async def _gather_stats(self):
        site_stats = await self.db.get_all_stats()
        total_leads = await self.db.get_total_leads()
        total_msgs = await self.db.get_total_messages()
        summary = await self.db.get_all_sites_summary()
        bot_stats = {}
        for name, bot in self.bots.items():
            bot_stats[name] = bot.stats()
        proxy_stats = self.proxy_mgr.stats() if self.proxy_mgr else {"total": 0, "available": 0, "dead": 0}
        return {
            "sites": {s["site"]: s for s in site_stats},
            "bots": bot_stats,
            "summary": summary,
            "totals": {"leads": total_leads, "messages": total_msgs},
            "proxy": proxy_stats,
        }

    def _update_header(self, stats):
        fsm_enabled = self.config.get("fixed_sms", {}).get("enabled", False)
        snap = ""
        if fsm_enabled and self.fixed_engine:
            snap = self.fixed_engine._snap_username or self.config.get("snap_username", "")
        if not snap:
            snap = self.config.get("snap_username", "")
        pa = stats["proxy"].get("available", 0)
        pt = stats["proxy"].get("total", 0)
        elapsed = int(time.time() - self._start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        try:
            self.query_one("#header").update(
                f"[bold]Multi-Site Bot Dashboard[/]  |  "
                f"Snap: {snap}  |  Proxy: {pa}/{pt}  |  Uptime: {h}h {m}m {s}s"
            )
        except Exception:
            pass

    def _update_overview(self, stats):
        total_sent = sum(b.get("total_sent", 0) for b in stats["bots"].values())
        total_recv = sum(b.get("total_received", 0) for b in stats["bots"].values())
        total_leads = stats["totals"]["leads"]
        total_conv = sum(s.get("total_conversations", 0) for s in stats["summary"].values())
        total_users = sum(s.get("total_users", 0) for s in stats["summary"].values())
        pa = stats["proxy"]["available"]
        pt = stats["proxy"]["total"]

        updates = {
            "stat-leads": f"Leads\n[bold orange]{total_leads}[/]",
            "stat-sent": f"Sent\n[bold blue]{total_sent}[/]",
            "stat-recv": f"Recv\n[bold green]{total_recv}[/]",
            "stat-convos": f"Convos\n[bold purple]{total_conv}[/]",
            "stat-users": f"Users\n[bold cyan]{total_users}[/]",
            "stat-proxy": f"Proxy\n[bold {'green' if pa > 0 else 'red'}]{pa}/{pt}[/]",
        }
        for wid, val in updates.items():
            try: self.query_one(f"#{wid}").update(val)
            except Exception: pass

        for name, bot in self.bots.items():
            sd = stats["sites"].get(name, {})
            sm = stats["summary"].get(name, {})
            running = sd.get("running", 0) == 1
            status = "[green]RUNNING[/]" if running else "[red]STOPPED[/]"
            text = (
                f"[bold]{name}[/]  {status}\n"
                f"Sent: {bot.get('total_sent', 0)} | Recv: {bot.get('total_received', 0)} | "
                f"Leads: {sm.get('total_leads', 0)} | Convos: {sm.get('total_conversations', 0)} | "
                f"Users: {sm.get('total_users', 0)} | Errors: {sd.get('errors', 0)} | "
                f"Sessions: {bot.get('active_sessions', 0)}/{bot.get('max_sessions', 0)}"
            )
            try: self.query_one(f"#ov-{name}").update(text)
            except Exception: pass

    def _update_control(self, stats):
        for name, bot in self.bots.items():
            sd = stats["sites"].get(name, {})
            running = sd.get("running", 0) == 1
            status = "[green]RUNNING[/]" if running else "[red]STOPPED[/]"
            try:
                self.query_one(f"#ctrl-title-{name}").update(f"[bold]{name}[/]  {status}")
                self.query_one(f"#ctrl-stats-{name}").update(
                    f"Sessions: {bot.get('active_sessions', 0)}/{bot.get('max_sessions', 0)} | "
                    f"Sent: {bot.get('total_sent', 0)} | Recv: {bot.get('total_received', 0)} | "
                    f"Errors: {sd.get('errors', 0)}"
                )
                err = sd.get("last_error", "")
                self.query_one(f"#ctrl-err-{name}").update(
                    f"[red]Last Error: {err}[/]" if err else ""
                )
                btn_start = self.query_one(f"#btn-start-{name}", Button)
                btn_stop = self.query_one(f"#btn-stop-{name}", Button)
                if running:
                    btn_start.disabled = True
                    btn_stop.disabled = False
                else:
                    btn_start.disabled = False
                    btn_stop.disabled = True
            except Exception:
                pass

    def _update_breakdown(self, stats):
        try:
            tbl = self.query_one("#breakdown-table", DataTable)
            tbl.clear()
            for site, s in stats["summary"].items():
                tbl.add_row(
                    site,
                    str(s.get("total_leads", 0)),
                    str(s.get("total_messages", 0)),
                    str(s.get("total_users", 0)),
                    str(s.get("total_conversations", 0)),
                    str(s.get("snap_shares", 0)),
                )
        except Exception:
            pass

    # ═══ Logs refresh ═══
    async def _refresh_logs(self):
        try:
            logs = await self.db.get_live_logs_since(self._log_site, self._last_log_id, limit=200)
            if not logs:
                return
            log_view = self.query_one("#log-view", RichLog)
            for l in logs:
                if l["id"] > self._last_log_id:
                    self._last_log_id = l["id"]
                t = _ts(l.get("timestamp"))
                site = l.get("site", "")
                direction = l.get("direction", "")
                nick = l.get("nickname", "")
                text = l.get("text", "")
                arrow = "[green]<[/]" if direction == "in" else ("[orange]>[/]" if direction == "out" else "[red]*[/]")
                log_view.write(f"[dim]{t}[/] [cyan]{site:<12}[/] {arrow} [dim]{nick}[/] {text}")
            try:
                self.query_one("#log-count").update(f"{self._last_log_id} logs")
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"log refresh error: {e}")

    # ═══ Leads refresh ═══
    async def _refresh_leads(self):
        try:
            leads = await self.db.get_recent_leads(50)
            msgs = await self.db.get_recent_messages(50)
            for table_id, data, cols in [
                ("overview-leads", leads, ["site", "nickname", "conversation_id", "messages_exchanged", "timestamp"]),
                ("leads-table", leads, ["site", "nickname", "conversation_id", "messages_exchanged", "timestamp"]),
                ("overview-msgs", msgs, ["site", "direction", "nickname", "text", "timestamp"]),
            ]:
                try:
                    tbl = self.query_one(f"#{table_id}", DataTable)
                    tbl.clear()
                    for row in data:
                        vals = []
                        for c in cols:
                            v = row.get(c, "")
                            if c == "timestamp": v = _ts(v)
                            elif c == "conversation_id": v = str(v)[:15] if v else "-"
                            elif c == "text": v = str(v)[:80] if v else ""
                            else: v = str(v) if v else ""
                            vals.append(v)
                        tbl.add_row(*vals)
                except Exception: pass
        except Exception as e:
            logger.debug(f"leads refresh error: {e}")

    # ═══ Fixed SMS refresh ═══
    async def _refresh_fsm(self):
        if not self.fixed_engine:
            return
        try:
            status = await self.fixed_engine.get_status()
            try:
                self.query_one("#fsm-toggle", Switch).value = status["enabled"]
            except Exception: pass
            if status.get("folder") and not self._fsm_path_locked:
                try: self.query_one("#fsm-folder", Input).value = status["folder"]
                except Exception: pass
            files_text = "\n".join(
                f"  {f['name']} ({f['lines']} lines)" for f in status.get("files", [])
            ) or "  No folder set"
            try: self.query_one("#fsm-files").update(files_text)
            except Exception: pass
            snap = status.get("snap_username", "")
            try:
                self.query_one("#fsm-snap-status").update(
                    f"[green]Snap: {snap}[/]" if snap else "[red]Snap not loaded[/]"
                )
            except Exception: pass
            assignments = await self.fixed_engine.get_assignments()
            try:
                tbl = self.query_one("#fsm-assignments-table", DataTable)
                tbl.clear()
                for a in assignments:
                    tbl.add_row(a["site"], a["session_id"], a["assigned_file"], str(a["current_line"]))
            except Exception: pass
        except Exception as e:
            logger.debug(f"fsm refresh error: {e}")

    # ═══ Debug refresh ═══
    async def _refresh_debug(self):
        try:
            from debug_utils import (get_state_inspector, get_crash_tracker,
                                     get_trace_capture, get_debug_level)
            insp = get_state_inspector()
            ct = get_crash_tracker()
            tc = get_trace_capture()

            sessions = insp.snapshot()
            tbl = self.query_one("#debug-sessions", DataTable); tbl.clear()
            for s in sessions[:30]:
                tbl.add_row(s.get("site", ""), str(s.get("session_id", "")), s.get("state", "?"),
                            str(s.get("messages_sent", 0)), str(s.get("messages_received", 0)),
                            _ts(s.get("last_activity", 0)))

            crashes = ct.get_recent(30)
            tbl = self.query_one("#debug-crashes", DataTable); tbl.clear()
            for c in crashes:
                tbl.add_row(c.get("ts", ""), c.get("site", ""), c.get("session", ""),
                            c.get("exc", ""), c.get("msg", "")[:80])

            cs = ct.stats()
            ps = self.proxy_mgr.stats() if self.proxy_mgr else {}
            ss = insp.stats(120)
            tstats = tc.stats()
            flaps = cs.get("flapping", [])
            flap_txt = f"  |  [red]Flapping: {', '.join(f['session'] for f in flaps[:3])}[/]" if flaps else ""
            try:
                self.query_one("#debug-summary").update(
                    f"[bold]Level:[/] {__import__('logging').getLevelName(get_debug_level())}"
                    f"  |  [bold]Sessions:[/] {ss.get('total', 0)} (idle {ss.get('idle', 0)})"
                    f"  |  [bold]Crashes:[/] {cs.get('total', 0)}{flap_txt}\n"
                    f"[bold]Trace:[/] {tstats.get('total_requests', 0)} req, "
                    f"{tstats.get('total_errors', 0)} err "
                    f"({tstats.get('error_rate', 0)}%), "
                    f"avg {tstats.get('latency_avg_ms', 0)}ms / p95 {tstats.get('latency_p95_ms', 0)}ms"
                    f"  |  [bold]Proxy:[/] {ps.get('available', 0)}/{ps.get('total', 0)} avail, "
                    f"{ps.get('dead', 0)} dead"
                )
            except Exception:
                pass
            try:
                self.query_one("#debug-proxy").update(
                    f"Proxy: {ps.get('available', 0)}/{ps.get('total', 0)} avail, "
                    f"{ps.get('dead', 0)} dead  |  "
                    f"Crashes: {cs.get('total', 0)}  |  "
                    f"Dead sessions: {ss.get('idle', 0)}"
                )
            except Exception: pass

            try:
                tf = self.query_one("#debug-trace-filter", Select).value
            except Exception:
                tf = "all"
            live = tc.get_recent(site=None if tf == "all" else tf, limit=25)
            tbl = self.query_one("#debug-trace-live", DataTable); tbl.clear()
            for e in live:
                tbl.add_row(e.get("ts", ""), e.get("site", ""), e.get("session", ""),
                            e.get("dir", ""), e.get("endpoint", "")[:40],
                            str(e.get("status", "")), str(e.get("latency_ms", "")),
                            e.get("data", "")[:60])

            errs = tc.errors_only(limit=30)
            tbl = self.query_one("#debug-trace-errors", DataTable); tbl.clear()
            for e in errs:
                tbl.add_row(e.get("ts", ""), e.get("site", ""), e.get("session", ""),
                            e.get("endpoint", ""), str(e.get("status", "")), e.get("error", "")[:120])
        except Exception as e:
            logger.debug(f"debug refresh error: {e}")

    # ═══ Button handlers ═══
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id
        if bid == "btn-start-all": self._start_all()
        elif bid == "btn-stop-all": self._stop_all()
        elif bid == "btn-save-global": self._save_global()
        elif bid == "btn-save-config": self._save_config()
        elif bid == "btn-clear-logs": self._clear_logs()
        elif bid and bid.startswith("btn-start-") and bid != "btn-start-all":
            self._toggle_site(bid.replace("btn-start-", ""), start=True)
        elif bid and bid.startswith("btn-stop-") and bid != "btn-stop-all":
            self._toggle_site(bid.replace("btn-stop-", ""), start=False)
        elif bid and bid.startswith("btn-restart-"):
            self._restart_site(bid.replace("btn-restart-", ""))
        elif bid and bid.startswith("btn-save-") and bid != "btn-save-global" and bid != "btn-save-config":
            site = bid.replace("btn-save-", "")
            if site in self.bots: self._save_site_settings(site)
        elif bid == "btn-fsm-toggle": self._fsm_toggle()
        elif bid == "btn-fsm-folder": self._fsm_set_folder()
        elif bid == "btn-fsm-browse-folder": self._browse_folder()
        elif bid == "btn-fsm-snap": self._fsm_set_snap()
        elif bid == "btn-fsm-browse-snap": self._browse_snap_file()
        elif bid == "btn-health-check": self._run_health_check()
        elif bid == "btn-force-gc": self._force_gc()
        elif bid == "btn-clear-crashes": self._clear_crashes()
        elif bid == "btn-export-debug": self._export_debug()
        elif bid == "btn-apply-mode": self._apply_mode()
        elif bid == "btn-set-mood": self._set_mood()
        elif bid == "btn-cycle-mood": self._cycle_mood()
        elif bid == "btn-dbbank-refresh": self._refresh_dbbank()
        elif bid == "btn-dbbank-reset": self._reset_dbbank()
        elif bid == "btn-threads-refresh": self._refresh_threads()
        elif bid == "btn-threads-cleanup": self._cleanup_threads()
        elif bid == "btn-proxy-refresh": self._refresh_proxy_tab()
        elif bid == "btn-proxy-reload": self._reload_proxies()
        elif bid == "btn-snap-apply": self._apply_snap()
        elif bid == "btn-sms-apply": self._apply_sms()
        elif bid == "btn-sms-refresh": self._refresh_sms_tab()

    def _start_all(self):
        for bot in self.bots.values():
            if not bot.running:
                asyncio.create_task(bot.start())
        self._notify("Starting all sites...")

    def _stop_all(self):
        for bot in self.bots.values():
            if bot.running:
                asyncio.create_task(bot.stop())
        self._notify("Stopping all sites...")

    def _toggle_site(self, site, start=True):
        if site not in self.bots: return
        bot = self.bots[site]
        if start and not bot.running:
            asyncio.create_task(bot.start())
            self._notify(f"{site}: starting...")
        elif not start and bot.running:
            asyncio.create_task(bot.stop())
            self._notify(f"{site}: stopping...")

    def _restart_site(self, site):
        if site not in self.bots: return
        bot = self.bots[site]
        async def _do():
            if bot.running: await bot.stop(); await asyncio.sleep(1)
            await bot.start()
        asyncio.create_task(_do())
        self._notify(f"{site}: restarting...")

    def _save_global(self):
        try:
            data_dir = self.query_one("#g-data-dir", Input).value
            proxy_file = self.query_one("#g-proxy-file", Input).value
            dmin = float(self.query_one("#g-delay-min", Input).value or 2)
            dmax = float(self.query_one("#g-delay-max", Input).value or 6)
            snap_n = int(self.query_one("#g-snap-n", Input).value or 3)
            use_proxy = self.query_one("#g-proxy", Switch).value
            autostart = self.query_one("#g-autostart", Switch).value

            self.config["data_dir"] = data_dir
            self.config["proxy_file"] = proxy_file
            self.config["reply_delay_min_sec"] = dmin
            self.config["reply_delay_max_sec"] = dmax
            self.config["snap_share_after_n_messages"] = snap_n
            self.config["use_proxy"] = use_proxy
            self.config["autostart"] = autostart

            for bot in self.bots.values():
                bot.update_config({
                    "snap_share_after_n_messages": snap_n,
                    "reply_delay_min_sec": dmin,
                    "reply_delay_max_sec": dmax,
                })
            self._notify("Global settings saved")
        except Exception as e:
            self._notify(f"Error: {e}", error=True)

    def _save_site_settings(self, site):
        try:
            max_s = int(self.query_one(f"#ss-{site}-max", Input).value or 5)
            dmin = float(self.query_one(f"#ss-{site}-dmin", Input).value or 2)
            dmax = float(self.query_one(f"#ss-{site}-dmax", Input).value or 6)
            snap_n = int(self.query_one(f"#ss-{site}-snapn", Input).value or 3)
            headless_val = self.query_one(f"#ss-{site}-headless", Switch).value
            headless = 1 if headless_val else 0

            settings = {
                "max_sessions": max_s,
                "reply_delay_min": dmin,
                "reply_delay_max": dmax,
                "snap_after_n": snap_n,
                "headless": headless,
            }

            async def _do():
                await self.db.update_site_settings(site, settings)
                if site in self.bots:
                    self.bots[site].update_config(settings)

            asyncio.create_task(_do())
            self._notify(f"{site} settings saved")
        except Exception as e:
            self._notify(f"Error: {e}", error=True)

    def _save_config(self):
        if not self.config_path:
            self._notify("Config path not available", error=True)
            return
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            self._notify("Config saved to disk")
        except Exception as e:
            self._notify(f"Error: {e}", error=True)

    def _clear_logs(self):
        async def _do():
            await self.db.clear_live_logs(self._log_site if self._log_site != "all" else None)
            self._last_log_id = 0
            try: self.query_one("#log-view", RichLog).clear()
            except Exception: pass
        asyncio.create_task(_do())
        self._notify("Logs cleared")

    # ═══ Fixed SMS ═══
    def _fsm_toggle(self):
        if not self.fixed_engine:
            self._notify("Fixed SMS not available", error=True)
            return
        try:
            enabled = self.query_one("#fsm-toggle", Switch).value
            self.fixed_engine.set_enabled(enabled)
            self.config.setdefault("fixed_sms", {})["enabled"] = enabled
            self._notify(f"Fixed SMS: {'ON' if enabled else 'OFF'}")
        except Exception as e:
            self._notify(f"Error: {e}", error=True)

    def _fsm_set_folder(self):
        if not self.fixed_engine:
            self._notify("Fixed SMS not available", error=True)
            return
        path = self.query_one("#fsm-folder", Input).value.strip()
        if not path:
            self._notify("Enter folder path", error=True)
            return
        self._fsm_path_locked = True
        async def _do():
            result = await self.fixed_engine.set_folder(path)
            if result.get("ok"):
                self.config.setdefault("fixed_sms", {})["folder"] = path
                self._notify(f"Folder: {len(result['files'])} files loaded")
            else:
                self._notify(result.get("error", "Error"), error=True)
            self._fsm_path_locked = False
        asyncio.create_task(_do())

    def _fsm_set_snap(self):
        if not self.fixed_engine:
            self._notify("Fixed SMS not available", error=True)
            return
        path = self.query_one("#fsm-snap-file", Input).value.strip()
        if not path:
            self._notify("Enter snap file path", error=True)
            return
        async def _do():
            self.config.setdefault("fixed_sms", {})["snap_username_file"] = path
            snap = await self.fixed_engine.load_snap_username()
            self._notify(f"Snap: {snap}")
        asyncio.create_task(_do())

    def _browse_folder(self):
        async def _do():
            path = await asyncio.to_thread(self._pick_folder_dialog)
            if path:
                try: self.query_one("#fsm-folder", Input).value = path
                except Exception: pass
        asyncio.create_task(_do())

    @staticmethod
    def _pick_folder_dialog():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        folder = filedialog.askdirectory(title="Select Script Folder")
        root.destroy()
        return folder

    def _browse_snap_file(self):
        async def _do():
            path = await asyncio.to_thread(self._pick_file_dialog)
            if path:
                try: self.query_one("#fsm-snap-file", Input).value = path
                except Exception: pass
        asyncio.create_task(_do())

    @staticmethod
    def _pick_file_dialog():
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        f = filedialog.askopenfilename(title="Select Snap Username File",
                                        filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        root.destroy()
        return f

    # ═══ Debug actions ═══
    def _run_health_check(self):
        async def _do():
            results = {}
            for name, bot in self.bots.items():
                if hasattr(bot, 'health_check'):
                    r = await bot.health_check()
                    results[name] = r
            total_active = sum(r.get("active", 0) for r in results.values())
            total_dead = sum(r.get("dead", 0) for r in results.values())
            self._notify(f"Health: {total_active} active, {total_dead} dead")
            try:
                self.query_one("#debug-status").update(
                    f"[green]Health: {total_active} active, {total_dead} dead cleaned[/]"
                )
            except Exception: pass
        asyncio.create_task(_do())

    def _force_gc(self):
        import gc
        collected = gc.collect()
        self._notify(f"GC: collected {collected}")
        try: self.query_one("#debug-status").update(f"[green]GC: {collected} objects freed[/]")
        except Exception: pass

    def _set_debug_level(self, level):
        try:
            from debug_utils import set_debug_level
            set_debug_level(level)
            self.config["debug_level"] = level
            try: self.query_one("#debug-status").update(f"[green]Log level -> {level}[/]")
            except Exception: pass
        except Exception as e:
            self._notify(f"Level: {e}", error=True)

    def _clear_crashes(self):
        async def _do():
            try:
                from debug_utils import get_crash_tracker
                n = len(get_crash_tracker().get_recent(limit=10000))
                get_crash_tracker().clear()
                self._notify(f"Crash history cleared ({n})")
                try: self.query_one("#debug-status").update(f"[green]Cleared {n} crash records[/]")
                except Exception: pass
            except Exception as e:
                self._notify(f"Clear: {e}", error=True)
        asyncio.create_task(_do())

    def _export_debug(self):
        async def _do():
            try:
                from debug_utils import export_debug_dump
                ps = self.proxy_mgr.stats() if self.proxy_mgr else {}
                path = export_debug_dump(proxy_stats=ps)
                self._notify(f"Debug dump: {path.name}")
                try: self.query_one("#debug-status").update(f"[green]Exported: {path}[/]")
                except Exception: pass
            except Exception as e:
                self._notify(f"Export: {e}", error=True)
        asyncio.create_task(_do())

    # ═══ MODE tab ═══
    async def _refresh_mode(self):
        try:
            if self.mood_manager:
                moods = await self.mood_manager.get_all_moods()
                tbl = self.query_one("#mode-moods-table", DataTable); tbl.clear()
                for site, info in moods.items():
                    tbl.add_row(site, info["mood"],
                                "Yes" if info["auto_cycle"] else "No",
                                str(info["cycle_interval"]))
            if self.fixed_engine:
                try: self.query_one("#mode-fixedsms", Switch).value = self.fixed_engine.is_enabled()
                except Exception: pass
        except Exception as e:
            logger.debug(f"mode refresh error: {e}")

    def _init_mood_site_select(self):
        try:
            sel = self.query_one("#mood-site-select", Select)
            sel.set_options([(name, name) for name in self.bots.keys()])
        except Exception: pass

    def _apply_mode(self):
        async def _do():
            try:
                template = self.query_one("#mode-template", Switch).value
                fixedsms = self.query_one("#mode-fixedsms", Switch).value
                dbreply = self.query_one("#mode-dbreply", Switch).value
                mode = "template" if template else ("fixedsms" if fixedsms else ("dbreply" if dbreply else "none"))
                if self.fixed_engine:
                    self.fixed_engine.set_enabled(fixedsms)
                self.config["mode"] = mode
                self._notify(f"Mode: {mode}")
                try: self.query_one("#mode-status").update(f"[green]{mode}[/]")
                except Exception: pass
            except Exception as e:
                self._notify(f"Error: {e}", error=True)
        asyncio.create_task(_do())

    def _set_mood(self):
        if not self.mood_manager:
            self._notify("Mood manager not available", error=True)
            return
        async def _do():
            site = self.query_one("#mood-site-select", Select).value
            mood = self.query_one("#mood-select", Select).value
            autocycle = self.query_one("#mood-autocycle", Switch).value
            interval = int(self.query_one("#mood-cycle-interval", Input).value or 5)
            if site and mood:
                await self.mood_manager.set_mood(site, mood)
                await self.mood_manager.set_auto_cycle(site, autocycle, interval)
                self._notify(f"Mood: {site} → {mood}")
                try: self.query_one("#mood-status-label").update(f"[green]{site}: {mood}[/]")
                except Exception: pass
        asyncio.create_task(_do())

    def _cycle_mood(self):
        if not self.mood_manager:
            self._notify("Mood manager not available", error=True)
            return
        async def _do():
            site = self.query_one("#mood-site-select", Select).value
            if site:
                new_mood = await self.mood_manager.cycle(site)
                self._notify(f"Cycled {site} → {new_mood}")
                try: self.query_one("#mood-status-label").update(f"[green]{site} → {new_mood}[/]")
                except Exception: pass
        asyncio.create_task(_do())

    # ═══ DB BANK tab ═══
    async def _refresh_dbbank(self):
        try:
            if not self.db_reply_engine:
                try: self.query_one("#dbbank-stats").update("[dim]DB Reply Engine not loaded[/]")
                except Exception: pass
                return
            stats = await self.db_reply_engine.get_stats()
            total = stats.get("total_conversations", 0)
            breakdown = stats.get("by_site_state", {})
            line = f"Total: [bold]{total}[/] conversations  |  "
            for site, states in breakdown.items():
                line += f"{site}: " + " ".join(f"{s}={c}" for s, c in states.items()) + "  "
            try: self.query_one("#dbbank-stats").update(line)
            except Exception: pass

            convos = await self.db_reply_engine.get_conversations(limit=50)
            tbl = self.query_one("#dbbank-convos", DataTable); tbl.clear()
            for c in convos:
                tbl.add_row(c.get("site", ""), str(c.get("conversation_id", ""))[:20],
                            c.get("state", ""), str(c.get("msg_count", 0)),
                            str(c.get("middle_count", 0)), _ts(c.get("updated_at", 0)))
        except Exception as e:
            logger.debug(f"dbbank refresh error: {e}")

    def _reset_dbbank(self):
        if not self.db_reply_engine:
            self._notify("DB Reply Engine not available", error=True)
            return
        async def _do():
            self.db_reply_engine.reset()
            self._notify("DB reply state reset")
            try: self.query_one("#dbbank-status").update("[green]Reset complete[/]")
            except Exception: pass
        asyncio.create_task(_do())

    # ═══ THREADS tab ═══
    async def _refresh_threads(self):
        try:
            if not self.thread_manager:
                return
            pool_stats = await self.thread_manager.get_pool_stats()
            tbl = self.query_one("#threads-pool-table", DataTable); tbl.clear()
            for site, s in pool_stats.items():
                tbl.add_row(site, str(s.get("active", 0)), str(s.get("pending", 0)),
                            str(s.get("completed", 0)), str(s.get("errors", 0)),
                            str(s.get("max_concurrent", 0)))

            active = await self.thread_manager.get_active_threads()
            tbl = self.query_one("#threads-active-table", DataTable); tbl.clear()
            for a in active:
                tbl.add_row(a["site"], a["session_id"], a["status"],
                            _ts(a.get("started_at", 0)), str(a.get("errors", 0)),
                            a.get("last_error", "")[:60])
        except Exception as e:
            logger.debug(f"threads refresh error: {e}")

    def _cleanup_threads(self):
        if not self.thread_manager:
            self._notify("Thread manager not available", error=True)
            return
        async def _do():
            await self.thread_manager.cleanup()
            self._notify("Threads cleaned")
            try: self.query_one("#threads-status").update("[green]Cleanup complete[/]")
            except Exception: pass
        asyncio.create_task(_do())

    # ═══ PROXY tab ═══
    async def _refresh_proxy_tab(self):
        try:
            if not self.proxy_mgr:
                return
            ps = self.proxy_mgr.stats()
            try:
                self.query_one("#proxy-stats-header").update(
                    f"Total: [bold]{ps['total']}[/]  |  "
                    f"Available: [bold green]{ps['available']}[/]  |  "
                    f"Dead: [bold red]{ps['dead']}[/]"
                )
            except Exception: pass

            tbl = self.query_one("#proxy-pool-table", DataTable); tbl.clear()
            for p in self.proxy_mgr.proxies[:100]:
                status = "[green]ALIVE[/]" if p.available else "[red]DEAD[/]"
                tbl.add_row(p.key, p.protocol, status, str(p.uses), str(p.fails),
                            str(p.successes), _ts(p.last_used))
        except Exception as e:
            logger.debug(f"proxy tab refresh error: {e}")

    def _reload_proxies(self):
        async def _do():
            self.proxy_mgr.proxies.clear()
            proxy_file = self.config.get("proxy_file", "proxy.txt")
            self.proxy_mgr._load(proxy_file)
            self._notify(f"Reloaded {self.proxy_mgr.total} proxies")
            try: self.query_one("#proxy-status").update(f"[green]{self.proxy_mgr.total} proxies[/]")
            except Exception: pass
        asyncio.create_task(_do())

    # ═══ SNAP tab ═══
    async def _refresh_snap_tab(self):
        try:
            leads = await self.db.get_recent_leads(50)
            tbl = self.query_one("#snap-leads-table", DataTable); tbl.clear()
            for l in leads:
                tbl.add_row(l.get("site", ""), l.get("nickname", ""),
                            str(l.get("conversation_id", ""))[:15],
                            str(l.get("messages_exchanged", 0)), _ts(l.get("timestamp", 0)))

            summary = await self.db.get_all_sites_summary()
            tbl = self.query_one("#snap-stats-table", DataTable); tbl.clear()
            for site, s in summary.items():
                tbl.add_row(site, str(s.get("total_leads", 0)),
                            str(s.get("snap_shares", 0)), str(s.get("total_messages", 0)))

            try:
                self.query_one("#snap-username-input", Input).value = self.config.get("snap_username", "")
                self.query_one("#snap-after-n-input", Input).value = str(self.config.get("snap_share_after_n_messages", 3))
            except Exception: pass
        except Exception as e:
            logger.debug(f"snap tab refresh error: {e}")

    def _apply_snap(self):
        async def _do():
            try:
                snap = self.query_one("#snap-username-input", Input).value.strip()
                after_n = int(self.query_one("#snap-after-n-input", Input).value or 3)
                self.config["snap_username"] = snap
                self.config["snap_share_after_n_messages"] = after_n
                self.reply_engine.snap_username = snap
                self.reply_engine.snap_after_n = after_n
                for bot in self.bots.values():
                    bot.update_config({"snap_username": snap, "snap_share_after_n_messages": after_n})
                self._notify(f"Snap: {snap} (after {after_n} msgs)")
                try: self.query_one("#snap-status").update(f"[green]{snap}[/]")
                except Exception: pass
            except Exception as e:
                self._notify(f"Error: {e}", error=True)
        asyncio.create_task(_do())

    # ═══ SMS tab ═══
    async def _refresh_sms_tab(self):
        try:
            if not self.fixed_engine:
                return
            status = await self.fixed_engine.get_status()
            try: self.query_one("#sms-engine-toggle", Switch).value = status["enabled"]
            except Exception: pass

            pool_table = self.query_one("#sms-pool-table", DataTable); pool_table.clear()
            for f in status.get("files", []):
                assignments = await self.fixed_engine.get_assignments()
                file_assignments = sum(1 for a in assignments if a.get("assigned_file") == f["name"])
                pool_table.add_row(f["name"], str(f["lines"]), str(file_assignments))

            assignments = await self.fixed_engine.get_assignments()
            tbl = self.query_one("#sms-assignments-table", DataTable); tbl.clear()
            for a in assignments:
                tbl.add_row(a["site"], a["session_id"], a["assigned_file"], str(a["current_line"]))
        except Exception as e:
            logger.debug(f"sms tab refresh error: {e}")

    def _apply_sms(self):
        if not self.fixed_engine:
            self._notify("SMS Engine not available", error=True)
            return
        async def _do():
            try:
                enabled = self.query_one("#sms-engine-toggle", Switch).value
                self.fixed_engine.set_enabled(enabled)
                self.config.setdefault("fixed_sms", {})["enabled"] = enabled
                self._notify(f"SMS Engine: {'ON' if enabled else 'OFF'}")
                try: self.query_one("#sms-status").update(f"[green]{'ON' if enabled else 'OFF'}[/]")
                except Exception: pass
            except Exception as e:
                self._notify(f"Error: {e}", error=True)
        asyncio.create_task(_do())

    # ═══ Select / Switch handlers ═══
    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "log-site-select":
            self._log_site = event.value
            self._last_log_id = 0
            try: self.query_one("#log-view", RichLog).clear()
            except Exception: pass
        elif event.select.id == "debug-level-select":
            self._set_debug_level(event.value)

    def on_switch_changed(self, event: Switch.Changed) -> None:
        pass  # switches are read on Save button press

    # ═══ Utils ═══
    def _notify(self, msg, error=False):
        try:
            self.query_one("#control-status").update(f"[{'red' if error else 'green'}]{msg}[/]")
        except Exception: pass

    def action_refresh(self):
        asyncio.create_task(self._refresh())
        asyncio.create_task(self._refresh_leads())


def run_dashboard(bots, db, proxy_mgr, reply_engine, config, config_path=None, fixed_engine=None,
                  db_reply_engine=None, mood_manager=None, thread_manager=None):
    app = BotDashboard(bots, db, proxy_mgr, reply_engine, config, config_path=config_path, fixed_engine=fixed_engine,
                       db_reply_engine=db_reply_engine, mood_manager=mood_manager, thread_manager=thread_manager)
    app.run()
