# -*- mode: python ; coding: utf-8 -*-

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Conditionally include version.txt only if it exists (CI writes it)
datas = [('config.yaml', '.')]
if os.path.exists('version.txt'):
    datas.append(('version.txt', '.'))

# Collect ALL submodules and data files (including YAML configs) for SAM2
try:
    sam2_hidden = collect_submodules('sam2')
    sam2_datas = collect_data_files('sam2', include_py_files=False)
    datas.extend(sam2_datas)
except Exception:
    sam2_hidden = []

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        'qt_material',
        'qt_material.resources',
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
        'iopath',
        'tqdm',
    ] + sam2_hidden,
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
