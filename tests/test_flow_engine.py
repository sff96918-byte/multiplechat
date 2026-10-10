"""Tests for the legacy EVA flow engine adapter (offline, no network)."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from eva.brain.flow_reply_engine import FlowReplyEngine


class TestFlowEngine(unittest.TestCase):
    def setUp(self):
        self.eng = FlowReplyEngine()
        self.p = {"id": "partner-1", "username": "Michael"}

    def test_opener_is_greeting(self):
        out = self.eng.opener(self.p)
        self.assertTrue(out.strip())
        # opener answered the greeting pool -> funnel now waits for age/gender
        self.assertEqual(self.eng.stage(self.p["id"]), "WAIT_AGE_GENDER")

    def test_age_gender_reply(self):
        self.eng.opener(self.p)
        out = self.eng.reply(self.p, "m 21")
        self.assertTrue(out.strip())
        self.assertEqual(self.eng.stage(self.p["id"]), "WAIT_COUNTRY")

    def test_country_flow(self):
        self.eng.opener(self.p)
        self.eng.reply(self.p, "m 21")
        out = self.eng.reply(self.p, "usa")
        self.assertTrue(out.strip())
        self.assertIn(self.eng.stage(self.p["id"]), ("MIDDLE", "WAIT_COUNTRY"))

    def test_snap_share_sets_end(self):
        self.eng.opener(self.p)
        self.eng.reply(self.p, "m 21")
        self.eng.reply(self.p, "usa")
        self.eng.reply(self.p, "yes send")
        # positive answer -> eventually share snap -> END
        self.assertIn(self.eng.stage(self.p["id"]), ("END", "MIDDLE"))

    def test_reply_never_empty(self):
        self.eng.opener(self.p)
        for msg in ("lol", "what?", "", "ok cool", "hbu", "gtg"):
            self.assertTrue(self.eng.reply(self.p, msg).strip())

    def test_forget_clears_state(self):
        self.eng.opener(self.p)
        self.eng.forget(self.p["id"])
        self.assertIsNone(self.eng._states.get(self.p["id"]))

    def test_delay_humanlike(self):
        d1 = self.eng.delay_for("hi")
        d2 = self.eng.delay_for("hello there my friend how are you doing today")
        self.assertGreater(d2, d1)
        self.assertGreater(d1, 0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
