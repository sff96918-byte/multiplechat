# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — builds the EVA Dashboard Windows exe.

Build on Windows:  build_exe.bat   (runs:  pyinstaller EVA_Dashboard.spec)
Output:            dist\\EVA Dashboard\\EVA Dashboard.exe   (onedir, windowed)

data banks (eva/brain/data) are bundled so eva_flow's relative DATA_DIR works.
"""

import os

block_cipher = None

datas = [
    ("eva/brain/data", "eva/brain/data"),
    ("configs/chitchat_bot.example.json", "configs"),
    ("configs/session.example.json", "configs"),
    ("configs/fixed_script.txt", "configs"),
    ("configs/fixed_script.example.txt", "configs"),
    ("configs/snap.txt.example", "configs"),
    ("README.md", "."),
    ("BANGLA_QUICK_START.txt", "."),
    ("docs/DASHBOARD_OPTIONS_BN.md", "docs"),
]

hiddenimports = []
try:
    from PyInstaller.utils.hooks import collect_all
    d0, b0, h0 = collect_all("aiohttp")
    datas += d0; hiddenimports += h0
except Exception:
    hiddenimports += ["aiohttp"]

a = Analysis(
    ["dashboard_main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports + [
        "eva.gui.dashboard",
        "eva.brain.eva_flow",
        "eva.brain.flow_reply_engine",
        "eva.brain.fixed_reply_engine",
        "eva.debugtools",
        "eva.dashboard.cdp_session",
        "eva.transport.ws_chat_loop",
        "eva.transport.chitchat_api",
        "eva.transport.chitchat_socket",
        "eva.transport.socketio_codec",
        "eva.transport.protocol",
        "psutil",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "playwright", "matplotlib", "numpy"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EVA Dashboard",
    icon="eva/brain/data/chitchat-bot.ico" if os.path.exists("eva/brain/data/chitchat-bot.ico") else None,
    debug=False,
    strip=False,
    upx=False,
    console=False,          # windowed app (no black console)
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name="EVA Dashboard",
)
