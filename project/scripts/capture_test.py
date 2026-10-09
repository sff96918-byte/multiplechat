# -*- coding: utf-8 -*-
"""
Live protocol capture — actually connects to each site and records real traffic.
No guessing. Real connections, real responses.
"""
import asyncio
import ssl
import socket
import json
import time
import random
import string
import aiohttp
from aiohttp_socks import ProxyConnector, ProxyType

# ── Proxies ──────────────────────────────────────────────────────────────
SOCKS5_PROXY = "socks5://vmLElhTf-148.59.2.158:NVRf69LCWfeILf6C@148.59.2.158.static.flameproxies.com:1337"
HTTP_PROXY = "http://34d99b34747b4c4e63b7__cr.us:219c40489f5eff94@gw.dataimpulse.com:823"

def socks5_connector():
    return ProxyConnector(
        proxy_type=ProxyType.SOCKS5,
        host="148.59.2.158.static.flameproxies.com",
        port=1337,
        username="vmLElhTf-148.59.2.158",
        password="NVRf69LCWfeILf6C",
        rdns=True,
    )

def http_connector():
    return ProxyConnector(
        proxy_type=ProxyType.HTTP,
        host="gw.dataimpulse.com",
        port=823,
        username="34d99b34747b4c4e63b7__cr.us",
        password="219c40489f5eff94",
        rdns=True,
    )

def rand_nick():
    return "Guest" + "".join(random.choices(string.ascii_lowercase + string.digits, k=6))

def log(tag, msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] [{tag}] {msg}")

