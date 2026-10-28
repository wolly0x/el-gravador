# -*- mode: python ; coding: utf-8 -*-
"""Spec do PyInstaller para gerar El_Gravador_18_Pro_Max.exe (onefile, sem console)."""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, collect_dynamic_libs

hiddenimports = [
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    "pynput._util.win32",
    "PIL._tkinter_finder",
    "cv2",
    "numpy",
    "tkinter",
    "tkinter.filedialog",
    "tkinter.messagebox",
    "tkinter.simpledialog",
    "tkinter.colorchooser",
    "webview",
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
    "bottle",
    "clr",
    "clr_loader",
    "System",
    "Microsoft.Web.WebView2.Core",
]
hiddenimports += collect_submodules("pynput")

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=collect_dynamic_libs("webview"),
    datas=[("ui_web", "ui_web")] + collect_data_files("webview"),
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "pandas", "scipy", "PyQt5", "PySide6", "notebook", "PyQt6"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="El_Gravador_18_Pro_Max",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
