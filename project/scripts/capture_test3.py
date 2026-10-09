# -*- coding: utf-8 -*-
"""
Round 3:
- Joingy: Full conversation with reply engine (receive message, reply, disconnect)
- iSexyChat: Playwright browser test (KiwiIRC web client)
- ChatRandom: Try the API hosts found in JS
"""
import asyncio
import json
import time
import random
import string
import sys
import os
import aiohttp
from aiohttp_socks import ProxyConnector, ProxyType

SOCKS5 = ("148.59.2.158.static.flameproxies.com", 1337, "vmLElhTf-148.59.2.158", "NVRf69LCWfeILf6C")

def socks5_conn():
    return ProxyConnector(proxy_type=ProxyType.SOCKS5, host=SOCKS5[0], port=SOCKS5[1], username=SOCKS5[2], password=SOCKS5[3], rdns=True)

def rand_id(n=10):
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

def log(tag, msg):
    print(f"[{time.strftime('%H:%M:%S')}] [{tag}] {msg}", flush=True)


# ════════════════════════════════════════════════════════════════════════
# Joingy — Full conversation with event polling loop
# ════════════════════════════════════════════════════════════════════════
async def joingy_conversation():
    log("JOINGY", "=== Full conversation test ===")
    connector = socks5_conn()
    timeout = aiohttp.ClientTimeout(total=120)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Referer": "https://joingy.com/",
        "Origin": "https://joingy.com",
    }

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Step 1: Start
        randid = rand_id()
        fp_hash = "".join(random.choices("abcdef0123456789", k=32))
        log("JOINGY", f"POST /start randid={randid}")
        async with session.post(
            "https://back.joingy.com/start",
            json={"randid": randid, "vid": False, "hash": fp_hash},
            headers={**headers, "Content-Type": "application/json"},
        ) as resp:
            uid = (await resp.text()).strip().strip('"')
            log("JOINGY", f"UID: {uid}")
            if not uid or uid in ("ratelimit", "ban"):
                log("JOINGY", "FAILED")
                return

        # Step 2: Event poll loop
        messages_received = []
        messages_sent = 0
        partner_connected = False

        for poll_iter in range(30):  # max 30 polls
            try:
                async with session.post(
                    "https://back.joingy.com/event",
                    data={"uid": uid, "vid": "false"},
                    headers=headers,
                ) as resp:
                    text = await resp.text()
                    if not text:
                        log("JOINGY", f"Poll {poll_iter}: empty response")
                        await asyncio.sleep(1)
                        continue

                    try:
                        event = json.loads(text)
                    except json.JSONDecodeError:
                        log("JOINGY", f"Poll {poll_iter}: non-JSON: {text[:100]}")
                        await asyncio.sleep(1)
                        continue

                    evt_type = event.get("event", "")
                    log("JOINGY", f"Poll {poll_iter}: event={evt_type} data={json.dumps(event)[:200]}")

                    if evt_type == "connected":
                        partner_connected = True
                        log("JOINGY", "*** Partner connected! ***")
                        # Send first message
                        await asyncio.sleep(2)
                        async with session.post(
                            "https://back.joingy.com/boop",
                            data={"uid": uid, "msg": "hey, how are you?", "vid": "false"},
                            headers=headers,
                        ) as r:
                            log("JOINGY", f"Sent 'hey, how are you?' [{r.status}]")
                            messages_sent += 1

                    elif evt_type == "message":
                        msg_text = event.get("val", "")
                        log("JOINGY", f"<<< Stranger: {msg_text}")
                        messages_received.append(msg_text)

                        # Reply after delay
                        await asyncio.sleep(random.uniform(2, 4))
                        reply = "thats cool, what do you like to do for fun?"
                        async with session.post(
                            "https://back.joingy.com/boop",
                            data={"uid": uid, "msg": reply, "vid": "false"},
                            headers=headers,
                        ) as r:
                            log("JOINGY", f">>> Sent: {reply} [{r.status}]")
                            messages_sent += 1

                    elif evt_type == "typing":
                        typing = event.get("val", "")
                        if typing == "true":
                            log("JOINGY", "Stranger is typing...")

                    elif evt_type == "disconnected":
                        log("JOINGY", "*** Partner disconnected ***")
                        break

            except asyncio.TimeoutError:
                log("JOINGY", f"Poll {poll_iter}: timeout")
            except Exception as e:
                log("JOINGY", f"Poll {poll_iter}: error: {e}")

        # Disconnect
        try:
            async with session.post(
                "https://back.joingy.com/disconnect",
                data={"uid": uid, "vid": "false"},
                headers=headers,
            ) as r:
                log("JOINGY", f"Disconnected [{r.status}]")
        except:
            pass

        log("JOINGY", f"=== Done: sent={messages_sent}, received={len(messages_received)} ===")

        # Save conversation
        with open("capture_joingy_conversation.txt", "w", encoding="utf-8") as f:
            f.write(f"UID: {uid}\n")
            f.write(f"Messages sent: {messages_sent}\n")
            f.write(f"Messages received: {len(messages_received)}\n")
            f.write(f"Partner connected: {partner_connected}\n")
            for i, msg in enumerate(messages_received):
                f.write(f"\nReceived #{i+1}: {msg}\n")