# ════════════════════════════════════════════════════════════════════════
# 1. iSexyChat — IRC Protocol Capture (irc.freechat.zone:6697 TLS)
# ════════════════════════════════════════════════════════════════════════
async def test_isexychat_irc():
    log("ISEXYCHAT", "Connecting to irc.freechat.zone:6697 TLS...")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    reader, writer = await asyncio.wait_for(
        asyncio.open_connection("irc.freechat.zone", 6697, ssl=ctx),
        timeout=15,
    )
    log("ISEXYCHAT", "Connected! Capturing IRC protocol...")

    nick = rand_nick()
    log("ISEXYCHAT", f"Using nick: {nick}")

    # IRC handshake
    writer.write(f"NICK {nick}\r\nUSER {nick} 0 * :{nick}\r\n".encode())
    await writer.drain()

    # Join sex-chat channel
    writer.write(b"JOIN #sex-chat\r\n")
    await writer.drain()
    log("ISEXYCHAT", "Joined #sex-chat")

    # Capture responses for 15 seconds
    start = time.time()
    messages = []
    while time.time() - start < 15:
        try:
            data = await asyncio.wait_for(reader.readline(), timeout=3.0)
            if not data:
                break
            line = data.decode("utf-8", errors="replace").strip()
            messages.append(line)

            # Respond to PING
            if line.startswith("PING"):
                pong = line.replace("PING", "PONG", 1)
                writer.write((pong + "\r\n").encode())
                await writer.drain()
                log("ISEXYCHAT", f"PING/PONG: {pong}")

            # Log PRIVMSG (chat messages)
            if "PRIVMSG" in line:
                # Parse: :nick!user@host PRIVMSG #channel :message
                parts = line.split(" ", 3)
                if len(parts) >= 4:
                    sender = parts[0].split("!")[0].lstrip(":")
                    target = parts[2]
                    msg_text = parts[3].lstrip(":")
                    log("ISEXYCHAT", f"MSG [{target}] {sender}: {msg_text[:80]}")

            # Log JOIN/PART/NICK
            if " JOIN " in line or " PART " in line or " 353 " in line or " 366 " in line:
                log("ISEXYCHAT", f"IRC: {line[:120]}")

        except asyncio.TimeoutError:
            continue

    writer.close()
    try:
        await writer.wait_closed()
    except:
        pass

    log("ISEXYCHAT", f"Captured {len(messages)} lines total")
    # Save raw capture
    with open("capture_isexychat_irc.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(messages))
    log("ISEXYCHAT", "Saved to capture_isexychat_irc.txt")
    return len(messages) > 0


# ════════════════════════════════════════════════════════════════════════
# 2. Joingy — HTTP API Capture (back.joingy.com)
# ════════════════════════════════════════════════════════════════════════
async def test_joingy_api():
    log("JOINGY", "Testing HTTP API at back.joingy.com...")

    connector = socks5_connector()
    timeout = aiohttp.ClientTimeout(total=30)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        # Step 1: Start a text chat session
        randid = "".join(random.choices(string.ascii_lowercase + string.digits, k=10))
        fp_hash = "".join(random.choices("abcdef0123456789", k=32))

        start_payload = {"randid": randid, "vid": False, "hash": fp_hash}
        log("JOINGY", f"POST /start payload: {json.dumps(start_payload)}")

        try:
            async with session.post(
                "https://back.joingy.com/start",
                json=start_payload,
                headers={"Content-Type": "application/json", "Referer": "https://joingy.com/", "Origin": "https://joingy.com"},
            ) as resp:
                status = resp.status
                text = await resp.text()
                log("JOINGY", f"/start response [{status}]: {text[:300]}")

                if status == 200 and text and text != "ratelimit" and text != "ban":
                    # We got a uid — try polling for events
                    try:
                        uid_data = json.loads(text)
                        uid = uid_data.get("uid", "")
                        log("JOINGY", f"Got uid: {uid}")

                        if uid:
                            # Poll for events
                            log("JOINGY", f"POST /event with uid={uid}")
                            async with session.post(
                                "https://back.joingy.com/event",
                                data={"uid": uid, "vid": "false"},
                                headers={"Referer": "https://joingy.com/", "Origin": "https://joingy.com"},
                            ) as event_resp:
                                event_text = await event_resp.text()
                                log("JOINGY", f"/event response [{event_resp.status}]: {event_text[:300]}")

                            # Try sending a message
                            log("JOINGY", f"POST /boop (send msg) with uid={uid}")
                            async with session.post(
                                "https://back.joingy.com/boop",
                                data={"uid": uid, "msg": "hi", "vid": "false"},
                                headers={"Referer": "https://joingy.com/", "Origin": "https://joingy.com"},
                            ) as boop_resp:
                                boop_text = await boop_resp.text()
                                log("JOINGY", f"/boop response [{boop_resp.status}]: {boop_text[:200]}")

                            # Disconnect
                            async with session.post(
                                "https://back.joingy.com/disconnect",
                                data={"uid": uid, "vid": "false"},
                                headers={"Referer": "https://joingy.com/", "Origin": "https://joingy.com"},
                            ) as dc_resp:
                                log("JOINGY", f"/disconnect [{dc_resp.status}]")
                    except json.JSONDecodeError:
                        log("JOINGY", f"Non-JSON response: {text[:200]}")
                else:
                    log("JOINGY", f"Start failed or rate limited: {text[:200]}")

        except Exception as e:
            log("JOINGY", f"Error: {e}")

    return True


# ════════════════════════════════════════════════════════════════════════
# 3. Chatib.net — Capture chat page and find WebSocket/AJAX endpoints
# ════════════════════════════════════════════════════════════════════════
async def test_chatib():
    log("CHATIB", "Fetching chat page...")
    connector = socks5_connector()
    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }
        try:
            async with session.get("https://chatib.net/chat/", headers=headers) as resp:
                text = await resp.text()
                log("CHATIB", f"Chat page [{resp.status}] len={len(text)}")

                # Search for WebSocket, AJAX, API endpoints in the HTML
                import re
                ws_matches = re.findall(r'wss?://[^\s"\'<>]+', text)
                ajax_matches = re.findall(r'\$\.ajax\s*\(\s*\{[^}]*url[^}]*\}', text, re.DOTALL)
                fetch_matches = re.findall(r'fetch\s*\([^\)]+\)', text)
                url_matches = re.findall(r'(?:url|action)\s*[:=]\s*["\']([^"\']+)["\']', text)

                log("CHATIB", f"WebSocket URLs: {ws_matches}")
                log("CHATIB", f"AJAX calls: {len(ajax_matches)}")
                log("CHATIB", f"Fetch calls: {len(fetch_matches)}")
                log("CHATIB", f"URLs found: {url_matches[:20]}")

                # Save for analysis
                with open("capture_chatib.html", "w", encoding="utf-8") as f:
                    f.write(text)
                log("CHATIB", "Saved to capture_chatib.html")

        except Exception as e:
            log("CHATIB", f"Error: {e}")

    return True


