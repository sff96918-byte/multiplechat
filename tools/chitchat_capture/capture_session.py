"""capture_session.py — একবার browser খুলে login করো; session ও WebSocket URL সেভ করো।

Browser শুধু এই ধাপে খোলে। সেভ হয় (LOCAL ONLY, শেয়ার/commit নিষেধ):
  capture_out/session_<time>/session_cookies.LOCAL.json   chitchat.gg cookie
  capture_out/session_<time>/session_meta.LOCAL.json      browser-এর intercept করা
                                                          WebSocket URL + User-Agent

WebSocket URL অনুমান করা হয় না — browser নিজে যে wss:// URL খোলে, সেটাই নেওয়া হয়
(chitchat.gg host হলে)। Token/localStorage/request header লেখা হয় না।

তারপর bot-এ:
  python -m core.session_chat --import <session_cookies.LOCAL.json-এর পথ>
  python -m core.session_chat --run          # browser ছাড়া live chat

চালানো:  python capture_session.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from capture_direct import (  # noqa: E402  (একই ফোল্ডারের helper ব্যবহার)
    OUT_ROOT,
    PROFILE_DIR,
    TARGET_HOST,
    export_session_cookies,
)

START_URL = "https://app.chitchat.gg"
META_FILE = "session_meta.LOCAL.json"


def _valid_ws(url: str) -> bool:
    """শুধু wss:// এবং chitchat.gg host গ্রহণ। অন্য কিছু কখনো সেভ হবে না।"""
    try:
        u = urlsplit(url or "")
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    return u.scheme == "wss" and (host == "chitchat.gg" or host.endswith(".chitchat.gg"))


def save_meta(out_dir: Path, ws_url: str, user_agent: str) -> Path:
    """WebSocket URL ও User-Agent লেখে (0600, atomic)। Token এখানে থাকে না।"""
    path = out_dir / META_FILE
    tmp = out_dir / (META_FILE + ".tmp")
    data = {
        "ws_url": ws_url,
        "user_agent": user_agent,
        "captured_at": datetime.now().isoformat(timespec="seconds"),
    }
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    tmp.replace(path)
    return path


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] playwright নেই। আগে: pip install -r requirements.txt")
        return 1

    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    out_dir = OUT_ROOT / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    ws_seen: list = []

    def on_websocket(ws):
        url = ws.url
        if _valid_ws(url) and url not in ws_seen:
            ws_seen.append(url)
            print(f"[OK] WebSocket intercept: {urlsplit(url).scheme}://{urlsplit(url).hostname}/…")

    with sync_playwright() as p:
        try:
            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(PROFILE_DIR), headless=False,
                args=["--no-first-run", "--no-default-browser-check"])
        except Exception as exc:  # noqa: BLE001
            print(f"[ERROR] browser চালু হলো না: {exc}")
            print("[FIX] python -m playwright install chromium")
            return 1
        try:
            ctx.on("page", lambda pg: pg.on("websocket", on_websocket))
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.on("websocket", on_websocket)
            page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
            print(f"[INFO] Browser খুলেছে ({TARGET_HOST}). Login করে একটু chat করুন।")
            input("[INFO] Login ও chat শেষ হলে এখানে Enter চাপুন… ")
            try:
                user_agent = page.evaluate("() => navigator.userAgent") or ""
            except Exception:  # noqa: BLE001
                user_agent = ""
            n = export_session_cookies(ctx, out_dir)
        finally:
            ctx.close()

    if n <= 0:
        print("[X] chitchat cookie পাওয়া যায়নি — login হয়েছে কি না দেখুন, তারপর আবার চালান।")
        return 2
    ws_url = ws_seen[0] if ws_seen else ""
    save_meta(out_dir, ws_url, user_agent)
    if not ws_url:
        print("[WARN] WebSocket URL ধরা পড়েনি — chat শুরু করার পরে Enter চাপলে সাধারণত ধরা পড়ে। "
              "তবে session cookie সেভ হয়েছে।")
    print(f"[DONE] এখন চালান: python -m core.session_chat --import "
          f"\"{out_dir / 'session_cookies.LOCAL.json'}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
