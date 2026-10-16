# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules

datas = []
hiddenimports = []
datas += collect_data_files('lilt')
hiddenimports += collect_submodules('lilt')


a = Analysis(
    ['launch.pyw'],
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
# Qt on Windows uses the system ICU. An unrelated ICU on PATH has differently
# named exports and would prevent every Qt extension from loading if bundled.
a.binaries = [
    entry for entry in a.binaries
    if entry[0].rsplit('/', 1)[-1].rsplit('\\', 1)[-1].lower() != 'icuuc.dll'
    and not entry[0].rsplit('/', 1)[-1].rsplit('\\', 1)[-1].lower().startswith('icudt')
]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Lilt',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['tools/lilt.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Lilt',
)
