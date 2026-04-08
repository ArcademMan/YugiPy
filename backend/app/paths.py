"""Centralized data paths for YugiPy.

All mutable data (databases, downloaded images) lives under a platform-specific
user data directory so the application can be installed system-wide without
permission issues.
"""

import os
import sys
from pathlib import Path

if sys.platform == "darwin":
    _BASE = Path.home() / "Library" / "Application Support" / "AmMstools" / "YugiPy"
elif sys.platform == "win32":
    _BASE = Path(os.environ.get("APPDATA", Path.home())) / "AmMstools" / "YugiPy"
else:
    _BASE = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "AmMstools" / "YugiPy"

DATA_DIR = _BASE / "data"

# Databases
COLLECTION_DB = DATA_DIR / "yugipy.db"
HASH_DB = DATA_DIR / "card_hashes.db"

# Downloaded images
IMAGES_DIR = DATA_DIR / "card_images"
FULL_IMAGES_DIR = DATA_DIR / "card_images_full"
CARDS_JSON = IMAGES_DIR / "_cards.json"


def ensure_dirs():
    """Create all data directories if they don't exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    IMAGES_DIR.mkdir(exist_ok=True)
    FULL_IMAGES_DIR.mkdir(exist_ok=True)
