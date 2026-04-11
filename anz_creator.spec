# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for Anz-Creator.
Build command: pyinstaller anz_creator.spec
"""

import sys
import os

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.yaml', '.'),
        ('assets', 'assets'),
    ],
    hiddenimports=[
        'PyQt6',
        'qt_material',
        'yaml',
        'cv2',
        'numpy',
        'PIL',
        'torch',
        'torchvision',
        'ultralytics',
        'requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Anz-Creator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window
    icon='assets/icons/app.ico' if os.path.exists('assets/icons/app.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Anz-Creator',
)
