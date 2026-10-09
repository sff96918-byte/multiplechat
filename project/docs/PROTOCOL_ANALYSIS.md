# PROTOCOL ANALYSIS — Captured from Live Traffic
Generated: 2026-10-03

## Sites Captured:
1. iSexyChat.com — FULL Socket.IO + API captured
2. Chatib.net — Coomeet API detected
3. EmeraldChat.com — REST API detected
4. Joingy.com — HTTP API (already known)
5. DirtyRoulette/Flingster/Shagle — Cloudflare blocked (need proxy)

---

## 1. iSexyChat.com (LiveJasmin Whitelabel)

### Architecture
- **API**: `api-protected.protoawegw.com` (LiveJasmin backend)
- **Chat**: Socket.IO v4 WebSocket at `wss://ls-entry-pt-*.dditsadn.com/socket.io/`
- **Video**: H5Live WebSocket at `wss://ngs-edge-*.dditscdn.com/`

### Signup / Guest Login
No registration needed. Guest token is auto-generated.

**Step 1: Get Performer Info**
```
GET https://api-protected.protoawegw.com/v2/player/performer/get
    ?product=livejasmin&siteId=joy&category=girl&withSb=1
    &psid=xlinkbot&pstool=302_2
    &profilePictureSize=896x504,504x896

Response 200:
{
  "status": "OK",
  "data": {
    "performerId": "TiffaanyAdams",
    "displayName": "TiffanyAddams",
    "status": "free",
    "chatPage": "...",
    ...
  }
}
```

**Step 2: Connect to Socket.IO**
```
WSS: wss://ls-entry-pt-95-128-123-127.dditsadn.com/socket.io/
     ?psid=xlinkbot&pstool=302_2&applicationId=oneconnection
     &EIO=4&transport=websocket

Server -> Client: 0{"sid":"gudZho97FMfg3EKJatsL","upgrades":[],"pingInterval":2000,"pingTimeout":5000}

Client -> Server: 40{"token":"eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiIsImtpZCI6InYxIn0..."}
                 (JWT token with sessionId, userType:"guest", userId:0, countryCode, regionCode)

Server -> Client: 40{"sid":"X1svdSXtUHBi0-ZmatsQ"}
Server -> Client: 42["accept",null]
```

**Step 3: Join Room**
```
Client -> Server: 42["join",{
  "roomId":"TiffaanyAdams",
  "isPassive":false,
  "chatHistoryRequired":true,
  "sendSharedObject":["data/chat_so"]
}]

Server -> Client: 430[{"response":{
  "fmsIp":"10.97.111.177",
  "applicationId":"memberChat/jasminTiffaanyAdamsa35e3f5432e961be3f93861a579b75d2"
}}]

Server -> Client: 42["preferredStreamStatus",{"roomId":"TiffaanyAdams"},"NONE"]
Server -> Client: 42["chatHistory",{"roomId":"TiffaanyAdams"},[{...messages}]]
Server -> Client: 42["initVipShow",{"roomId":"TiffaanyAdams"},{"status":"pre-show","goal":12,...}]
Server -> Client: 42["setName",{"roomId":"TiffaanyAdams"},"GoofWhisper","GUEST","fr76svq14t0y40a07x44246w6u368664"]
Server -> Client: 42["updateSO",{"roomId":"TiffaanyAdams","name":"data/chat_so"},{...state}]
Server -> Client: 42["updateChatType",{"roomId":"TiffaanyAdams"},{"chatType":"predefined","maxMessageCount":3}]
```

**Step 4: Request Video Stream**
```
Client -> Server: 42["getVideoData",{"roomId":"TiffaanyAdams"},{"protocols":["h5live"],"streamId":"...","correlationId":"..."}]
Server -> Client: 42["setVideoData",{"roomId":"TiffaanyAdams"},[{"isSuccess":true,"streamId":"...","node":"uslax",...}]]
```

**Step 5: Heartbeat (every 2s)**
```
Server -> Client: 2  (ping)
Client -> Server: 3  (pong)
```

### Incoming Messages
Chat history arrives in `chatHistory` event:
```json
42["chatHistory",{"roomId":"TiffaanyAdams"},[
  {
    "msg":"hi bb",
    "msgKey":null,
    "broadcastOnly":true,
    "id":"1849370633766035",
    "memberType":"member",
    "ismobile":0,
    "performerID":"TiffaanyAdams",
    "type":"member",
    "userNick":"PantiB..."
  }
]]
```

### Outgoing Messages (PREDICTED — not yet captured)
Likely format:
```
Client -> Server: 42["sendMessage",{"roomId":"TiffaanyAdams"},"hello there"]
```
OR:
```
Client -> Server: 42["message",{"roomId":"TiffaanyAdams","msg":"hello there"}]
```

