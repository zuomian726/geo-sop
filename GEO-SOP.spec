# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['flask', 'flask_login', 'flask_sqlalchemy', 'flask_cors', 'playwright', 'requests', 'openpyxl', 'PIL', 'local_paths', 'profile_utils', 'browser_config', 'browser_utils', 'config', 'utils']
hiddenimports += collect_submodules('playwright')
hiddenimports += collect_submodules('apscheduler')


a = Analysis(
    ['desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=[('web_app', 'web_app'), ('platforms', 'platforms'), ('reference_sentiment', 'reference_sentiment'), ('tools', 'tools'), ('version.py', '.')],
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
    [],
    exclude_binaries=True,
    name='GEO-SOP',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['build/geo-sop-icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='GEO-SOP',
)
app = BUNDLE(
    coll,
    name='GEO-SOP.app',
    icon='build/geo-sop-icon.icns',
    bundle_identifier=None,
)
