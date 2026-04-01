"""
Build the card image-hash index for artwork-based recognition.

Usage:
    python -m backend.build_index              # download ALL images (cropped + full) + build hashes
    python -m backend.build_index --rehash     # rebuild hashes from local full images (no download)
    python -m backend.build_index --update     # only download new cards
    python -m backend.build_index --full-only  # only download full card images (skip cropped)

Images are saved locally so hash parameters can be changed without re-downloading.
  - card_images/       → cropped artwork (624x624) for ORB matching
  - card_images_full/  → full card images for hash index building
"""

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import cv2
import imagehash
import numpy as np
from PIL import Image

YGOPRODECK_API = "https://db.ygoprodeck.com/api/v7/cardinfo.php"

# Import centralized paths (works both as module and standalone)
try:
    from backend.app.paths import HASH_DB as DB_PATH, IMAGES_DIR, FULL_IMAGES_DIR, CARDS_JSON, ensure_dirs
    ensure_dirs()
except ImportError:
    from app.paths import HASH_DB as DB_PATH, IMAGES_DIR, FULL_IMAGES_DIR, CARDS_JSON, ensure_dirs
    ensure_dirs()

HASH_SIZE = 8
REQUESTS_PER_SECOND = 12
BATCH_SIZE = 50

# Must match hash_matcher.py exactly
WARP_W = 590
WARP_H = 860
ARTWORK_REGION = {"x": 0.13, "y": 0.18, "w": 0.74, "h": 0.47}
NORMALIZE_SIZE = 256


