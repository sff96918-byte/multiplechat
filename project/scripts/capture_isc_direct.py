# -*- coding: utf-8 -*-
"""iSexyChat Playwright — direct connection (no proxy)"""
import asyncio
import time
import random
import string

def rand_id(n=6):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

def log(tag, msg):
    safe = str(msg).encode("ascii", "replace").decode("ascii")
    print(f"[{time.strftime('%H:%M:%S')}] [{tag}] {safe}", flush=True)


async def main():
    from playwright.async_api import async_playwright

    log("ISEXYCHAT", "=== Direct connection (no proxy) ===")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        page = await context.new_page()

        # Capture WebSocket
        ws_urls = []
        def on_ws(ws):
            log("ISEXYCHAT-WS", f"WebSocket: {ws.url}")
            ws_urls.append(ws.url)

        page.on("websocket", on_ws)
        page.on("console", lambda msg: log("CONSOLE", f"{msg.type}: {repr(msg.text[:200])}"))

        def on_req(req):
            if any(kw in req.url.lower() for kw in ["webirc", "kiwi", "irc", "ws"]):
                log("NET-REQ", f"{req.method} {req.url[:150]}")

        def on_resp(resp):
            if any(kw in resp.url.lower() for kw in ["webirc", "kiwi", "irc", "ws"]):
                log("NET-RESP", f"{resp.status} {resp.url[:150]}")

        page.on("request", on_req)
        page.on("response", on_resp)

        log("ISEXYCHAT", "Navigating to chat.isexychat.com...")
        await page.goto("https://chat.isexychat.com/", wait_until="networkidle", timeout=45000)
        log("ISEXYCHAT", f"Title: {await page.title()}")

        await asyncio.sleep(3)
        await page.screenshot(path="capture_isc_01.png")

        # Get page text
        body = await page.evaluate("() => document.body?.innerText?.substring(0, 2000) || ''")
        log("ISEXYCHAT", f"Body: {body[:500]}")

        # Find inputs
        inputs = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input, textarea, button, [role=button]')).map(el => ({
                tag: el.tagName,
                type: el.type || '',
                name: el.name || '',
                id: el.id || '',
                placeholder: el.placeholder || '',
                text: (el.innerText || '').trim().substring(0, 50),
                className: el.className?.substring?.(0, 60) || '',
                visible: el.offsetParent !== null
            }));
        }""")
        log("ISEXYCHAT", f"Elements: {len(inputs)}")
        for i, el in enumerate(inputs[:25]):
            log("ISEXYCHAT", f"  [{i}] <{el['tag']}> type={el['type']} name={el['name']} id={el['id']} ph={el['placeholder']} text='{el['text']}' cls={el['className'][:40]}")

        # Try to fill nickname
        nick = "Guest" + rand_id(4)
        log("ISEXYCHAT", f"Trying nick: {nick}")

        # KiwiIRC selectors
        for sel in ["input[placeholder*='nick']", "input[type='text']", ".kiwi-welcome-simple-nick input", "input.kiwi-welcome-simple-nick-input"]:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await el.fill(nick)
                    log("ISEXYCHAT", f"Filled nick via '{sel}'")
                    break
            except:
                continue

        # Try clicking start
        for sel in ["button[type='submit']", ".kiwi-welcome-simple-start", ".u-button", "button"]:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    text = (await el.text_content() or "").strip()
                    if text:
                        log("ISEXYCHAT", f"Found button: '{text}' via '{sel}'")
                        if "start" in text.lower() or "connect" in text.lower() or "go" in text.lower():
                            await el.click()
                            log("ISEXYCHAT", f"Clicked: {text}")
                            await asyncio.sleep(5)
                            break
            except:
                continue

        await page.screenshot(path="capture_isc_02.png")
        log("ISEXYCHAT", f"WS connections: {ws_urls}")

        # Check if chat loaded
        msg_input = await page.query_selector(".kiwi-inputbar-input, textarea.kiwi-inputbar-input, .kiwi-controlinput-inner input")
        if msg_input:
            log("ISEXYCHAT", "*** CHAT INPUT FOUND — We're in the chat! ***")
        else:
            log("ISEXYCHAT", "No chat input found yet")
            body2 = await page.evaluate("() => document.body?.innerText?.substring(0, 1000) || ''")
            log("ISEXYCHAT", f"Body after: {body2[:300]}")

        await browser.close()

    log("ISEXYCHAT", "Done")


if __name__ == "__main__":
    asyncio.run(main())