# ════════════════════════════════════════════════════════════════════════
# iSexyChat — Playwright browser test
# ════════════════════════════════════════════════════════════════════════
async def isexychat_playwright():
    log("ISEXYCHAT", "=== Playwright browser test ===")
    from playwright.async_api import async_playwright

    proxy_config = {
        "server": f"socks5://{SOCKS5[0]}:{SOCKS5[1]}",
        "username": SOCKS5[2],
        "password": SOCKS5[3],
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            proxy=proxy_config,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
        )
        page = await context.new_page()

        # Capture console messages
        page.on("console", lambda msg: log("ISEXYCHAT-CONSOLE", f"{msg.type}: {msg.text[:150]}"))

        # Capture network requests
        async def on_request(request):
            url = request.url
            if any(kw in url for kw in ["webirc", "kiwiirc", "irc", "websocket", "ws"]):
                log("ISEXYCHAT-NET", f"REQ: {request.method} {url[:120]}")

        async def on_response(response):
            url = response.url
            if any(kw in url for kw in ["webirc", "kiwiirc", "irc", "websocket", "ws"]):
                log("ISEXYCHAT-NET", f"RESP: {response.status} {url[:120]}")

        page.on("request", on_request)
        page.on("response", on_response)

        log("ISEXYCHAT", "Navigating to chat.isexychat.com...")
        try:
            await page.goto("https://chat.isexychat.com/", wait_until="networkidle", timeout=30000)
        except Exception as e:
            log("ISEXYCHAT", f"Navigation error: {e}")

        log("ISEXYCHAT", f"Page title: {await page.title()}")

        # Take screenshot
        await page.screenshot(path="capture_isexychat_browser.png")
        log("ISEXYCHAT", "Screenshot saved: capture_isexychat_browser.png")

        # Get page content
        content = await page.content()
        with open("capture_isexychat_browser.html", "w", encoding="utf-8") as f:
            f.write(content)
        log("ISEXYCHAT", f"HTML saved ({len(content)} bytes)")

        # Look for the KiwiIRC welcome form
        log("ISEXYCHAT", "Looking for chat form elements...")

        # KiwiIRC has a nickname input and channel selection
        inputs = await page.query_selector_all("input")
        log("ISEXYCHAT", f"Found {len(inputs)} input elements")
        for i, inp in enumerate(inputs):
            name = await inp.get_attribute("name") or ""
            placeholder = await inp.get_attribute("placeholder") or ""
            inp_type = await inp.get_attribute("type") or ""
            log("ISEXYCHAT", f"  input[{i}]: name={name} type={inp_type} placeholder={placeholder}")

        buttons = await page.query_selector_all("button")
        log("ISEXYCHAT", f"Found {len(buttons)} buttons")
        for i, btn in enumerate(buttons):
            text = await btn.text_content() or ""
            log("ISEXYCHAT", f"  button[{i}]: {text.strip()[:50]}")

        # Try to fill nickname and connect
        nick = "Guest" + rand_id(4)
        log("ISEXYCHAT", f"Trying to connect with nick: {nick}")

        # KiwiIRC uses a welcome screen with nickname input
        nick_input = await page.query_selector("input[placeholder*='nick'], input[placeholder*='Nick'], input[name='nick'], .kiwi-welcome-simple-nick input, #nick")
        if nick_input:
            await nick_input.fill(nick)
            log("ISEXYCHAT", f"Filled nick: {nick}")

            # Find and click start/connect button
            start_btn = await page.query_selector("button[type='submit'], .kiwi-welcome-simple-start, .u-button")
            if start_btn:
                await start_btn.click()
                log("ISEXYCHAT", "Clicked start button")
                await asyncio.sleep(5)

                # Check if we're in the chat
                log("ISEXYCHAT", f"After connect - title: {await page.title()}")
                await page.screenshot(path="capture_isexychat_connected.png")
                log("ISEXYCHAT", "Post-connect screenshot saved")

                # Look for chat messages
                messages = await page.query_selector_all(".kiwi-messagelist-message, .kiwi-messagelist-body")
                log("ISEXYCHAT", f"Found {len(messages)} messages in chat")

                # Look for message input
                msg_input = await page.query_selector(".kiwi-inputbar-input, textarea, input[placeholder*='message'], input[placeholder*='Message']")
                if msg_input:
                    log("ISEXYCHAT", "Found message input! Chat is ready!")
                else:
                    log("ISEXYCHAT", "No message input found")
            else:
                log("ISEXYCHAT", "No start button found")
        else:
            log("ISEXYCHAT", "No nickname input found — page might need different flow")

        # Get all text content for debugging
        body_text = await page.evaluate("() => document.body?.innerText?.substring(0, 2000) || ''")
        log("ISEXYCHAT", f"Body text: {body_text[:500]}")

        await browser.close()
        log("ISEXYCHAT", "Browser closed")


# ════════════════════════════════════════════════════════════════════════
async def main():
    print("=" * 70)
    print("  ROUND 3 — Full conversation + Playwright")
    print("=" * 70)

    # Joingy full conversation
    await joingy_conversation()
    print()

    # iSexyChat Playwright
    await isexychat_playwright()

    print()
    print("=" * 70)
    print("  ROUND 3 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())