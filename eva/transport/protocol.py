"""Capture-derived constants for chitchat.gg.

Single source of truth = eva/transport/protocol_manifest.json.
Every value here appears verbatim in the captures.
"""

CHITCHAT_API_BASE = "https://api.chitchat.gg"

# wss endpoint as captured (15_websocket_all.json WEBSOCKET_CREATED)
CHITCHAT_WS_URL = "wss://api.chitchat.gg/socket.io/?EIO=4&transport=websocket"

# browser origin of the text app (all captured REST requests carry it)
DEFAULT_ORIGIN = "https://app.chitchat.gg"
DEFAULT_REFERER = "https://app.chitchat.gg/"

# the exact UA captured from the user's browser (Chrome 155, Windows)
DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36")

# frontend git sha observed in the captured namespace-connect frame
# 40{"release":"b01c3724172e05407a2d46737b9c5fa0c857e0f2"}
RELEASE_SHA = "b01c3724172e05407a2d46737b9c5fa0c857e0f2"

# captured handshake: pingInterval 25000ms (server pings, we pong)
DEFAULT_PING_INTERVAL_MS = 25000

# captured client cadence: 42["presenceSync"] every ~30s
PRESENCE_SYNC_INTERVAL_S = 30.0

# captured message POST latency ~0.5-0.7s; typing indicator precedes send
TYPING_LEAD_S = 0.5

# REST endpoints (all captured in 17_endpoints_summary.json)
EP_ME = "/users/me"
EP_MATCH_ACTIVE = "/match/active"
EP_MATCH = "/match"
EP_MATCH_DISCONNECT = "/match/disconnect"
EP_MOD_STANDING = "/moderation/standing"
EP_MOD_BAN = "/moderation/ban"
EP_CONVERSATION_MESSAGES = "/users/me/conversations/{cid}/messages"
EP_CONVERSATION_TYPING = "/users/me/conversations/{cid}/typing"
EP_CONVERSATION_READ = "/users/me/conversations/{cid}/read"

# message POST body mode: captured content-type was multipart/form-data;
# response keys prove fields "content" and "nonce". JSON fallback switchable.
MESSAGE_BODY_FORMAT_MULTIPART = "multipart"
MESSAGE_BODY_FORMAT_JSON = "json"
