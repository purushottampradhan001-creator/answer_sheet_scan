# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for bundling Python backend

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect all data files and hidden imports
datas = []
hiddenimports = [
    'flask',
    'flask_cors',
    'cv2',
    'PIL',
    'numpy',
    'imagehash',
    'reportlab',
    'watchdog',
    'sqlite3',
    'src.services.image_validator',
    'src.services.pdf_generator',
    'src.services.image_editor',
    'src.services.scanner_watcher',
    'src.models.database',
    'src.models.answer_copy',
    'src.utils.file_utils',
    'src.utils.image_utils',
    'src.app.config',
]

# Collect data files for opencv
try:
    cv2_datas = collect_data_files('cv2')
    datas.extend(cv2_datas)
except:
    pass

# Collect data files for reportlab
try:
    reportlab_datas = collect_data_files('reportlab')
    datas.extend(reportlab_datas)
except:
    pass

a = Analysis(
    ['src/app/main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='image_engine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
