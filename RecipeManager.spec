# PyInstaller spec for Recipe Manager
#
# Cross-platform: produces a single-file binary on whichever OS you run it on.
#   Windows:  pyinstaller --clean --noconfirm RecipeManager.spec   →  dist/RecipeManager.exe
#   Linux:    pyinstaller --clean --noconfirm RecipeManager.spec   →  dist/RecipeManager       (ELF)
#   macOS:    pyinstaller --clean --noconfirm RecipeManager.spec   →  dist/RecipeManager       (Mach-O)
#
# NOTE: PyInstaller does NOT cross-compile. You must run it on each target OS
# (either natively or via CI / a VM). See .github/workflows/build.yml for an
# automated multi-OS build.

import os
import sys

block_cipher = None

repo_dir = os.path.abspath(os.path.dirname(SPEC))  # noqa: F821 (provided by PyInstaller)
is_windows = sys.platform.startswith("win")

# Bundle the seed DB only if it exists; otherwise the app will create an empty
# database with demo data on first run.
datas = []
seed_db = os.path.join(repo_dir, ".recipe_manager.db")
if os.path.exists(seed_db):
    datas.append((seed_db, "."))


a = Analysis(  # noqa: F821
    ["main.py"],
    pathex=[repo_dir],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # recipe-scrapers loads site modules dynamically; collect them.
        "recipe_scrapers",
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
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="RecipeManager",     # PyInstaller appends .exe automatically on Windows
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    # console=False hides the terminal window on Windows. On Linux/macOS this
    # flag is effectively ignored for GUI apps but kept for cross-OS parity.
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
