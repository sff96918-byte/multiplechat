"""Tests for the agent memory CLI (offline, temp HOME-free — uses real memory/ but cleans up)."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ops.tools import memory as M


class TestMemoryTool(unittest.TestCase):
    def setUp(self):
        # real memory/ নোংরা করা যাবে না — temp dir-এ লিখি
        import tempfile
        tmp = Path(tempfile.mkdtemp(prefix="eva-mem-test-"))
        self._old_mem = M.MEM
        M.MEM = tmp
        M.FILES = {k: tmp / f"{k}s.md" for k in ("session", "decision", "bug", "fact", "question")}
        for k in M.FILES:
            M._ensure_file(k)

    def tearDown(self):
        M.MEM = self._old_mem
        M.FILES = None  # reassigned per-test; real paths restored lazily below
        M.FILES = {
            "session": M.MEM / "sessions.md",
            "decision": M.MEM / "decisions.md",
            "bug": M.MEM / "bugs_fixed.md",
            "fact": M.MEM / "protocol_facts.md",
            "question": M.MEM / "open_questions.md",
        }

    def test_files_exist(self):
        for kind, path in M.FILES.items():
            self.assertTrue(path.exists(), f"missing memory file: {path}")

    def test_add_entry_creates_formatted_entry(self):
        marker = f"TEST-ENTRY-{M._today()}"
        M.add_entry("bug", marker, "Symptom: x\nCause: y\nFix: z")
        text = M.FILES["bug"].read_text(encoding="utf-8")
        self.assertIn(marker, text)
        self.assertIn("Symptom: x", text)
        # clean up the test entry
        lines = [l for l in text.splitlines() if marker not in l]
        cleaned = "\n".join(lines)
        # also drop the body block right after the marker header (best-effort)
        M.FILES["bug"].write_text(cleaned + "\n", encoding="utf-8")

    def test_index_gets_appended(self):
        idx = M.MEM / "INDEX.md"
        idx.parent.mkdir(parents=True, exist_ok=True)
        idx.write_text("# temp index\n", encoding="utf-8")
        before = idx.read_text(encoding="utf-8")
        marker = f"TEST-IDX-{M._today()}"
        M.add_entry("fact", marker, "some body")
        after = idx.read_text(encoding="utf-8")
        self.assertIn(marker, after)
        self.assertGreater(len(after), len(before))
        # cleanup index line
        idx_lines = [l for l in after.splitlines() if marker not in l]
        idx.write_text("\n".join(idx_lines) + "\n", encoding="utf-8")
        # cleanup fact file
        ft = M.FILES["fact"].read_text(encoding="utf-8")
        ft_lines = [l for l in ft.splitlines() if marker not in l]
        M.FILES["fact"].write_text("\n".join(ft_lines) + "\n", encoding="utf-8")

    def test_newest_first_order(self):
        text = M.FILES["session"].read_text(encoding="utf-8")
        dates = [l.split("|")[0].strip("## ") for l in text.splitlines() if l.startswith("## ")]
        self.assertEqual(dates, sorted(dates, reverse=True), "sessions.md newest-first না")

    def test_all_memory_files_have_headers(self):
        for kind, path in M.FILES.items():
            first = path.read_text(encoding="utf-8").splitlines()[0]
            self.assertTrue(first.startswith("# "), f"{path} header নেই")


if __name__ == "__main__":
    unittest.main(verbosity=2)
