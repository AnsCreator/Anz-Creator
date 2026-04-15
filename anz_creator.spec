# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Add PyQt6 binary path
from PyQt6 import QtCore
qt_bin_path = os.path.dirname(QtCore.__file__).replace('Qt6', 'Qt6/bin')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[
        (os.path.join(qt_bin_path, 'Qt6Core.dll'), '.'),
        (os.path.join(qt_bin_path, 'Qt6Gui.dll'), '.'),
        (os.path.join(qt_bin_path, 'Qt6Widgets.dll'), '.'),
        (os.path.join(qt_bin_path, 'Qt6Network.dll'), '.'),
        (os.path.join(qt_bin_path, 'Qt6Svg.dll'), '.'),
    ],
    datas=[
        ('config.yaml', '.'),
        ('version.txt', '.'),
    ] + collect_data_files('PyQt6') + collect_data_files('qt_material') + 
        collect_data_files('sam2') + collect_data_files('ultralytics'),
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        'qt_material',
        'qt_material.resources',
        'sam2',
        'sam2.build_sam',
        'sam2.sam2_image_predictor',
        'sam2.sam2_video_predictor',
        'sam2.modeling',
        'sam2.modeling.sam2_base',
        'sam2.modeling.transformer',
        'sam2.modeling.backbones',
        'sam2.modeling.backbones.hieradet',
        'sam2.modeling.backbones.image_encoder',
        'sam2.modeling.memory_attention',
        'sam2.modeling.memory_encoder',
        'sam2.utils',
        'sam2.utils.amg',
        'sam2.utils.misc',
        'sam2.utils.transforms',
        'ultralytics',
        'ultralytics.nn.modules',
        'ultralytics.data',
        'torch',
        'torchvision',
        'torchvision.ops',
        'torchvision.transforms',
        'cv2',
        'numpy',
        'PIL',
        'yaml',
        'requests',
        'scenedetect',
        'hydra',
        'omegaconf',
        'tqdm',
    ],
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
        'torch.cuda',
        'nvidia',
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
