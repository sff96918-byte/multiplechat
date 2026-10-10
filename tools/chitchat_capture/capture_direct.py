#!/usr/bin/env python3
"""
ChitChat.gg DIRECT capture tool (Playwright).

Chrome window নিজেই খুলবে। আপনি login করে নিজে chat করবেন।
এই tool নিজে থেকে সব কিছু save করবে:

  * HTTP request / response (fetch/xhr body সহ, token ও email masked)
  * WebSocket frame (socket.io event নামসহ)
  * Chat DOM snapshot + bot যে selector ব্যবহার করে তার health
  * UI event: Enter চাপা, button click (কোন action এর পর কোন request গেল, মেলানোর জন্য)
  * নতুন partner message এলে screenshot

Output (capture_out/session_<time>/):
  events.jsonl      সব event, পূর্ণ text সহ  -> LOCAL ONLY, শেয়ার করবেন না
  dom/              DOM snapshot (.json + .html)  -> LOCAL ONLY
  screens/          screenshot                    -> LOCAL ONLY
  browser_profile/  login session (cookie)        -> LOCAL ONLY, কখনো শেয়ার করবেন না
  summary.json      সংক্ষিপ্ত সারাংশ (masked)
  REPORT.md         মানুষের পড়ার রিপোর্ট (masked)
  share_bundle.json শেয়ার করার ফাইল (message text ও username masked, token redacted)

Usage:
  python capture_direct.py                       # default URL, unlimited (quit লিখে বন্ধ করুন)
  python capture_direct.py --minutes 30          # ৩০ মিনিট পর নিজে বন্ধ
  python capture_direct.py --url https://app.chitchat.gg/text
  python capture_direct.py --selftest            # browser ছাড়া নিজের লজিক যাচাই

Terminal command (চলাকালীন):
  note <text>   একটা annotation লিখবে, যেমন: note skip চাপলাম
  shot          এখনকার screenshot
  quit          capture শেষ করে রিপোর্ট লিখবে (অথবা browser বন্ধ করুন)
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import queue
import re
import sys
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

HERE = Path(__file__).resolve().parent
DEFAULT_URL = "https://app.chitchat.gg/start/new"
PROFILE_DIR = HERE / "browser_profile"
OUT_ROOT = HERE / "capture_out"
TARGET_HOST = "chitchat.gg"

MAX_BODY = 200_000          # bytes; এর বেশি body শুধু head রাখা হবে
MAX_SCREENS = 200
MAX_DOM_SNAPSHOTS = 400
BUNDLE_OUTLINE_SNAPS = 12   # bundle-এ কতগুলো DOM outline যাবে

# ---------------------------------------------------------------- redaction
SECRET_KEY_RE = re.compile(
    r"(token|passw|pwd|secret|session|cookie|jwt|email|phone|ipaddr|ip_address|"
    r"birth|api[_-]?key|csrf|otp|authorization)", re.I)
JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
SENSITIVE_HEADERS = {"cookie", "set-cookie", "authorization", "proxy-authorization",
                     "x-csrf-token", "x-xsrf-token"}
# bundle-এ এই key-গুলোর value মুছে শুধু length যাবে (structure থাকবে)
TEXT_KEYS = {"text", "content", "message", "body", "username", "displayname",
             "display_name", "nickname", "name", "username_text", "own_text_sample"}


def redact_text(s: str) -> str:
    s = JWT_RE.sub("<JWT>", s)
    return EMAIL_RE.sub("<EMAIL>", s)


def redact_value(key, v):
    if key is not None and SECRET_KEY_RE.search(str(key)) and v not in (None, "", [], {}):
        return f"<redacted:{type(v).__name__}>"
    if isinstance(v, dict):
        return {k: redact_value(k, x) for k, x in v.items()}
    if isinstance(v, list):
        return [redact_value(None, x) for x in v]
    if isinstance(v, str):
        return redact_text(v)
    return v


def redact_headers(h) -> dict:
    out = {}
    for k, v in dict(h or {}).items():
        if k.lower() in SENSITIVE_HEADERS:
            if k.lower() == "cookie":
                names = [c.split("=", 1)[0].strip() for c in str(v).split(";") if c.strip()]
                out[k] = {"cookie_names": names}
            else:
                out[k] = f"<redacted len={len(str(v))}>"
        else:
            out[k] = redact_text(str(v))
    return out


def redact_url(u: str) -> str:
    p = urlsplit(u)
    q = [(k, "REDACTED" if SECRET_KEY_RE.search(k) else v)
         for k, v in parse_qsl(p.query, keep_blank_values=True)]
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), ""))


def mask_for_share(o, keep_text: bool = False, key=None):
    """Bundle-এর জন্য: text-like value মুছে শুধু length রাখা (keep_text=False হলে)।"""
    if isinstance(o, dict):
        return {k: mask_for_share(v, keep_text, k) for k, v in o.items()}
    if isinstance(o, list):
        return [mask_for_share(x, keep_text, key) for x in o]
    if isinstance(o, str) and not keep_text and key is not None and str(key).lower() in TEXT_KEYS:
        return f"<text len={len(o)}>"
    return o


def shape(o, depth: int = 0):
    """Value বাদ দিয়ে শুধু structure (key + type)।"""
    if depth > 6:
        return "..."
    if isinstance(o, dict):
        return {k: shape(v, depth + 1) for k, v in list(o.items())[:60]}
    if isinstance(o, list):
        return [shape(o[0], depth + 1)] if o else []
    if isinstance(o, bool):
        return "bool"
    if isinstance(o, int):
        return "int"
    if isinstance(o, float):
        return "float"
    if o is None:
        return "null"
    if isinstance(o, str):
        return "str"
    return type(o).__name__


ID_RE = re.compile(r"/[0-9a-f]{24}|/[0-9a-f]{8}-[0-9a-f-]{27}|/\d+", re.I)


def norm_path(url: str) -> str:
    return ID_RE.sub("/{id}", urlsplit(url).path)


def parse_body(raw: bytes | None, ctype: str):
    if not raw:
        return None
    if len(raw) > MAX_BODY:
        return {"_truncated": True, "_size": len(raw),
                "_head": redact_text(raw[:1500].decode("utf-8", "replace"))}
    text = raw.decode("utf-8", "replace")
    if "json" in (ctype or "") or text[:1] in ("{", "["):
        try:
            return redact_obj(json.loads(text))
        except ValueError:
            pass
    if "multipart" in (ctype or ""):
        return {"_multipart_raw": redact_text(text[:4000])}
    return redact_text(text[:4000])


def parse_multipart(raw: bytes | None, ctype: str):
    """multipart/form-data body -> list of parts (names, types, sizes).

    Text fields keep their value (mask_for_share hides it unless --keep-text),
    file parts keep only name/type/size. Needed to learn the exact field names
    of e.g. POST …/messages without guessing.
    """
    if not raw or "multipart" not in (ctype or ""):
        return None
    m = re.search(r'boundary=("?)([^";]+)\1', ctype)
    if not m:
        return None
    boundary = b"--" + m.group(2).strip().encode("utf-8", "replace")
    parts = []
    for chunk in raw.split(boundary):
        if chunk[:2] == b"--" or not chunk.strip():
            continue
        chunk = chunk[2:] if chunk.startswith(b"\r\n") else chunk
        head, sep, body = chunk.partition(b"\r\n\r\n")
        if not sep:
            continue
        body = body[:-2] if body.endswith(b"\r\n") else body
        headers = head.decode("utf-8", "replace")
        name = re.search(r'name="([^"]*)"', headers)
        fname = re.search(r'filename="([^"]*)"', headers)
        ptype = re.search(r"Content-Type:\s*([^\r\n]+)", headers, re.I)
        entry = {"name": name.group(1) if name else None,
                 "content_type": ptype.group(1).strip() if ptype else None}
        if fname:
            entry.update({"filename": "<file>", "size": len(body)})
        else:
            text_val = body.decode("utf-8", "replace")
            # text-like field names use key "text" so mask_for_share hides them by default
            key = "text" if (name and name.group(1) in TEXT_KEYS) else "value"
            entry.update({"value_len": len(body), key: text_val})
        parts.append(entry)
    return parts


def redact_obj(o):
    return redact_value(None, o)


def parse_socketio(payload: str):
    """socket.io packet: '42["event", {...}]' -> (event_name, data)."""
    m = re.match(r"^(\d+)(\[.*)$", payload, re.S)
    if not m:
        return None, None
    try:
        arr = json.loads(m.group(2))
    except ValueError:
        return None, None
    if isinstance(arr, list) and arr and isinstance(arr[0], str):
        return arr[0], arr[1] if len(arr) > 1 else None
    return None, None


# ---------------------------------------------------------------- in-page JS
SNAP_JS = r"""
() => {
  const txt = (el) => (el && el.textContent ? el.textContent.trim() : '');
  const cls = (el) => (el && typeof el.className === 'string' ? el.className : '');
  const vis = (el) => {
    const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const out = { url: location.href, title: document.title };

  const SEL = {
    main_ol: 'main ol',
    msg_li_select_text: 'main ol li.select-text',
    username_span: 'span.font-bold[role="button"]',
    msg_span_emoji: 'span.emoji-content',
    textarea_name_message: 'textarea[name="message"]',
    textarea_placeholder_message: 'textarea[placeholder*="message" i]',
    input_text: 'input[type="text"]',
    textarea_any: 'textarea',
    sidebar_truncate_user: 'button .truncate.text-sm.font-bold',
    sidebar_bg_panel_user: '.bg-panel button span.truncate',
  };
  out.selectors = {};
  for (const [k, s] of Object.entries(SEL)) {
    try {
      const els = document.querySelectorAll(s);
      out.selectors[k] = { count: els.length, visible: [...els].filter(vis).length,
                           sample_len: els.length ? txt(els[0]).length : 0 };
    } catch (e) { out.selectors[k] = { error: String(e).slice(0, 80) }; }
  }

  // আমার username (bot যেভাবে খোঁজে সেভাবে)
  const me = {};
  const ub = document.querySelector('button .truncate.text-sm.font-bold');
  if (ub) me.sidebar_truncate = txt(ub);
  const up = document.querySelector('.bg-panel button span.truncate');
  if (up) me.bg_panel = txt(up);
  const ps = document.querySelector('span[alt][username]');
  if (ps && ps.closest('.bg-panel')) me.profile_attr = ps.getAttribute('username');
  out.me = me;

  const main_ol = document.querySelector('main ol');
  const items = main_ol ? [...main_ol.querySelectorAll('li')] : [];
  out.message_items_total = items.length;
  out.messages = items.slice(-80).map((li) => {
    const u = li.querySelector('span.font-bold[role="button"]');
    const m = li.querySelector('span.emoji-content');
    return {
      li_cls: cls(li).slice(0, 160),
      has_select_text: li.classList.contains('select-text'),
      username: txt(u),
      text: txt(m),
      has_text_span: !!m,
      child_tags: [...li.children].slice(0, 6).map((c) => c.tagName.toLowerCase() +
        (cls(c) ? '.' + cls(c).split(/\s+/).slice(0, 2).join('.') : '')),
    };
  });

  out.inputs = [...document.querySelectorAll('textarea, input[type="text"]')].slice(0, 12).map((el) => ({
    tag: el.tagName.toLowerCase(), name: el.getAttribute('name'),
    placeholder: el.getAttribute('placeholder'), disabled: !!el.disabled,
    visible: vis(el), cls: cls(el).slice(0, 140),
  }));

  out.buttons = [...document.querySelectorAll('button')].filter(vis).slice(0, 40).map((b) => ({
    text: txt(b).slice(0, 30), cls: cls(b).slice(0, 180), aria: b.getAttribute('aria-label'),
  }));

  const body = document.body ? (document.body.innerText || document.body.textContent || '') : '';
  const low = body.toLowerCase();
  out.disconnect_markers_found = ['has skipped this chat', 'partner has left',
    'chat has ended', 'disconnected'].filter((m) => low.includes(m));
  out.body_text_len = body.length;

  // structure-only outline (কোনো text নেই) + পূর্ণ html (local)
  const root = main_ol ? (main_ol.parentElement || main_ol) : (document.querySelector('main') || document.body);
  const outline = (el, d) => {
    if (!el || d > 7) return null;
    const n = { t: el.tagName.toLowerCase() };
    const c = cls(el).split(/\s+/).filter(Boolean).slice(0, 4);
    if (c.length) n.c = c.join(' ');
    const role = el.getAttribute('role'); if (role) n.role = role;
    const nm = el.getAttribute('name'); if (nm) n.name = nm;
    const ph = el.getAttribute('placeholder'); if (ph) n.ph = ph.slice(0, 40);
    const own = [...el.childNodes].filter((x) => x.nodeType === 3).map((x) => x.textContent.trim()).join('').length;
    if (own) n.own_text_len = own;
    const kids = [...el.children];
    if (kids.length) {
      n.kids = kids.slice(0, 12).map((k) => outline(k, d + 1));
      if (kids.length > 12) n.more = kids.length - 12;
    }
    return n;
  };
  out.outline = outline(root, 0);

  const clone = root.cloneNode(true);
  clone.querySelectorAll('script,style,noscript,svg,img,video,source,iframe').forEach((n) => n.remove());
  clone.querySelectorAll('*').forEach((el) => {
    for (const a of [...el.attributes]) {
      if (a.name === 'src' || a.name === 'href' || a.name === 'srcset' || a.name.startsWith('on')) {
        el.removeAttribute(a.name);
      } else if (a.value.length > 120) {
        el.setAttribute(a.name, a.value.slice(0, 120));
      }
    }
  });
  out.html = clone.outerHTML.slice(0, 80000);
  return out;
}
"""

UI_INIT_JS = r"""
(() => {
  if (window.__capInstalled) return;
  window.__capInstalled = true;
  window.__capUi = [];
  const push = (o) => {
    if (window.__capUi.length < 500) { o.t = Date.now(); window.__capUi.push(o); }
  };
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      const t = e.target || {};
      push({ type: 'enter', target_tag: t.tagName ? t.tagName.toLowerCase() : null,
             target_name: t.getAttribute ? t.getAttribute('name') : null,
             value_len: ((t.value || t.textContent || '') + '').length });
    }
  }, true);
  document.addEventListener('click', (e) => {
    const b = e.target && e.target.closest ? e.target.closest('button,a,[role="button"]') : null;
    if (b) push({ type: 'click', tag: b.tagName.toLowerCase(),
                  text: (b.textContent || '').trim().slice(0, 30), aria: b.getAttribute('aria-label') });
  }, true);
})();
"""

DRAIN_JS = "() => { const a = window.__capUi || []; window.__capUi = []; return a; }"

# ---------------------------------------------------------------- recorder
class Recorder:
    def __init__(self, out_dir: Path):
        self.dir = out_dir
        (self.dir / "dom").mkdir(parents=True, exist_ok=True)
        (self.dir / "screens").mkdir(parents=True, exist_ok=True)
        self.fh = open(self.dir / "events.jsonl", "a", encoding="utf-8")
        self.t0 = time.time()
        self.kinds = Counter()
        self.dom_n = 0
        self.screens_n = 0
        self.health = defaultdict(lambda: {"polls": 0, "hit": 0, "last_count": None})
        self.last_sig = None

    def event(self, kind: str, data) -> dict:
        now = time.time()
        rec = {"t": round(now, 3), "rel": round(now - self.t0, 3), "kind": kind,
               "data": redact_obj(data)}
        self.fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.fh.flush()
        self.kinds[kind] += 1
        return rec

    def dom_snapshot(self, snap: dict) -> bool:
        sig = json.dumps([snap.get("message_items_total"),
                          [m.get("text", "")[-30:] for m in snap.get("messages", [])[-3:]],
                          [b.get("text") for b in snap.get("buttons", [])],
                          snap.get("disconnect_markers_found")], ensure_ascii=False)
        for sel, info in (snap.get("selectors") or {}).items():
            h = self.health[sel]
            h["polls"] += 1
            c = info.get("count") if isinstance(info, dict) else None
            h["last_count"] = c
            if c:
                h["hit"] += 1
        if sig == self.last_sig or self.dom_n >= MAX_DOM_SNAPSHOTS:
            return False
        self.last_sig = sig
        self.dom_n += 1
        html = snap.pop("html", "")
        base = self.dir / "dom" / f"{self.dom_n:04d}"
        base.with_suffix(".json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        base.with_suffix(".html").write_text(redact_text(html), encoding="utf-8")   # token/email masked; chat text still local-only
        return True

    def screenshot_bytes_ok(self) -> bool:
        return self.screens_n < MAX_SCREENS

    def close(self):
        self.fh.close()


# ---------------------------------------------------------------- analysis
def load_events(path: Path) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


def analyse(events: list[dict], recorder_health: dict | None = None) -> dict:
    endpoints: dict = {}
    ws_counts = Counter()
    ws_shapes: dict = {}
    third_party = Counter()
    ui = []
    ws_partner_t = []
    http_out = []
    for ev in events:
        k, d = ev["kind"], ev["data"]
        if k == "http":
            key = f'{d.get("method")} {norm_path(d.get("url", ""))}'
            e = endpoints.setdefault(key, {"count": 0, "statuses": Counter(),
                                           "req_shape": None, "res_shape": None,
                                           "req_headers_names": None})
            e["count"] += 1
            e["statuses"][str(d.get("status"))] += 1
            if e["req_shape"] is None and d.get("req_json") is not None:
                e["req_shape"] = shape(d["req_json"])
            if e["res_shape"] is None and d.get("res_json") is not None:
                e["res_shape"] = shape(d["res_json"])
            if e["req_headers_names"] is None:
                e["req_headers_names"] = sorted((d.get("req_headers") or {}).keys())
            http_out.append((ev["rel"], key, d.get("status")))
        elif k == "third_party":
            third_party[d.get("host", "?")] += 1
        elif k == "ws":
            name = d.get("event") or ("raw:" + str(d.get("dir")))
            ws_counts[f'{d.get("dir")}:{name}'] += 1
            if d.get("event") and d["event"] not in ws_shapes and d.get("data") is not None:
                ws_shapes[d["event"]] = shape(d["data"])
            if d.get("dir") == "in" and d.get("event") == "chatMessage":
                ws_partner_t.append(ev["rel"])
        elif k == "ui":
            ui.append((ev["rel"], d))

    # UI action -> next 4s এর HTTP request (কোন button/Enter কোন request আনে)
    ui_map = []
    for rel, d in ui:
        near = [f"{key} [{st}]" for (r, key, st) in http_out if 0 <= r - rel <= 4][:6]
        ui_map.append({"at": round(rel, 2), "ui": d, "next_http": near})

    # partner message -> প্রথম outgoing POST /messages-এর দেরি
    delays = []
    post_msgs = [r for (r, key, st) in http_out if "messages" in key and key.startswith("POST")]
    for t in ws_partner_t:
        nxt = [p for p in post_msgs if p > t]
        if nxt:
            delays.append(round((nxt[0] - t) * 1000))

    health_out = {}
    if recorder_health:
        for sel, h in recorder_health.items():
            rate = round(h["hit"] / h["polls"], 3) if h["polls"] else None
            health_out[sel] = {"hit_rate": rate, "last_count": h["last_count"],
                               "status": "OK" if rate and rate > 0 else "NOT FOUND"}

    return {
        "endpoints": {k: {"count": v["count"], "statuses": dict(v["statuses"]),
                          "request_shape": v["req_shape"], "response_shape": v["res_shape"],
                          "request_header_names": v["req_headers_names"]}
                      for k, v in sorted(endpoints.items(), key=lambda x: -x[1]["count"])},
        "websocket_counts": dict(ws_counts.most_common()),
        "websocket_event_shapes": ws_shapes,
        "third_party_hosts": dict(third_party.most_common(20)),
        "ui_actions": ui_map[:200],
        "partner_to_our_post_ms": delays[:200],
        "selector_health": health_out,
    }


def build_report(summary: dict, kinds: Counter, out_dir: Path) -> str:
    lines = ["# ChitChat capture report", "",
             f"Session: `{out_dir.name}`", "",
             "## Event counts", ""]
    for k, v in kinds.most_common():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Selector health (bot যে selector ব্যবহার করে)", "",
              "| selector | hit rate | last count | status |", "|---|---|---|---|"]
    for sel, h in summary["selector_health"].items():
        lines.append(f"| {sel} | {h['hit_rate']} | {h['last_count']} | {h['status']} |")
    lines += ["", "## HTTP endpoints", "", "| request | count | statuses |", "|---|---|---|"]
    for k, v in summary["endpoints"].items():
        lines.append(f"| `{k}` | {v['count']} | {v['statuses']} |")
    lines += ["", "## WebSocket events", ""]
    for k, v in summary["websocket_counts"].items():
        lines.append(f"- `{k}`: {v}")
    lines += ["", "## Partner message -> our send delay (ms)", "",
              f"{summary['partner_to_our_post_ms'][:30]}"]
    lines += ["", "## UI action -> next HTTP", ""]
    for u in summary["ui_actions"][:30]:
        lines.append(f"- t={u['at']} {u['ui']} -> {u['next_http'][:3]}")
    lines += ["", "> এই রিপোর্টে message text ও username masked। পূর্ণ data শুধু local events.jsonl-এ।", ""]
    return "\n".join(lines)


def build_bundle(events: list[dict], summary: dict, out_dir: Path, keep_text: bool) -> dict:
    dom_items = []
    dom_files = sorted((out_dir / "dom").glob("*.json"))
    picks = dom_files[:2] + dom_files[-(BUNDLE_OUTLINE_SNAPS - 2):] if len(dom_files) > BUNDLE_OUTLINE_SNAPS else dom_files
    for p in picks:
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        dom_items.append({"file": p.name,
                          "url_path": urlsplit(s.get("url", "")).path,
                          "selectors": s.get("selectors"),
                          "me": s.get("me"),
                          "inputs": s.get("inputs"),
                          "buttons": s.get("buttons"),
                          "disconnect_markers_found": s.get("disconnect_markers_found"),
                          "message_items_total": s.get("message_items_total"),
                          "messages_sample": s.get("messages", [])[-5:],
                          "outline": s.get("outline")})
    ws_samples = {}
    for ev in events:
        if ev["kind"] == "ws" and ev["data"].get("event") and ev["data"]["event"] not in ws_samples:
            ws_samples[ev["data"]["event"]] = ev["data"].get("data")
    bundle = {
        "tool": "chitchat_capture/capture_direct.py v1",
        "session": out_dir.name,
        "created": datetime.now().isoformat(timespec="seconds"),
        "keep_text": keep_text,
        "summary": summary,
        "ws_event_samples": ws_samples,
        "dom_snapshots": dom_items,
        "event_counts": dict(Counter(e["kind"] for e in events)),
    }
    bundle = mask_for_share(bundle, keep_text)
    # ws sample-এর মধ্যেও text masked (mask_for_share recursive)
    return bundle


def finalize(out_dir: Path, recorder: Recorder, keep_text: bool) -> None:
    recorder.close()
    events = load_events(out_dir / "events.jsonl")
    summary = analyse(events, dict(recorder.health))
    (out_dir / "summary.json").write_text(
        json.dumps(mask_for_share(summary, keep_text), ensure_ascii=False, indent=1), encoding="utf-8")
    (out_dir / "REPORT.md").write_text(
        build_report(mask_for_share(summary, keep_text), recorder.kinds, out_dir), encoding="utf-8")
    bundle = build_bundle(events, summary, out_dir, keep_text)
    (out_dir / "share_bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n[DONE] শেয়ার করুন: {out_dir / 'share_bundle.json'}")
    print(f"[DONE] পড়ুন:       {out_dir / 'REPORT.md'}")
    print("[NOTE] events.jsonl, dom/, screens/, browser_profile/ শেয়ার করবেন না।")


# ---------------------------------------------------------------- session export
COOKIE_FILE = "session_cookies.LOCAL.json"


def export_session_cookies(ctx, out_dir: Path) -> int:
    """LOCAL ONLY: chitchat.gg cookie (login token সহ) Playwright storage_state-ধাঁচে লেখে।

    এই ফাইল browser_profile-এর বদলে bot-এর session হিসেবে ব্যবহার হয়
    (session_chat --import). এতে login token আছে — কখনো শেয়ার/commit করবেন না।
    মান কোথাও print হয় না; শুধু cookie-র নাম ও সংখ্যা। Never raises; -1 = ব্যর্থ।
    """
    try:
        cookies = [c for c in ctx.cookies() if TARGET_HOST in (c.get("domain") or "")]
    except Exception:  # noqa: BLE001
        return -1
    path = out_dir / COOKIE_FILE
    tmp = out_dir / (COOKIE_FILE + ".tmp")
    try:
        tmp.write_text(json.dumps({"cookies": cookies, "origins": []}, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        try:
            tmp.chmod(0o600)
        except OSError:
            pass
        tmp.replace(path)
    except OSError:
        return -1
    names = sorted({str(c.get("name")) for c in cookies})
    print(f"[OK] login cookie local-এ সেভ: {len(cookies)}টি ({', '.join(names)}) -> {path.name}")
    print("[NOTE] session_cookies.LOCAL.json শেয়ার করবেন না — এতে login token আছে।")
    return len(cookies)


# ---------------------------------------------------------------- browser loop
def run_capture(url: str, minutes: float, channel: str, keep_text: bool) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[ERROR] playwright নেই। আগে: pip install -r requirements.txt")
        return 1

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUT_ROOT / f"session_{stamp}"
    rec = Recorder(out_dir)
    rec.event("session_start", {"url": url, "minutes": minutes, "channel": channel})

    q: "queue.Queue[tuple]" = queue.Queue()
    cmd_q: "queue.Queue[str]" = queue.Queue()

    def stdin_reader():
        try:
            for line in sys.stdin:
                cmd_q.put(line.strip())
        except Exception:
            pass

    threading.Thread(target=stdin_reader, daemon=True).start()
    print(f"[INFO] Output: {out_dir}")
    print("[INFO] Chrome খুলছে। Login করে নিজে chat করুন।")
    print("[INFO] Terminal: note <text> | shot | quit")

    with sync_playwright() as p:
        ctx = None
        kwargs = dict(user_data_dir=str(PROFILE_DIR), headless=False,
                      viewport={"width": 1280, "height": 860},
                      args=["--no-first-run", "--no-default-browser-check"])
        try:
            ctx = p.chromium.launch_persistent_context(**({"channel": channel} if channel else {}), **kwargs)
        except Exception as e:
            print(f"[WARN] '{channel}' channel চালু হলো না ({e.__class__.__name__}), bundled Chromium নিচ্ছি")
            try:
                ctx = p.chromium.launch_persistent_context(**kwargs)
            except Exception as e2:
                print(f"[ERROR] Chrome বা Chromium চালু করা গেলো না: {e2}")
                print("[FIX] Google Chrome install করুন, অথবা চালান: python -m playwright install chromium")
                return 1

        ctx.add_init_script(UI_INIT_JS)

        def on_request_finished(req):
            q.put(("request", req))

        def on_response(resp):
            q.put(("response", resp))

        def on_page(pg):
            attach_page(pg)

        def attach_page(pg):
            try:
                pg.on("websocket", lambda ws: attach_ws(ws))
            except Exception:
                pass

        def attach_ws(ws):
            url_ws = ws.url
            rec.event("ws_open", {"url": redact_url(url_ws)})
            ws.on("framesent", lambda pl: q.put(("ws", "out", url_ws, pl)))
            ws.on("framereceived", lambda pl: q.put(("ws", "in", url_ws, pl)))
            ws.on("close", lambda *_: q.put(("ws_close", url_ws)))

        ctx.on("request", on_request_finished)
        ctx.on("response", on_response)
        ctx.on("page", on_page)
        for pg in ctx.pages:
            attach_page(pg)

        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        attach_page(page)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
        except Exception as e:
            rec.event("goto_error", {"error": str(e)[:300]})
            print(f"[WARN] page খুলতে সমস্যা: {e}")

        deadline = time.time() + minutes * 60 if minutes > 0 else None
        last_poll = 0.0
        last_msg_count = -1
        stop = False
        closed_reason = "quit"

        try:
            while not stop:
                if deadline and time.time() > deadline:
                    closed_reason = "time limit"
                    break
                # terminal command
                while not cmd_q.empty():
                    cmd = cmd_q.get()
                    if cmd.lower() in ("quit", "exit", "q"):
                        stop = True
                    elif cmd.lower().startswith("note "):
                        rec.event("note", {"text": cmd[5:]})
                        print(f"[NOTE] {cmd[5:]}")
                    elif cmd.lower() == "shot":
                        take_shot(page, rec, "manual")
                # network queue
                drain(q, rec, ctx)
                # DOM poll
                if time.time() - last_poll >= 1.0:
                    last_poll = time.time()
                    pages = [x for x in ctx.pages if TARGET_HOST in (x.url or "")] or ctx.pages
                    if not pages:
                        closed_reason = "browser closed"
                        break
                    page = pages[-1]
                    try:
                        snap = page.evaluate(SNAP_JS)
                        ui_items = page.evaluate(DRAIN_JS)
                        for u in ui_items or []:
                            rec.event("ui", u)
                        count = snap.get("message_items_total", 0)
                        if count != last_msg_count:
                            rec.event("dom_messages", {"total": count, "url_path": urlsplit(snap.get("url", "")).path})
                            if count > last_msg_count >= 0 and rec.screenshot_bytes_ok():
                                take_shot(page, rec, "new_message")
                            last_msg_count = count
                        rec.dom_snapshot(snap)
                    except Exception as e:
                        if "closed" in str(e).lower() or "target" in str(e).lower():
                            closed_reason = "browser closed"
                            break
                try:
                    page.wait_for_timeout(250)
                except Exception:
                    closed_reason = "browser closed"
                    break

        except KeyboardInterrupt:
            closed_reason = "ctrl+c"
        drain(q, rec, ctx)
        rec.event("session_end", {"reason": closed_reason})
        export_session_cookies(ctx, out_dir)   # browser বন্ধ হওয়ার আগে
        try:
            ctx.close()
        except Exception:
            pass

    finalize(out_dir, rec, keep_text)
    return 0


def take_shot(page, rec: Recorder, label: str) -> None:
    try:
        name = f"{rec.screens_n + 1:04d}_{label}.jpg"
        page.screenshot(path=str(rec.dir / "screens" / name), type="jpeg", quality=55, timeout=8000)
        rec.screens_n += 1
        rec.event("screenshot", {"file": name, "label": label})
    except Exception as e:
        rec.event("screenshot_error", {"error": str(e)[:200]})


def drain(q: "queue.Queue[tuple]", rec: Recorder, ctx) -> None:
    while True:
        try:
            item = q.get_nowait()
        except queue.Empty:
            return
        kind = item[0]
        try:
            if kind == "request":
                req = item[1]
                rtype = req.resource_type
                host = urlsplit(req.url).netloc
                if TARGET_HOST not in host:
                    rec.event("third_party", {"host": host, "type": rtype})
            elif kind == "response":
                resp = item[1]
                req = resp.request
                if TARGET_HOST not in urlsplit(req.url).netloc or req.resource_type not in ("fetch", "xhr"):
                    continue
                ctype = resp.headers.get("content-type", "")
                body = None
                try:
                    body = resp.body()
                except Exception:
                    body = None
                parsed = parse_body(body, ctype)
                data = {"method": req.method, "url": redact_url(req.url), "status": resp.status,
                        "req_headers": redact_headers(req.headers),
                        "res_headers": redact_headers(resp.headers),
                        "res_content_type": ctype}
                if isinstance(parsed, (dict, list)):
                    data["res_json"] = parsed
                elif parsed is not None:
                    data["res_text"] = parsed
                ctype_req = req.headers.get("content-type", "")
                try:
                    raw_req = req.post_data_buffer
                except Exception:  # noqa: BLE001 — not every request has a body buffer
                    raw_req = None
                if raw_req is None:
                    post = req.post_data
                    raw_req = post.encode("utf-8") if post else None
                data["req_json_or_text"] = parse_body(raw_req, ctype_req)
                mp = parse_multipart(raw_req, ctype_req)
                if mp is not None:
                    data["req_multipart"] = mp
                if isinstance(data["req_json_or_text"], (dict, list)):
                    data["req_json"] = data["req_json_or_text"]
                rec.event("http", data)
            elif kind == "ws":
                _, direction, url_ws, payload = item
                if isinstance(payload, bytes):
                    rec.event("ws", {"dir": direction, "url": redact_url(url_ws),
                                     "binary_len": len(payload),
                                     "b64_head": base64.b64encode(payload[:64]).decode()})
                    continue
                ev, data = parse_socketio(str(payload))
                entry = {"dir": direction, "url": redact_url(url_ws), "event": ev,
                         "data": data if ev else None}
                if not ev:
                    entry["raw_head"] = redact_text(str(payload)[:300])
                rec.event("ws", entry)
            elif kind == "ws_close":
                rec.event("ws_close", {"url": redact_url(item[1])})
        except Exception as e:
            rec.event("capture_error", {"kind": kind, "error": str(e)[:200]})


# ---------------------------------------------------------------- selftest
def selftest() -> int:
    fails = 0

    def ok(name, cond):
        nonlocal fails
        print(("PASS " if cond else "FAIL ") + name)
        if not cond:
            fails += 1

    ok("JWT masked", "<JWT>" in redact_text("tok eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2Q"))
    ok("email masked", "<EMAIL>" in redact_text("mail me a.b@example.com now"))
    r = redact_obj({"token": "abc", "author": {"id": "u1"}, "content": "hi", "statusCode": 200})
    ok("secret key value masked", r["token"].startswith("<redacted"))
    ok("author not masked (no false positive)", r["author"]["id"] == "u1")
    ok("statusCode kept", r["statusCode"] == 200)
    h = redact_headers({"Cookie": "token=xyz; __Secure-text-session=v", "Origin": "https://app.chitchat.gg"})
    ok("cookie value hidden, names kept", h["Cookie"]["cookie_names"] == ["token", "__Secure-text-session"])
    ok("origin kept", h["Origin"] == "https://app.chitchat.gg")
    ok("url query secret masked", "token=REDACTED" in redact_url("https://x.gg/a?token=123&page=2"))
    ok("url query normal kept", "page=2" in redact_url("https://x.gg/a?token=123&page=2"))
    ok("path id normalised", norm_path("https://x.gg/users/me/conversations/6a9257898ac97f8d3c432262/messages")
       == "/users/me/conversations/{id}/messages")
    ok("socket.io parse", parse_socketio('42["chatMessage",{"a":1}]') == ("chatMessage", {"a": 1}))
    ok("socket.io non-event", parse_socketio("2") == (None, None))
    m = mask_for_share({"messages": [{"text": "secret words", "n": 1}]}, keep_text=False)
    ok("share mask hides text", m["messages"][0]["text"] == "<text len=12>")
    ok("share mask keeps keep_text", mask_for_share({"text": "a"}, keep_text=True)["text"] == "a")
    # v23: multipart request body -> field names visible (send_message form fields)
    mp_ctype = "multipart/form-data; boundary=----WebKitFormBoundaryABC"
    mp_raw = (b"------WebKitFormBoundaryABC\r\n"
              b'Content-Disposition: form-data; name="content"\r\n\r\n'
              b"hello there\r\n"
              b"------WebKitFormBoundaryABC\r\n"
              b'Content-Disposition: form-data; name="nonce"\r\n\r\n'
              b"n-123\r\n"
              b"------WebKitFormBoundaryABC\r\n"
              b'Content-Disposition: form-data; name="attachment"; filename="a.png"\r\n'
              b"Content-Type: image/png\r\n\r\n"
              b"\x89PNG\r\n"
              b"------WebKitFormBoundaryABC--\r\n")
    mp = parse_multipart(mp_raw, mp_ctype)
    ok("multipart: field names parsed", [f["name"] for f in mp] == ["content", "nonce", "attachment"])
    ok("multipart: file part marked, no bytes kept",
       mp[2].get("filename") == "<file>" and mp[2].get("size") == 4 and "value" not in mp[2])
    ok("multipart: text value kept for nonce", mp[1].get("value") == "n-123")
    ok("multipart: content value masked on share",
       mask_for_share({"req_multipart": mp}, keep_text=False)["req_multipart"][0].get("text") != "hello there")
    ok("multipart: no boundary -> None", parse_multipart(mp_raw, "multipart/form-data") is None)
    sh = shape({"a": 1, "b": [{"c": "x"}]})
    ok("shape has types, no values", sh == {"a": "int", "b": [{"c": "str"}]})

    # recorder + analysis on synthetic data
    tmp = HERE / "capture_out" / "_selftest"
    if tmp.exists():
        for f in sorted(tmp.rglob("*"), reverse=True):
            if f.is_file():
                f.unlink()
            elif f.is_dir():
                f.rmdir()
    rec = Recorder(tmp)
    rec.event("http", {"method": "POST", "url": "https://app.chitchat.gg/api/users/me/conversations/6a9257898ac97f8d3c432262/messages",
                       "status": 201, "req_json": {"content": "hello", "nonce": "n"},
                       "res_json": {"id": "x", "nonce": "n"}, "req_headers": {}})
    rec.event("ws", {"dir": "in", "url": "wss://x", "event": "chatMessage",
                     "data": {"message": {"content": "partner text"}}})
    rec.event("ui", {"type": "enter", "target_tag": "textarea"})
    rec.event("ws", {"dir": "in", "url": "wss://x", "event": "chatMessage", "data": {}})
    rec.dom_snapshot({"url": "https://app.chitchat.gg/text", "message_items_total": 2,
                      "messages": [{"text": "partner text"}], "buttons": [],
                      "selectors": {"msg_li_select_text": {"count": 2, "visible": 2}},
                      "html": "<main></main>"})
    rec.close()
    events = load_events(tmp / "events.jsonl")
    s = analyse(events, dict(rec.health))
    ok("endpoint normalised in summary", any("{id}" in k for k in s["endpoints"]))
    ok("ui -> next http mapped", s["ui_actions"] and s["ui_actions"][0]["next_http"])
    ok("selector health OK", s["selector_health"]["msg_li_select_text"]["status"] == "OK")
    ok("dom snapshot written", (tmp / "dom" / "0001.json").exists() and (tmp / "dom" / "0001.html").exists())
    ok("partner->post delay computed", isinstance(s["partner_to_our_post_ms"], list))
    b = build_bundle(events, s, tmp, keep_text=False)
    txt = json.dumps(b, ensure_ascii=False)
    ok("bundle has no raw 'partner text'", "partner text" not in txt)
    ok("bundle has no raw token", "\"abc\"" not in txt)
    # session cookie export (fake context; no browser)
    class _FakeCtx:
        def cookies(self):
            return [
                {"name": "token", "value": "SELFTEST-VALUE-1", "domain": ".chitchat.gg"},
                {"name": "__Secure-text-session", "value": "SELFTEST-VALUE-2", "domain": "app.chitchat.gg"},
                {"name": "other", "value": "x", "domain": "example.com"},
            ]
    cdir = HERE / "capture_out" / "_selftest_cookies"
    cdir.mkdir(parents=True, exist_ok=True)
    n = export_session_cookies(_FakeCtx(), cdir)
    cf = cdir / COOKIE_FILE
    ck = json.loads(cf.read_text(encoding="utf-8")).get("cookies", []) if cf.exists() else []
    ok("cookie export keeps only chitchat cookies", n == 2 and {c["name"] for c in ck} == {"token", "__Secure-text-session"})
    ok("cookie export leaves no tmp file", not (cdir / (COOKIE_FILE + ".tmp")).exists())
    if os.name != "nt":
        ok("cookie export file mode 0600", (cf.stat().st_mode & 0o777) == 0o600)
    for f in sorted(cdir.rglob("*"), reverse=True):
        if f.is_file():
            f.unlink()
    cdir.rmdir()

    print(f"\nSELFTEST {'PASSED' if fails == 0 else f'FAILED ({fails})'}")
    return 0 if fails == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="ChitChat direct capture (Playwright)")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--minutes", type=float, default=0, help="0 = quit লিখে বন্ধ করা পর্যন্ত")
    ap.add_argument("--channel", default="chrome", help="chrome | msedge | '' (bundled chromium)")
    ap.add_argument("--keep-text", action="store_true",
                    help="share_bundle.json-এ message text রাখবে (সাধারণত দরকার নেই)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    return run_capture(a.url, a.minutes, a.channel, a.keep_text)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[INFO] Ctrl+C — capture শেষ হচ্ছে, রিপোর্ট লেখা হচ্ছে...")
        raise SystemExit(0)
