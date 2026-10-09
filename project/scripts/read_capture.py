import json, sys

f = open(sys.argv[1], "r", encoding="utf-8")
data = json.load(f)
f.close()

ws_frames = data.get("websocket_frames", [])
text_msgs = []
for w in ws_frames:
    d = w.get("data", "")
    if not d:
        continue
    if isinstance(d, str) and not d.startswith("b'"):
        text_msgs.append(w)

print("Total WS frames:", len(ws_frames))
print("Text WS frames:", len(text_msgs))
print()
print("=== Text WS Messages ===")
for m in text_msgs[:80]:
    print(f"  {m['event']:4s} {m.get('time','')} {m['data'][:250]}")

print()
print("=== WS URLs ===")
for u in data.get("summary", {}).get("ws_urls", []):
    print(f"  {u[:200]}")

print()
print("=== API URLs ===")
for u in data.get("summary", {}).get("api_urls", []):
    print(f"  {u[:200]}")

print()
print("=== API Calls with responses ===")
for a in data.get("api_calls", []):
    if a.get("is_api"):
        resp = a.get("response", {})
        print(f"  {a['method']} {a['url'][:120]}")
        if "post_data" in a:
            print(f"    POST: {a['post_data'][:200]}")
        if resp:
            print(f"    RESP {resp.get('status','')}: {resp.get('body','')[:200]}")