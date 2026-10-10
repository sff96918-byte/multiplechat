"""capture_session.py — একবার browser খুলে login করো, তারপর session cookie সেভ করো।

Browser শুধু এই ধাপে খোলে। সেভ হয় শুধু chitchat.gg-র cookie (LOCAL ONLY):
  capture_out/session_<time>/session_cookies.LOCAL.json

তারপর bot-এ:
  python -m core.session_chat --import <ওই ফাইলের পথ>
  python -m core.session_chat --run          # browser ছাড়া live chat

এই script ইচ্ছাকৃতভাবে localStorage, sessionStorage, request header বা ওয়েব
সাইটের অন্য কোনো data লেখে না — সেগুলোতে credential থাকতে পারে।
চালানো:  python capture_session.py
"""
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from capture_direct import (  # noqa: E402  (একই ফোল্ডারের helper ব্যবহার)
    OUT_ROOT,
    PROFILE_DIR,
    TARGET_HOST,
    export_session_cookies,
)

START_URL = "https://app.chitchat.gg"


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
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
            print(f"[INFO] Browser খুলেছে ({TARGET_HOST}). Login করে একটু chat করুন।")
            input("[INFO] Login শেষ হলে এখানে Enter চাপুন… ")
            n = export_session_cookies(ctx, out_dir)
        finally:
            ctx.close()

    if n <= 0:
        print("[X] chitchat cookie পাওয়া যায়নি — login হয়েছে কি না দেখুন, তারপর আবার চালান।")
        return 2
    print(f"[DONE] এখন চালান: python -m core.session_chat --import "
          f"\"{out_dir / 'session_cookies.LOCAL.json'}\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
