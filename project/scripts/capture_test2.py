# -*- coding: utf-8 -*-
"""
Round 2: Fix issues from round 1.
- iSexyChat: Try via KiwiIRC webirc gateway (webirc.bb.chat)
- Joingy: We got a UID! Now properly poll events + send message
- Chatib: Parse the 242KB HTML for chat JS/API
- ChatRandom: Parse the 33KB app_loader response
"""
import asyncio
import ssl
import json
import time
import random
import string
import re
import aiohttp
from aiohttp_socks import ProxyConnector, ProxyType

SOCKS5_PROXY = ("148.59.2.158.static.flameproxies.com", 1337, "vmLElhTf-148.59.2.158", "NVRf69LCWfeILf6C")
HTTP_PROXY = ("gw.dataimpulse.com", 823, "34d99b34747b4c4e63b7__cr.us", "219c40489f5eff94")

def socks5_conn():
    return ProxyConnector(proxy_type=ProxyType.SOCKS5, host=SOCKS5_PROXY[0], port=SOCKS5_PROXY[1], username=SOCKS5_PROXY[2], password=SOCKS5_PROXY[3], rdns=True)

def http_conn():
    return ProxyConnector(proxy_type=ProxyType.HTTP, host=HTTP_PROXY[0], port=HTTP_PROXY[1], username=HTTP_PROXY[2], password=HTTP_PROXY[3], rdns=True)

def rand_nick():
    return "Guest" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))

def log(tag, msg):
    print(f"[{time.strftime('%H:%M:%S')}] [{tag}] {msg}")


# ════════════════════════════════════════════════════════════════════════
# 1. iSexyChat via KiwiIRC webirc gateway
# ════════════════════════════════════════════════════════════════════════
async def test_isexychat_webirc():
    log("ISEXYCHAT", "Trying KiwiIRC webirc gateway at webirc.bb.chat...")
    connector = socks5_conn()
    timeout = aiohttp.ClientTimeout(total=30)

    # KiwiIRC uses a websocket proxy to connect to the IRC server
    # The gateway URL is: https://webirc.bb.chat/webirc/kiwiirc/
    # It proxies IRC over WebSocket

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Origin": "https://chat.isexychat.com",
            "Referer": "https://chat.isexychat.com/",
        }

        # Try the KiwiIRC webirc endpoint
        nick = rand_nick()
        log("ISEXYCHAT", f"Trying webirc proxy with nick: {nick}")

        # KiwiIRC webirc uses POST to create a websocket connection
        try:
            # First try the webirc init endpoint
            async with session.post(
                "https://webirc.bb.chat/webirc/kiwiirc/",
                json={
                    "server": "irc.freechat.zone",
                    "port": 6697,
                    "tls": True,
                    "nick": nick,
                    "channel": "#ifap",
                    "direct": False,
                },
                headers=headers,
            ) as resp:
                status = resp.status
                text = await resp.text()
                log("ISEXYCHAT", f"webirc init [{status}]: {text[:500]}")

                # Check if we get a websocket URL or session token
                if status == 200:
                    try:
                        data = json.loads(text)
                        log("ISEXYCHAT", f"webirc response JSON: {json.dumps(data, indent=2)[:500]}")
                    except:
                        pass
        except Exception as e:
            log("ISEXYCHAT", f"webirc POST error: {e}")

        # Try WebSocket connection to the gateway
        log("ISEXYCHAT", "Trying WebSocket to wss://webirc.bb.chat/webirc/kiwiirc/...")
        try:
            ws_url = "wss://webirc.bb.chat/webirc/kiwiirc/"
            async with session.ws_connect(ws_url, headers=headers) as ws:
                log("ISEXYCHAT", "WebSocket connected!")

                # Send IRC commands over WebSocket
                await ws.send_str(f"NICK {nick}\r\nUSER {nick} 0 * :{nick}\r\n")
                log("ISEXYCHAT", f"Sent NICK/USER: {nick}")

                # Wait for welcome
                start = time.time()
                connected = False
                while time.time() - start < 20:
                    try:
                        msg = await asyncio.wait_for(ws.receive(), timeout=5.0)
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = msg.data
                            for line in data.split("\r\n"):
                                line = line.strip()
                                if not line:
                                    continue
                                log("ISEXYCHAT", f"WS<- {line[:150]}")

                                if "PING" in line:
                                    await ws.send_str(line.replace("PING", "PONG", 1) + "\r\n")

                                if " 001 " in line:
                                    connected = True
                                    log("ISEXYCHAT", "Connected! Joining #ifap...")
                                    await ws.send_str("JOIN #ifap\r\n")

                                if " 376 " in line and connected:
                                    log("ISEXYCHAT", "MOTD end — fully connected!")
                                    # Listen for chat messages
                                    await asyncio.sleep(10)

                                if "PRIVMSG" in line:
                                    parts = line.split(" ", 3)
                                    if len(parts) >= 4:
                                        sender = parts[0].split("!")[0].lstrip(":")
                                        target = parts[2]
                                        text_msg = parts[3].lstrip(":")
                                        log("ISEXYCHAT", f"CHAT [{target}] {sender}: {text_msg[:80]}")

                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            log("ISEXYCHAT", f"WebSocket closed: {msg.type}")
                            break
                    except asyncio.TimeoutError:
                        continue

                await ws.close()
                log("ISEXYCHAT", "WebSocket session ended")

        except Exception as e:
            log("ISEXYCHAT", f"WebSocket error: {e}")


