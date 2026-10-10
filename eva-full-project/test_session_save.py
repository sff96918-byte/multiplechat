"""test_session_save.py — browserless session: token save + headless CLI (v28).

Checks (synthetic; real configs/session.json is never touched, no network):
  * core.session_chat imports with PyQt6 blocked (browserless CLI needs no GUI library)
  * --save with a valid token writes configs/session.json (temp path) and the file
    is discoverable as a session source
  * --save with a 401 token writes NOTHING and returns 2
  * the token value is never printed
  * the CLI run path closes the API session even when WsChatLoop.start() fails

    python test_session_save.py
"""
import contextlib
import io
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

passed = failed = 0


def ok(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {extra}")


# 1. browserless import: block PyQt6 before importing the module
for mod in list(sys.modules):
    if mod.startswith("PyQt6") or mod == "core.session_chat":
        del sys.modules[mod]
sys.modules["PyQt6"] = None          # any `import PyQt6` now raises ImportError
sys.modules["PyQt6.QtCore"] = None
try:
    import core.session_chat as sc   # noqa: E402
    ok("import without PyQt6", True)
except Exception as exc:  # noqa: BLE001
    ok("import without PyQt6", False, repr(exc))
    sys.exit(1)

FAKE_TOKEN = "fake-token-abcdef-0123456789"
tmpdir = tempfile.mkdtemp()
sc.SESSION_FILE = Path(tmpdir) / "configs" / "session.json"   # never the real file


class _FakeApiOK:
    def __init__(self, cookies, user_agent=""):
        self.cookies = cookies

    async def me(self):
        return {"username": "tester", "id": "u1"}

    async def close(self):
        return None


class _FakeApi401(_FakeApiOK):
    async def me(self):
        raise sc.SessionExpiredError(401, "/users/me", {})


def run_save(api_cls, token):
    sc.ChitchatApi = api_cls
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = sc._cli(["--save", "--token", token])
    return rc, buf.getvalue()


# 2. valid token -> file written, discoverable
rc, out = run_save(_FakeApiOK, FAKE_TOKEN)
ok("--save valid returns 0", rc == 0, f"rc={rc} out={out!r}")
ok("session file created", sc.SESSION_FILE.exists())
if sc.SESSION_FILE.exists():
    data = json.loads(sc.SESSION_FILE.read_text(encoding="utf-8"))
    ok("saved token value matches", data.get("cookies", {}).get("token") == FAKE_TOKEN)
    ok("no tmp file left behind", not sc.SESSION_FILE.with_suffix(".json.tmp").exists())
    if os.name != "nt":
        ok("file mode is 0600", (sc.SESSION_FILE.stat().st_mode & 0o777) == 0o600)
ok("token never printed", FAKE_TOKEN not in out)

# discoverable as a session source
sc.ROOT = Path(tmpdir)
sources = sc.discover_session_sources()
ok("saved file is a session source",
   any(s.get("kind") == "session_json" for s in sources), repr(sources))

# 3. 401 token -> nothing written, rc 2
sc.SESSION_FILE.unlink()
rc, out = run_save(_FakeApi401, "bad-token-xxxxxx")
ok("--save 401 returns 2", rc == 2, f"rc={rc}")
ok("401 writes no session file", not sc.SESSION_FILE.exists())
ok("401 token never printed", "bad-token-xxxxxx" not in out)

# 4. run path: WsChatLoop.start() fails -> API session still closed
closed = {"api": False}


class _TrackApi(_FakeApiOK):
    async def close(self):
        closed["api"] = True


class _BoomLoop:
    def __init__(self, *a, **k):
        self._running = False

    async def start(self):
        raise RuntimeError("boom start")

    async def stop(self, reason=""):
        return None


sc.ChitchatApi = _TrackApi
sc.WsChatLoop = _BoomLoop
sc.ChitchatSocket = lambda *a, **k: None
sc.save_session_file(FAKE_TOKEN)           # give resolve_session a source
buf = io.StringIO()
try:
    with contextlib.redirect_stdout(buf):
        rc = sc._cli(["--run", "--token", FAKE_TOKEN])
except Exception as exc:  # noqa: BLE001
    rc = f"raised {type(exc).__name__}"
ok("run path: API session closed when start() fails", closed["api"], f"rc={rc}")

# 5. --import from a browser capture cookie file (v29 bridge)
IMP_TOKEN = "import-token-zyxw-98765"
IMP_SESSION = "import-session-cookie-abc"
cap_file = Path(tmpdir) / "session_cookies.LOCAL.json"


def write_cap(cookies):
    cap_file.write_text(json.dumps({"cookies": cookies, "origins": []}), encoding="utf-8")


write_cap([
    {"name": "token", "value": IMP_TOKEN, "domain": ".chitchat.gg"},
    {"name": "__Secure-text-session", "value": IMP_SESSION, "domain": "app.chitchat.gg"},
    {"name": "unrelated", "value": "zzz", "domain": "example.com"},
])
if sc.SESSION_FILE.exists():
    sc.SESSION_FILE.unlink()
sc.ChitchatApi = _FakeApiOK
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = sc._cli(["--import", str(cap_file)])
out = buf.getvalue()
ok("--import valid returns 0", rc == 0, f"rc={rc} out={out!r}")
if sc.SESSION_FILE.exists():
    saved = json.loads(sc.SESSION_FILE.read_text(encoding="utf-8")).get("cookies", {})
    ok("--import keeps token + session cookie", saved == {"token": IMP_TOKEN, "__Secure-text-session": IMP_SESSION}, repr(sorted(saved)))
    ok("--import drops non-chitchat cookie", "unrelated" not in saved)
else:
    ok("--import keeps token + session cookie", False, "no session file")
ok("--import never prints token/session value", IMP_TOKEN not in out and IMP_SESSION not in out)
sources = sc.discover_session_sources()
ok("--import result is a session source", any(s.get("kind") == "session_json" for s in sources))

# 5b. no token in file -> rc 2, nothing written
sc.SESSION_FILE.unlink()
write_cap([{"name": "__Secure-text-session", "value": IMP_SESSION, "domain": "app.chitchat.gg"}])
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = sc._cli(["--import", str(cap_file)])
ok("--import without token returns 2 and writes nothing", rc == 2 and not sc.SESSION_FILE.exists(), f"rc={rc}")
ok("--import without token prints no cookie value", IMP_SESSION not in buf.getvalue())

# 5c. 401 token from file -> rc 2, nothing written
write_cap([{"name": "token", "value": IMP_TOKEN, "domain": ".chitchat.gg"}])
sc.ChitchatApi = _FakeApi401
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = sc._cli(["--import", str(cap_file)])
ok("--import 401 returns 2 and writes nothing", rc == 2 and not sc.SESSION_FILE.exists(), f"rc={rc}")
ok("--import 401 prints no token value", IMP_TOKEN not in buf.getvalue())

# 6. browser-intercepted WebSocket URL + User-Agent (v31)
sc.ChitchatApi = _FakeApiOK
from core.ws_transport.chitchat_socket import ChitchatSocket as _RealSocket  # noqa: E402
sc.ChitchatSocket = _RealSocket   # section 4 ছিল dummy — আসল class ফেরত
GOOD_WS = "wss://api.chitchat.gg/socket.io/?EIO=4&transport=websocket"
ok("valid_chitchat_ws_url accepts chitchat wss", sc.valid_chitchat_ws_url(GOOD_WS) == GOOD_WS)
ok("valid_chitchat_ws_url rejects http", sc.valid_chitchat_ws_url("https://chitchat.gg/x") == "")
ok("valid_chitchat_ws_url rejects other host", sc.valid_chitchat_ws_url("wss://evil.example.com/s") == "")
ok("valid_chitchat_ws_url rejects lookalike host", sc.valid_chitchat_ws_url("wss://chitchat.gg.evil.com/s") == "")

meta_path = cap_file.parent / "session_meta.LOCAL.json"
meta_path.write_text(json.dumps({"ws_url": GOOD_WS, "user_agent": "UA-TEST/1.0"}), encoding="utf-8")
write_cap([{"name": "token", "value": IMP_TOKEN, "domain": ".chitchat.gg"}])
if sc.SESSION_FILE.exists():
    sc.SESSION_FILE.unlink()
with contextlib.redirect_stdout(io.StringIO()):
    rc = sc._cli(["--import", str(cap_file)])
saved = json.loads(sc.SESSION_FILE.read_text(encoding="utf-8")) if sc.SESSION_FILE.exists() else {}
ok("--import stores browser ws_url", rc == 0 and saved.get("ws_url") == GOOD_WS, repr(saved.get("ws_url")))
ok("--import stores browser user_agent", saved.get("user_agent") == "UA-TEST/1.0", repr(saved.get("user_agent")))
ok("saved_ws_url reads it back", sc.saved_ws_url() == GOOD_WS)
sock = sc._socket_for({"token": IMP_TOKEN}, "UA-TEST/1.0")
ok("--run socket uses saved ws_url", sock._ws_url == GOOD_WS, repr(sock._ws_url))

meta_path.write_text(json.dumps({"ws_url": "wss://evil.example.com/x", "user_agent": "UA"}), encoding="utf-8")
sc.SESSION_FILE.unlink()
with contextlib.redirect_stdout(io.StringIO()):
    sc._cli(["--import", str(cap_file)])
saved = json.loads(sc.SESSION_FILE.read_text(encoding="utf-8")) if sc.SESSION_FILE.exists() else {}
ok("--import drops invalid ws_url", "ws_url" not in saved)
sock = sc._socket_for({"token": IMP_TOKEN}, "UA")
ok("socket falls back to captured URL when none saved", sock._ws_url == sc.CHITCHAT_WS_URL if hasattr(sc, "CHITCHAT_WS_URL") else sock._ws_url.startswith("wss://api.chitchat.gg/"), repr(sock._ws_url))
meta_path.unlink()

print(f"\nRESULT: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
