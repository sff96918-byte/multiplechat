# -*- coding: utf-8 -*-
"""
State Machine Reply Engine — follows the conversation flow map.

STAGES:
  1. GREETING      → user says "hi"       → reply greeting.txt      → AGE_GENDER
  2. AGE_GENDER    → user says "m21"      → reply agegender.txt     → COUNTRY
  3. COUNTRY       → user says "from?"    → reply country.txt       → COUNTRY_REPLY
  4. COUNTRY_REPLY → user says "usa"      → reply flirty_questions  → MIDDLE_CHAT
  5. MIDDLE_CHAT   → detect 3 paths:
       PATH A (HORNY)  → horny.txt         → ASK_SNAP
       PATH B (FLIRTY) → flirty_reply.txt  → ASK_SNAP
       PATH C (NORMAL) → normal.txt        → ASK_SNAP
       Sub: horny_question → horny_answer + horny → ASK_SNAP
       Sub: how_are_you    → how_are_you.txt      → stay
       Sub: warm           → warm_reply.txt       → stay
       Sub: busy           → busy_later.txt       → stay
  6. ASK_SNAP      → bot sends ask_snap.txt (auto after path reply)
  7. SHARE_SNAP    → user says anything   → share_snap.txt (%username%) → END
  8. END           → disconnect, find new user

Data files:
  data_dir/input/   — detection triggers (what user says)
  data_dir/output/  — reply templates (what bot sends)
"""
import os
import random
import logging

logger = logging.getLogger("reply_engine")

GREETING = "GREETING"
AGE_GENDER = "AGE_GENDER"
COUNTRY = "COUNTRY"
COUNTRY_REPLY = "COUNTRY_REPLY"
MIDDLE_CHAT = "MIDDLE_CHAT"
SHARE_SNAP = "SHARE_SNAP"
END = "END"

MAX_MIDDLE_CHAT_LOOPS = 8


