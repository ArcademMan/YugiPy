import base64
import re

import cv2
import httpx
import numpy as np
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"D:\Tools\Tesseract\tesseract.exe"
from fastapi import APIRouter, Form, UploadFile, File, HTTPException
from PIL import Image

from ..schemas import CardBase, CardSet, ScanCandidate, ScanResult
from ..hash_matcher import match_artwork, is_index_available

router = APIRouter(prefix="/api", tags=["scan"])

YGOPRODECK_API = "https://db.ygoprodeck.com/api/v7/cardinfo.php"

# --- Yu-Gi-Oh card proportions ---
CARD_RATIO = 59 / 86  # ~0.686
CARD_RATIO_TOLERANCE = 0.15

# Warp target size (pixels) for the straightened card
WARP_W = 590
WARP_H = 860

# Fixed set code zone on a standard Yu-Gi-Oh card (warped)
SET_CODE_ZONE = {"x": 0.55, "y": 0.71, "w": 0.42, "h": 0.04}
# Fixed card name zone (fallback OCR)
CARD_NAME_ZONE = {"x": 0.04, "y": 0.03, "w": 0.76, "h": 0.05}

OCR_DEFAULTS = {"clip_limit": 3.0, "block_size": 31, "c_value": 10, "denoise": 12}
# Lighter preprocessing for set code (small dark text on light background)
OCR_SETCODE = {"clip_limit": 1.5, "block_size": 15, "c_value": 5, "denoise": 0}


# =============================================================
# Card detection via OpenCV
# =============================================================

def _order_points(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]
    rect[3] = pts[np.argmax(d)]
    return rect


