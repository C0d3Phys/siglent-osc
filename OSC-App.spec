# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

project_root = Path(SPECPATH)
os.environ["QT_API"] = "PySide6"

a = Analysis(
    [str(project_root / "osc_app" / "__main__.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (
            str(project_root / "osc_app" / "resources" / "osc_app_logo.png"),
            "osc_app/resources",
        )
    ],
    hiddenimports=["pyqtgraph.exporters"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["PyQt5", "PyQt6", "PySide2"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="OSC-App",
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
    icon=str(project_root / "osc_app" / "resources" / "osc_app_logo.png"),
)
