"""Setup wizard API – download images and build hash index with live progress via SSE."""

import asyncio
import json
import sqlite3
import time

import cv2
import imagehash
import numpy as np
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from PIL import Image

from ..paths import (
    HASH_DB as DB_PATH,
    IMAGES_DIR,
    FULL_IMAGES_DIR,
    CARDS_JSON,
    ensure_dirs,
)

router = APIRouter(prefix="/api/setup", tags=["setup"])

ensure_dirs()

YGOPRODECK_API = "https://db.ygoprodeck.com/api/v7/cardinfo.php"
REQUESTS_PER_SECOND = 12
HASH_SIZE = 8
WARP_W = 590
WARP_H = 860
ARTWORK_REGION = {"x": 0.13, "y": 0.18, "w": 0.74, "h": 0.47}
NORMALIZE_SIZE = 256

# Simple state to prevent concurrent runs and allow cancellation
_state = {"running": False, "cancel": False}


@router.get("/status")
def setup_status():
    """Return current index status: how many images and whether hash DB exists."""
    cropped_count = len(list(IMAGES_DIR.glob("*.jpg"))) if IMAGES_DIR.exists() else 0
    full_count = len(list(FULL_IMAGES_DIR.glob("*.jpg"))) if FULL_IMAGES_DIR.exists() else 0
    has_hash_db = DB_PATH.exists()
    hash_db_size = DB_PATH.stat().st_size if has_hash_db else 0

    hash_count = 0
    if has_hash_db:
        try:
            conn = sqlite3.connect(str(DB_PATH))
            hash_count = conn.execute("SELECT COUNT(*) FROM card_hashes").fetchone()[0]
            conn.close()
        except Exception:
            pass

    return {
        "cropped_images": cropped_count,
        "full_images": full_count,
        "has_hash_db": has_hash_db,
        "hash_db_size": hash_db_size,
        "hash_count": hash_count,
        "ready": has_hash_db and hash_count > 0,
        "running": _state["running"],
    }


@router.post("/cancel")
def cancel_setup():
    """Cancel a running setup process."""
    if _state["running"]:
        _state["cancel"] = True
        return {"ok": True}
    return {"ok": False, "error": "not_running"}


@router.get("/run")
async def run_setup():
    """Run the full setup (download images + build hashes) with SSE progress."""
    if _state["running"]:
        async def already():
            yield f"data: {json.dumps({'error': 'already_running'})}\n\n"
        return StreamingResponse(already(), media_type="text/event-stream")

    return StreamingResponse(_setup_stream(), media_type="text/event-stream")


@router.get("/download-images")
async def download_images():
    """Download missing full card images (all cards in YGOProDeck DB). SSE progress."""
    if _state["running"]:
        async def already():
            yield f"data: {json.dumps({'error': 'already_running'})}\n\n"
        return StreamingResponse(already(), media_type="text/event-stream")

    return StreamingResponse(_download_images_stream(), media_type="text/event-stream")