# ════════════════════════════════════════════════════════════════════════
# 2. Joingy — Full API flow with event polling
# ════════════════════════════════════════════════════════════════════════
async def test_joingy_full():
    log("JOINGY", "Full API test — start, poll events, send message...")
    connector = socks5_conn()
    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": "https://joingy.com/",
            "Origin": "https://joingy.com",
        }

        randid = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        fp_hash = "".join(random.choices("abcdef0123456789", k=32))

        # Step 1: Start
        log("JOINGY", f"POST /start randid={randid}")
        async with session.post(
            "https://back.joingy.com/start",
            json={"randid": randid, "vid": False, "hash": fp_hash},
            headers={**headers, "Content-Type": "application/json"},
        ) as resp:
            start_text = await resp.text()
            log("JOINGY", f"/start [{resp.status}]: {start_text[:200]}")

            # Response is a quoted string (the uid)
            uid = start_text.strip().strip('"')
            if not uid or uid in ("ratelimit", "ban"):
                log("JOINGY", f"Failed: {uid}")
                return

            log("JOINGY", f"Got UID: {uid}")

        # Step 2: Poll for events (long-poll)
        log("JOINGY", f"POST /event uid={uid} (waiting for partner...)")
        try:
            async with session.post(
                "https://back.joingy.com/event",
                data={"uid": uid, "vid": "false"},
                headers=headers,
            ) as event_resp:
                event_text = await event_resp.text()
                log("JOINGY", f"/event [{event_resp.status}]: {event_text[:500]}")

                try:
                    event_data = json.loads(event_text)
                    log("JOINGY", f"Event: {json.dumps(event_data, indent=2)}")

                    if event_data.get("event") == "connected":
                        log("JOINGY", "Partner connected! Sending test message...")

                        # Step 3: Send a message
                        async with session.post(
                            "https://back.joingy.com/boop",
                            data={"uid": uid, "msg": "hey :)", "vid": "false"},
                            headers=headers,
                        ) as boop_resp:
                            boop_text = await boop_resp.text()
                            log("JOINGY", f"/boop (send) [{boop_resp.status}]: {boop_text[:200]}")

                        # Step 4: Poll for partner's reply
                        log("JOINGY", "Polling for partner reply...")
                        async with session.post(
                            "https://back.joingy.com/event",
                            data={"uid": uid, "vid": "false"},
                            headers=headers,
                        ) as reply_resp:
                            reply_text = await reply_resp.text()
                            log("JOINGY", f"/event (reply) [{reply_resp.status}]: {reply_text[:500]}")

                    elif event_data.get("event") == "disconnected":
                        log("JOINGY", "Partner disconnected immediately")
                except json.JSONDecodeError:
                    log("JOINGY", f"Non-JSON event response: {event_text[:200]}")

        except asyncio.TimeoutError:
            log("JOINGY", "Event poll timed out (no partner found in 60s)")

        # Disconnect
        try:
            async with session.post(
                "https://back.joingy.com/disconnect",
                data={"uid": uid, "vid": "false"},
                headers=headers,
            ) as dc_resp:
                log("JOINGY", f"/disconnect [{dc_resp.status}]")
        except:
            pass


