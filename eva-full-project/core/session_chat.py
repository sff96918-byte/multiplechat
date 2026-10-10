"""SESSION CHAT — account session/token দিয়ে browser ছাড়া লাইভ chat।

* Reply logic = প্রজেক্টের নিজের ``chat.ChatRuleBot`` (eva_flow diagram funnel) —
  browser mode যে engine দিয়ে উত্তর দেয়, session mode হুবহু সেটাই ব্যবহার করে
  (data/input + data/output categories, snap round-robin, সব এক)।
* Human timing = প্রজেক্টের নিজের config (``human_behavior`` + ``chat_timing``) —
  browser mode-এর typing simulator/reading pause-এর মতোই।
* Worker = QThread + pyqtSignal (ChitchatWorker-এর একই pattern) — GUI সরাসরি
  Live Chat feed-এ লাইন পাঠায়, আলাদা কোনো process/setup লাগে না।

CLI (ডিবাগের জন্য):  python -m core.session_chat --list
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from PyQt6.QtCore import QThread, pyqtSignal
except ImportError:  # browserless CLI (--save / --run) works without the GUI library
    QThread = object  # type: ignore[assignment,misc]

    def pyqtSignal(*_args, **_kwargs):  # type: ignore[no-redef]
        return None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config_loader import load_chat_timing, load_runtime_config  # noqa: E402
from core.ws_transport.chitchat_api import ChitchatApi, SessionExpiredError  # noqa: E402
from core.ws_transport.chitchat_socket import ChitchatSocket  # noqa: E402
from core.ws_transport.ws_chat_loop import LoopConfig, WsChatLoop  # noqa: E402

log = logging.getLogger("session_chat")

FALLBACK_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
SESSION_THREAD_ID = 97          # Live Chat feed-এ [S97] হিসেবে দেখাবে
DOMAIN_HINT = "chitchat"


# ----------------------------------------------------------------- sessions
def _b64_user_from_token(token: str) -> str:
    """JWT payload থেকে username/id (শুধু দেখানোর জন্য — কোনো secret নয়)।"""
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return "?"
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(pad))
        return str(payload.get("username") or payload.get("id") or "?")
    except Exception:  # noqa: BLE001
        return "?"


def _cookies_from_storage_state(path: Path) -> Dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    picked: Dict[str, str] = {}
    for c in data.get("cookies") or []:
        if DOMAIN_HINT in (c.get("domain") or "").lstrip(".") and c.get("value"):
            picked[c["name"]] = c["value"]
    if "token" not in picked:
        raise RuntimeError(f"{path}-এ chitchat 'token' cookie নেই")
    return picked


def discover_session_sources() -> List[dict]:
    """সব usable session source: account_sessions/* + configs/session.json।"""
    out: List[dict] = []
    sj = ROOT / "configs" / "session.json"
    if sj.exists():
        try:
            data = json.loads(sj.read_text(encoding="utf-8"))
            cks = data.get("cookies") or {}
            if "token" in cks:
                user = _b64_user_from_token(cks["token"])
                out.append({"label": f"session.json (user: {user})",
                            "path": str(sj), "kind": "session_json"})
        except Exception as exc:  # noqa: BLE001
            log.debug("session.json skip: %s", exc)
    adir = ROOT / "account_sessions"
    if adir.is_dir():
        for d in sorted(adir.iterdir()):
            ss = d / "storage_state.json"
            if not ss.exists():
                continue
            try:
                _cookies_from_storage_state(ss)   # validate
            except Exception as exc:  # noqa: BLE001
                log.debug("account session skip %s: %s", d.name, exc)
                continue
            email = ""
            mp = d / "metadata.json"
            if mp.exists():
                try:
                    email = json.loads(mp.read_text(encoding="utf-8")).get("email") or ""
                except Exception:  # noqa: BLE001
                    pass
            label = f"{d.name.replace('account_', '')[:14]}… ({email or 'saved session'})"
            out.append({"label": label, "path": str(ss), "kind": "storage_state"})
    return out


def resolve_session(label: str = "", token: str = "") -> Tuple[Dict[str, str], str, str]:
    """(cookies, user_agent, human_label) — token দিলে সেটাই priority।"""
    token = (token or "").strip()
    if token:
        return {"token": token}, FALLBACK_UA, f"acc token (user: {_b64_user_from_token(token)})"
    sources = discover_session_sources()
    if not sources:
        raise RuntimeError(
            "কোনো session পাওয়া যায়নি — browser mode-এ একবার login করলে "
            "account_sessions তৈরি হবে, অথবা উপরে acc token পেস্ট করো")
    pick = sources[0]
    for s in sources:
        if s["label"] == label:
            pick = s
            break
    path = Path(pick["path"])
    if pick["kind"] == "storage_state":
        cookies = _cookies_from_storage_state(path)
        ua = ""       # storage_state-এ UA থাকে না — fallback
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
        cookies = dict(data.get("cookies") or {})
        ua = data.get("user_agent") or ""
    return cookies, ua or FALLBACK_UA, pick["label"]


# ----------------------------------------------------------------- engine
def _session_loop_config() -> LoopConfig:
    """Silence timeout = config (Settings → Silence timeout). Chat cap নেই।"""
    try:
        silence = float(load_chat_timing().get("silence_timeout_seconds", 90.0))
    except Exception:  # noqa: BLE001
        silence = 90.0
    return LoopConfig(skip_idle_s=silence, skip_after_msgs=0)


class _ChatRuleEngine:
    """WsChatLoop-এর engine API → প্রজেক্টের ChatRuleBot (eva_flow funnel)।

    Browser mode যেভাবে উত্তর ঠিক করে (new_conversation → reply →
    pending_replies), session mode হুবহু সেভাবেই করে।
    """

    name = "flow"

    def __init__(self) -> None:
        from chat import ChatRuleBot          # প্রজেক্টের নিজের engine
        self.bot = ChatRuleBot()
        self._states: Dict[str, Dict[str, Any]] = {}
        self._load_timing()

    def _load_timing(self) -> None:
        try:
            self.chat_timing = load_chat_timing()
        except Exception:  # noqa: BLE001
            self.chat_timing = {}
        try:
            self.human = load_runtime_config().get("human_behavior") or {}
        except Exception:  # noqa: BLE001
            self.human = {}

    def _state_for(self, partner: dict) -> Dict[str, Any]:
        pid = (partner or {}).get("id") or "?"
        if pid not in self._states:
            self._states[pid] = self.bot.new_conversation()
        return self._states[pid]

    @staticmethod
    def _with_pending(reply: str, state: Dict[str, Any]) -> str:
        pending = state.get("pending_replies") or []
        state["pending_replies"] = []
        parts = [r for r in ([reply] + list(pending)) if r]
        return "\n".join(parts)

    def opener(self, partner: dict) -> str:
        state = self._state_for(partner)
        reply = self.bot.reply("hi", state)          # greeting pool
        out = self._with_pending(reply, state)
        log.debug("opener: %r %s", (out or "")[:60], self.bot.last_debug_summary())
        return out

    def reply(self, partner: dict, incoming: str, history=None) -> str:
        state = self._state_for(partner)
        reply = self.bot.reply(incoming or "hi", state)
        out = self._with_pending(reply, state)
        log.debug("flow %r -> %r | %s", (incoming or "")[:40], (out or "")[:60],
                  self.bot.last_debug_summary())
        return out

    def forget(self, partner_id: str) -> None:
        self._states.pop(partner_id, None)

    def snap_shared(self, partner_id: str) -> bool:
        st = self._states.get(partner_id or "?")
        return bool(st and st.get("snap_pivoted"))

    # ---- human timing (browser mode-এর মতোই, প্রজেক্ট config থেকে) ----
    def _hb(self, key: str, default: float) -> float:
        try:
            return float(self.human.get(key, default))
        except (TypeError, ValueError):
            return default

    def delay_for(self, incoming: str) -> float:
        text = incoming or "hi"
        total = (random.uniform(self._hb("reaction_pause_min_seconds", 0.25),
                                self._hb("reaction_pause_max_seconds", 0.85))
                 + random.uniform(self._hb("read_reply_min_seconds", 0.8),
                                  self._hb("read_reply_max_seconds", 2.5))
                 + min(len(text) * self._hb("typing_ms_per_char", 20.0) / 1000.0,
                       self._hb("typing_max_seconds", 2.5)))
        if random.random() < self._hb("micro_idle_chance", 0.35):
            total += random.uniform(self._hb("micro_idle_min_seconds", 0.4),
                                    self._hb("micro_idle_max_seconds", 1.8))
        return round(total, 2)

    def opener_delay(self) -> float:
        ct = self.chat_timing or {}
        lo = float(ct.get("new_chat_delay_min_seconds", 5.0))
        hi = float(ct.get("new_chat_delay_max_seconds", 5.0))
        return round(random.uniform(min(lo, hi), max(lo, hi)), 2)


# ----------------------------------------------------------------- worker
class SessionChatWorker(QThread):
    """ChitchatWorker-এর মতোই QThread worker — কিন্তু browser নয়, WS token chat।

    Signals একই ধাঁচে: log_signal / chat_signal(thread_id, who, text) /
    session_signal / finished_signal — GUI-র বাকি সব কিছু অপরিবর্তিত।
    """

    log_signal = pyqtSignal(str)
    chat_signal = pyqtSignal(int, str, str)
    session_signal = pyqtSignal(int, str)
    finished_signal = pyqtSignal()

    def __init__(self, cookies: Dict[str, str], ua: str, label: str = "",
                 max_matches: int = 0, parent=None):
        super().__init__(parent)
        self._cookies = dict(cookies)
        self._ua = ua or FALLBACK_UA
        self._label = label
        self._max_matches = max_matches
        self._stop_requested = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._chat_loop: Optional[WsChatLoop] = None

    # ---- GUI API ----
    def request_stop(self) -> None:
        self._stop_requested = True
        loop, cl = self._loop, self._chat_loop
        if loop and cl and cl._running:
            async def _stop():
                try:
                    await cl.stop("dashboard stop")
                except Exception:  # noqa: BLE001
                    pass
            try:
                asyncio.run_coroutine_threadsafe(_stop(), loop)
            except RuntimeError:
                pass

    # ---- thread ----
    def run(self) -> None:  # noqa: D102 (QThread override)
        try:
            asyncio.run(self._amain())
        except Exception as exc:  # noqa: BLE001
            msg = f"{type(exc).__name__}: {exc}"
            if "SessionExpired" in msg or isinstance(exc, SessionExpiredError):
                msg = ("SESSION মেয়াদ শেষ (401) — browser mode-এ chitchat.gg আবার "
                       "login করে নতুন session/token দাও")
            self.log_signal.emit(f"[session] [X] {msg}")
        finally:
            self.finished_signal.emit()

    async def _amain(self) -> None:
        self._loop = asyncio.get_running_loop()
        api = ChitchatApi(self._cookies, user_agent=self._ua)
        try:
            me = await api.me()                      # preflight — 401 হলে এখানেই শেষ
        except BaseException:                        # 401 বা net fail — session ফেলে নয়
            try:
                await api.close()
            except Exception:  # noqa: BLE001
                pass
            raise
        who = me.get("username", "?")
        self.log_signal.emit(f"[session] [ok] token valid — logged in as {who} "
                             f"(id={me.get('id')})  session: {self._label}")
        self.session_signal.emit(SESSION_THREAD_ID, f"token-live ({who})")

        engine = _ChatRuleEngine()                   # প্রজেক্টের নিজের reply logic
        socket = _socket_for(self._cookies, self._ua)
        cfg = _session_loop_config()
        self._chat_loop = WsChatLoop(api, socket, engine, cfg)

        t0 = time.monotonic()
        last_partner: Optional[str] = None
        try:
            # v26: start() inside try, so a failed start still closes the API session
            await self._chat_loop.start()
            self.log_signal.emit("[session] [ok] SESSION CHAT LIVE — token দিয়ে chat চলছে "
                                 "(browser ছাড়া, engine = প্রজেক্টের flow funnel)")
            while self._chat_loop._running and not self._stop_requested:
                await asyncio.sleep(5)
                st = self._chat_loop.stats.snapshot()
                partner = self._chat_loop.partner.display() if self._chat_loop.partner else ""
                if partner and partner != last_partner:
                    self.log_signal.emit(f"[session] [chat] new partner: {partner}")
                    last_partner = partner
                if partner and self._chat_loop.conversation_id:
                    # বটের সর্বশেষ পাঠানো লাইন feed-এ আসে chat_signal দিয়ে (নিচে hook)
                    pass
                self.log_signal.emit(
                    f"[session] [stat] state={self._chat_loop.state.value} "
                    f"partner={partner or '-'} matches={st['matches']} "
                    f"sent={st['messages_sent']} recv={st['messages_received']} "
                    f"dropped={st['dropped_replies']} send_fail_streak={self._chat_loop._send_failures} "
                    f"up={int(time.monotonic() - t0)}s")
                if self._max_matches and st["matches"] >= self._max_matches:
                    self.log_signal.emit(f"[session] [i] max-matches {self._max_matches} "
                                         "হয়েছে — থামানো হচ্ছে")
                    await self._chat_loop.stop("max-matches")
        finally:
            try:
                if self._chat_loop and self._chat_loop._running:
                    await self._chat_loop.stop("worker exit")
            except Exception:  # noqa: BLE001
                pass
            try:
                await api.close()
            except Exception:  # noqa: BLE001
                pass
            st = self._chat_loop.stats.snapshot() if self._chat_loop else {}
            self.log_signal.emit(f"[session] [done] matches={st.get('matches', 0)} "
                                 f"sent={st.get('messages_sent', 0)} "
                                 f"recv={st.get('messages_received', 0)}")


# ----------------------------------------------------------------- CLI
SESSION_FILE = ROOT / "configs" / "session.json"   # .gitignore-এ আছে, zip-এ যায় না


def read_chitchat_cookies(path: Path) -> Dict[str, str]:
    """Browser capture-এর cookie ফাইল (Playwright storage_state বা cookie list) থেকে
    chitchat cookie নেয়। মান return করে, print করে না। 'token' না থাকলে RuntimeError।"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    cookies = data.get("cookies", []) if isinstance(data, dict) else data
    if not isinstance(cookies, list):
        raise RuntimeError("cookie ফাইলের format চেনা যাচ্ছে না")
    picked: Dict[str, str] = {}
    for c in cookies:
        if not isinstance(c, dict):
            continue
        if DOMAIN_HINT in (c.get("domain") or "").lstrip(".") and c.get("value") and c.get("name"):
            picked[str(c["name"])] = str(c["value"])
    if "token" not in picked:
        raise RuntimeError("cookie ফাইলে chitchat 'token' cookie নেই — browser-এ login করে capture আবার চালাও")
    return picked


def valid_chitchat_ws_url(url: str) -> str:
    """Browser-এ intercept করা WebSocket URL — শুধু wss:// এবং chitchat.gg host হলে গ্রহণ।
    অন্য কিছু হলে "" (অজানা URL কখনো ব্যবহার হবে না)।"""
    from urllib.parse import urlsplit
    try:
        u = urlsplit((url or "").strip())
    except ValueError:
        return ""
    host = (u.hostname or "").lower()
    if u.scheme != "wss" or not (host == "chitchat.gg" or host.endswith(".chitchat.gg")):
        return ""
    return (url or "").strip()


def saved_ws_url() -> str:
    """configs/session.json-এ সেভ করা ws_url (না থাকলে "")।"""
    try:
        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return valid_chitchat_ws_url(str(data.get("ws_url") or ""))


def _socket_for(cookies: Dict[str, str], ua: str) -> ChitchatSocket:
    """সেভ করা ws_url থাকলে সেটি, না থাকলে protocol-এর captured URL।"""
    url = saved_ws_url()
    if url:
        return ChitchatSocket(cookies, user_agent=ua, ws_url=url)
    return ChitchatSocket(cookies, user_agent=ua)


def save_session_file(token: str, user_agent: str = "",
                      extra_cookies: Optional[Dict[str, str]] = None,
                      saved_by: str = "core.session_chat --save",
                      ws_url: str = "") -> Path:
    """session configs/session.json-এ লেখে (atomic, মান কোথাও print হয় না)।

    extra_cookies: browser capture থেকে আসা অন্য chitchat cookie (socket-এর জন্য)।
    """
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    cookies: Dict[str, str] = {k: str(v) for k, v in (extra_cookies or {}).items() if v}
    cookies["token"] = token.strip()
    data = {
        "cookies": cookies,
        "user_agent": user_agent or FALLBACK_UA,
        "saved_by": saved_by,
    }
    if valid_chitchat_ws_url(ws_url):
        data["ws_url"] = valid_chitchat_ws_url(ws_url)
    tmp = SESSION_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        tmp.chmod(0o600)   # Windows-এ no-op, Linux/macOS-এ শুধু মালিক পড়তে পারবে
    except OSError:
        pass
    tmp.replace(SESSION_FILE)
    return SESSION_FILE


def _cli(argv: Optional[List[str]] = None) -> int:
    import argparse
    import getpass
    ap = argparse.ArgumentParser(
        description="Browserless session chat: token save + headless live chat (GUI-র বাইরে)")
    ap.add_argument("--list", action="store_true", help="saved session source দেখাও")
    ap.add_argument("--token", default="", help="acc token (না দিলে --save এ hidden prompt)")
    ap.add_argument("--save", action="store_true",
                    help="token যাচাই করে configs/session.json-এ সেভ করো")
    ap.add_argument("--run", action="store_true",
                    help="--save-এর পরেও live chat চালাও (ডিফল্ট: --save হলে থামে)")
    ap.add_argument("--import", dest="import_file", default="",
                    help="browser capture-এর session_cookies.LOCAL.json → যাচাই করে সেভ")
    ap.add_argument("--max-matches", type=int, default=0)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")

    if args.import_file:
        try:
            cookies = read_chitchat_cookies(Path(args.import_file))
        except (OSError, ValueError, RuntimeError) as exc:
            print(f"[X] {exc}")
            return 2

        async def _check_full() -> dict:
            api = ChitchatApi(cookies, user_agent=FALLBACK_UA)
            try:
                return await api.me()
            finally:
                await api.close()
        try:
            me = asyncio.run(_check_full())
        except SessionExpiredError:
            print("[X] cookie-র token কাজ করছে না (401) — browser capture আবার চালিয়ে নতুন login নাও")
            return 2
        except Exception as exc:  # noqa: BLE001
            print(f"[X] server যাচাই করা যায়নি ({type(exc).__name__}) — নেটওয়ার্ক দেখো")
            return 2
        meta: Dict[str, str] = {}
        meta_path = Path(args.import_file).parent / "session_meta.LOCAL.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                meta = {}
        ws_url = valid_chitchat_ws_url(str(meta.get("ws_url") or ""))
        ua = str(meta.get("user_agent") or "")
        path = save_session_file(cookies["token"], user_agent=ua, extra_cookies=cookies,
                                 saved_by=f"core.session_chat --import ({Path(args.import_file).name})",
                                 ws_url=ws_url)
        if ws_url:
            print("[ok] WebSocket URL browser থেকে নেওয়া হয়েছে (chitchat.gg host যাচাই করা)")
        else:
            print("[i] session_meta.LOCAL.json নেই বা URL অবৈধ — protocol-এর captured URL ব্যবহার হবে")
        print(f"[ok] session valid — user: {me.get('username', '?')} (id={me.get('id', '?')})")
        print(f"[ok] {len(cookies)}টি chitchat cookie সেভ হয়েছে: {path}")
        if not args.run:
            return 0

    if args.save:
        token = args.token or getpass.getpass("acc token পেস্ট করো (দেখাবে না): ")
        if not token.strip():
            print("[X] token খালি")
            return 2

        async def _check() -> dict:
            api = ChitchatApi({"token": token.strip()}, user_agent=FALLBACK_UA)
            try:
                return await api.me()
            finally:
                await api.close()
        try:
            me = asyncio.run(_check())
        except SessionExpiredError:
            print("[X] token কাজ করছে না (401) — নতুন token নাও")
            return 2
        path = save_session_file(token)
        print(f"[ok] token valid — user: {me.get('username', '?')} (id={me.get('id', '?')})")
        print(f"[ok] সেভ হয়েছে: {path}")
        if not args.run:
            return 0

    sources = discover_session_sources()
    print(f"{len(sources)}ta session source:")
    for i, s in enumerate(sources, 1):
        print(f"  {i}. {s['label']}")
    if args.list:
        return 0
    try:
        cookies, ua, label = resolve_session(token=args.token)
    except RuntimeError as exc:
        print(f"[X] {exc}")
        return 2
    print(f"[i] session: {label}")

    engine = _ChatRuleEngine()
    print("[i] engine check: opener =", repr(engine.opener({"id": "cli-test"}))[:80])
    engine.forget("cli-test")

    async def _go():
        api = ChitchatApi(cookies, user_agent=ua)
        loop = None
        try:
            me = await api.me()
            print(f"[ok] logged in as {me.get('username')}")
            loop = WsChatLoop(api, _socket_for(cookies, ua), engine,
                              _session_loop_config())
            await loop.start()   # v28: start() ও try-এর ভিতরে — ব্যর্থ হলেও API session বন্ধ হবে
            print("[ok] LIVE — Ctrl+C to stop")
            while loop._running:
                await asyncio.sleep(5)
                st = loop.stats.snapshot()
                print(f"[stat] matches={st['matches']} sent={st['messages_sent']} "
                      f"recv={st['messages_received']}")
                if args.max_matches and st["matches"] >= args.max_matches:
                    await loop.stop("max-matches")
        finally:
            if loop is not None:
                await loop.stop("exit")
            await api.close()
    try:
        asyncio.run(_go())
    except SessionExpiredError:
        print("[X] SESSION মেয়াদ শেষ (401) — নতুন token দিয়ে --save করো")
        return 2
    except KeyboardInterrupt:
        print("\n[i] থামানো হয়েছে")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