async def _download_images_stream():
    import httpx

    _state["running"] = True
    _state["cancel"] = False

    try:
        yield _sse("info", message="Fetching card database...")

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(YGOPRODECK_API)
                resp.raise_for_status()
                cards = resp.json()["data"]
        except Exception as e:
            yield _sse("error", message=f"Failed to fetch card database: {e}")
            return

        # Collect all image IDs (including alternate arts)
        FULL_IMAGES_DIR.mkdir(exist_ok=True)
        existing = {p.stem for p in FULL_IMAGES_DIR.glob("*.jpg")}

        to_download = []
        for card in cards:
            for img in card.get("card_images", []):
                img_id = str(img["id"])
                url = img.get("image_url")
                if img_id not in existing and url:
                    to_download.append((img_id, url))

        total = len(to_download)
        if total == 0:
            yield _sse("done", message="All images already downloaded")
            return

        yield _sse("info", message=f"{total} images to download")

        done = 0
        failed = 0
        interval = 1.0 / REQUESTS_PER_SECOND

        async with httpx.AsyncClient(timeout=15) as client:
            for img_id, url in to_download:
                if _state["cancel"]:
                    yield _sse("cancelled")
                    return

                t0 = time.monotonic()
                try:
                    resp = await client.get(url, timeout=15)
                    resp.raise_for_status()
                    (FULL_IMAGES_DIR / f"{img_id}.jpg").write_bytes(resp.content)
                    done += 1
                except Exception:
                    failed += 1

                if (done + failed) % 50 == 0 or (done + failed) == total:
                    yield _sse("progress", done=done + failed, total=total, ok=done, failed=failed)

                elapsed = time.monotonic() - t0
                if elapsed < interval:
                    await asyncio.sleep(interval - elapsed)

        yield _sse("done", message=f"Downloaded {done} images, {failed} failed")

    except Exception as e:
        yield _sse("error", message=str(e))
    finally:
        _state["running"] = False


def _sse(event_type: str, **data):
    """Format an SSE message."""
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload)}\n\n"


async def _setup_stream():
    import httpx

    _state["running"] = True
    _state["cancel"] = False

    try:
        # Step 1: Fetch card database
        yield _sse("step", step=1, label="Scaricamento database carte...")
        await asyncio.sleep(0)

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(YGOPRODECK_API)
                resp.raise_for_status()
                cards = resp.json()["data"]
        except Exception as e:
            yield _sse("error", message=f"Errore scaricamento database: {e}")
            return

        total_cards = len(cards)
        yield _sse("info", message=f"{total_cards} carte trovate")

        # Save card metadata
        IMAGES_DIR.mkdir(exist_ok=True)
        CARDS_JSON.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")

        # Step 2: Download cropped artwork
        yield _sse("step", step=2, label="Download artwork ritagliati...")
        await asyncio.sleep(0)

        if _state["cancel"]:
            yield _sse("cancelled")
            return

        cropped_stats = await _download_batch_async(cards, IMAGES_DIR, "image_url_cropped",
                                                     "cropped", lambda msg: msg)
        if cropped_stats is None:
            yield _sse("cancelled")
            return
        for msg in cropped_stats["messages"]:
            yield msg

        # Step 3: Download full card images
        yield _sse("step", step=3, label="Download immagini complete...")
        await asyncio.sleep(0)

        if _state["cancel"]:
            yield _sse("cancelled")
            return

        full_stats = await _download_batch_async(cards, FULL_IMAGES_DIR, "image_url",
                                                  "full", lambda msg: msg)
        if full_stats is None:
            yield _sse("cancelled")
            return
        for msg in full_stats["messages"]:
            yield msg

        # Step 4: Build hash index
        yield _sse("step", step=4, label="Costruzione indice hash...")
        await asyncio.sleep(0)

        if _state["cancel"]:
            yield _sse("cancelled")
            return

        hash_messages = list(_build_hashes_with_progress(cards))
        for msg in hash_messages:
            yield msg

        yield _sse("done")

    except Exception as e:
        yield _sse("error", message=str(e))
    finally:
        _state["running"] = False


