"""EVA web dashboard — session setup + bot control in the browser.

Run:  python -m eva.dashboard.server            (http://127.0.0.1:8800)
      python -m eva.dashboard.server --host 0.0.0.0 --port 8800

Panels:
  1. SESSION    — Launch Browser (CDP) -> manual login -> Save Session
  2. BOT        — Start / Stop, live state, partner, stats
  3. CONFIG     — engine + fixed file + loop tuning (saved to configs/chitchat_bot.json)
  4. LOGS       — live log tail
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from collections import deque
from pathlib import Path
from typing import Optional

from aiohttp import web

from ..transport.chitchat_api import ChitchatApi
from ..transport.chitchat_socket import ChitchatSocket
from ..transport.protocol import DEFAULT_UA
from ..transport.ws_chat_loop import LoopConfig, LoopState, WsChatLoop
from .cdp_session import CdpSessionManager, find_browser

log = logging.getLogger("eva.dashboard")

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "configs" / "chitchat_bot.json"
SESSION_PATH = ROOT / "configs" / "session.json"


class RingLog(logging.Handler):
    """Keep the last N log lines for the dashboard."""

    def __init__(self, n: int = 400) -> None:
        super().__init__()
        self.lines: deque = deque(maxlen=n)
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                                            datefmt="%H:%M:%S"))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append(self.format(record))
        except Exception:  # noqa: BLE001
            pass


class BotManager:
    """Owns the running WsChatLoop inside the dashboard process."""

    def __init__(self) -> None:
        self.loop_obj: Optional[WsChatLoop] = None
        self.api: Optional[ChitchatApi] = None
        self.task: Optional[asyncio.Task] = None
        self.error: str = ""

    @property
    def running(self) -> bool:
        return bool(self.loop_obj and self.loop_obj._running)

    def status(self) -> dict:
        if self.error and not self.running:
            return {"running": False, "error": self.error}
        if not self.loop_obj:
            return {"running": False}
        lp = self.loop_obj
        st = lp.stats.snapshot()
        ws = lp.socket.stats.snapshot()
        return {
            "running": self.running,
            "state": lp.state.value if isinstance(lp.state, LoopState) else str(lp.state),
            "partner": lp.partner.display() if lp.partner else None,
            "conversationId": lp.conversation_id or None,
            "matches": st.get("matches", 0),
            "sent": st.get("messages_sent", 0),
            "recv": st.get("messages_received", 0),
            "skips_partner": st.get("partner_skips", 0),
            "skips_ours": st.get("our_skips", 0),
            "flagged": st.get("flagged_403", 0),
            "uptime_s": st.get("uptime_s", 0),
            "ws": ws,
            "error": self.error,
        }

    async def start(self) -> None:
        if self.running:
            return
        self.error = ""
        if not SESSION_PATH.exists():
            self.error = "configs/session.json নেই — আগে 'Save Session' করো"
            raise RuntimeError(self.error)
        session = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
        cookies = session.get("cookies") or {}
        ua = session.get("user_agent") or DEFAULT_UA
        cfg = _load_config()

        engine_name = (cfg.get("engine") or "flow").lower()
        if engine_name == "fixed":
            from ..brain.fixed_reply_engine import FixedReplyEngine
            engine = FixedReplyEngine(script_path=cfg.get("fixed_file"),
                                      timing=cfg.get("timing"))
        else:
            from ..brain.flow_reply_engine import FlowReplyEngine
            engine = FlowReplyEngine(snap_usernames=cfg.get("snap_usernames"),
                                     timing=cfg.get("timing"))
        loop_cfg = LoopConfig(**{k: tuple(v) if isinstance(v, list) else v
                                 for k, v in (cfg.get("loop") or {}).items()})

        self.api = ChitchatApi(cookies, user_agent=ua,
                               message_body_format=cfg.get("message_body_format", "multipart"))
        me = await self.api.me()  # preflight — raises if session dead
        socket = ChitchatSocket(cookies, user_agent=ua)
        self.loop_obj = WsChatLoop(self.api, socket, engine, loop_cfg)
        await self.loop_obj.start()
        log.info("bot started as %s", me.get("username"))

    async def stop(self) -> None:
        if self.loop_obj:
            try:
                await self.loop_obj.stop("dashboard stop")
            except Exception:  # noqa: BLE001
                log.exception("stop failed")
        if self.api:
            try:
                await self.api.close()
            except Exception:  # noqa: BLE001
                pass
        self.loop_obj = None
        self.api = None


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    example = ROOT / "configs" / "chitchat_bot.example.json"
    if example.exists():
        try:
            return json.loads(example.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {}


def _save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


# ============================================================ HTTP handlers

def build_app() -> web.Application:
    ring = RingLog()
    logging.getLogger("eva").addHandler(ring)
    if not logging.getLogger("eva").handlers:
        logging.getLogger("eva").addHandler(logging.NullHandler())

    mgr = BotManager()
    cdp = CdpSessionManager()
    started = time.time()

    async def index(_req: web.Request) -> web.Response:
        return web.Response(text=HTML_PAGE, content_type="text/html", charset="utf-8")

    async def api_status(_req: web.Request) -> web.Response:
        session = cdp.session_status()
        username = None
        if session.get("exists"):
            try:
                me = await cdp.verify(_session_cookies(), _session_ua())
                username = (me or {}).get("username")
                session["verified"] = bool(me)
            except Exception:  # noqa: BLE001
                session["verified"] = False
        info = await cdp.cdp_info()
        return web.json_response({
            "bot": mgr.status(),
            "session": session,
            "session_username": username,
            "cdp": {"up": bool(info), "browser": (info or {}).get("Browser")},
            "browser_found": bool(find_browser()),
            "uptime_s": round(time.time() - started, 1),
            "logs": list(ring.lines)[-120:],
        })

    async def api_launch(_req: web.Request) -> web.Response:
        try:
            body = await _req.json()
        except Exception:  # noqa: BLE001
            body = {}
        if body.get("browser_path"):
            cdp.browser_path = body["browser_path"]
        result = await cdp.launch(start_url=body.get("url", "https://chitchat.gg"))
        return web.json_response(result)

    async def api_save_session(_req: web.Request) -> web.Response:
        try:
            result = await cdp.pull_and_save()
            return web.json_response(result)
        except Exception as exc:  # noqa: BLE001
            return web.json_response({"saved": False, "error": str(exc)}, status=400)

    async def api_bot_start(_req: web.Request) -> web.Response:
        try:
            await mgr.start()
            return web.json_response({"ok": True})
        except Exception as exc:  # noqa: BLE001
            mgr.error = str(exc)
            return web.json_response({"ok": False, "error": str(exc)}, status=400)

    async def api_bot_stop(_req: web.Request) -> web.Response:
        await mgr.stop()
        return web.json_response({"ok": True})

    async def api_config_get(_req: web.Request) -> web.Response:
        return web.json_response(_load_config())

    async def api_config_post(req: web.Request) -> web.Response:
        try:
            body = await req.json()
        except Exception:  # noqa: BLE001
            return web.json_response({"ok": False, "error": "bad json"}, status=400)
        cfg = _load_config()
        if "engine" in body:
            cfg["engine"] = body["engine"]
        if "fixed_file" in body:
            cfg["fixed_file"] = body["fixed_file"]
        if "loop" in body:
            cfg.setdefault("loop", {}).update(body["loop"])
        _save_config(cfg)
        return web.json_response({"ok": True})

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/api/status", api_status)
    app.router.add_post("/api/launch", api_launch)
    app.router.add_post("/api/save-session", api_save_session)
    app.router.add_post("/api/bot/start", api_bot_start)
    app.router.add_post("/api/bot/stop", api_bot_stop)
    app.router.add_get("/api/config", api_config_get)
    app.router.add_post("/api/config", api_config_post)
    return app


def _session_cookies() -> dict:
    try:
        return json.loads(SESSION_PATH.read_text(encoding="utf-8")).get("cookies") or {}
    except Exception:  # noqa: BLE001
        return {}


def _session_ua() -> str:
    try:
        return json.loads(SESSION_PATH.read_text(encoding="utf-8")).get("user_agent") or DEFAULT_UA
    except Exception:  # noqa: BLE001
        return DEFAULT_UA


# ============================================================ UI

HTML_PAGE = """<!doctype html>
<html lang="bn">
<head>
<meta charset="utf-8">
<title>EVA — Chitchat Bot Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root{--bg:#0d1117;--card:#161b22;--line:#30363d;--fg:#e6edf3;--dim:#8b949e;
        --ok:#3fb950;--bad:#f85149;--warn:#d29922;--acc:#58a6ff}
  *{box-sizing:border-box;font-family:'Segoe UI',system-ui,sans-serif}
  body{background:var(--bg);color:var(--fg);margin:0;padding:24px;max-width:980px;margin:auto}
  h1{font-size:1.4rem;margin:0 0 4px} h1 small{color:var(--dim);font-weight:400}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px}
  .card h2{font-size:1.02rem;margin:0 0 10px;color:var(--acc)}
  .full{grid-column:1/-1}
  button{background:#21262d;color:var(--fg);border:1px solid var(--line);border-radius:6px;
         padding:8px 14px;cursor:pointer;font-size:.92rem;margin:2px 4px 2px 0}
  button:hover{border-color:var(--acc)} button.primary{background:#1f6feb;border-color:#1f6feb}
  button.stop{background:#b62324;border-color:#b62324} button:disabled{opacity:.45;cursor:default}
  .badge{display:inline-block;padding:2px 10px;border-radius:12px;font-size:.8rem;
         border:1px solid var(--line)}
  .ok{color:var(--ok);border-color:var(--ok)} .bad{color:var(--bad);border-color:var(--bad)}
  .warn{color:var(--warn);border-color:var(--warn)}
  .stat{display:flex;gap:14px;flex-wrap:wrap;margin:6px 0}
  .stat div{background:#0d1117;border:1px solid var(--line);border-radius:8px;padding:8px 12px;min-width:86px}
  .stat b{display:block;font-size:1.25rem} .stat span{color:var(--dim);font-size:.75rem}
  input{background:#0d1117;border:1px solid var(--line);color:var(--fg);border-radius:6px;
        padding:7px 10px;width:110px;font-size:.9rem}
  input.wide{width:340px}
  #logs{background:#0d1117;border:1px solid var(--line);border-radius:8px;padding:10px;
        font-family:Consolas,monospace;font-size:.78rem;height:260px;overflow-y:auto;
        white-space:pre-wrap;color:#9fb3c8}
  .muted{color:var(--dim);font-size:.85rem} .row{margin:8px 0}
  #msg{margin-top:8px;font-size:.9rem;min-height:20px}
  .bn{font-size:.85rem;color:var(--dim)}
</style>
</head>
<body>
<h1>EVA — Chitchat Bot Dashboard <small id="uptime"></small></h1>
<div class="muted">session → browser login → save → bot start : সব এখান থেকেই</div>
<div id="msg"></div>

<div class="grid">
  <div class="card">
    <h2>🔑 সেশন (Session)</h2>
    <div>Status: <span id="sessBadge" class="badge">…</span>
         <span id="sessUser" class="muted"></span></div>
    <div class="row bn">১) Launch Browser → যে window খুলবে সেখানে chitchat.gg-তে LOGIN করো<br>
         ২) তারপর ফিরে এসে Save Session চাপো — cookies নিজেই টেনে আনবে</div>
    <div class="row">
      <button class="primary" onclick="launch()">🚀 Launch Browser</button>
      <button onclick="saveSession()">💾 Save Session</button>
    </div>
    <div class="row">
      <input id="browserPath" class="wide" placeholder="(optional) browser path — auto-detected">
      <button onclick="saveSessionPath()">Set Path</button>
    </div>
    <div id="cdpLine" class="muted"></div>
  </div>

  <div class="card">
    <h2>🤖 বট কন্ট্রোল</h2>
    <div>Status: <span id="botBadge" class="badge">STOPPED</span></div>
    <div class="row">
      <button class="primary" id="btnStart" onclick="botStart()">▶ Start Bot</button>
      <button class="stop" id="btnStop" onclick="botStop()">■ Stop</button>
    </div>
    <div class="stat">
      <div><b id="stMatches">0</b><span>matches</span></div>
      <div><b id="stSent">0</b><span>sent</span></div>
      <div><b id="stRecv">0</b><span>received</span></div>
      <div><b id="stPartner">-</b><span>partner</span></div>
    </div>
    <div class="stat">
      <div><b id="stWsIn">0</b><span>ws in</span></div>
      <div><b id="stWsOut">0</b><span>ws out</span></div>
      <div><b id="stSkip">0/0</b><span>skips them/us</span></div>
      <div><b id="stFlag">0</b><span>flagged 403</span></div>
    </div>
  </div>

  <div class="card">
    <h2>⚙️ কনফিগ (engine + loop)</h2>
    <div class="row">
      engine
      <select id="cEngine">
        <option value="flow">flow — SMS detect → input/output matching</option>
        <option value="fixed">fixed — txt ফাইল line-by-line</option>
      </select>
      fixed file <input id="cFixed" class="wide" placeholder="configs/fixed_script.txt">
    </div>
    <div class="row">
      skip idle (sec) <input id="cIdle" type="number" style="width:70px">
      typing indicator
      <select id="cTyping"><option value="true">on</option><option value="false">off</option></select>
      auto next
      <select id="cAuto"><option value="true">on</option><option value="false">off</option></select>
    </div>
    <button onclick="saveConfig()">💾 Save Config</button>
    <span class="bn">— Start Bot এর আগে save করো</span>
  </div>

  <div class="card">
    <h2>📜 লাইভ লগ</h2>
    <div id="logs">…</div>
  </div>
</div>

<script>
let cfgLoaded=false;
function $id(x){return document.getElementById(x)}
function msg(t,bad){const m=$id('msg');m.textContent=t||'';m.style.color=bad?'var(--bad)':'var(--ok)';
  if(t)setTimeout(()=>{if(m.textContent===t)m.textContent=''},6000)}
async function refresh(){
  try{
    const s=await (await fetch('/api/status')).json();
    // session
    const sb=$id('sessBadge'), su=$id('sessUser');
    if(s.session.exists){
      sb.textContent=s.session_username?'VALID ✓ ('+s.session_username+')':'SAVED (unverified)';
      sb.className='badge '+(s.session_username?'ok':'warn');
      su.textContent='';
    } else {sb.textContent='MISSING — Save করো';sb.className='badge bad'}
    $id('cdpLine').textContent='CDP browser: '+(s.cdp.up?('running — '+s.cdp.browser):'not running')+
      ' | system browser: '+(s.browser_found?'found ✓':'NOT FOUND (Chrome/Edge install করো বা path দাও)');
    // bot
    const b=s.bot||{};
    const bb=$id('botBadge');
    if(b.running){bb.textContent=b.state+(b.partner?(' — '+b.partner):'');bb.className='badge ok'}
    else{bb.textContent=b.error?('ERROR'):'STOPPED';bb.className='badge '+(b.error?'bad':'')}
    $id('stMatches').textContent=b.matches??0; $id('stSent').textContent=b.sent??0;
    $id('stRecv').textContent=b.recv??0; $id('stPartner').textContent=b.partner||'-';
    $id('stWsIn').textContent=(b.ws&&b.ws.frames_in)||0; $id('stWsOut').textContent=(b.ws&&b.ws.frames_out)||0;
    $id('stSkip').textContent=(b.skips_partner??0)+'/'+(b.skips_ours??0);
    $id('stFlag').textContent=b.flagged??0;
    $id('uptime').textContent='up '+Math.round(s.uptime_s||0)+'s';
    $id('logs').textContent=(s.logs||[]).join('\\n');
    $id('logs').scrollTop=$id('logs').scrollHeight;
    if(!cfgLoaded){loadConfig();cfgLoaded=true}
  }catch(e){msg('dashboard refresh failed: '+e,true)}
}
async function launch(){
  msg('browser launch হচ্ছে…');
  try{
    const r=await fetch('/api/launch',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({browser_path:$id('browserPath').value||undefined})});
    const d=await r.json();
    msg('browser: '+d.status+(d.browser?(' — '+d.browser):'')+(d.hint?(' — '+d.hint):''), d.status!=='launched'&&d.status!=='already-running');
  }catch(e){msg('launch failed: '+e,true)}
}
async function saveSession(){
  msg('cookies আনা হচ্ছে… (browser-এ login করেছো তো?)');
  try{
    const r=await fetch('/api/save-session',{method:'POST'});
    const d=await r.json();
    if(d.saved){msg('✓ session saved'+(d.username?(' — logged in as '+d.username):' (verify skip হয়েছে, নেট সমস্যা হতে পারে)'))}
    else msg('✗ '+d.error,true);
  }catch(e){msg('save failed: '+e,true)}
}
async function botStart(){
  try{const r=await fetch('/api/bot/start',{method:'POST'});const d=await r.json();
      msg(d.ok?'✓ bot started — live চলছে':'✗ '+(d.error||'start failed'),!d.ok)}
  catch(e){msg('start failed: '+e,true)}
}
async function botStop(){
  try{await fetch('/api/bot/stop',{method:'POST'});msg('bot stopped')}
  catch(e){msg('stop failed: '+e,true)}
}
async function loadConfig(){
  try{const c=await (await fetch('/api/config')).json();
    $id('cEngine').value=c.engine||'flow';
    $id('cFixed').value=c.fixed_file||'configs/fixed_script.txt';
    $id('cIdle').value=(c.loop&&c.loop.skip_idle_s)||90;
    $id('cTyping').value=String((c.loop&&c.loop.typing_indicator)??true);
    $id('cAuto').value=String((c.loop&&c.loop.auto_next)??true);
  }catch(e){}
}
async function saveConfig(){
  const body={engine:$id('cEngine').value,fixed_file:$id('cFixed').value,
              loop:{skip_idle_s:parseFloat($id('cIdle').value)||90,
                typing_indicator:$id('cTyping').value==='true',
                auto_next:$id('cAuto').value==='true'}};
  try{const r=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(body)});const d=await r.json();
      msg(d.ok?'✓ config saved':'✗ save failed',!d.ok)}catch(e){msg('config failed: '+e,true)}
}
refresh(); setInterval(refresh,2500);
</script>
</body>
</html>
"""


def main(argv: Optional[list] = None) -> None:
    ap = argparse.ArgumentParser(description="EVA dashboard")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8800)
    ap.add_argument("--cdp-port", type=int, default=9222)
    ap.add_argument("--no-open", action="store_true", help="don't auto-open the browser")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")

    app = build_app()
    url = f"http://{args.host}:{args.port}"
    print(f"\n  EVA Dashboard  ->  {url}\n")
    if not args.no_open:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
