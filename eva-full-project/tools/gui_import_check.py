"""
gui_import_check.py — import entry.main with PyQt6 widgets/gui and winsound stubbed.

Why: the sandbox has no libGL (QtWidgets cannot load) and no winsound (Windows only).
This proves the GUI module graph imports without a NameError/ImportError. It does NOT
prove that any window renders or any button works — that needs a real Windows run.

Run from the project root:  python tools/gui_import_check.py
Exit 0 = import OK, 1 = import failed.
"""
import os
import sys
import types

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class _Dummy:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        return _Dummy()

    def __call__(self, *a, **k):
        return _Dummy()

    def __iter__(self):
        return iter([])


class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        cls = type(name, (_Dummy,), {})
        setattr(self, name, cls)
        return cls


def install_stubs() -> None:
    ws = types.ModuleType("winsound")
    ws.Beep = lambda *a, **k: None
    ws.PlaySound = lambda *a, **k: None
    ws.SND_FILENAME = 0
    ws.SND_ASYNC = 0
    sys.modules["winsound"] = ws
    for m in ("PyQt6.QtWidgets", "PyQt6.QtGui"):
        sys.modules[m] = _StubModule(m)
    try:
        import PyQt6  # real package: QtCore is used as-is
        PyQt6.QtWidgets = sys.modules["PyQt6.QtWidgets"]
        PyQt6.QtGui = sys.modules["PyQt6.QtGui"]
    except ImportError:
        pass


def main() -> int:
    install_stubs()
    try:
        import entry.main as em  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print(f"GUI IMPORT FAILED: {type(exc).__name__}: {exc}")
        return 1
    print("GUI-STUB IMPORT OK (entry.main); ApplicationController present:",
          hasattr(em, "ApplicationController"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