async def _download_batch_async(cards, target_dir, url_key, phase, _wrap):
    import httpx

    target_dir.mkdir(exist_ok=True)
    existing = {p.stem for p in target_dir.glob("*.jpg")}

    to_download = []
    for card in cards:
        card_id = str(card["id"])
        if card_id in existing:
            continue
        images = card.get("card_images", [{}])
        url = images[0].get(url_key) if images else None
        if url:
            to_download.append((card_id, url))

    total = len(to_download)
    messages = []

    if total == 0:
        messages.append(_sse("progress", phase=phase, done=0, total=0,
                             message="Tutte le immagini già presenti"))
        return {"messages": messages, "done": 0, "failed": 0}

    messages.append(_sse("progress", phase=phase, done=0, total=total,
                         message=f"{total} immagini da scaricare"))

    done = 0
    failed = 0
    interval = 1.0 / REQUESTS_PER_SECOND

    async with httpx.AsyncClient(timeout=15) as client:
        for card_id, url in to_download:
            if _state["cancel"]:
                return None

            t0 = time.monotonic()
            try:
                resp = await client.get(url, timeout=15)
                resp.raise_for_status()
                (target_dir / f"{card_id}.jpg").write_bytes(resp.content)
                done += 1
            except Exception:
                failed += 1

            if (done + failed) % 50 == 0 or (done + failed) == total:
                messages.append(_sse("progress", phase=phase,
                                     done=done + failed, total=total,
                                     ok=done, failed=failed))

            elapsed = time.monotonic() - t0
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed)

    messages.append(_sse("progress", phase=phase, done=total, total=total,
                         ok=done, failed=failed,
                         message=f"Completato: {done} scaricate, {failed} fallite"))
    return {"messages": messages, "done": done, "failed": failed}


def _extract_artwork(img_cv):
    warped = cv2.resize(img_cv, (WARP_W, WARP_H))
    h, w = warped.shape[:2]
    x1 = int(w * ARTWORK_REGION["x"])
    y1 = int(h * ARTWORK_REGION["y"])
    x2 = int(w * (ARTWORK_REGION["x"] + ARTWORK_REGION["w"]))
    y2 = int(h * (ARTWORK_REGION["y"] + ARTWORK_REGION["h"]))
    return warped[y1:y2, x1:x2]


def _normalize_for_hash(img):
    gray = np.array(img.convert("L"))
    gray = cv2.equalizeHist(gray)
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(4, 4))
    gray = clahe.apply(gray)
    gray = cv2.resize(gray, (NORMALIZE_SIZE, NORMALIZE_SIZE), interpolation=cv2.INTER_AREA)
    return Image.fromarray(gray)


def _build_hashes_with_progress(cards):
    conn = sqlite3.connect(str(DB_PATH))
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

    total = len(cards)
    done = 0
    skipped = 0

    for card in cards:
        if _state["cancel"]:
            conn.close()
            yield _sse("cancelled")
            return

        card_id = card["id"]
        img_path = FULL_IMAGES_DIR / f"{card_id}.jpg"

        if not img_path.exists():
            skipped += 1
            continue

        try:
            img_cv = cv2.imread(str(img_path), cv2.IMREAD_COLOR)
            if img_cv is None:
                raise ValueError("decode failed")
            artwork_cv = _extract_artwork(img_cv)
            artwork_pil = Image.fromarray(cv2.cvtColor(artwork_cv, cv2.COLOR_BGR2RGB))
            normalized = _normalize_for_hash(artwork_pil)
            phash = str(imagehash.phash(normalized, hash_size=HASH_SIZE))
            dhash = str(imagehash.dhash(normalized, hash_size=HASH_SIZE))
            ahash = str(imagehash.average_hash(normalized, hash_size=HASH_SIZE))
        except Exception:
            skipped += 1
            continue

        conn.execute(
            """INSERT OR REPLACE INTO card_hashes
               (card_id, name, type, frame_type, race, attribute, archetype, image_url,
                phash, dhash, ahash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (card_id, card["name"], card.get("type", ""), card.get("frameType", ""),
             card.get("race"), card.get("attribute"), card.get("archetype"),
             card.get("card_images", [{}])[0].get("image_url"),
             phash, dhash, ahash),
        )

        done += 1
        if done % 500 == 0:
            conn.commit()
            yield _sse("progress", phase="hash", done=done + skipped, total=total,
                        ok=done, skipped=skipped)

    conn.commit()
    conn.close()
    yield _sse("progress", phase="hash", done=total, total=total,
                ok=done, skipped=skipped,
                message=f"Indicizzate {done} carte, {skipped} saltate")
