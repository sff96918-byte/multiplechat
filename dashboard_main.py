#!/usr/bin/env python3
"""PyInstaller entry point for the EVA Dashboard exe (see EVA_Dashboard.spec)."""
import sys
from pathlib import Path

# exe-এর পাশের configs/ ব্যবহার হবে (eva/paths.py frozen-aware)
sys.path.insert(0, str(Path(__file__).resolve().parent))

from eva.gui.dashboard import run_gui

if __name__ == "__main__":
    sys.exit(run_gui())
