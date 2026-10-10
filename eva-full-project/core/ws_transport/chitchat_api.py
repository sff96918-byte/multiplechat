"""chitchat.gg REST client — only endpoints proven by the capture.

Auth = session cookies (token JWT + __Secure-text-session), same as the
browser. No credentials are guessed, stored or logged here; the user supplies
their own session file.
"""

from __future__ import annotations

import asyncio
from collections import deque
import json as _json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import aiohttp

from . import protocol as P

log = logging.getLogger("eva.chitchat_api")


class ApiError(RuntimeError):
    def __init__(self, status: int, path: str, body: Any) -> None:
        self.status = status
        self.path = path
        self.body = body
        super().__init__(f"{status} {path}: {body}")


class FlaggedError(ApiError):
    """403 /match 'Flagged' — account temporarily unmatchable (observed in capture)."""


class SessionExpiredError(ApiError):
    """401 — the saved session (token cookie) is no longer valid.

    User-facing fix: dashboard 'Pull Session' again (or extract_session).
    """


@dataclass
class ApiStats:
    requests: int = 0
    errors: int = 0
    messages_sent: int = 0
    last_status: int = 0

    def snapshot(self) -> dict:
        return dict(self.__dict__)


class ChitchatApi:
    def __init__(
        self,
        cookies: Dict[str, str],
        *,
        origin: str = P.DEFAULT_ORIGIN,
        user_agent: str = P.DEFAULT_UA,
        message_body_format: str = P.MESSAGE_BODY_FORMAT_MULTIPART,
        request_spacing_s: float = 0.35,
        base_url: str = P.CHITCHAT_API_BASE,
    ) -> None:
        self._cookies = dict(cookies)
        self._origin = origin
        self._ua = user_agent
        self._msg_format = message_body_format
        self._spacing_s = request_spacing_s
        self._base_url = base_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_request_t = 0.0
        self._recent: deque = deque(maxlen=200)   # debug ring buffer
        self.stats = ApiStats()

    # ------------------------------------------------------------ lifecycle

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                base_url=self._base_url,
                cookies=self._cookies,
                headers={
                    "Origin": self._origin,
                    "Referer": P.DEFAULT_REFERER,
                    "User-Agent": self._ua,
                },
            )
        return self._session

    async def _request(self, method: str, path: str, **kw: Any) -> Any:
        # gentle spacing so we never approach the ~500/min bucket
        now = time.monotonic()
        wait = self._last_request_t + self._spacing_s - now
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_request_t = time.monotonic()

        s = await self._http()
        self.stats.requests += 1
        t0 = time.monotonic()
        async with s.request(method, path, **kw) as resp:
            self.stats.last_status = resp.status
            text = await resp.text()
            elapsed_ms = round((time.monotonic() - t0) * 1000)
            self._recent.append({"t": time.strftime("%H:%M:%S"),
                                 "req": f"{method} {path}", "status": resp.status,
                                 "ms": elapsed_ms, "bytes": len(text or "")})
            log.debug("API %s %s -> %s (%sms, %sB)", method, path, resp.status,
                      elapsed_ms, len(text or ""))
            try:

                body: Any = _json.loads(text) if text else None
            except ValueError:
                body = text
            if resp.status >= 400:
                self.stats.errors += 1
                if resp.status == 401:
                    raise SessionExpiredError(resp.status, path, body)
                if resp.status == 403 and isinstance(body, dict) and body.get("message") == "Flagged":
                    raise FlaggedError(resp.status, path, body)
                raise ApiError(resp.status, path, body)
            return body

    def recent_requests(self) -> List[dict]:
        return list(self._recent)

    # ------------------------------------------------------------ endpoints

    async def me(self) -> dict:
        """GET /users/me — confirms the session works, returns self profile."""
        return await self._request("GET", P.EP_ME)

    async def self_id(self) -> str:
        me = await self.me()
        return me.get("id", "")

    async def match_active(self) -> dict:
        """GET /match/active -> {inQueue: bool}"""
        return await self._request("GET", P.EP_MATCH_ACTIVE)

    async def join_match_queue(self) -> bool:
        """POST /match -> {'matched': bool}. Raises FlaggedError on 403 Flagged.

        Capture-exact request: EMPTY body (0 bytes, captured 32/32 times,
        body_size=0) with only a Content-Type: application/json header.
        """
        body = await self._request("POST", P.EP_MATCH,
                                   headers={"Content-Type": "application/json"})
        return bool(body.get("matched", False)) if isinstance(body, dict) else False

    async def leave_match(self) -> None:
        """PATCH /match/disconnect — skip current match / leave queue.

        Capture-exact: empty body (captured 18/18 times, body_size=0).
        """
        await self._request("PATCH", P.EP_MATCH_DISCONNECT,
                            headers={"Content-Type": "application/json"})

    async def moderation_standing(self) -> dict:
        return await self._request("GET", P.EP_MOD_STANDING)

    async def send_typing(self, conversation_id: str) -> None:
        """POST /users/me/conversations/{cid}/typing — empty body (captured 14/14, body_size=0)."""
        await self._request("POST", P.EP_CONVERSATION_TYPING.format(cid=conversation_id),
                            headers={"Content-Type": "application/json"})

    async def mark_read(self, conversation_id: str) -> None:
        """PATCH /users/me/conversations/{cid}/read — empty body (captured body_size=0)."""
        await self._request("PATCH", P.EP_CONVERSATION_READ.format(cid=conversation_id),
                            headers={"Content-Type": "application/json"})

    async def fetch_messages(self, conversation_id: str, limit: int = 50, offset: int = 0) -> list:
        path = P.EP_CONVERSATION_MESSAGES.format(cid=conversation_id)
        return await self._request("GET", path, params={"limit": str(limit), "offset": str(offset)})

    async def send_message(self, conversation_id: str, content: str, nonce: Optional[str] = None) -> dict:
        """POST /users/me/conversations/{cid}/messages.

        Capture proves: content-type multipart/form-data, response 201 Message
        object containing the client-generated `nonce`. Multipart field names
        are inferred from those response keys; if the server rejects multipart
        we retry once with a JSON body (config switch message_body_format).
        """
        path = P.EP_CONVERSATION_MESSAGES.format(cid=conversation_id)
        nonce = nonce or str(uuid.uuid4())

        if self._msg_format == P.MESSAGE_BODY_FORMAT_MULTIPART:
            form = aiohttp.FormData()
            # content_type forces multipart encoding — the captured browser
            # request was multipart/form-data (aiohttp would otherwise
            # optimize text-only forms down to urlencoded)
            form.add_field("content", content, content_type="text/plain; charset=utf-8")
            form.add_field("nonce", nonce, content_type="text/plain; charset=utf-8")
            try:
                body = await self._request("POST", path, data=form)
            except ApiError as exc:
                if exc.status == 400 and self._msg_format == P.MESSAGE_BODY_FORMAT_MULTIPART:
                    log.warning("multipart rejected (400) — retrying once as JSON body")
                    self._msg_format = P.MESSAGE_BODY_FORMAT_JSON
                    body = await self._request("POST", path, json={"content": content, "nonce": nonce})
                else:
                    raise
        else:
            body = await self._request("POST", path, json={"content": content, "nonce": nonce})

        self.stats.messages_sent += 1
        return body if isinstance(body, dict) else {}

    # ------------------------------------------------------------ helpers

    @staticmethod
    def extract_partner(match_payload: dict, self_id: str) -> dict:
        """From a matchUpdate payload, return the partner profile dict."""
        conv = (match_payload.get("match") or {}).get("conversation") or {}
        for p in conv.get("participants", []):
            profile = p.get("profile") or {}
            if profile.get("id") and profile.get("id") != self_id:
                return profile
        return {}
