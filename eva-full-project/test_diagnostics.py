"""test_diagnostics.py — crash log + redaction + doctor (v21).

    python test_diagnostics.py
"""
import os
import sys
import threading

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core import diagnostics as D  # noqa: E402

passed = failed = 0


def ok(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {extra}")


# 1) redaction
r = D.redact("token=abc123SECRET user@mail.com eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeK Bearer xyz.tok password: hunter2")
ok("token value masked", "abc123SECRET" not in r)
ok("email masked", "user@mail.com" not in r and "<email>" in r)
ok("JWT masked", "eyJhbGciOi" not in r and "<JWT>" in r)
ok("bearer masked", "xyz.tok" not in r)
ok("password masked", "hunter2" not in r)
ok("normal text kept", D.redact("hello there 3 replies") == "hello there 3 replies")
ok("non-string safe", D.redact("") == "")

# 2) crash log written from worker thread, redacted, and readable back
logs = os.path.join(ROOT, "data", "logs", "crash.log")
for p in (logs, logs + ".1"):
    if os.path.exists(p):
        os.remove(p)
D.install_excepthooks()


def boom():
    raise RuntimeError("worker boom token=SECRET999 user@x.com")


t = threading.Thread(target=boom, name="test-worker")
t.start()
t.join()
text = open(logs, encoding="utf-8").read() if os.path.exists(logs) else ""
ok("crash.log created by thread hook", "test-worker" in text, text[:120])
ok("crash.log has no secret", "SECRET999" not in text and "user@x.com" not in text)
ok("summary returns header", any("test-worker" in h for h in D.tail_crash_summary()))
os.remove(logs)

# 3) doctor runs end-to-end and never crashes (exit 0 or 1 only)
import tools.doctor as DR  # noqa: E402
DR.RESULTS.clear()
rc = DR.main()
ok("doctor exit code is 0/1", rc in (0, 1), str(rc))
ok("doctor produced checks", len(DR.RESULTS) >= 10, str(len(DR.RESULTS)))
ok("doctor never crashed a check",
   not any("doctor check crashed" in d for _, _, d in DR.RESULTS))

print(f"\nRESULT: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
