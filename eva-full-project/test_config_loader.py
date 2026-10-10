"""test_config_loader.py — save_config_sections keeps decimal values (v26).

Regression: when config.json held an integer (hand-edited, e.g. "silence_timeout_seconds": 90),
saving 120.5 from Settings was truncated to 120 because the new value was coerced to the
old value's type. Synthetic temp files only; the real data/config.json is never touched.

    python test_config_loader.py
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from core import config_loader as cl  # noqa: E402

passed = failed = 0


def ok(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}  {extra}")


def save_case(initial_timing, updates):
    d = tempfile.mkdtemp(prefix="cfg_test_")
    path = os.path.join(d, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"chat_timing": initial_timing}, f)
    result = cl.save_config_sections({"chat_timing": updates}, path=path)
    with open(path, encoding="utf-8") as f:
        stored = json.load(f)["chat_timing"]
    return result, stored


# 1) integer on disk + decimal from Settings -> decimal kept
res, stored = save_case({"silence_timeout_seconds": 90}, {"silence_timeout_seconds": 120.5})
ok("save returns True", res is True)
ok("int-on-disk: 120.5 is not truncated to 120",
   stored["silence_timeout_seconds"] == 120.5, repr(stored["silence_timeout_seconds"]))

# 2) integer on disk + whole number -> stored as a number equal to the value
res, stored = save_case({"silence_timeout_seconds": 90}, {"silence_timeout_seconds": 100})
ok("int-on-disk: whole 100 stored as 100", stored["silence_timeout_seconds"] == 100)

# 3) float on disk (shipped default) -> unchanged behaviour
res, stored = save_case({"silence_timeout_seconds": 90.0}, {"silence_timeout_seconds": 120.5})
ok("float-on-disk: 120.5 kept", stored["silence_timeout_seconds"] == 120.5)

# 4) missing key -> float stored
res, stored = save_case({}, {"new_chat_delay_min_seconds": 6.5})
ok("missing key: 6.5 stored", stored["new_chat_delay_min_seconds"] == 6.5)

# 5) round trip through the loader keeps the decimal
d = tempfile.mkdtemp(prefix="cfg_test_")
path = os.path.join(d, "config.json")
with open(path, "w", encoding="utf-8") as f:
    json.dump({"chat_timing": {"silence_timeout_seconds": 90,
                               "new_chat_delay_min_seconds": 5,
                               "new_chat_delay_max_seconds": 5}}, f)
cl.save_config_sections({"chat_timing": {"silence_timeout_seconds": 120.5}}, path=path)
ok("loader round trip: silence 120.5", cl.load_chat_timing(path)["silence_timeout_seconds"] == 120.5)

# 6) nan / inf must be refused: save returns False and the file is left as it was
for bad in (float("nan"), float("inf"), float("-inf")):
    d = tempfile.mkdtemp(prefix="cfg_test_")
    path = os.path.join(d, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"chat_timing": {"silence_timeout_seconds": 120}}, f)
    res = cl.save_config_sections({"chat_timing": {"silence_timeout_seconds": bad}}, path=path)
    with open(path, encoding="utf-8") as f:
        kept = json.load(f)["chat_timing"]["silence_timeout_seconds"]
    ok(f"non-finite {bad!r}: save returns False", res is False, repr(res))
    ok(f"non-finite {bad!r}: file keeps 120", kept == 120, repr(kept))

print(f"\nRESULT: {passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
