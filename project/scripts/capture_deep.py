# -*- coding: utf-8 -*-
"""
Deep Protocol Capture — loads page, fills forms, clicks buttons, captures everything.
Usage: python capture_deep.py <url> [wait_sec]
"""
import asyncio
import json
import sys
import os
import time
import random
import string
from datetime import datetime

CAPTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")


def rand_nick(n=6):
    return "Guest" + "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


async def capture_deep(url: str, wait_sec: int = 40):
    from playwright.async_api import async_playwright

    os.makedirs(CAPTURE_DIR, exist_ok=True)
    site_name = url.split("//")[1].split("/")[0].replace("www.", "").replace(".", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = os.path.join(CAPTURE_DIR, f"{site_name}_deep_{ts}.json")

    api_logs = []
    ws_logs = []
    console_logs = []
    page_html = ""

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled", "--use-fake-ui-for-media-stream"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        await context.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        page = await context.new_page()

        # ═══ Intercept ALL requests ═══
        async def on_request(request):
            req_type = request.resource_type
            rurl = request.url
            method = request.method
            if req_type in ("image", "stylesheet", "font", "media"):
                return

            entry = {
                "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                "type": req_type,
                "method": method,
                "url": rurl,
                "headers": dict(request.headers),
            }
            if method == "POST":
                try:
                    pd = request.post_data
                    if pd:
                        entry["post_data"] = pd[:1000]
                except:
                    pass

            is_api = (
                req_type in ("xhr", "fetch", "websocket")
                or any(k in rurl.lower() for k in ["/api/", "/event", "/send", "/message", "/start",
                     "/connect", "/boop", "/socket", "/ws", "/chat", "/join", "/register",
                     "/login", "/user", "/session", "/token", "/auth", "/poll", "/sync"])
            )
            if is_api:
                entry["is_api"] = True
                api_logs.append(entry)
                tag = "WS" if req_type == "websocket" else "API"
                print(f"  [{tag}] {method} {rurl[:120]}")
                if "post_data" in entry:
                    print(f"        POST: {entry['post_data'][:200]}")

        page.on("request", on_request)

        async def on_response(response):
            rurl = response.url
            status = response.status
            rtype = response.request.resource_type
            if rtype in ("xhr", "fetch") or any(k in rurl.lower() for k in
                ["/api/", "/event", "/send", "/message", "/start", "/connect", "/socket", "/chat"]):
                try:
                    body = await response.text()
                    body_preview = body[:800] if body else ""
                except:
                    body_preview = "(binary)"
                for entry in api_logs:
                    if entry["url"] == rurl and "response" not in entry:
                        entry["response"] = {"status": status, "body": body_preview}
                        print(f"  [RESP] {status} {rurl[:80]} -> {body_preview[:120]}")
                        break

        page.on("response", on_response)

        # ═══ WebSocket ═══
        def on_ws(ws):
            ws_url = ws.url
            print(f"  [WS CONNECT] {ws_url}")
            ws_logs.append({"time": datetime.now().strftime("%H:%M:%S"), "event": "connect", "url": ws_url})

            def on_ws_send(payload):
                ws_logs.append({
                    "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "event": "send", "url": ws_url, "data": str(payload)[:800],
                })
                print(f"  [WS >>>] {str(payload)[:300]}")

            def on_ws_recv(payload):
                ws_logs.append({
                    "time": datetime.now().strftime("%H:%M:%S.%f")[:-3],
                    "event": "recv", "url": ws_url, "data": str(payload)[:800],
                })
                print(f"  [WS <<<] {str(payload)[:300]}")

            ws.on("framesent", on_ws_send)
            ws.on("framereceived", on_ws_recv)
            ws.on("close", lambda: ws_logs.append({
                "time": datetime.now().strftime("%H:%M:%S"), "event": "close", "url": ws_url,
            }))

        page.on("websocket", on_ws)

        def on_console(msg):
            console_logs.append({
                "time": datetime.now().strftime("%H:%M:%S"),
                "type": msg.type,
                "text": msg.text[:500],
            })

        page.on("console", on_console)

        # ═══ Navigate ═══
        print(f"\n{'='*60}")
        print(f"  Deep Capture: {url}")
        print(f"{'='*60}\n")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  [WARN] Navigation: {e}")

        await asyncio.sleep(3)
        print(f"\n  --- Phase 1: Page loaded, scanning forms ---")

        # ═══ Phase 1: Fill text inputs ═══
        inputs = await page.query_selector_all("input[type='text'], input:not([type]), input[type='email']")
        nick = rand_nick()
        for i, inp in enumerate(inputs[:5]):
            try:
                placeholder = await inp.get_attribute("placeholder") or ""
                name = await inp.get_attribute("name") or ""
                id_attr = await inp.get_attribute("id") or ""
                print(f"    input[{i}]: name={name} id={id_attr} placeholder={placeholder}")
                await inp.click()
                await inp.fill("")
                await asyncio.sleep(0.3)
                await inp.type(nick, delay=30)
                await asyncio.sleep(0.3)
            except:
                pass

        # ═══ Phase 2: Click submit/start buttons ═══
        print(f"\n  --- Phase 2: Clicking buttons ---")
        buttons = await page.query_selector_all("button, input[type='submit'], a[role='button']")
        for i, btn in enumerate(buttons[:8]):
            try:
                text = (await btn.inner_text()).strip()
                tag = await btn.evaluate("el => el.tagName")
                print(f"    button[{i}]: <{tag}> '{text[:50]}'")
            except:
                pass

        # Try clicking likely "start" / "enter" / "chat" buttons
        for i, btn in enumerate(buttons[:8]):
            try:
                text = (await btn.inner_text()).strip().lower()
                if any(k in text for k in ["start", "enter", "chat", "join", "connect", "go", "begin", "continue"]):
                    print(f"\n  >> Clicking: '{text}'")
                    await btn.click(timeout=5000)
                    await asyncio.sleep(5)
                    break
            except:
                pass

        # ═══ Phase 3: Wait for traffic ═══
        print(f"\n  --- Phase 3: Waiting {wait_sec}s for chat traffic ---\n")
        await asyncio.sleep(wait_sec)

        # ═══ Phase 4: Try typing a message if chat input exists ═══
        print(f"\n  --- Phase 4: Looking for chat input ---")
        chat_inputs = await page.query_selector_all(
            "textarea, input[type='text'].chat-input, .kiwi-inputbar-input, "
            "#chat-input, .message-input, [contenteditable='true']"
        )
        for i, ci in enumerate(chat_inputs[:3]):
            try:
                tag = await ci.evaluate("el => el.tagName")
                print(f"    chat_input[{i}]: <{tag}>")
                await ci.click()
                await ci.type("hello", delay=50)
                await asyncio.sleep(1)
                await ci.press("Enter")
                print(f"    -> Sent 'hello'")
                await asyncio.sleep(5)
            except:
                pass

        # Capture page HTML for analysis
        try:
            page_html = await page.content()
            page_html = page_html[:5000]
        except:
            pass

        # ═══ Save ═══
        capture = {
            "site": url,
            "timestamp": ts,
            "nickname_used": nick,
            "api_calls": api_logs,
            "websocket_frames": ws_logs,
            "console_logs": console_logs[-50:],
            "page_html_preview": page_html,
            "summary": {
                "total_api": len(api_logs),
                "total_ws": len(ws_logs),
                "ws_urls": list(set(w["url"] for w in ws_logs if "url" in w)),
                "api_urls": list(set(a["url"] for a in api_logs)),
            },
        }

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(capture, f, indent=2, ensure_ascii=False)

        print(f"\n{'='*60}")
        print(f"  DEEP CAPTURE COMPLETE")
        print(f"  API calls:  {len(api_logs)}")
        print(f"  WS frames:  {len(ws_logs)}")
        print(f"  WS URLs:    {capture['summary']['ws_urls']}")
        print(f"  API URLs:   {len(capture['summary']['api_urls'])} unique")
        print(f"  Saved:      {out_file}")
        print(f"{'='*60}\n")

        await browser.close()

    return capture


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python capture_deep.py <url> [wait_sec]")
        sys.exit(1)
    url = sys.argv[1]
    wait = int(sys.argv[2]) if len(sys.argv) > 2 else 40
    asyncio.run(capture_deep(url, wait))