# -*- mode: python ; coding: utf-8 -*-

import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect qt-material themes
material_datas = collect_data_files('qt_material')
ultralytics_datas = collect_data_files('ultralytics')

# Hidden imports for AI libraries
hiddenimports = [
    'torch',
    'torchvision',
    'numpy',
    'cv2',
    'ultralytics',
    'ultralytics.nn',
    'ultralytics.utils',
    'scenedetect',
    'scenedetect.detectors',
    'yaml',
    'requests',
    'PIL',
    'sam2',
    'sam2.build_sam',
    'sam2.sam2_image_predictor',
    'sam2.sam2_video_predictor',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.yaml', '.'),
        ('version.txt', '.'),
        ('ui/*.py', 'ui'),
        ('core/*.py', 'core'),
        ('features/**/*.py', 'features'),
        ('utils/*.py', 'utils'),
    ] + material_datas + ultralytics_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'jupyter', 'IPython', 'pytest'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Anz-Creator',
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
    icon='icon.ico' if os.path.exists('icon.ico') else None,
)
