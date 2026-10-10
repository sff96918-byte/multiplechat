"""debugtools — masking, report export, ring buffers টেস্ট।"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eva.debugtools import export_debug_report, mask_secrets
from eva.transport.chitchat_socket import ChitchatSocket


def test_mask_secrets_masks_sensitive_keys():
    out = mask_secrets({"token": "eyJhbGciOiLongJwtHere", "name": "bob",
                        "cookies": {"token": "abc123", "other": "x"},
                        "api_secret": "topsecret", "note": "token in text is fine"})
    assert out["name"] == "bob"
    assert out["token"].endswith("MASKED") and not out["token"].endswith("JwtHere")
    assert out["cookies"].endswith("MASKED")   # cookie key দেখলেই পুরো dict মাস্ক
    assert out["api_secret"].endswith("MASKED")
    assert out["note"] == "token in text is fine"   # value-তে থাকলে কাটে না


def test_report_excludes_session_content(tmp_path):
    sess = tmp_path / "session.json"
    secret_value = "SUPERSECRETVALUE123"
    sess.write_text(json.dumps({"cookies": {"token": secret_value},
                                "user_agent": "UA"}), encoding="utf-8")
    sock = ChitchatSocket(cookies={"token": secret_value})
    sock.record_frame("OUT", json.dumps({"emit": ["ping", secret_value]}))
    rep = export_debug_report(tmp_path, config={"engine": "flow", "snap_usernames": ["a"]},
                              session_path=sess, stats={"matches": 3}, socket=sock,
                              log_tail=["12:00:00 INFO test line"])
    text = rep.read_text(encoding="utf-8")
    assert secret_value not in text, "SECRET LEAK রিপোর্টে!"
    assert "SUPERSECRET" not in text
    assert "DEBUG REPORT" in text
    assert '"engine": "flow"' in text
    assert "exists=True" in text and "has_token=True" in text
    assert "matches" in text and "OUT" in text
    assert "12:00:00 INFO test line" in text


def test_socket_ring_buffer_truncates_and_counts():
    s = ChitchatSocket(cookies={})
    big = "x" * 500
    s.record_frame("IN", big)
    fr = s.recent_frames()
    assert len(fr) == 1
    assert fr[0]["len"] == 500 and len(fr[0]["preview"]) == 180
    s.record_frame("OUT", "small")
    assert len(s.recent_frames()) == 2
    assert s.recent_frames()[-1]["dir"] == "OUT"


def test_engine_decision_buffers():
    from eva.brain.fixed_reply_engine import FixedReplyEngine
    eng = FixedReplyEngine(Path(__file__).parents[1] / "configs" / "fixed_script.example.txt")
    p = {"id": "p1"}
    eng.opener(p)
    eng.reply(p, "hii")
    decs = eng.decisions()
    assert len(decs) == 2 and decs[0]["out"]
    assert all(len(d["in"]) <= 60 and len(d["out"]) <= 60 for d in decs)


def test_flow_engine_decision_buffer():
    from eva.brain.flow_reply_engine import FlowReplyEngine
    eng = FlowReplyEngine()
    eng.opener({"id": "p1", "username": "Bob"})
    eng.reply({"id": "p1", "username": "Bob"}, "19 f")
    decs = eng.decisions()
    assert len(decs) == 2
    assert decs[1]["in"].startswith("19")
    assert decs[1]["stage"]
