"""Frozen-exe aware project root resolution.

PyInstaller exe-এ configs/ + data/ exe-এর পাশে থাকে; না হলে repo root।
"""

from __future__ import annotations

import sys
from pathlib import Path


def project_root() -> Path:
    if getattr(sys, "frozen", False):  # running as PyInstaller exe
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]