# ════════════════════════════════════════════════════════════════════════
# 4. AdultChat.net — Capture chat page
# ════════════════════════════════════════════════════════════════════════
async def test_adultchat():
    log("ADULTCHAT", "Fetching chat page...")
    connector = http_connector()
    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        }
        try:
            async with session.get("https://www.adultchat.net/chat/", headers=headers) as resp:
                text = await resp.text()
                log("ADULTCHAT", f"Chat page [{resp.status}] len={len(text)}")

                import re
                ws_matches = re.findall(r'wss?://[^\s"\'<>]+', text)
                ajax_urls = re.findall(r'(?:url|action)\s*[:=]\s*["\']([^"\']+)["\']', text)
                script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', text)

                log("ADULTCHAT", f"WebSocket URLs: {ws_matches}")
                log("ADULTCHAT", f"AJAX URLs: {ajax_urls[:20]}")
                log("ADULTCHAT", f"Script sources: {script_srcs[:10]}")

                with open("capture_adultchat.html", "w", encoding="utf-8") as f:
                    f.write(text)
                log("ADULTCHAT", "Saved to capture_adultchat.html")

        except Exception as e:
            log("ADULTCHAT", f"Error: {e}")

    return True


# ════════════════════════════════════════════════════════════════════════
# 5. ChatRandom — POST to app_loader.php
# ════════════════════════════════════════════════════════════════════════
async def test_chatrandom():
    log("CHATRANDOM", "Testing API at chatrandom.com...")
    connector = socks5_connector()
    timeout = aiohttp.ClientTimeout(total=20)

    async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Referer": "https://chatrandom.com/",
            "Origin": "https://chatrandom.com",
            "X-Requested-With": "XMLHttpRequest",
        }
        try:
            async with session.post(
                "https://chatrandom.com/api/app_loader.php",
                data={"page_type": "homepage"},
                headers=headers,
            ) as resp:
                text = await resp.text()
                log("CHATRANDOM", f"app_loader.php [{resp.status}] len={len(text)}")

                # Save response
                with open("capture_chatrandom_apploader.html", "w", encoding="utf-8") as f:
                    f.write(text)
                log("CHATRANDOM", "Saved to capture_chatrandom_apploader.html")

                # Look for WebSocket/API in response
                import re
                ws_matches = re.findall(r'wss?://[^\s"\'<>]+', text)
                ajax_urls = re.findall(r'(?:url|action)\s*[:=]\s*["\']([^"\']+)["\']', text)
                log("CHATRANDOM", f"WebSocket URLs: {ws_matches}")
                log("CHATRANDOM", f"AJAX URLs: {ajax_urls[:20]}")

        except Exception as e:
            log("CHATRANDOM", f"Error: {e}")

    return True


# ════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════
async def main():
    print("=" * 70)
    print("  LIVE PROTOCOL CAPTURE — Real connections, real data")
    print("=" * 70)

    # Test all sites in parallel where possible
    # iSexyChat IRC first (most important)
    await test_isexychat_irc()

    print()

    # Joingy API
    await test_joingy_api()

    print()

    # Chatib, AdultChat, ChatRandom in parallel
    await asyncio.gather(
        test_chatib(),
        test_adultchat(),
        test_chatrandom(),
    )

    print()
    print("=" * 70)
    print("  CAPTURE COMPLETE — Check capture_*.txt files for raw data")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())