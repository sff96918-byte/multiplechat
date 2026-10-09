"""Unit tests for the capture-derived protocol pieces (fully offline)."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eva.transport import socketio_codec as codec
from eva.replies import Persona, ReplyEngine
from eva.transport.chitchat_api import ChitchatApi

FIXTURES = json.loads((ROOT / "tests" / "fixtures" / "captured_frames.json").read_text())


class TestCodec(unittest.TestCase):
    def test_decode_captured_handshake(self):
        f = codec.decode(FIXTURES["handshake"])
        self.assertEqual(f.kind, "open")
        hs = codec.parse_handshake(f)
        self.assertEqual(hs["sid"], "9Z_Qg1JCiaoEsGlaAE8v")
        self.assertEqual(hs["ping_interval_ms"], 25000)
        self.assertEqual(hs["ping_timeout_ms"], 20000)
        self.assertEqual(hs["max_payload"], 1000000)

    def test_decode_captured_connect_ack(self):
        f = codec.decode(FIXTURES["connect_ack"])
        self.assertEqual(f.kind, "connect")
        self.assertIn("pid", f.payload)

    def test_decode_event(self):
        f = codec.decode('42["typing",{"userId":"u1","conversationId":"c1"}]')
        self.assertEqual(f.kind, "event")
        self.assertEqual(f.event, "typing")
        self.assertEqual(f.args[0]["userId"], "u1")

    def test_decode_ping_pong_disconnect(self):
        self.assertEqual(codec.decode("2").kind, "ping")
        self.assertEqual(codec.decode("3").kind, "pong")
        self.assertEqual(codec.decode("41").kind, "disconnect")
        self.assertEqual(codec.decode('44{"message":"bad"}').kind, "connect_error")

    def test_encode_connect_with_release(self):
        out = codec.encode_connect({"release": "abc"})
        self.assertEqual(out, '40{"release":"abc"}')

    def test_encode_event_matches_wire_format(self):
        out = codec.encode_event("presenceSync")
        self.assertEqual(out, '42["presenceSync"]')
        out2 = codec.encode_event("typing", {"a": 1})
        self.assertEqual(out2, '42["typing",{"a":1}]')

    def test_roundtrip_real_event(self):
        raw = '42["matchUpdate",{"match":{"closure":{"closed":false}},"inQueue":false}]'
        f = codec.decode(raw)
        self.assertEqual(f.event, "matchUpdate")
        self.assertFalse(f.args[0]["match"]["closure"]["closed"])


class TestReplyEngine(unittest.TestCase):
    def setUp(self):
        self.eng = ReplyEngine(persona=Persona(name="Alex", age=24, gender="m"))
        self.partner = {"id": "123", "username": "Michael"}

    def test_m_or_f(self):
        out = self.eng.reply(self.partner, "M or F")
        self.assertIn("m", out)

    def test_age(self):
        out = self.eng.reply(self.partner, "age?")
        self.assertIn("24", out)

    def test_reply_never_empty(self):
        for text in ("hi", "wanna talk?", "ok boomer", "", "🤔"):
            self.assertTrue(self.eng.reply(self.partner, text))

    def test_delay_scales_with_length(self):
        self.assertLess(self.eng.delay_for("hi"), self.eng.delay_for("hello there how are you doing today"))


class TestPartnerExtraction(unittest.TestCase):
    def test_partner_from_captured_match(self):
        match_payload = {
            "match": {
                "conversation": {
                    "participants": [
                        {"profile": {"id": "685150d89c39b50899dbbfc6", "username": "Michael"}},
                        {"profile": {"id": "6a9257898ac97f8d3c432262", "username": "rheumatic rifleman"}},
                    ]
                }
            }
        }
        partner = ChitchatApi.extract_partner(match_payload, "6a9257898ac97f8d3c432262")
        self.assertEqual(partner["username"], "Michael")


if __name__ == "__main__":
    unittest.main(verbosity=2)
