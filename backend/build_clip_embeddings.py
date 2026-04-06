"""
Build CLIP embedding index for all card artwork.

Usage:
    python -m backend.build_clip_embeddings
"""

import json
import sqlite3
import time

import cv2
import numpy as np
import torch
import open_clip
from PIL import Image

try:
    from backend.app.paths import FULL_IMAGES_DIR, CARDS_JSON, HASH_DB, ensure_dirs
    ensure_dirs()
except ImportError:
    from app.paths import FULL_IMAGES_DIR, CARDS_JSON, HASH_DB, ensure_dirs
    ensure_dirs()

WARP_W = 590
WARP_H = 860
ARTWORK_REGION = {"x": 0.13, "y": 0.18, "w": 0.74, "h": 0.47}


def _extract_artwork(img_cv):
    warped = cv2.resize(img_cv, (WARP_W, WARP_H))
    h, w = warped.shape[:2]
    x1 = int(w * ARTWORK_REGION["x"])
    y1 = int(h * ARTWORK_REGION["y"])
    x2 = int(w * (ARTWORK_REGION["x"] + ARTWORK_REGION["w"]))
    y2 = int(h * (ARTWORK_REGION["y"] + ARTWORK_REGION["h"]))
    return warped[y1:y2, x1:x2]


def main():
    if not CARDS_JSON.exists():
        print("No card data found. Run build_index first to download images.")
        return

    cards = json.loads(CARDS_JSON.read_text(encoding="utf-8"))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Device: {device}")
    print("Loading CLIP model...")
    model, _, preprocess = open_clip.create_model_and_transforms(
        "ViT-L-14", pretrained="laion2b_s32b_b82k", device=device
    )
    model.eval()
    print("CLIP model loaded.")

    conn = sqlite3.connect(str(HASH_DB))
    conn.execute("DROP TABLE IF EXISTS card_embeddings")
    conn.execute("""
        CREATE TABLE card_embeddings (
            card_id INTEGER PRIMARY KEY,
            embedding BLOB NOT NULL
        )
    """)

    done = 0
    skipped = 0
    t0 = time.time()

    # Process in batches for GPU efficiency
    BATCH = 64
    batch_ids = []
    batch_imgs = []

    for card in cards:
        card_id = card["id"]
        img_path = FULL_IMAGES_DIR / f"{card_id}.jpg"
        if not img_path.exists():
            skipped += 1
            continue

        img_cv = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
        if img_cv is None:
            skipped += 1
            continue

        artwork_cv = _extract_artwork(img_cv)
        artwork_pil = Image.fromarray(cv2.cvtColor(artwork_cv, cv2.COLOR_BGR2RGB)).convert("RGB")
        inp = preprocess(artwork_pil)
        batch_ids.append(card_id)
        batch_imgs.append(inp)

        if len(batch_imgs) >= BATCH:
            _process_batch(model, device, conn, batch_ids, batch_imgs)
            done += len(batch_ids)
            batch_ids = []
            batch_imgs = []
            if done % 1000 == 0:
                conn.commit()
                elapsed = time.time() - t0
                print(f"  [{done}/{len(cards)}] {elapsed:.0f}s")

    # Remaining
    if batch_imgs:
        _process_batch(model, device, conn, batch_ids, batch_imgs)
        done += len(batch_ids)

    conn.commit()
    conn.close()
    elapsed = time.time() - t0
    print(f"\nDone! {done} cards embedded, {skipped} skipped, {elapsed:.0f}s")


def _process_batch(model, device, conn, card_ids, imgs):
    import torch
    batch = torch.stack(imgs).to(device)
    with torch.no_grad():
        embs = model.encode_image(batch)
        embs = embs / embs.norm(dim=-1, keepdim=True)
    embs = embs.cpu().numpy().astype(np.float32)

    for i, card_id in enumerate(card_ids):
        vec = embs[i]
        conn.execute(
            "INSERT OR REPLACE INTO card_embeddings (card_id, embedding) VALUES (?, ?)",
            (card_id, vec.tobytes()),
        )


if __name__ == "__main__":
    main()
