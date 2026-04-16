# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# 1. Automatically collect ALL submodules and data files (like YAML configs) for SAM2
sam2_hidden = collect_submodules('sam2')
sam2_datas = collect_data_files('sam2')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.yaml', '.'),
        ('version.txt', '.'),
    ] + sam2_datas,  # 2. Append the collected SAM2 config files here
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        'qt_material',
        'qt_material.resources',
        # Replaced the manual sam2 imports with sam2_hidden below
        'ultralytics',
        'torch',
        'torchvision',
        'cv2',
        'numpy',
        'PIL',
        'yaml',
        'requests',
        'scenedetect',
        'hydra',
        'omegaconf',
        'tqdm',
    ] + sam2_hidden, # 3. Append all SAM2 internal modeling files here
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'jupyter',
        'notebook',
        'IPython',
        'tensorboard',
        'torch.utils.tensorboard',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
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
