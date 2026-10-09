# -*- coding: utf-8 -*-
"""
Test 1: Direct IRC connection from local IP (no proxy)
Test 2: WebSocket to webirc.bb.chat gateway with proper headers
"""
import asyncio
import ssl
import time
import random
import string
import json

def rand_nick():
    return "Guest" + "".join(random.choices(string.ascii_lowercase + string.digits, k=5))

def log(tag, msg):
    safe = str(msg).encode("ascii", "replace").decode("ascii")
    print(f"[{time.strftime('%H:%M:%S')}] [{tag}] {safe}", flush=True)


async def test_direct_irc():
    """Try direct IRC connection from local IP"""
    log("IRC", "Direct connect to irc.freechat.zone:6697 (local IP)...")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection("irc.freechat.zone", 6697, ssl=ctx),
            timeout=15,
        )
        log("IRC", "Connected!")

        nick = rand_nick()
        log("IRC", f"Nick: {nick}")

        writer.write(f"NICK {nick}\r\nUSER {nick} 0 * :{nick}\r\n".encode())
        await writer.drain()

        # Wait for registration to complete
        start = time.time()
        registered = False
        banned = False
        lines = []

        while time.time() - start < 20:
            try:
                data = await asyncio.wait_for(reader.readline(), timeout=3.0)
                if not data:
                    break
                line = data.decode("utf-8", errors="replace").strip()
                lines.append(line)
                log("IRC", f"<- {line[:150]}")

                if line.startswith("PING"):
                    writer.write(line.replace("PING", "PONG", 1).encode() + b"\r\n")
                    await writer.drain()

                if " 001 " in line:
                    registered = True
                    log("IRC", "*** REGISTERED! ***")

                if " 376 " in line:
                    log("IRC", "*** MOTD end — fully connected! ***")
                    # Join channel
                    writer.write(b"JOIN #ifap\r\n")
                    await writer.drain()
                    log("IRC", "Joined #ifap")

                if " 465 " in line or "G-lined" in line or "ERROR" in line:
                    banned = True
                    log("IRC", f"BANNED: {line[:200]}")

                if "PRIVMSG" in line and " 001 " not in line:
                    parts = line.split(" ", 3)
                    if len(parts) >= 4:
                        sender = parts[0].split("!")[0].lstrip(":")
                        target = parts[2]
                        msg = parts[3].lstrip(":")
                        log("IRC", f"CHAT [{target}] {sender}: {msg[:80]}")

                if " 353 " in line:
                    log("IRC", f"NAMES: {line[:200]}")

                if " 366 " in line:
                    log("IRC", "*** Channel joined successfully! ***")
                    # Listen for chat for 10 seconds
                    chat_start = time.time()
                    while time.time() - chat_start < 10:
                        try:
                            data = await asyncio.wait_for(reader.readline(), timeout=2.0)
                            if not data:
                                break
                            line = data.decode("utf-8", errors="replace").strip()
                            if "PRIVMSG" in line:
                                parts = line.split(" ", 3)
                                if len(parts) >= 4:
                                    sender = parts[0].split("!")[0].lstrip(":")
                                    target = parts[2]
                                    msg = parts[3].lstrip(":")
                                    log("IRC", f"CHAT [{target}] {sender}: {msg[:100]}")
                            elif line.startswith("PING"):
                                writer.write(line.replace("PING", "PONG", 1).encode() + b"\r\n")
                                await writer.drain()
                        except asyncio.TimeoutError:
                            continue
                    break

            except asyncio.TimeoutError:
                continue

        writer.close()
        try:
            await writer.wait_closed()
        except:
            pass

        log("IRC", f"Result: registered={registered} banned={banned} lines={len(lines)}")

        with open("capture_irc_direct.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return registered and not banned

    except Exception as e:
        log("IRC", f"Error: {e}")
        return False


async def test_webirc_websocket():
    """Try WebSocket to webirc.bb.chat with proper KiwiIRC headers"""
    log("WEBIRC", "Trying wss://webirc.bb.chat/webirc/kiwiirc/ ...")
    import websockets

    headers = {
        "Origin": "https://chat.isexychat.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    }

    try:
        async with websockets.connect(
            "wss://webirc.bb.chat/webirc/kiwiirc/",
            additional_headers=headers,
            ssl=ssl.create_default_context(),
            open_timeout=15,
        ) as ws:
            log("WEBIRC", "WebSocket connected!")

            nick = rand_nick()
            # Send IRC commands
            await ws.send(f"NICK {nick}\r\nUSER {nick} 0 * :{nick}\r\n")
            log("WEBIRC", f"Sent NICK/USER: {nick}")

            start = time.time()
            while time.time() - start < 20:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
                    for line in msg.split("\r\n"):
                        line = line.strip()
                        if not line:
                            continue
                        log("WEBIRC", f"<- {line[:150]}")

                        if line.startswith("PING"):
                            await ws.send(line.replace("PING", "PONG", 1) + "\r\n")

                        if " 001 " in line:
                            log("WEBIRC", "*** REGISTERED! ***")
                            await ws.send("JOIN #ifap\r\n")

                        if " 366 " in line:
                            log("WEBIRC", "*** Channel joined! ***")

                        if "PRIVMSG" in line:
                            parts = line.split(" ", 3)
                            if len(parts) >= 4:
                                sender = parts[0].split("!")[0].lstrip(":")
                                target = parts[2]
                                text = parts[3].lstrip(":")
                                log("WEBIRC", f"CHAT [{target}] {sender}: {text[:80]}")
                except asyncio.TimeoutError:
                    continue

            await ws.close()
            log("WEBIRC", "Done")
            return True

    except Exception as e:
        log("WEBIRC", f"Error: {e}")
        return False


async def main():
    print("=" * 70)
    print("  IRC Connection Tests")
    print("=" * 70)

    # Test 1: Direct IRC
    ok1 = await test_direct_irc()
    print()

    if not ok1:
        # Test 2: WebIRC WebSocket
        ok2 = await test_webirc_websocket()
        print()

    print("=" * 70)
    print(f"  Direct IRC: {'OK' if ok1 else 'FAILED'}")
    if not ok1:
        print(f"  WebIRC WS:  {'OK' if ok2 else 'FAILED'}")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())