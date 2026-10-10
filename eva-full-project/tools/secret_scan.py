"""secret_scan.py — dependency-free secret pattern scan over project text files (v26).

    python tools/secret_scan.py          # exit 1 if a likely secret is found

Prints file:line and the pattern NAME only. It never prints the matched value.
A line that is a deliberate test fixture can carry the inline marker
`secretscan: ignore` (reviewed by hand; keep these rare).

Limits (stated plainly):
- Regex heuristics. It can miss secrets and can flag harmless code.
- It is NOT a substitute for gitleaks. gitleaks is run by verify_gate.py when
  installed (see tools/verify_gate.py); this scanner always runs.
- Scans the project tree only, not git history.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "account_sessions",
             "browser_profile", "capture_out", "logs", "build", "dist"}
SKIP_EXT = {".zip", ".exe", ".dll", ".pyc", ".png", ".jpg", ".jpeg", ".ico",
            ".gif", ".db", ".sqlite", ".idx", ".bin", ".pdf", ".woff", ".ttf",
            ".so", ".pyd", ".whl", ".gz"}
MAX_BYTES = 2_000_000
IGNORE_MARK = "secretscan: ignore"

PATTERNS = [
    ("private-key-block", re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY")),
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("jwt", re.compile(
        r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("assigned-secret", re.compile(
        r"""(?i)\b(password|passwd|api[_-]?key|secret[_-]?key|access[_-]?token)\s*[:=]\s*["']([^"'\s]{10,})["']""")),
]


def iter_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            ext = os.path.splitext(name)[1].lower()
            if ext in SKIP_EXT:
                continue
            path = os.path.join(dirpath, name)
            try:
                if os.path.getsize(path) > MAX_BYTES:
                    continue
            except OSError:
                continue
            yield path


def scan_file(path):
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return []
    if b"\x00" in raw[:4096]:
        return []
    text = raw.decode("utf-8", errors="replace")
    hits = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if IGNORE_MARK in line:
            continue
        for name, rx in PATTERNS:
            if rx.search(line):
                hits.append((lineno, name))
    return hits


def selftest():
    """Prove each pattern class fires on a synthetic line (fake values)."""
    import tempfile
    samples = {
        "private-key-block": "-----BEGIN RSA PRIVATE KEY-----",
        "aws-access-key-id": "id = AKIAABCDEFGHIJKLMNOP",
        "github-token": "t = ghp_" + "a" * 36,
        "slack-token": "s = xoxb-1234567890-abcdef",
        "jwt": "j = eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijk",
        "assigned-secret": 'password = "fakeFAKEfake123"',
    }
    ok = True
    with tempfile.TemporaryDirectory() as d:
        for name, line in samples.items():
            p = os.path.join(d, name + ".txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("clean line\n" + line + "\n# secretscan: ignore\n")
            found = [n for _, n in scan_file(p)]
            hit = name in found
            ok = ok and hit
            print(f"  selftest {name:18s} {'PASS' if hit else 'FAIL'}")
        p = os.path.join(d, "ignored.txt")
        with open(p, "w", encoding="utf-8") as f:
            f.write('password = "fakeFAKEfake123"  # secretscan: ignore\n')
        if scan_file(p):
            ok = False
            print("  selftest ignore-marker FAIL")
        else:
            print("  selftest ignore-marker PASS")
    print("SELFTEST " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


def main():
    if "--selftest" in sys.argv:
        return selftest()
    total = 0
    files = 0
    for path in iter_files():
        files += 1
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        if rel == "tools/secret_scan.py":
            continue
        for lineno, name in scan_file(path):
            total += 1
            print(f"  SECRET?  {rel}:{lineno}  [{name}]")
    print(f"scanned {files} files; findings: {total}")
    if total:
        print("FAIL  review the lines above (value not printed)")
        return 1
    print("PASS  no likely secrets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