def _detect_card(img_cv: np.ndarray) -> np.ndarray | None:
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

    # Two blur strategies: Gaussian (general) + bilateral (preserves edges better)
    blurred_g = cv2.GaussianBlur(gray, (5, 5), 0)
    blurred_b = cv2.bilateralFilter(gray, 9, 75, 75)

    candidates = []

    # Canny edge detection with multiple thresholds on both blurs
    for blurred in [blurred_g, blurred_b]:
        for thresh_lo, thresh_hi in [(20, 60), (30, 100), (50, 150), (80, 200)]:
            edges = cv2.Canny(blurred, thresh_lo, thresh_hi)
            edges = cv2.dilate(edges, None, iterations=2)
            contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            candidates.extend(contours)

    # Adaptive threshold (two block sizes)
    for block_size, c_val in [(15, 4), (25, 6)]:
        bw = cv2.adaptiveThreshold(blurred_g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY, block_size, c_val)
        contours2, _ = cv2.findContours(bw, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates.extend(contours2)

    # Otsu threshold (good for high contrast card on solid background)
    _, otsu = cv2.threshold(blurred_g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    contours3, _ = cv2.findContours(otsu, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates.extend(contours3)

    candidates.sort(key=cv2.contourArea, reverse=True)
    img_area = img_cv.shape[0] * img_cv.shape[1]

    for contour in candidates[:40]:
        area = cv2.contourArea(contour)
        if area < img_area * 0.02 or area > img_area * 0.95:
            continue

        peri = cv2.arcLength(contour, True)

        # Try multiple epsilon values for polygon approximation
        for eps_mult in [0.02, 0.03, 0.04, 0.05]:
            approx = cv2.approxPolyDP(contour, eps_mult * peri, True)

            if len(approx) != 4:
                continue

            pts = _order_points(approx.reshape(4, 2))

            w_top = np.linalg.norm(pts[1] - pts[0])
            w_bot = np.linalg.norm(pts[2] - pts[3])
            h_left = np.linalg.norm(pts[3] - pts[0])
            h_right = np.linalg.norm(pts[2] - pts[1])

            avg_w = (w_top + w_bot) / 2
            avg_h = (h_left + h_right) / 2

            if avg_h == 0 or avg_w == 0:
                continue

            ratio = min(avg_w, avg_h) / max(avg_w, avg_h)
            if abs(ratio - CARD_RATIO) <= CARD_RATIO_TOLERANCE:
                if avg_w > avg_h:
                    pts = np.array([pts[3], pts[0], pts[1], pts[2]])
                return pts

    return None


def _warp_card(img_cv: np.ndarray, pts: np.ndarray) -> np.ndarray:
    dst = np.array([
        [0, 0],
        [WARP_W - 1, 0],
        [WARP_W - 1, WARP_H - 1],
        [0, WARP_H - 1],
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(pts.astype("float32"), dst)
    return cv2.warpPerspective(img_cv, M, (WARP_W, WARP_H))


# High-res warp multiplier for OCR zones
HIRES_SCALE = 4  # 590*4=2360, 860*4=3440


def _warp_card_hires(img_cv: np.ndarray, pts: np.ndarray) -> np.ndarray:
    """Warp the card at high resolution for OCR. Uses the full camera resolution."""
    hires_w = WARP_W * HIRES_SCALE
    hires_h = WARP_H * HIRES_SCALE
    dst = np.array([
        [0, 0],
        [hires_w - 1, 0],
        [hires_w - 1, hires_h - 1],
        [0, hires_h - 1],
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(pts.astype("float32"), dst)
    return cv2.warpPerspective(img_cv, M, (hires_w, hires_h))


def _img_to_b64(img_cv: np.ndarray, quality: int = 80) -> str:
    _, buf = cv2.imencode(".jpg", img_cv, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.b64encode(buf.tobytes()).decode()


# =============================================================
# OCR (used only in final scan, not in live preview)
# =============================================================

def _preprocess_for_ocr(
    cropped: Image.Image,
    upscale: int = 1,
    clip_limit: float = 3.0,
    block_size: int = 31,
    c_value: int = 10,
    denoise: int = 12,
    invert: bool = False,
) -> Image.Image:
    if upscale > 1:
        cropped = cropped.resize(
            (cropped.width * upscale, cropped.height * upscale),
            Image.LANCZOS,
        )

    img_cv = np.array(cropped.convert("RGB"))
    img_cv = cv2.cvtColor(img_cv, cv2.COLOR_RGB2GRAY)

    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
    img_cv = clahe.apply(img_cv)

    if denoise > 0:
        img_cv = cv2.fastNlMeansDenoising(img_cv, h=denoise)

    bs = max(3, block_size)
    if bs % 2 == 0:
        bs += 1

    thresh_type = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
    img_cv = cv2.adaptiveThreshold(
        img_cv, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        thresh_type,
        blockSize=bs,
        C=c_value,
    )

    return Image.fromarray(img_cv)


def _ocr_zone(card_img: np.ndarray, zone: dict, is_set_code: bool = False) -> str:
    """OCR a fixed zone on the warped card. Tries normal + inverted threshold."""
    h, w = card_img.shape[:2]
    left = int(w * zone["x"])
    top = int(h * zone["y"])
    right = int(w * (zone["x"] + zone["w"]))
    bottom = int(h * (zone["y"] + zone["h"]))

    cropped_cv = card_img[top:bottom, left:right]
    cropped_pil = Image.fromarray(cv2.cvtColor(cropped_cv, cv2.COLOR_BGR2RGB))

    ocr_params = OCR_SETCODE if is_set_code else OCR_DEFAULTS
    upscale = 2  # hires warp already provides good resolution
    best = ""

    for invert in [False, True]:
        processed = _preprocess_for_ocr(cropped_pil, upscale=upscale, invert=invert, **ocr_params)

        if is_set_code:
            whitelist = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
            config = f"--psm 7 -c tessedit_char_whitelist={whitelist}"
            try:
                text = pytesseract.image_to_string(processed, config=config).strip()
                if sum(1 for c in text if c.isalpha()) > sum(1 for c in best if c.isalpha()):
                    best = text
            except Exception:
                pass
        else:
            for psm in ["--psm 7", "--psm 6"]:
                try:
                    text = pytesseract.image_to_string(processed, config=psm)
                    for line in text.splitlines():
                        cleaned = line.strip()
                        if len(cleaned) >= 2 and not cleaned.isdigit() and len(cleaned) > len(best):
                            best = cleaned
                except Exception:
                    continue

    return best.strip()


def _clean_card_name(raw: str) -> str:
    cleaned = re.sub(r"[^\w\s\-'.]", "", raw, flags=re.UNICODE).strip()
    return re.sub(r"\s+", " ", cleaned)


def _clean_set_code(raw: str) -> str:
    match = re.search(r"[A-Z0-9]{2,5}[-–][A-Z]{0,3}\d{2,4}", raw.upper())
    if match:
        return match.group().replace("–", "-")
    return re.sub(r"[^A-Z0-9\-]", "", raw.upper()).strip()


# =============================================================
# API search
# =============================================================

async def _search_api(client: httpx.AsyncClient, params: dict) -> list[dict]:
    try:
        resp = await client.get(YGOPRODECK_API, params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("data", [])
    except Exception:
        pass
    return []


async def _fuzzy_search(card_name: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        for lang_params in [{"language": "it"}, {}]:
            results = await _search_api(client, {"fname": card_name, **lang_params})
            if results:
                return results

            words = card_name.split()

            if len(words) > 1:
                shorter = " ".join(words[:-1])
                results = await _search_api(client, {"fname": shorter, **lang_params})
                if results:
                    return results

            for n in range(min(len(words), 3), 0, -1):
                partial = " ".join(words[:n])
                if len(partial) < 3:
                    continue
                results = await _search_api(client, {"fname": partial, **lang_params})
                if results:
                    return results

    return []


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


# =============================================================
# Card parsing
# =============================================================

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


def _parse_card(data: dict) -> CardBase:
    prices = data.get("card_prices", [{}])[0]
    images = data.get("card_images", [{}])[0]
    return CardBase(
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
    )


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# =============================================================
# Helpers
# =============================================================

def _apply_rotation(img_cv: np.ndarray, rotation: int) -> np.ndarray:
    if rotation == 90:
        return cv2.rotate(img_cv, cv2.ROTATE_90_CLOCKWISE)
    elif rotation == 180:
        return cv2.rotate(img_cv, cv2.ROTATE_180)
    elif rotation == 270:
        return cv2.rotate(img_cv, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img_cv


def _draw_detection_debug(img_cv: np.ndarray, pts: np.ndarray | None) -> np.ndarray:
    vis = img_cv.copy()
    if pts is None:
        cv2.putText(vis, "Carta non rilevata", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        return vis

    pts_int = pts.astype(int)
    cv2.polylines(vis, [pts_int], True, (0, 255, 0), 3)

    for i, label in enumerate(["TL", "TR", "BR", "BL"]):
        cv2.putText(vis, label, tuple(pts_int[i]), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    return vis


# =============================================================
# Endpoints
# =============================================================

@router.post("/ocr-preview")
async def ocr_preview(
    file: UploadFile = File(...),
    rotation: int = Form(default=0),
):
    """Live preview: detect card + image hash match. No OCR in preview."""
    contents = await file.read()
    if not contents:
        return {"mode": "no_image"}

    img_cv = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
    if img_cv is None:
        return {"mode": "no_image"}

    if rotation:
        img_cv = _apply_rotation(img_cv, rotation)

    pts = _detect_card(img_cv)
    debug_img = _draw_detection_debug(img_cv, pts)
    debug_b64 = _img_to_b64(debug_img, quality=60)

    if pts is None:
        return {
            "mode": "no_card",
            "debug_image": debug_b64,
        }

    warped = _warp_card(img_cv, pts)

    # Image hash matching
    hash_match_name = ""
    hash_match_confidence = 0.0
    hash_match_image = ""
    artwork_b64 = ""
    if is_index_available():
        from ..hash_matcher import extract_artwork
        artwork_pil = extract_artwork(warped)
        import io as _io
        buf = _io.BytesIO()
        artwork_pil.save(buf, format="JPEG", quality=80)
        artwork_b64 = base64.b64encode(buf.getvalue()).decode()

        matches = match_artwork(warped, top_n=3)
        if matches:
            hash_match_name = matches[0]["name"]
            hash_match_confidence = matches[0]["confidence"]
            hash_match_image = matches[0].get("image_url", "")

    warped_b64 = _img_to_b64(warped, quality=70)


    return {
        "mode": "detected",
        "debug_image": debug_b64,
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
    """Detect card, match via image hash (primary) or OCR (fallback)."""
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    img_cv = cv2.imdecode(np.frombuffer(contents, np.uint8), cv2.IMREAD_COLOR)
    if img_cv is None:
        raise HTTPException(status_code=400, detail="Invalid image")

    if rotation:
        img_cv = _apply_rotation(img_cv, rotation)

    pts = _detect_card(img_cv)
    if pts is None:
        raise HTTPException(
            status_code=422,
            detail="Carta non rilevata nell'immagine. Assicurati che la carta sia ben visibile su uno sfondo contrastante.",
        )

    warped = _warp_card(img_cv, pts)

    # --- Strategy 1: Image hash matching (primary) ---
    hash_matches = []
    if is_index_available():
        all_matches = match_artwork(warped, top_n=10)
        # Keep only matches with reasonable confidence (>30%)
        # and don't show garbage results far below the best match
        if all_matches:
            best_dist = all_matches[0]["distance"]
            hash_matches = [
                m for m in all_matches
                if m["confidence"] > 0.3 and m["distance"] <= best_dist * 1.5
            ]
            # Always keep at least the best match
            if not hash_matches:
                hash_matches = all_matches[:1]

    # --- Build candidates ---
    candidates = []

    if hash_matches:
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
    else:
        # --- Strategy 2: OCR fallback ---
        card_name_raw = _ocr_zone(warped, CARD_NAME_ZONE, is_set_code=False)
        card_name = _clean_card_name(card_name_raw)
        if not card_name:
            raise HTTPException(
                status_code=422,
                detail="Carta rilevata ma impossibile identificarla. Prova con piu' luce.",
            )

        results = await _fuzzy_search(card_name)
        candidates = [_parse_candidate(card) for card in results[:10]]
        extracted = f"[OCR] {card_name}"

    return ScanResult(
        extracted_text=extracted,
        candidates=candidates,
    )


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
                    return [_parse_candidate(card) for card in data[:20]]

    return []
