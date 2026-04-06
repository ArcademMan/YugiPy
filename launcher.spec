# -*- mode: python ; coding: utf-8 -*-

import os
import subprocess
from pathlib import Path

ROOT = os.path.abspath('.')

a = Analysis(
    ['launcher.py'],
    pathex=[ROOT],
    binaries=[],
    datas=[
        # Frontend (served by FastAPI StaticFiles)
        ('frontend', 'frontend'),
        # Backend package (imported at runtime by uvicorn)
        ('backend/app', 'backend/app'),
        ('backend/build_index.py', 'backend'),
        ('backend/alembic.ini', 'backend'),
        ('backend/alembic', 'backend/alembic'),
        # Assets
        ('assets/icon.png', 'assets'),
        ('assets/icon.ico', 'assets'),
        ('assets/yugipy-price-sync.xpi', 'assets'),
        # Extension source for users
        ('extension', 'extension'),
        # CLIP ONNX model + prebuilt card embeddings
        (os.path.join(os.environ.get('APPDATA', ''), 'AmMstools', 'YugiPy', 'data', 'clip_visual.onnx'), 'data'),
        (os.path.join(os.environ.get('APPDATA', ''), 'AmMstools', 'YugiPy', 'data', 'card_hashes.db'), 'data'),
    ],
    hiddenimports=[
        # -- FastAPI / Uvicorn stack --
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'fastapi',
        'fastapi.middleware.cors',
        'fastapi.staticfiles',
        'fastapi.responses',
        'starlette.responses',
        'starlette.websockets',
        'anyio._backends._asyncio',
        # -- Database --
        'sqlalchemy',
        'sqlalchemy.orm',
        'sqlalchemy.exc',
        'sqlalchemy.dialects.sqlite',
        # -- Pydantic --
        'pydantic',
        'pydantic._internal',
        # -- HTTP --
        'httpx',
        'httpx._transports',
        'httpcore',
        # -- Image / CV --
        'cv2',
        'PIL',
        'PIL.Image',
        'numpy',
        'imagehash',
        'pybktree',
        # -- OCR --
        'pytesseract',
        # -- ONNX Runtime (CLIP inference) --
        'onnxruntime',
        # -- SSL certs --
        'cryptography',
        # -- PySide6 --
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        # -- Backend modules (loaded by uvicorn as string path) --
        'backend',
        'backend.app',
        'backend.app.main',
        'backend.app.paths',
        'backend.app.database',
        'backend.app.models',
        'backend.app.schemas',
        'backend.app.hash_matcher',
        'backend.app.cardmarket_maps',
        'backend.app.routes',
        'backend.app.routes.scan',
        'backend.app.routes.cards',
        'backend.app.routes.cardmarket',
        'backend.app.routes.settings',
        'backend.app.routes.setup',
        'backend.app.routes.stats',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'pandas',
        'pytest',
        'IPython',
        'notebook',
        # Not needed at runtime — ONNX replaces PyTorch for inference
        'torch',
        'torchvision',
        'torchaudio',
        'open_clip',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='YugiPy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,        # No console window — PySide6 GUI only
    icon='assets/icon.ico',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='YugiPy',
)

# ── Build Inno Setup installer after COLLECT ──
ISCC = r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
ISS_FILE = os.path.join(ROOT, 'installer.iss')

if os.path.exists(ISCC) and os.path.exists(ISS_FILE):
    print(f'\n{"="*50}')
    print('  Building installer with Inno Setup...')
    print(f'{"="*50}\n')
    subprocess.run([ISCC, ISS_FILE], cwd=ROOT, check=True)
    print(f'\n{"="*50}')
    print('  Installer created in installer_output/')
    print(f'{"="*50}\n')
else:
    if not os.path.exists(ISCC):
        print(f'[WARN] Inno Setup not found at {ISCC}, skipping installer')
    if not os.path.exists(ISS_FILE):
        print(f'[WARN] installer.iss not found, skipping installer')
