"""CDP session manager — launch a real Chrome/Edge browser for manual login,
then pull the chitchat.gg session cookies through the Chrome DevTools Protocol.

Flow (all buttons on the dashboard):
  1. launch()  -> starts chrome --remote-debugging-port=9222 with a dedicated
                  profile (data/chrome-profile). You log in manually once;
                  the profile keeps you logged in for next times.
  2. pull_and_save() -> CDP Storage.getCookies -> filter chitchat.gg cookies
                  -> verify against GET /users/me -> write configs/session.json

No third-party deps: CDP is spoken over aiohttp HTTP+WS.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

from ..transport.protocol import CHITCHAT_API_BASE

log = logging.getLogger("eva.cdp_session")

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_DIR = ROOT / "data" / "chrome-profile"
DEFAULT_SESSION_PATH = ROOT / "configs" / "session.json"
DEFAULT_CDP_PORT = 9222

REQUIRED_COOKIE = "token"
SESSION_COOKIE = "__Secure-text-session"
COOKIE_DOMAIN_HINT = "chitchat.gg"

# Windows + Linux + macOS browser candidates, checked in order
BROWSER_CANDIDATES: List[str] = [
    # Chrome (Windows)
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    # Edge (Windows — same CDP, ships with Windows)
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    # Brave (Windows)
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    # Linux
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/usr/bin/microsoft-edge",
    # macOS
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def find_browser() -> Optional[str]:
    """First existing browser executable, or None."""
    for path in BROWSER_CANDIDATES:
        if path and Path(path).exists():
            return path
    # PATH lookup fallback (linux/mac)
    for name in ("google-chrome", "google-chrome-stable", "chromium",
                 "chromium-browser", "microsoft-edge"):
        for dir_ in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(dir_) / name
            if candidate.exists():
                return str(candidate)
    return None


class CdpSessionManager:
    def __init__(
        self,
        cdp_port: int = DEFAULT_CDP_PORT,
        profile_dir: Optional[Path] = None,
        browser_path: Optional[str] = None,
        session_path: Path = DEFAULT_SESSION_PATH,
        verify_url: str = f"{CHITCHAT_API_BASE}/users/me",
        do_verify: bool = True,
    ) -> None:
        self.cdp_port = cdp_port
        self.profile_dir = Path(profile_dir or DEFAULT_PROFILE_DIR)
        self.browser_path = browser_path
        self.session_path = Path(session_path)
        self.verify_url = verify_url
        self.do_verify = do_verify
        self._proc: Optional[subprocess.Popen] = None

    # ------------------------------------------------------------ CDP probes

    def _cdp_base(self) -> str:
        return f"http://127.0.0.1:{self.cdp_port}"

    async def cdp_info(self) -> Optional[dict]:
        """CDP /json/version if a debug browser is up, else None."""
        try:
            timeout = aiohttp.ClientTimeout(total=2)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(f"{self._cdp_base()}/json/version") as r:
                    if r.status == 200:
                        return await r.json(content_type=None)
        except Exception:  # noqa: BLE001
            return None
        return None

    # ------------------------------------------------------------ launch

    async def launch(self, start_url: str = "https://chitchat.gg") -> dict:
        """Start (or attach to) a CDP-enabled browser and return status."""
        info = await self.cdp_info()
        if info:
            return {"status": "already-running", "browser": info.get("Browser", "?"),
                    "user_agent": info.get("User-Agent", "")}

        exe = self.browser_path or find_browser()
        if not exe:
            return {"status": "browser-not-found",
                    "hint": "Install Chrome/Edge, or set the browser path in the dashboard"}

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        args = [
            exe,
            f"--remote-debugging-port={self.cdp_port}",
            f"--user-data-dir={self.profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-features=Translate",
            start_url,
        ]
        log.info("launching browser: %s", exe)
        flags = 0
        if sys.platform.startswith("win"):
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # keep console clean
        self._proc = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL, creationflags=flags)

        # wait for the CDP endpoint to come up
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            info = await self.cdp_info()
            if info:
                return {"status": "launched", "browser": info.get("Browser", "?"),
                        "user_agent": info.get("User-Agent", "")}
            await asyncio.sleep(0.5)
        return {"status": "launch-timeout",
                "hint": f"browser started but CDP did not open port {self.cdp_port}"}

    # ------------------------------------------------------------ cookie pull

    async def pull_cookies(self) -> Tuple[Dict[str, str], str]:
        """Return ({cookie_name: value}, user_agent) filtered to chitchat.gg."""
        info = await self.cdp_info()
        if not info:
            raise RuntimeError("CDP browser not running — click 'Launch Browser' first")
        ua = info.get("User-Agent", "")

        cookies = await self._cookies_via_browser_ws()
        if cookies is None:
            cookies = await self._cookies_via_page_ws()

        picked: Dict[str, str] = {}
        for c in cookies or []:
            domain = (c.get("domain") or "").lstrip(".")
            if COOKIE_DOMAIN_HINT not in domain:
                continue
            name = c.get("name")
            if name in (REQUIRED_COOKIE, SESSION_COOKIE) and c.get("value"):
                picked[name] = c["value"]

        if REQUIRED_COOKIE not in picked:
            raise RuntimeError(
                "chitchat.gg 'token' cookie not found — are you LOGGED IN in the opened browser? "
                "(login first, then click Save Session again)")
        return picked, ua

    async def _cookies_via_browser_ws(self) -> Optional[List[dict]]:
        info = await self.cdp_info()
        ws_url = (info or {}).get("webSocketDebuggerUrl")
        if not ws_url:
            return None
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.ws_connect(ws_url, max_msg_size=16 * 1024 * 1024) as ws:
                    await ws.send_str(json.dumps({
                        "id": 1, "method": "Storage.getCookies", "params": {},
                    }))
                    deadline = time.monotonic() + 6
                    while time.monotonic() < deadline:
                        msg = await ws.receive(timeout=5)
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        data = json.loads(msg.data)
                        if data.get("id") == 1:
                            result = data.get("result") or {}
                            return result.get("cookies") or []
        except Exception as exc:  # noqa: BLE001
            log.debug("browser-level Storage.getCookies failed: %s", exc)
        return None

    async def _cookies_via_page_ws(self) -> Optional[List[dict]]:
        """Fallback: find the chitchat.gg page target and use Network.getAllCookies."""
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(f"{self._cdp_base()}/json") as r:
                    targets = await r.json(content_type=None)
            page = next((t for t in targets
                         if t.get("type") == "page" and COOKIE_DOMAIN_HINT in t.get("url", "")), None)
            if not page:
                page = next((t for t in targets if t.get("type") == "page"), None)
            if not page or not page.get("webSocketDebuggerUrl"):
                return None
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.ws_connect(page["webSocketDebuggerUrl"],
                                        max_msg_size=16 * 1024 * 1024) as ws:
                    await ws.send_str(json.dumps({
                        "id": 2, "method": "Network.getAllCookies", "params": {},
                    }))
                    deadline = time.monotonic() + 6
                    while time.monotonic() < deadline:
                        msg = await ws.receive(timeout=5)
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        data = json.loads(msg.data)
                        if data.get("id") == 2:
                            result = data.get("result") or {}
                            return result.get("cookies") or []
        except Exception as exc:  # noqa: BLE001
            log.debug("page-level Network.getAllCookies failed: %s", exc)
        return None

    # ------------------------------------------------------------ verify + save

    async def verify(self, cookies: Dict[str, str], ua: str = "") -> Optional[dict]:
        """GET /users/me with the pulled cookies -> profile dict or None."""
        headers = {"User-Agent": ua} if ua else {}
        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout, cookies=cookies) as s:
                async with s.get(self.verify_url, headers=headers) as r:
                    if r.status == 200:
                        return await r.json(content_type=None)
        except Exception as exc:  # noqa: BLE001
            log.warning("session verify failed (network?): %s", exc)
        return None

    def save(self, cookies: Dict[str, str], ua: str = "") -> Path:
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {"cookies": dict(cookies)}
        if ua:
            payload["user_agent"] = ua
        self.session_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        try:
            self.session_path.chmod(0o600)  # best-effort restrictive perms
        except Exception:  # noqa: BLE001
            pass
        log.info("session saved -> %s", self.session_path)
        return self.session_path

    async def pull_and_save(self) -> dict:
        """Full pipeline used by the dashboard button."""
        cookies, ua = await self.pull_cookies()
        me = await self.verify(cookies, ua) if self.do_verify else None
        self.save(cookies, ua)
        return {
            "saved": True,
            "path": str(self.session_path),
            "verified": bool(me),
            "username": (me or {}).get("username"),
            "cookie_names": sorted(cookies.keys()),
        }

    # ------------------------------------------------------------ status helper

    def session_status(self) -> dict:
        exists = self.session_path.exists()
        out: Dict[str, Any] = {"exists": exists, "path": str(self.session_path)}
        if exists:
            try:
                data = json.loads(self.session_path.read_text(encoding="utf-8"))
                out["has_token"] = "token" in (data.get("cookies") or {})
            except Exception:  # noqa: BLE001
                out["has_token"] = False
        return out
