import base64
import re

import cv2
import httpx
import numpy as np
from fastapi import APIRouter, Form, UploadFile, File, HTTPException
from PIL import Image

from ..schemas import CardSet, ScanCandidate, ScanResult
from ..hash_matcher import match_artwork, is_index_available

router = APIRouter(prefix="/api", tags=["scan"])

YGOPRODECK_API = "https://db.ygoprodeck.com/api/v7/cardinfo.php"

# Warp target size (pixels) for the straightened card
WARP_W = 590
WARP_H = 860

# Fixed artwork region on a standard Yu-Gi-Oh card (warped)
ARTWORK_REGION = {"x": 0.13, "y": 0.18, "w": 0.74, "h": 0.47}


# =============================================================
# Helpers
# =============================================================

def _img_to_b64(img_cv: np.ndarray, quality: int = 80) -> str:
    _, buf = cv2.imencode(".jpg", img_cv, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf.tobytes()).decode()


def _apply_rotation(img_cv: np.ndarray, rotation: int) -> np.ndarray:
    if rotation == 90:
        return cv2.rotate(img_cv, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == 180:
        return cv2.rotate(img_cv, cv2.ROTATE_180)
    elif rotation == 270:
        return cv2.rotate(img_cv, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img_cv


def _extract_artwork_direct(warped_cv: np.ndarray) -> np.ndarray:
    """Extract artwork from a warped card image (590x860) using fixed proportions."""
    h, w = warped_cv.shape[:2]
    x1 = int(w * ARTWORK_REGION["x"])
    y1 = int(h * ARTWORK_REGION["y"])
    x2 = int(w * (ARTWORK_REGION["x"] + ARTWORK_REGION["w"]))
    y2 = int(h * (ARTWORK_REGION["y"] + ARTWORK_REGION["h"]))
    return warped_cv[y1:y2, x1:x2]


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# =============================================================
# Card parsing
# =============================================================

def _parse_sets(card_sets: list[dict]) -> list[CardSet]:
    return [
        CardSet(
            set_name=s.get("set_name", ""),
            set_code=s.get("set_code", ""),
            set_rarity=s.get("set_rarity", ""),
            set_price=_safe_float(s.get("set_price")),
        )
        for s in card_sets
    ]


def _parse_candidate(data: dict) -> ScanCandidate:
    prices = data.get("card_prices", [{}])[0]
    images = data.get("card_images", [{}])[0]
    card_sets = data.get("card_sets", [])

    return ScanCandidate(
        card_id=data["id"],
        name=data.get("name_en") or data["name"],
        type=data["type"],
        frame_type=data.get("frameType", ""),
        description=data.get("desc", ""),
        atk=data.get("atk"),
        def_=data.get("def"),
        level=data.get("level"),
        race=data.get("race"),
        attribute=data.get("attribute"),
        archetype=data.get("archetype"),
        image_url=images.get("image_url"),
        price_cardmarket=_safe_float(prices.get("cardmarket_price")),
        price_tcgplayer=_safe_float(prices.get("tcgplayer_price")),
        sets=_parse_sets(card_sets),
    )


# =============================================================
# Endpoints
# =============================================================

@router.post("/ocr-preview")
async def ocr_preview(
    file: UploadFile = File(...),
    rotation: int = Form(default=0),
):
    """Live preview: extract artwork directly from card-shaped crop and match."""
    contents = await file.read()
    if not contents:
        return {"mode": "no_image"}

    img_cv = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
    if img_cv is None:
        return {"mode": "no_image"}

    if rotation:
        img_cv = _apply_rotation(img_cv, rotation)

    # Frontend sends a card-shaped crop from the overlay guide.
    # Just resize to standard card dimensions — no card detection.
    warped = cv2.resize(img_cv, (WARP_W, WARP_H))
    warped_b64 = _img_to_b64(warped, quality=70)

    artwork_cv = _extract_artwork_direct(warped)
    artwork_b64 = _img_to_b64(artwork_cv, quality=80)

    # Match
    hash_match_name = ""
    hash_match_confidence = 0.0
    hash_match_image = ""
    if is_index_available():
        matches = match_artwork(warped, top_n=3)
        if matches:
            hash_match_name = matches[0]["name"]
            hash_match_confidence = matches[0]["confidence"]
            hash_match_image = matches[0].get("image_url", "")

    return {
        "mode": "detected",
        "debug_image": warped_b64,
        "warped_image": warped_b64,
        "hash_match_name": hash_match_name,
        "hash_match_confidence": hash_match_confidence,
        "hash_match_image": hash_match_image,
        "artwork_debug": artwork_b64,
    }


@router.post("/scan", response_model=ScanResult)
async def scan_card(
    file: UploadFile = File(...),
    rotation: int = Form(default=0),
):
    """Match card from overlay crop — no card detection needed."""
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    img_cv = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
    if img_cv is None:
        raise HTTPException(status_code=400, detail="Invalid image")

    if rotation:
        img_cv = _apply_rotation(img_cv, rotation)

    # Frontend sends card-shaped crop — just resize, no card detection
    warped = cv2.resize(img_cv, (WARP_W, WARP_H))

    # Image matching (CLIP embedding)
    if not is_index_available():
        raise HTTPException(
            status_code=422,
            detail="Indice non disponibile. Esegui il setup prima di scansionare.",
        )

    all_matches = match_artwork(warped, top_n=10)
    if not all_matches:
        raise HTTPException(
            status_code=422,
            detail="Impossibile identificare la carta. Prova a posizionarla meglio nell'overlay.",
        )

    top5 = [(m["name"], round(m["confidence"], 4)) for m in all_matches[:5]]
    print(f"[scan] top5: {top5}")
    best_conf = all_matches[0]["confidence"]
    # Only show other results if very close to top match
    gap = best_conf - (all_matches[1]["confidence"] if len(all_matches) > 1 else 0)
    if gap > 0.03:
        # Clear winner — show only top match
        hash_matches = all_matches[:1]
    else:
        # Ambiguous — show results within 0.02 of top
        hash_matches = [all_matches[0]]
        for m in all_matches[1:]:
            if m["confidence"] >= best_conf - 0.02:
                hash_matches.append(m)
            else:
                break

    # Build candidates from API
    candidates = []
    matched_ids = [m["card_id"] for m in hash_matches]
    async with httpx.AsyncClient(timeout=10) as client:
        for card_id in matched_ids:
            try:
                resp = await client.get(YGOPRODECK_API, params={"id": card_id})
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    if data:
                        candidates.append(_parse_candidate(data[0]))
            except Exception:
                continue

    extracted = f"[Image Match] {hash_matches[0]['name']} ({hash_matches[0]['confidence']:.0%})"

    return ScanResult(
        extracted_text=extracted,
        candidates=candidates,
    )


# =============================================================
# Set code search
# =============================================================

YGOPRODECK_SETS_API = "https://db.ygoprodeck.com/api/v7/cardsets.php"

# Cache: set code prefix → set name (loaded on first use)
_SET_CODE_MAP: dict[str, str] | None = None


async def _get_set_code_map() -> dict[str, str]:
    global _SET_CODE_MAP
    if _SET_CODE_MAP is None:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(YGOPRODECK_SETS_API)
                if resp.status_code == 200:
                    _SET_CODE_MAP = {}
                    for s in resp.json():
                        code = s.get("set_code", "").upper()
                        if code and code not in _SET_CODE_MAP:
                            # Keep the first (base) variant for each code
                            _SET_CODE_MAP[code] = s["set_name"]
        except Exception:
            pass
        if _SET_CODE_MAP is None:
            _SET_CODE_MAP = {}
        print(f"[scan] Loaded {len(_SET_CODE_MAP)} set code mappings")
    return _SET_CODE_MAP


@router.get("/search", response_model=list[ScanCandidate])
async def search_card(q: str):
    """Search cards by name or set code (e.g. BLMR-IT065, BLMR). Returns candidates with sets."""
    if len(q) < 2:
        raise HTTPException(status_code=400, detail="Query too short")

    q_upper = q.strip().upper()

    # Detect set code pattern: "BLMR", "BLMR-IT065", "MP23-EN044"
    set_code_match = re.match(r"^([A-Z0-9]{2,6})(?:-[A-Z]{0,3}\d{0,4})?$", q_upper)

    if set_code_match:
        prefix = set_code_match.group(1)
        code_map = await _get_set_code_map()
        set_name = code_map.get(prefix)

        if set_name:
            # Search all cards in this set
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    YGOPRODECK_API, params={"cardset": set_name}
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    if data:
                        # If full set code given (e.g. BLMR-IT065), filter to that specific card
                        # Normalize: strip the language part to match regardless of IT/EN/FR/DE
                        # TN23-IT016 → TN23-???016, matches TN23-EN016
                        if "-" in q_upper and len(q_upper) > len(prefix) + 1:
                            # Extract number suffix (e.g. "016" from "TN23-IT016")
                            num_match = re.search(r"(\d+)$", q_upper)
                            num_suffix = num_match.group(1) if num_match else ""

                            filtered = [
                                card for card in data
                                if any(
                                    cs.get("set_code", "").upper().startswith(prefix)
                                    and cs.get("set_code", "").upper().endswith(num_suffix)
                                    for cs in card.get("card_sets", [])
                                )
                            ] if num_suffix else []
                            if filtered:
                                return [_parse_candidate(card) for card in filtered]
                        # Otherwise return all cards in the set
                        return [_parse_candidate(card) for card in data]

    # Fallback: search by name (fname = fuzzy name)
    async with httpx.AsyncClient(timeout=10) as client:
        for lang_params in [{"language": "it"}, {}]:
            resp = await client.get(
                YGOPRODECK_API, params={"fname": q, **lang_params}
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    return [_parse_candidate(card) for card in data]

    return []
