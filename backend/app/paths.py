"""Centralized data paths for YugiPy.

All mutable data (databases, downloaded images) lives under APPDATA so the
application can be installed in Program Files without permission issues.
"""

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "AmMstools" / "YugiPy" / "data"

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