class ReplyEngine:
    def __init__(self, data_dir=None, snap_username="username", snap_after_n=3, **kwargs):
        self.snap_username = snap_username
        self.snap_after_n = snap_after_n
        self.data_dir = data_dir
        self.inputs = {}
        self.outputs = {}
        self.conv_state = {}
        self.conv_used = {}
        self.conv_msg_count = {}
        self.conv_middle_count = {}
        self._load_data()

    # ═══ Data Loading ═══
    def _load_data(self):
        if not self.data_dir or not os.path.isdir(self.data_dir):
            logger.error(f"Data dir not found: {self.data_dir}")
            return

        inp = os.path.join(self.data_dir, "input")
        out = os.path.join(self.data_dir, "output")

        self._load_input(inp, "greeting.txt", "greeting")
        self._load_input(inp, "age_gender.txt", "age_gender")
        self._load_input(inp, "country.txt", "country")
        self._load_input(inp, "horny.txt", "horny")
        self._load_input(inp, "horny_answer.txt", "horny_question")
        self._load_input(inp, "how_are_you.txt", "how_are_you")
        self._load_input(inp, "share_snap.txt", "snap_positive")
        self._load_input(inp, "snapchat.txt", "user_snap")
        self._load_input(inp, "normal.txt", "normal")
        self._load_input(inp, os.path.join("middle_chat", "flirty_reply.txt"), "flirty")
        self._load_input(inp, os.path.join("middle_chat", "warm_reply.txt"), "warm")
        self._load_input(inp, os.path.join("middle_chat", "busy_later.txt"), "busy")

        self._load_output(out, "greeting.txt", "greeting")
        self._load_output(out, "age_gender.txt", "age_gender")
        self._load_output(out, "country.txt", "country")
        self._load_output(out, "flirty_questions.txt", "flirty_questions")
        self._load_output(out, "horny.txt", "horny")
        self._load_output(out, "horny_answer.txt", "horny_answer")
        self._load_output(out, "how_are_you.txt", "how_are_you")
        self._load_output(out, "ask_snap.txt", "ask_snap")
        self._load_output(out, "share_snap.txt", "share_snap")
        self._load_output(out, "snapchat.txt", "snapchat")
        self._load_output(out, "normal.txt", "normal")
        self._load_output(out, os.path.join("middle_chat", "flirty_reply.txt"), "flirty_reply")
        self._load_output(out, os.path.join("middle_chat", "warm_reply.txt"), "warm_reply")
        self._load_output(out, os.path.join("middle_chat", "busy_later.txt"), "busy_later")
        self._load_output(out, os.path.join("middle_chat", "new_topic.txt"), "new_topic")

        ti = sum(len(v) for v in self.inputs.values())
        to = sum(len(v) for v in self.outputs.values())
        logger.info(f"Loaded {ti} input triggers, {to} output replies from {self.data_dir}")

    def _load_input(self, base, relpath, category):
        path = os.path.join(base, relpath)
        if not os.path.isfile(path):
            logger.warning(f"Input file missing: {path}")
            return
        triggers = set()
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                triggers.add(line.lower())
        self.inputs[category] = list(triggers)
        logger.debug(f"  input/{category}: {len(triggers)} triggers")

    def _load_output(self, base, relpath, category):
        path = os.path.join(base, relpath)
        if not os.path.isfile(path):
            logger.warning(f"Output file missing: {path}")
            return
        replies = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                replies.append(line)
        self.outputs[category] = replies
        logger.debug(f"  output/{category}: {len(replies)} replies")

    # ═══ Public API ═══
    def reply(self, text, conversation_id=None, **kwargs):
        """Returns list of (message, category) tuples."""
        if conversation_id is None:
            conversation_id = "default"

        if conversation_id not in self.conv_state:
            self._init_conv(conversation_id)

        self.conv_msg_count[conversation_id] += 1
        state = self.conv_state[conversation_id]

        logger.info(f"reply() conv={conversation_id} state={state} msg#{self.conv_msg_count[conversation_id]} text={text[:60]}")

        if state == GREETING:
            return self._handle_greeting(text, conversation_id)
        elif state == AGE_GENDER:
            return self._handle_age_gender(text, conversation_id)
        elif state == COUNTRY:
            return self._handle_country(text, conversation_id)
        elif state == COUNTRY_REPLY:
            return self._handle_country_reply(text, conversation_id)
        elif state == MIDDLE_CHAT:
            return self._handle_middle_chat(text, conversation_id)
        elif state == SHARE_SNAP:
            return self._handle_share_snap(text, conversation_id)
        elif state == END:
            return [("...", "end")]
        return [("hey", "fallback")]

    def get_state(self, conversation_id):
        return self.conv_state.get(conversation_id, GREETING)

    def reset(self, conversation_id=None):
        if conversation_id is None:
            self.conv_state.clear()
            self.conv_used.clear()
            self.conv_msg_count.clear()
            self.conv_middle_count.clear()
        else:
            self.conv_state.pop(conversation_id, None)
            self.conv_used.pop(conversation_id, None)
            self.conv_msg_count.pop(conversation_id, None)
            self.conv_middle_count.pop(conversation_id, None)

    @property
    def template_count(self):
        return sum(len(v) for v in self.outputs.values())

    @property
    def category_count(self):
        return len(self.outputs)

    # ═══ State Handlers ═══
    def _handle_greeting(self, text, conv):
        if self._match(text, "greeting"):
            reply = self._pick("greeting", conv)
            self.conv_state[conv] = AGE_GENDER
            logger.info(f"  GREETING→AGE_GENDER: {reply[:50]}")
            return [(reply, "greeting")]
        if self._match(text, "age_gender"):
            reply = self._pick("age_gender", conv)
            self.conv_state[conv] = COUNTRY
            logger.info(f"  GREETING(skip)→COUNTRY: {reply[:50]}")
            return [(reply, "age_gender")]
        if self._match(text, "horny") or self._match(text, "horny_question"):
            return self._handle_middle_chat(text, conv)
        reply = self._pick("greeting", conv)
        self.conv_state[conv] = AGE_GENDER
        logger.info(f"  GREETING(default)→AGE_GENDER: {reply[:50]}")
        return [(reply, "greeting")]

    def _handle_age_gender(self, text, conv):
        if self._match(text, "age_gender"):
            reply = self._pick("age_gender", conv)
            self.conv_state[conv] = COUNTRY
            logger.info(f"  AGE_GENDER→COUNTRY: {reply[:50]}")
            return [(reply, "age_gender")]
        if self._match(text, "greeting"):
            reply = self._pick("greeting", conv)
            logger.info(f"  AGE_GENDER(greeting)→stay: {reply[:50]}")
            return [(reply, "greeting")]
        if self._match(text, "country"):
            reply = self._pick("country", conv)
            self.conv_state[conv] = COUNTRY_REPLY
            logger.info(f"  AGE_GENDER(skip)→COUNTRY_REPLY: {reply[:50]}")
            return [(reply, "country")]
        if self._match(text, "how_are_you"):
            reply = self._pick("how_are_you", conv)
            return [(reply, "how_are_you")]
        if self._match(text, "horny") or self._match(text, "horny_question"):
            return self._handle_middle_chat(text, conv)
        reply = self._pick("age_gender", conv)
        self.conv_state[conv] = COUNTRY
        logger.info(f"  AGE_GENDER(default)→COUNTRY: {reply[:50]}")
        return [(reply, "age_gender")]

    def _handle_country(self, text, conv):
        if self._match(text, "country"):
            reply = self._pick("country", conv)
            self.conv_state[conv] = COUNTRY_REPLY
            logger.info(f"  COUNTRY→COUNTRY_REPLY: {reply[:50]}")
            return [(reply, "country")]
        if self._match(text, "greeting"):
            reply = self._pick("greeting", conv)
            return [(reply, "greeting")]
        if self._match(text, "age_gender"):
            reply = self._pick("age_gender", conv)
            return [(reply, "age_gender")]
        if self._match(text, "how_are_you"):
            reply = self._pick("how_are_you", conv)
            return [(reply, "how_are_you")]
        reply = self._pick("country", conv)
        self.conv_state[conv] = COUNTRY_REPLY
        logger.info(f"  COUNTRY(default)→COUNTRY_REPLY: {reply[:50]}")
        return [(reply, "country")]

    def _handle_country_reply(self, text, conv):
        reply = self._pick("flirty_questions", conv)
        self.conv_state[conv] = MIDDLE_CHAT
        self.conv_middle_count[conv] = 0
        logger.info(f"  COUNTRY_REPLY→MIDDLE_CHAT: {reply[:50]}")
        return [(reply, "flirty_questions")]

    def _handle_middle_chat(self, text, conv):
        self.conv_middle_count[conv] = self.conv_middle_count.get(conv, 0) + 1
        mc = self.conv_middle_count[conv]

        if self._match(text, "snap_positive") or self._match(text, "user_snap"):
            reply = self._pick("share_snap", conv)
            self.conv_state[conv] = END
            logger.info(f"  MIDDLE_CHAT(snap direct)→END: {reply[:50]}")
            return [(reply, "share_snap")]

        if self._match(text, "horny_question"):
            r1 = self._pick("horny_answer", conv)
            r2 = self._pick("horny", conv)
            ask = self._pick("ask_snap", conv)
            self.conv_state[conv] = SHARE_SNAP
            logger.info(f"  MIDDLE_CHAT(horny_q)→SHARE_SNAP: 3 msgs")
            return [(r1, "horny_answer"), (r2, "horny"), (ask, "ask_snap")]

        if self._match(text, "horny"):
            reply = self._pick("horny", conv)
            ask = self._pick("ask_snap", conv)
            self.conv_state[conv] = SHARE_SNAP
            logger.info(f"  MIDDLE_CHAT(horny)→SHARE_SNAP: {reply[:50]}")
            return [(reply, "horny"), (ask, "ask_snap")]

        if self._match(text, "flirty"):
            reply = self._pick("flirty_reply", conv)
            ask = self._pick("ask_snap", conv)
            self.conv_state[conv] = SHARE_SNAP
            logger.info(f"  MIDDLE_CHAT(flirty)→SHARE_SNAP: {reply[:50]}")
            return [(reply, "flirty"), (ask, "ask_snap")]

        if self._match(text, "how_are_you"):
            reply = self._pick("how_are_you", conv)
            logger.info(f"  MIDDLE_CHAT(how_are_you)→stay: {reply[:50]}")
            return [(reply, "how_are_you")]

        if self._match(text, "busy"):
            reply = self._pick("busy_later", conv)
            logger.info(f"  MIDDLE_CHAT(busy)→stay: {reply[:50]}")
            return [(reply, "busy")]

        if self._match(text, "warm") and mc < MAX_MIDDLE_CHAT_LOOPS:
            reply = self._pick("warm_reply", conv)
            logger.info(f"  MIDDLE_CHAT(warm)→stay: {reply[:50]}")
            return [(reply, "warm")]

        if self._match(text, "normal") and mc < MAX_MIDDLE_CHAT_LOOPS:
            reply = self._pick("normal", conv)
            logger.info(f"  MIDDLE_CHAT(normal)→stay: {reply[:50]}")
            return [(reply, "normal")]

        if mc >= MAX_MIDDLE_CHAT_LOOPS:
            reply = self._pick("normal", conv)
            ask = self._pick("ask_snap", conv)
            self.conv_state[conv] = SHARE_SNAP
            logger.info(f"  MIDDLE_CHAT(max_loops)→SHARE_SNAP: {reply[:50]}")
            return [(reply, "normal"), (ask, "ask_snap")]

        reply = self._pick("normal", conv)
        ask = self._pick("ask_snap", conv)
        self.conv_state[conv] = SHARE_SNAP
        logger.info(f"  MIDDLE_CHAT(default)→SHARE_SNAP: {reply[:50]}")
        return [(reply, "normal"), (ask, "ask_snap")]

    def _handle_share_snap(self, text, conv):
        reply = self._pick("share_snap", conv)
        self.conv_state[conv] = END
        logger.info(f"  SHARE_SNAP→END: {reply[:50]}")
        return [(reply, "share_snap")]

    # ═══ Detection ═══
    def _match(self, text, category):
        triggers = self.inputs.get(category)
        if not triggers:
            return False
        low = text.lower().strip()
        if not low:
            return False
        if low in triggers:
            return True
        words = set(low.split())
        for t in triggers:
            if len(t) <= 3:
                if t in words or t == low:
                    continue
            elif t in low:
                return True
        for t in triggers:
            if len(t) <= 3 and t in words:
                return True
        return False

    def _pick(self, category, conv):
        replies = self.outputs.get(category)
        if not replies:
            return "..."
        used = self.conv_used.get(conv, set())
        available = [r for r in replies if r not in used]
        if not available:
            available = replies
        reply = random.choice(available)
        used.add(reply)
        self.conv_used[conv] = used
        return self._fill(reply)

    def _fill(self, text):
        return text.replace("%username%", self.snap_username)

    def _init_conv(self, conv):
        self.conv_state[conv] = GREETING
        self.conv_used[conv] = set()
        self.conv_msg_count[conv] = 0
        self.conv_middle_count[conv] = 0