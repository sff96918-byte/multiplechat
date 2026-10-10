"""Engine.IO v4 / Socket.IO v5 frame codec for chitchat.gg.

Everything here is derived from captured traffic (see protocol_manifest.json).
Pure functions, no I/O — fully unit-testable.

Frame grammar observed in captures:
  0{json}                      Engine.IO OPEN (server -> client handshake)
  2                            Engine.IO PING  (server -> client, EIO4 server-initiated)
  3                            Engine.IO PONG  (client -> server reply)
  40                           Socket.IO CONNECT (no payload)
  40{json}                     Socket.IO CONNECT with payload (client sends {"release": ...})
  40{json}                     Socket.IO CONNECT ack (server sends {"sid": ..., "pid": ...})
  42["event"]                  Socket.IO EVENT
  42["event",arg]              Socket.IO EVENT with one arg
  41                           Socket.IO DISCONNECT (server closes namespace)
  44{json}                     Socket.IO CONNECT_ERROR
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, List, Optional


class CodecError(ValueError):
    """Raised when a frame cannot be parsed."""


# Engine.IO packet types (EIO=4)
EIO_OPEN = "0"
EIO_PING = "2"
EIO_PONG = "3"
EIO_MESSAGE = "4"

# Socket.IO packet types (attached after "4")
SIO_CONNECT = "0"
SIO_DISCONNECT = "1"
SIO_EVENT = "2"
SIO_ACK = "3"
SIO_CONNECT_ERROR = "4"


@dataclass
class Frame:
    """Parsed protocol frame."""
    kind: str                 # "open" | "ping" | "pong" | "connect" | "disconnect" | "event" | "ack" | "connect_error" | "raw"
    event: Optional[str] = None
    args: List[Any] = field(default_factory=list)
    payload: Any = None       # raw json payload for open/connect/connect_error
    raw: str = ""

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        if self.kind == "event":
            return f"<Frame event={self.event!r} args={self.args!r}>"
        return f"<Frame {self.kind} payload={self.payload!r}>"


def decode(raw: str) -> Frame:
    """Decode one Engine.IO/Socket.IO text frame."""
    if not raw:
        raise CodecError("empty frame")

    eio = raw[0]

    if eio == EIO_OPEN:
        payload = None
        if len(raw) > 1:
            try:
                payload = json.loads(raw[1:])
            except json.JSONDecodeError as exc:
                raise CodecError(f"bad OPEN payload: {exc}") from exc
        return Frame(kind="open", payload=payload, raw=raw)

    if raw == EIO_PING:
        return Frame(kind="ping", raw=raw)

    if raw == EIO_PONG:
        return Frame(kind="pong", raw=raw)

    if eio != EIO_MESSAGE:
        # Unknown engine.io type — surface it, don't crash the connection.
        return Frame(kind="raw", raw=raw)

    sio = raw[1] if len(raw) > 1 else ""
    rest = raw[2:]

    if sio == SIO_CONNECT:
        payload = None
        if rest:
            try:
                payload = json.loads(rest)
            except json.JSONDecodeError as exc:
                raise CodecError(f"bad CONNECT payload: {exc}") from exc
        return Frame(kind="connect", payload=payload, raw=raw)

    if sio == SIO_DISCONNECT:
        return Frame(kind="disconnect", raw=raw)

    if sio == SIO_CONNECT_ERROR:
        payload = None
        if rest:
            try:
                payload = json.loads(rest)
            except json.JSONDecodeError:
                payload = rest
        return Frame(kind="connect_error", payload=payload, raw=raw)

    if sio in (SIO_EVENT, SIO_ACK):
        try:
            data = json.loads(rest)
        except json.JSONDecodeError as exc:
            raise CodecError(f"bad EVENT payload: {exc} :: {raw[:120]}") from exc
        if not isinstance(data, list) or not data or not isinstance(data[0], str):
            raise CodecError(f"EVENT payload is not [name, ...]: {raw[:120]}")
        return Frame(kind="event" if sio == SIO_EVENT else "ack",
                     event=data[0], args=data[1:], raw=raw)

    return Frame(kind="raw", raw=raw)


def encode_connect(payload: Optional[dict] = None) -> str:
    """Client -> server namespace CONNECT: 40 or 40{json}."""
    if payload:
        return f"40{json.dumps(payload, separators=(',', ':'))}"
    return "40"


def encode_event(event: str, *args: Any) -> str:
    """Client -> server EVENT: 42["name",arg...]."""
    data: List[Any] = [event]
    data.extend(args)
    return "42" + json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def encode_pong() -> str:
    return EIO_PONG


def parse_handshake(frame: Frame) -> dict:
    """Extract and validate handshake fields from an OPEN frame."""
    payload = frame.payload or {}
    return {
        "sid": payload.get("sid", ""),
        "upgrades": payload.get("upgrades", []),
        "ping_interval_ms": int(payload.get("pingInterval", 25000)),
        "ping_timeout_ms": int(payload.get("pingTimeout", 20000)),
        "max_payload": int(payload.get("maxPayload", 1000000)),
    }
