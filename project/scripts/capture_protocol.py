# -*- coding: utf-8 -*-
"""
Protocol Capture Script — intercepts API + WebSocket traffic for chat sites.
Usage: python capture_protocol.py <url>
       python capture_protocol.py https://chatib.net
"""
import asyncio
import json
import sys
import os
import time
from datetime import datetime

CAPTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")


async def capture_site(url: str, wait_sec: int = 30):
    from playwright.async_api import async_playwright

    os.makedirs(CAPTURE_DIR, exist_ok=True)
    site_name = url.split("//")[1].split("/")[0].replace("www.", "").replace(".", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(CAPTURE_DIR, f"{site_name}_{ts}.json")

    api_logs = []
    ws_logs = []
    all_requests = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
        )
        page = await context.new_page()

        # ═══ Intercept ALL requests ═══
        async def on_request(request):
            req_type = request.resource_type
            rurl = request.url
            method = request.method

            # Skip static assets
            if req_type in ("image", "stylesheet", "font", "media"):
                return

            entry = {
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "type": req_type,
                "method": method,
                "url": rurl,
                "headers": dict(request.headers),
            }

            # Capture POST bodies
            if method == "POST":
                try:
                    post_data = request.post_data
                    entry["post_data"] = post_data
                except:
                    pass

            # Mark API-like requests
            if req_type in ("xhr", "fetch", "websocket") or "/api/" in rurl or "/event" in rurl or "/send" in rurl or "/message" in rurl or "/start" in rurl or "/connect" in rurl or "/boop" in rurl or "/socket" in rurl or "/ws" in rurl:
                entry["is_api"] = True
                api_logs.append(entry)
                print(f"  [API] {method} {rurl}")
                if "post_data" in entry and entry["post_data"]:
                    print(f"        POST: {entry['post_data'][:200]}")

            all_requests.append(entry)

        page.on("request", on_request)

        # ═══ Intercept responses ═══
        async def on_response(response):
            rurl = response.url
            status = response.status
            rtype = response.request.resource_type

            if rtype in ("xhr", "fetch") or "/api/" in rurl or "/event" in rurl or "/send" in rurl or "/message" in rurl:
                try:
                    body = await response.text()
                    body_preview = body[:500] if body else ""
                except:
                    body_preview = "(binary or empty)"

                for entry in api_logs:
                    if entry["url"] == rurl and "response" not in entry:
                        entry["response"] = {
                            "status": status,
                            "body": body_preview,
                        }
                        print(f"  [RESP] {status} {rurl[:80]} -> {body_preview[:100]}")
                        break

        page.on("response", on_response)

        # ═══ Intercept WebSocket frames ═══
        def on_ws(ws):
            ws_url = ws.url
            print(f"  [WS CONNECT] {ws_url}")
            ws_logs.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "event": "connect",
                "url": ws_url,
            })

            def on_ws_send(payload):
                entry = {
                    "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "event": "send",
                    "url": ws_url,
                    "data": str(payload)[:500],
                }
                ws_logs.append(entry)
                print(f"  [WS >>>] {str(payload)[:200]}")

            def on_ws_recv(payload):
                entry = {
                    "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "event": "recv",
                    "url": ws_url,
                    "data": str(payload)[:500],
                }
                ws_logs.append(entry)
                print(f"  [WS <<<] {str(payload)[:200]}")

            def on_ws_close():
                ws_logs.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "event": "close",
                    "url": ws_url,
                })
                print(f"  [WS CLOSE] {ws_url}")

            ws.on("framesent", on_ws_send)
            ws.on("framereceived", on_ws_recv)
            ws.on("close", on_ws_close)

        page.on("websocket", on_ws)

        # ═══ Capture console logs ═══
        console_logs = []
        def on_console(msg):
            console_logs.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "type": msg.type,
                "text": msg.text[:300],
            })

        page.on("console", on_console)

        # ═══ Navigate ═══
        print(f"\n{'='*60}")
        print(f"  Capturing: {url}")
        print(f"  Output: {out_file}")
        print(f"{'='*60}\n")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  [WARN] Navigation: {e}")

        print(f"\n  Page loaded. Waiting {wait_sec}s for traffic...\n")

        # Try to interact — fill inputs, click buttons
        await asyncio.sleep(3)

        # Look for login/chat forms
        inputs = await page.query_selector_all("input[type='text'], input[type='email'], input:not([type])")
        print(f"  Found {len(inputs)} text inputs")

        for i, inp in enumerate(inputs[:3]):
            try:
                placeholder = await inp.get_attribute("placeholder") or ""
                name = await inp.get_attribute("name") or ""
                id_attr = await inp.get_attribute("id") or ""
                print(f"    input[{i}]: name={name} id={id_attr} placeholder={placeholder}")
            except:
                pass

        buttons = await page.query_selector_all("button, input[type='submit']")
        print(f"  Found {len(buttons)} buttons")
        for i, btn in enumerate(buttons[:5]):
            try:
                text = await btn.inner_text()
                print(f"    button[{i}]: {text}")
            except:
                pass

        # Wait for traffic
        await asyncio.sleep(wait_sec)

        # ═══ Save capture ═══
        capture = {
            "site": url,
            "timestamp": ts,
            "api_calls": api_logs,
            "websocket_frames": ws_logs,
            "all_requests": [{"time": r["time"], "type": r["type"], "method": r["method"], "url": r["url"]} for r in all_requests],
            "console_logs": console_logs,
            "summary": {
                "total_requests": len(all_requests),
                "api_requests": len(api_logs),
                "ws_frames": len(ws_logs),
                "ws_urls": list(set(w["url"] for w in ws_logs if "url" in w)),
            },
        }

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(capture, f, indent=2, ensure_ascii=False)

        print(f"\n{'='*60}")
        print(f"  CAPTURE COMPLETE")
        print(f"  Total requests: {len(all_requests)}")
        print(f"  API requests:   {len(api_logs)}")
        print(f"  WS frames:      {len(ws_logs)}")
        print(f"  WS URLs:        {capture['summary']['ws_urls']}")
        print(f"  Saved to: {out_file}")
        print(f"{'='*60}\n")

        await browser.close()

    return capture


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python capture_protocol.py <url> [wait_seconds]")
        print("Example: python capture_protocol.py https://chatib.net 30")
        sys.exit(1)

    url = sys.argv[1]
    wait = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    asyncio.run(capture_site(url, wait))