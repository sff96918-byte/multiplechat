"""test_rules_characterization.py — pins CURRENT behaviour of chat/rules.py (v26).

Purpose: a safety net before any refactor of the CRITICAL chat engine.
It checks contracts and invariants, not exact reply wording (replies are
random pools). It does NOT change any behaviour and does NOT judge reply
content quality.

Not a contract: same seed -> same replies. Reply cursors are persisted in
data/.*.idx (round-robin), so output differs across runs by design.

    python test_rules_characterization.py
"""
import os
import random
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from chat import rules as R  # noqa: E402

passed = failed = 0


def ok(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {extra}")


# 1) helper contracts -------------------------------------------------------
POSITIVE = {"yes": True, "yeah sure": True, "ok": True,
            "no": False, "nah": False, "hi": False, "": False, "   ": False}
for text, want in POSITIVE.items():
    ok(f"_is_positive({text!r}) is {want}", R._is_positive(text) is want)

QUESTION = {"what?": True, "how are you": True, "hi": False, "": False}
for text, want in QUESTION.items():
    ok(f"_is_question({text!r}) is {want}", R._is_question(text) is want)

COUNTRY = {"im from singapore": "singapore", "from india": "india",
           "i am in usa": "usa", "nothing": None, "": None}
for text, want in COUNTRY.items():
    ok(f"_country_from_text({text!r}) == {want!r}",
       R._country_from_text(text) == want,
       f"got {R._country_from_text(text)!r}")

toks = R._norm_tokens("hi, u r cute")
ok("_norm_tokens expands slang (u->you, r->are)",
   toks == ["hi", "you", "are", "cute"], str(toks))
ok("_norm_text lowercases and collapses spaces",
   R._norm_text("  Hi!!  U   ") == "hi you", repr(R._norm_text("  Hi!!  U   ")))

# 2) init_conversation shape ------------------------------------------------
random.seed(1)
engine = R.RuleEngine()
state = engine.init_conversation()
REQUIRED = {
    "conv_id", "message_count", "user_messages", "bot_messages",
    "snap_pivoted", "snap_hint_sent", "snap_intro_sent", "asked_snap",
    "snap_nudge_sent", "pending_scshare", "blocked", "pending_replies",
    "user_gender", "user_age", "age_revealed", "user_country",
    "country_rotator", "user_facts", "style_profile", "sequence_step",
    "flow_type", "horny_detected", "awaiting_answer", "last_bot_question",
    "age_asked", "country_asked", "gender_asked", "identity_answers",
    "io_used", "recent_flirty", "recent_acks", "agreement_streak",
    "react_count", "flirty_state", "greeting_done", "stage", "route",
    "country_replied",
}
missing = REQUIRED - set(state)
ok("init_conversation has all required keys", not missing, str(sorted(missing)))
ok("fresh conversation starts at GREETING", state["flirty_state"] == "GREETING")
ok("fresh conversation has message_count 0", state["message_count"] == 0)
ok("fresh conversation is not blocked", state["blocked"] is False)
ok("fresh conversation has no snap flags set",
   not any(state[k] for k in ("snap_pivoted", "asked_snap",
                              "snap_intro_sent", "pending_scshare")))

# 3) decide_reply contract --------------------------------------------------
INPUTS = ["hi", "hello", "how old are u", "im 22", "where r u from",
          "what is ur name", "im from singapore", "do u play basketball?",
          "bye", "asdf qwer", "yes", "no", "are u a bot", "what snap"]
random.seed(2)
engine = R.RuleEngine()
state = engine.init_conversation()
contract_ok = True
count_ok = True
aw_ok = True
for i, msg in enumerate(INPUTS, start=1):
    reply = engine.decide_reply(msg, state)
    if not (isinstance(reply, str) and reply.strip()):
        contract_ok = False
    if state["message_count"] != i:
        count_ok = False
    if state["awaiting_answer"] != R._is_question(reply):
        aw_ok = False
ok("decide_reply always returns a non-empty string", contract_ok)
ok("message_count increases by 1 per decide_reply", count_ok,
   f"final={state['message_count']}")
ok("awaiting_answer == _is_question(last reply)", aw_ok)
ok("no snap pivot in the first 14 messages of an ordinary chat",
   state["snap_pivoted"] is False and state["asked_snap"] is False)

# 4) edge inputs never crash ------------------------------------------------
EDGE = ["", "   ", "\t\n", "😀😀", "হ্যালো কেমন আছো", "x" * 2000, "im horny",
        "send me a pic", "??!!"]
random.seed(3)
engine = R.RuleEngine()
state = engine.init_conversation()
edge_ok = True
for msg in EDGE:
    try:
        r = engine.decide_reply(msg, state)
        edge_ok = edge_ok and isinstance(r, str) and bool(r.strip())
    except Exception as e:  # noqa: BLE001 - we want to report any crash
        edge_ok = False
        print(f"        crash on {msg[:20]!r}: {type(e).__name__}: {e}")
ok("edge inputs (empty, emoji, Bengali, 2000 chars, horny) do not crash",
   edge_ok)

# 5) blocked / END states still return a reply ------------------------------
random.seed(4)
engine = R.RuleEngine()
state = engine.init_conversation()
state["blocked"] = True
r = engine.decide_reply("hello", state)
ok("blocked conversation still returns a non-empty reply",
   isinstance(r, str) and bool(r.strip()))

random.seed(5)
engine = R.RuleEngine()
state = engine.init_conversation()
state["flirty_state"] = "END"
r = engine.decide_reply("hello", state)
ok("END state still returns a non-empty reply",
   isinstance(r, str) and bool(r.strip()))

# 6) long random soak, fixed seed -------------------------------------------
random.seed(7)
pool_rng = random.Random(7)
POOL = INPUTS + EDGE + ["ok", "lol", "ur cute", "tell me more", "u?"]
engine = R.RuleEngine()
state = engine.init_conversation()
soak_ok = True
for _ in range(300):
    msg = pool_rng.choice(POOL)
    try:
        r = engine.decide_reply(msg, state)
        if not (isinstance(r, str) and r.strip()):
            soak_ok = False
    except Exception as e:  # noqa: BLE001
        soak_ok = False
        print(f"        soak crash: {type(e).__name__}: {e}")
        break
ok("300 random messages keep the engine healthy", soak_ok)
ok("soak ends with a valid flirty_state",
   isinstance(state["flirty_state"], str) and bool(state["flirty_state"]))

print(f"\nRESULT: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
