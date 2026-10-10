"""Agent memory CLI — read/write the project's agent memory (memory/ folder).

Why: agents start fresh every session. This gives them cheap, reliable,
git-versioned memory: past sessions, decisions, fixed bugs, user preferences,
open questions. AGENTS.md makes reading/writing this MANDATORY.

Usage:
    python -m ops.tools.memory recent [N]          # latest entries, all files
    python -m ops.tools.memory search KEYWORD      # grep across memory
    python -m ops.tools.memory add session|decision|bug|fact|question "title" [--body "..."]
    python -m ops.tools.memory stats

Entries are appended as markdown; keep titles short, put details in --body.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEM = ROOT / "memory"

FILES = {
    "session": MEM / "sessions.md",
    "decision": MEM / "decisions.md",
    "bug": MEM / "bugs_fixed.md",
    "fact": MEM / "protocol_facts.md",
    "question": MEM / "open_questions.md",
}

HEADERS = {
    "session": "SESSIONS (নতুন আগে — newest first)",
    "decision": "DECISIONS (কেন এমন বানানো হলো — newest first)",
    "bug": "BUGS FIXED (আর খুঁজতে হবে না — newest first)",
    "fact": "PROTOCOL FACTS (verified chitchat.gg behavior)",
    "question": "OPEN QUESTIONS (এখনো মীমাংসা হয়নি)",
}


def _today() -> str:
    return datetime.date.today().isoformat()


def _rel(path: Path) -> str:
    import os
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _ensure_file(kind: str) -> Path:
    path = FILES[kind]
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"# {HEADERS[kind]}\n\n", encoding="utf-8")
    return path


def _extract_header_line(text: str) -> str:
    """First non-empty, non-heading line of body → index summary."""
    for line in text.splitlines():
        s = line.strip().lstrip("-* ").strip()
        if s:
            return s[:110]
    return ""


def add_entry(kind: str, title: str, body: str = "") -> None:
    path = _ensure_file(kind)
    stamp = _today()
    entry = f"\n## {stamp} | {title.strip()}\n"
    if body.strip():
        entry += "\n" + body.strip() + "\n"
    text = path.read_text(encoding="utf-8")

    lines = text.splitlines()
    header_at = 0
    for i, line in enumerate(lines):
        if line.strip().startswith("#"):
            header_at = i
            break
    out = "\n".join(lines[: header_at + 1]) + "\n" + entry + "\n".join(lines[header_at + 1:]).rstrip() + "\n"

    path.write_text(out, encoding="utf-8")

    # also refresh INDEX quick-list
    _index_add(kind, stamp, title.strip(), _extract_header_line(body))
    print(f"[ok] {kind} entry added -> {_rel(path)}")


def _index_add(kind: str, stamp: str, title: str, summary: str) -> None:
    idx = MEM / "INDEX.md"
    idx.parent.mkdir(parents=True, exist_ok=True)
    text = idx.read_text(encoding="utf-8") if idx.exists() else ""
    marker = "<!-- auto-appended by ops.tools.memory -->"
    line = f"| {stamp} | `{kind}` | {title} | {summary} |"
    if marker in text:
        text = text.replace(marker, marker + "\n" + line, 1)
    else:
        text += f"\n{marker}\n{line}\n"
    idx.write_text(text, encoding="utf-8")


def recent(n: int = 8) -> None:
    rows = []
    for kind, path in FILES.items():
        if not path.exists():
            continue
        cur: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                if cur:
                    rows.append((kind, cur))
                cur = [line[3:]]
            elif cur:
                cur.append(line)
        if cur:
            rows.append((kind, cur))
    # rows are newest-first per file; merge by date string (ISO sorts fine)
    rows.sort(key=lambda r: r[1][0], reverse=True)
    shown = 0
    for kind, lines in rows:
        if shown >= n:
            break
        title = lines[0]
        summary = _extract_header_line("\n".join(lines[1:]))
        print(f"[{title.split('|')[0].strip()}] ({kind}) {title.split('|')[-1].strip()}")
        if summary:
            print(f"    {summary[:110]}")
        shown += 1


def search(keyword: str) -> int:
    kw = keyword.lower()
    hits = 0
    for kind, path in FILES.items():
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if kw in text.lower():
            print(f"--- {_rel(path)} ---")
            for i, line in enumerate(text.splitlines()):
                if kw in line.lower():
                    print(f"  L{i+1}: {line.strip()[:150]}")
                    hits += 1
    print(f"\n{hits} matching lines for {keyword!r}")
    return hits


def stats() -> None:
    for kind, path in FILES.items():
        if not path.exists():
            print(f"{kind:9} -  (missing)")
            continue
        count = sum(1 for l in path.read_text(encoding="utf-8").splitlines() if l.startswith("## "))
        print(f"{kind:9} {count:3} entries  ({_rel(path)})")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="agent memory CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_r = sub.add_parser("recent")
    p_r.add_argument("n", nargs="?", type=int, default=8)

    p_s = sub.add_parser("search")
    p_s.add_argument("keyword")

    p_a = sub.add_parser("add")
    p_a.add_argument("kind", choices=list(FILES))
    p_a.add_argument("title")
    p_a.add_argument("--body", default="")

    sub.add_parser("stats")

    args = ap.parse_args(argv)
    if args.cmd == "recent":
        recent(args.n)
    elif args.cmd == "search":
        search(args.keyword)
    elif args.cmd == "add":
        add_entry(args.kind, args.title, args.body)
    elif args.cmd == "stats":
        stats()


if __name__ == "__main__":
    main()
