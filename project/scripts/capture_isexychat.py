# -*- coding: utf-8 -*-
"""
iSexyChat Playwright test with proxy auth fix.
Playwright doesn't support SOCKS5 auth natively, so we use a local proxy bridge
or use the HTTP proxy instead.
"""
import asyncio
import time
import random
import string
import os

def rand_id(n=6):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

def log(tag, msg):
    print(f"[{time.strftime('%H:%M:%S')}] [{tag}] {msg}", flush=True)


async def isexychat_playwright():
    log("ISEXYCHAT", "=== Playwright browser test (HTTP proxy) ===")
    from playwright.async_api import async_playwright

    # Use HTTP proxy (Playwright supports HTTP proxy auth)
    proxy_config = {
        "server": "http://gw.dataimpulse.com:823",
        "username": "34d99b34747b4c4e63b7__cr.us",
        "password": "219c40489f5eff94",
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy=proxy_config,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True,
        )

        # Enable stealth
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        """)

        page = await context.new_page()

        # Capture WebSocket connections
        ws_connections = []
        def on_websocket(ws):
            url = ws.url
            log("ISEXYCHAT-WS", f"WebSocket opened: {url}")
            ws_connections.append(ws)

        page.on("websocket", on_websocket)

        # Capture console
        page.on("console", lambda msg: log("ISEXYCHAT-CONSOLE", f"{msg.type}: {msg.text[:200]}"))

        # Capture network
        def on_request(request):
            url = request.url
            if any(kw in url.lower() for kw in ["webirc", "kiwiirc", "irc", "websocket", "ws://", "wss://", "socket"]):
                log("ISEXYCHAT-NET", f"REQ: {request.method} {url[:150]}")

        def on_response(response):
            url = response.url
            if any(kw in url.lower() for kw in ["webirc", "kiwiirc", "irc", "websocket", "socket"]):
                log("ISEXYCHAT-NET", f"RESP: {response.status} {url[:150]}")

        page.on("request", on_request)
        page.on("response", on_response)

        log("ISEXYCHAT", "Navigating to chat.isexychat.com...")
        try:
            await page.goto("https://chat.isexychat.com/", wait_until="networkidle", timeout=45000)
        except Exception as e:
            log("ISEXYCHAT", f"Navigation: {e}")

        log("ISEXYCHAT", f"Page title: {await page.title()}")
        await page.screenshot(path="capture_isexychat_01_landing.png")

        # Wait for KiwiIRC to load
        await asyncio.sleep(3)

        # Get all visible text
        body_text = await page.evaluate("() => document.body?.innerText?.substring(0, 3000) || ''")
        log("ISEXYCHAT", f"Body text (first 500): {body_text[:500]}")

        # Get all inputs
        inputs = await page.query_selector_all("input, textarea, button, [role='button'], .u-link, .u-button")
        log("ISEXYCHAT", f"Interactive elements: {len(inputs)}")
        for i, el in enumerate(inputs[:20]):
            tag = await el.evaluate("el => el.tagName")
            name = await el.get_attribute("name") or ""
            placeholder = await el.get_attribute("placeholder") or ""
            text = (await el.text_content() or "").strip()[:50]
            cls = await el.get_attribute("class") or ""
            log("ISEXYCHAT", f"  [{i}] <{tag}> name={name} placeholder={placeholder} text='{text}' class={cls[:40]}")

        # Try to find and fill nickname
        nick = "Guest" + rand_id(4)
        log("ISEXYCHAT", f"Looking for nickname input...")

        # KiwiIRC welcome screen selectors
        selectors = [
            "input[placeholder*='nick']",
            "input[placeholder*='Nick']",
            "input.kiwi-welcome-simple-nick-input",
            ".kiwi-welcome-simple-form input",
            "input[name='nick']",
            "input[type='text']",
        ]

        nick_filled = False
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el:
                    await el.fill(nick)
                    log("ISEXYCHAT", f"Filled nick '{nick}' into '{sel}'")
                    nick_filled = True
                    break
            except:
                continue

        if not nick_filled:
            log("ISEXYCHAT", "No nick input found via selectors, trying JS evaluation...")
            # Try to find any visible text input
            result = await page.evaluate("""() => {
                const inputs = document.querySelectorAll('input[type="text"], input:not([type])');
                return Array.from(inputs).map(i => ({
                    placeholder: i.placeholder,
                    name: i.name,
                    id: i.id,
                    className: i.className,
                    visible: i.offsetParent !== null
                }));
            }""")
            log("ISEXYCHAT", f"Text inputs via JS: {result}")

        # Take final screenshot
        await page.screenshot(path="capture_isexychat_02_form.png")

        # Get full HTML for analysis
        html = await page.content()
        with open("capture_isexychat_browser.html", "w", encoding="utf-8") as f:
            f.write(html)
        log("ISEXYCHAT", f"HTML saved ({len(html)} bytes)")

        # Check for WebSocket connections
        log("ISEXYCHAT", f"WebSocket connections captured: {len(ws_connections)}")

        await browser.close()
        log("ISEXYCHAT", "Browser closed")


async def main():
    print("=" * 70)
    print("  iSexyChat Playwright Capture")
    print("=" * 70)
    await isexychat_playwright()
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())