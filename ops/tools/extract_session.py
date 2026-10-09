"""Build configs/session.json for the chitchat bot from your browser session.

Ways to use:
  1) Interactive paste:
       python -m ops.tools.extract_session
     Then paste the `token` and `__Secure-text-session` cookie values from
     DevTools → Application → Cookies → https://chitchat.gg (while logged in).

  2) From a copied DevTools request header:
       python -m ops.tools.extract_session --cookie-string "token=eyJ...; __Secure-text-session=..."

  3) From a Netscape cookies.txt export:
       python -m ops.tools.extract_session --cookies-file cookies.txt

Output: configs/session.json (gitignored). Keep it private — it IS your account.
The tool never sends anything anywhere; it only writes the local file.
"""

from __future__ import annotations

import argparse
import json
import sys
from http.cookies import SimpleCookie
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "configs" / "session.json"

REQUIRED = {"token"}
KNOWN = ("token", "__Secure-text-session")


def parse_cookie_string(raw: str) -> dict:
    jar = SimpleCookie()
    try:
        jar.load(raw)
    except Exception:
        # devtools copies are usually fine, but be tolerant
        pairs = {}
        for part in raw.split(";"):
            if "=" in part:
                k, _, v = part.strip().partition("=")
                pairs[k] = v
        return pairs
    return {k: morsel.value for k, morsel in jar.items()}


def parse_netscape(path: Path) -> dict:
    cookies = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) >= 7:
            cookies[parts[5]] = parts[6]
    return cookies


def main() -> None:
    ap = argparse.ArgumentParser(description="build configs/session.json")
    ap.add_argument("--cookie-string", default="", help="raw Cookie header value")
    ap.add_argument("--cookies-file", default="", help="Netscape cookies.txt path")
    ap.add_argument("--user-agent", default="", help="your browser UA (recommended)")
    args = ap.parse_args()

    cookies: dict = {}
    if args.cookies_file:
        cookies.update(parse_netscape(Path(args.cookies_file)))
    if args.cookie_string:
        cookies.update(parse_cookie_string(args.cookie_string))
    if not cookies:
        print("Paste cookie values from DevTools → Application → Cookies → chitchat.gg")
        print("Press Enter to skip a field.\n")
        for name in KNOWN:
            val = input(f"  {name}: ").strip()
            if val:
                cookies[name] = val
        ua = input("\n  User-Agent (Enter to skip): ").strip()
    else:
        ua = args.user_agent

    missing = REQUIRED - set(cookies)
    if missing:
        sys.exit(f"[!] missing required cookie(s): {', '.join(missing)} — are you logged in?")

    payload = {"cookies": cookies}
    if ua:
        payload["user_agent"] = ua

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"\n[ok] wrote {OUT}")
    print("Next: python -m ops.tools.socket_smoke_test   (offline protocol check)")
    print("Then: python -m eva.transport.ws_bot --debug   (live)")


if __name__ == "__main__":
    main()
