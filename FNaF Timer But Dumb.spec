# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['timer_app.py'],
    pathex=[],
    binaries=[],
    datas=[('fnaf-timer_256x256_32bit.ico', '.')],
    hiddenimports=[],
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
    name='FNaF Timer But Dumb',
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
    icon=['C:\\Users\\thema\\OneDrive\\Documents\\GitHub\\fnaf-timer-but-dumb\\fnaf-timer_256x256_32bit.ico'],
)