# ════════════════════════════════════════════════════════════════════════
# 3. Chatib — Parse captured HTML for chat JS/API
# ════════════════════════════════════════════════════════════════════════
async def test_chatib_parse():
    log("CHATIB", "Parsing captured HTML for chat endpoints...")
    try:
        with open("capture_chatib.html", "r", encoding="utf-8") as f:
            html = f.read()

        # Find script sources
        scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html)
        log("CHATIB", f"Script sources ({len(scripts)}):")
        for s in scripts:
            log("CHATIB", f"  script: {s}")

        # Find inline JS with chat-related keywords
        inline_scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
        log("CHATIB", f"Inline scripts: {len(inline_scripts)}")

        for i, script in enumerate(inline_scripts):
            if any(kw in script.lower() for kw in ["websocket", "ws://", "wss://", "socket", "chat", "message", "send", "ajax", "fetch"]):
                log("CHATIB", f"Inline script #{i} has chat keywords (len={len(script)})")
                # Extract URLs
                urls = re.findall(r'["\']([^"\']*(?:chat|msg|send|message|socket|ws)[^"\']*)["\']', script, re.IGNORECASE)
                if urls:
                    log("CHATIB", f"  URLs: {urls[:15]}")

        # Find form actions
        forms = re.findall(r'<form[^>]+action=["\']([^"\']+)["\']', html)
        log("CHATIB", f"Form actions: {forms}")

        # Find data attributes
        data_attrs = re.findall(r'data-[a-z]+=["\']([^"\']+)["\']', html)
        log("CHATIB", f"Data attrs (first 20): {data_attrs[:20]}")

        # Save inline scripts that look relevant
        with open("capture_chatib_scripts.txt", "w", encoding="utf-8") as f:
            for i, script in enumerate(inline_scripts):
                if len(script) > 50:
                    f.write(f"=== INLINE SCRIPT #{i} (len={len(script)}) ===\n")
                    f.write(script[:2000])
                    f.write("\n\n")

        log("CHATIB", "Scripts saved to capture_chatib_scripts.txt")

    except FileNotFoundError:
        log("CHATIB", "capture_chatib.html not found")


# ════════════════════════════════════════════════════════════════════════
# 4. ChatRandom — Parse app_loader response
# ════════════════════════════════════════════════════════════════════════
async def test_chatrandom_parse():
    log("CHATRANDOM", "Parsing app_loader response...")
    try:
        with open("capture_chatrandom_apploader.html", "r", encoding="utf-8") as f:
            html = f.read()

        # Find script sources
        scripts = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html)
        log("CHATRANDOM", f"Script sources ({len(scripts)}):")
        for s in scripts:
            log("CHATRANDOM", f"  script: {s}")

        # Find inline JS
        inline_scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
        log("CHATRANDOM", f"Inline scripts: {len(inline_scripts)}")

        for i, script in enumerate(inline_scripts):
            if any(kw in script.lower() for kw in ["websocket", "ws://", "wss://", "socket", "roulette", "chat", "start", "next", "skip"]):
                log("CHATRANDOM", f"Inline script #{i} has chat keywords (len={len(script)})")
                urls = re.findall(r'["\']([^"\']*(?:chat|msg|send|start|next|skip|roulette|socket|ws)[^"\']*)["\']', script, re.IGNORECASE)
                if urls:
                    log("CHATRANDOM", f"  URLs: {urls[:15]}")

        # Find all URLs
        all_urls = re.findall(r'["\'](/[^"\']{3,80})["\']', html)
        unique_urls = list(set(all_urls))
        log("CHATRANDOM", f"Internal URLs ({len(unique_urls)}):")
        for u in sorted(unique_urls)[:30]:
            log("CHATRANDOM", f"  {u}")

        # Find data attributes
        data_attrs = re.findall(r'data-[a-z-]+=["\']([^"\']+)["\']', html)
        log("CHATRANDOM", f"Data attrs: {data_attrs[:20]}")

        # Save for analysis
        with open("capture_chatrandom_scripts.txt", "w", encoding="utf-8") as f:
            for i, script in enumerate(inline_scripts):
                if len(script) > 50:
                    f.write(f"=== INLINE SCRIPT #{i} (len={len(script)}) ===\n")
                    f.write(script[:3000])
                    f.write("\n\n")

        log("CHATRANDOM", "Scripts saved to capture_chatrandom_scripts.txt")

    except FileNotFoundError:
        log("CHATRANDOM", "capture_chatrandom_apploader.html not found")


# ════════════════════════════════════════════════════════════════════════
async def main():
    print("=" * 70)
    print("  ROUND 2 — Fix and deep capture")
    print("=" * 70)

    # iSexyChat via webirc gateway
    await test_isexychat_webirc()
    print()

    # Joingy full flow
    await test_joingy_full()
    print()

    # Parse Chatib and ChatRandom captures
    await asyncio.gather(
        test_chatib_parse(),
        test_chatrandom_parse(),
    )

    print()
    print("=" * 70)
    print("  ROUND 2 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())