### Key Notes
- iSexyChat is a CAM SITE (LiveJasmin whitelabel), NOT a 1-on-1 random text chat
- Chat is PUBLIC (everyone in the room sees messages)
- Guest users have message limits: `"chatType":"predefined","maxMessageCount":3`
- To send custom messages, likely need a registered account
- The existing KiwiIRC bot (`sites/isexychat.py`) uses a DIFFERENT interface (IRC channel)

---

## 2. Chatib.net (Coomeet Whitelabel)

### Architecture
- **Frontend**: WordPress site (chatib.net)
- **Chat Backend**: Coomeet API (`ap1.coomeet.com`) + iframe (`iframe.coomeet.com`)
- **Chat Protocol**: Not yet fully captured (iframe needs params to load chat)

### APIs Found
```
GET https://ap1.coomeet.com/v20/service/blacklist.site
Response: {"status":"OK","blacklist":["18fu.com","vibragame.org","emeraldchat.app",...]}

GET https://ap1.coomeet.com/v20/i18n/web/en
Response: {"status":"OK","i18n":{"5":"min","A_FRIEND_ADD":"Add to contacts",...}}
```

### Coomeet API Endpoints (PREDICTED based on JS module names)
- `ap1.coomeet.com/v20/service/blacklist.site` — blacklist check
- `ap1.coomeet.com/v20/i18n/web/en` — i18n strings
- `ap1.coomeet.com/v20/auth/...` — authentication (likely)
- `ap1.coomeet.com/v20/chat/...` — chat operations (likely)
- `ap1.coomeet.com/v20/user/...` — user operations (likely)

### JS Modules Loaded (from iframe.coomeet.com)
- ChatArea.js — chat message display
- ChatHeader.js — chat header UI
- LoginRegistration.js — login/register
- MessagesEnded.js — chat ended state
- SendGift.js — gift sending
- UserAccessDenied.js — banned state
- UserProfile.js — user profile
- UserNotes.js — user notes

### Next Steps for Chatib
Need to capture the iframe with proper parameters (partner ID, session token).
The iframe URL likely needs to be extracted from the Chatib page HTML.

---

## 3. EmeraldChat.com

### Architecture
- **Frontend**: Next.js app
- **API**: `api.emeraldchat.com/api/v1/`
- **Auth**: Cloudflare challenge + cookie-based auth

### APIs Found
```
GET https://api.emeraldchat.com/api/v1/auth/current_user
Response: 401 (not logged in)

GET https://api.emeraldchat.com/api/v1/stripe/payment_data
Response: {"public_key":"pk_live_51CwUC2KY5wwTXMsi..."}
```

### Form Fields Found
- input[name="name"] — username
- input[name="email"] — email

### Next Steps for EmeraldChat
Need to:
1. Create account (POST to /api/v1/auth/register or similar)
2. Start a chat session (POST to /api/v1/chat/start or similar)
3. Capture WebSocket for real-time messages

---

## 4. Joingy.com (Already Implemented)

### Architecture
- **API**: `https://back.joingy.com` (pure HTTP, no WebSocket)

### Protocol (CONFIRMED WORKING)
```
POST /start  {"randid":"xxx","vid":false,"hash":"xxx"} -> returns UID
POST /event  uid=xxx&vid=false -> {"event":"connected|message|typing|disconnected"}
POST /boop   uid=xxx&msg=text&vid=false -> send message
POST /disconnect uid=xxx&vid=false
```

---

## 5. Sites Blocked by Cloudflare
- DirtyRoulette.com — Cloudflare challenge (need proxy/captcha solver)
- Flingster.com — Cloudflare challenge
- Shagle.com — Cloudflare challenge
- Chatruletka.com — Timeout

These sites need either:
- Real browser with Cloudflare bypass
- Proxy rotation
- Headful browser (not headless)

---

## SUMMARY: Which Sites Are Bot-Ready?

| Site | Protocol | Bot Status | Difficulty |
|------|----------|-----------|------------|
| Joingy | HTTP API | WORKING | Easy |
| iSexyChat (KiwiIRC) | Playwright DOM | WORKING | Medium |
| iSexyChat (Socket.IO) | Socket.IO v4 | CAPTURED | Medium |
| Chatib (Coomeet) | Coomeet API | NEEDS DEEPER CAPTURE | Medium |
| EmeraldChat | REST API | NEEDS AUTH CAPTURE | Hard |
| DirtyRoulette | Unknown | BLOCKED | Hard |
| Flingster | Unknown | BLOCKED | Hard |
| Shagle | Unknown | BLOCKED | Hard |