def _init_db(conn: sqlite3.Connection):
    conn.execute("DROP TABLE IF EXISTS card_hashes")
    conn.execute("""
        CREATE TABLE card_hashes (
            card_id     INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            type        TEXT,
            frame_type  TEXT,
            race        TEXT,
            attribute   TEXT,
            archetype   TEXT,
            image_url   TEXT,
            phash       TEXT NOT NULL,
            dhash       TEXT NOT NULL,
            ahash       TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_phash ON card_hashes(phash)")
    conn.commit()


def _fetch_all_cards() -> list[dict]:
    import httpx
    print("Fetching card database from YGOProDeck...")
    with httpx.Client(timeout=60) as client:
        resp = client.get(YGOPRODECK_API)
        resp.raise_for_status()
        cards = resp.json()["data"]
    print(f"  -> {len(cards)} cards found")
    return cards


def _download_image(client, url: str) -> bytes | None:
    try:
        resp = client.get(url, timeout=15)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        print(f"  [WARN] Failed to download {url}: {e}")
        return None


def _extract_artwork_from_full(img_cv: np.ndarray) -> np.ndarray:
    """Resize full card to warp target and extract artwork region.

    Same pipeline as hash_matcher.extract_artwork, ensuring identical crops.
    """
    warped = cv2.resize(img_cv, (WARP_W, WARP_H))
    h, w = warped.shape[:2]
    x1 = int(w * ARTWORK_REGION["x"])
    y1 = int(h * ARTWORK_REGION["y"])
    x2 = int(w * (ARTWORK_REGION["x"] + ARTWORK_REGION["w"]))
    y2 = int(h * (ARTWORK_REGION["y"] + ARTWORK_REGION["h"]))
    return warped[y1:y2, x1:x2]


def normalize_for_hash(img: Image.Image) -> Image.Image:
    """Normalize an image before hashing.

    Aggressive contrast/brightness normalization so low-light camera
    images hash closer to clean digital references. Must be identical
    in build_index and hash_matcher.
    """
    gray = np.array(img.convert("L"))

    # Full histogram equalization — maps pixel distribution to uniform,
    # aggressively normalizing brightness differences
    gray = cv2.equalizeHist(gray)

    # CLAHE on top for local contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(4, 4))
    gray = clahe.apply(gray)

    # Resize to fixed square (no blur — preserve discriminative detail)
    gray = cv2.resize(gray, (NORMALIZE_SIZE, NORMALIZE_SIZE), interpolation=cv2.INTER_AREA)

    return Image.fromarray(gray)


def compute_hashes(img: Image.Image) -> tuple[str, str, str]:
    """Compute pHash, dHash, and aHash on a normalized image."""
    normalized = normalize_for_hash(img)
    p = str(imagehash.phash(normalized, hash_size=HASH_SIZE))
    d = str(imagehash.dhash(normalized, hash_size=HASH_SIZE))
    a = str(imagehash.average_hash(normalized, hash_size=HASH_SIZE))
    return p, d, a


def _download_batch(cards: list[dict], target_dir: Path, url_key: str,
                    update_only: bool = False):
    """Download images to target_dir, using url_key to pick the URL."""
    import httpx

    target_dir.mkdir(exist_ok=True)

    existing = set()
    if update_only:
        existing = {p.stem for p in target_dir.glob("*.jpg")}
        print(f"  -> {len(existing)} images already in {target_dir.name}/")

    to_download = []
    for card in cards:
        card_id = str(card["id"])
        if card_id in existing:
            continue
        images = card.get("card_images", [{}])
        url = images[0].get(url_key) if images else None
        if not url:
            continue
        to_download.append((card_id, url))

    if not to_download:
        print(f"  All {target_dir.name}/ images already downloaded.")
        return

    print(f"  Downloading {len(to_download)} images to {target_dir.name}/...")
    estimated_minutes = len(to_download) / REQUESTS_PER_SECOND / 60
    print(f"  Estimated time: ~{estimated_minutes:.0f} minutes")

    done = 0
    failed = 0
    interval = 1.0 / REQUESTS_PER_SECOND

    with httpx.Client(timeout=15) as client:
        for card_id, url in to_download:
            t0 = time.monotonic()

            data = _download_image(client, url)
            if data is None:
                failed += 1
            else:
                (target_dir / f"{card_id}.jpg").write_bytes(data)
                done += 1

            if done % BATCH_SIZE == 0 and done > 0:
                print(f"    [{done}/{len(to_download)}] downloaded... ({failed} failed)")

            elapsed = time.monotonic() - t0
            if elapsed < interval:
                time.sleep(interval - elapsed)

    print(f"  Done: {done} images ({failed} failed)")


def download_images(update_only: bool = False, full_only: bool = False):
    """Download card images from YGOProDeck and save locally."""
    cards = _fetch_all_cards()

    # Save card metadata
    IMAGES_DIR.mkdir(exist_ok=True)
    CARDS_JSON.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")

    if not full_only:
        print("\n[1/2] Cropped artwork images (for ORB matching):")
        _download_batch(cards, IMAGES_DIR, "image_url_cropped", update_only)

    print("\n[2/2] Full card images (for hash index):")
    _download_batch(cards, FULL_IMAGES_DIR, "image_url", update_only)


def build_hashes():
    """Build hash index from local full card images.

    Process: full card → resize to 590x860 → extract artwork region → normalize → hash.
    This matches the query pipeline in hash_matcher.py exactly.
    """
    if not CARDS_JSON.exists():
        print("No card data found. Run without --rehash first to download images.")
        return

    cards = json.loads(CARDS_JSON.read_text(encoding="utf-8"))
    print(f"Building hash index from full card images (hash_size={HASH_SIZE})...")

    conn = sqlite3.connect(str(DB_PATH))
    _init_db(conn)

    done = 0
    skipped = 0

    for card in cards:
        card_id = card["id"]
        img_path = FULL_IMAGES_DIR / f"{card_id}.jpg"

        if not img_path.exists():
            skipped += 1
            continue

        try:
            img_cv = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
            if img_cv is None:
                raise ValueError("Failed to decode image")

            # Same pipeline as camera: full card → warp size → extract artwork
            artwork_cv = _extract_artwork_from_full(img_cv)
            artwork_pil = Image.fromarray(cv2.cvtColor(artwork_cv, cv2.COLOR_BGR2RGB))

            phash, dhash, ahash = compute_hashes(artwork_pil)
        except Exception as e:
            print(f"  [WARN] Failed to hash {img_path.name}: {e}")
            skipped += 1
            continue

        conn.execute(
            """INSERT OR REPLACE INTO card_hashes
               (card_id, name, type, frame_type, race, attribute, archetype, image_url, phash, dhash, ahash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                card_id,
                card["name"],
                card.get("type", ""),
                card.get("frameType", ""),
                card.get("race"),
                card.get("attribute"),
                card.get("archetype"),
                card.get("card_images", [{}])[0].get("image_url"),
                phash,
                dhash,
                ahash,
            ),
        )

        done += 1
        if done % 1000 == 0:
            conn.commit()
            print(f"  [{done}] hashed...")

    conn.commit()
    conn.close()

    print(f"\nDone! {done} cards indexed, {skipped} skipped")
    print(f"Hash database: {DB_PATH} ({DB_PATH.stat().st_size / 1024 / 1024:.1f} MB)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build YugiPy card hash index")
    parser.add_argument("--update", action="store_true",
                        help="Only download cards not already saved locally")
    parser.add_argument("--rehash", action="store_true",
                        help="Rebuild hashes from local full images (no download)")
    parser.add_argument("--full-only", action="store_true",
                        help="Only download full card images (skip cropped)")
    args = parser.parse_args()

    try:
        if args.rehash:
            build_hashes()
        else:
            download_images(update_only=args.update, full_only=args.full_only)
            build_hashes()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
