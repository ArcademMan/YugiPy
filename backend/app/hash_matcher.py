"""
Artwork-based card matching using CLIP neural embeddings (ONNX Runtime).

Loads the precomputed embedding index (from build_clip_embeddings.py)
and card metadata (from build_index.py) for fast card lookup.
"""

import sqlite3

import cv2
import numpy as np
from PIL import Image

from .paths import HASH_DB as DB_PATH, DATA_DIR

# Artwork region on a standard warped Yu-Gi-Oh card (portrait, 590x860)
ARTWORK_REGION = {
    "x": 0.13,
    "y": 0.18,
    "w": 0.74,
    "h": 0.47,
}


# =============================================================
# Index entry
# =============================================================

class _CardEntry:
    __slots__ = ("card_id", "name", "card_type", "frame_type", "image_url")

    def __init__(self, card_id, name, card_type, frame_type, image_url):
        self.card_id = card_id
        self.name = name
        self.card_type = card_type
        self.frame_type = frame_type
        self.image_url = image_url


# =============================================================
# Index loading
# =============================================================

def _load_index() -> list[_CardEntry]:
    if not DB_PATH.exists():
        return []

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute(
        "SELECT card_id, name, type, frame_type, image_url FROM card_hashes"
    )
    entries = []
    for row in cursor.fetchall():
        entries.append(_CardEntry(row[0], row[1], row[2], row[3], row[4]))
    conn.close()

    return entries


_INDEX: list[_CardEntry] | None = None


def _get_index() -> list[_CardEntry]:
    global _INDEX
    if _INDEX is None:
        _INDEX = _load_index()
        print(f"[hash_matcher] Index loaded: {len(_INDEX)} cards")
    return _INDEX


def reload_index():
    global _INDEX, _EMB_INDEX
    _INDEX = None
    _EMB_INDEX = None


# =============================================================
# CLIP embedding matching
# =============================================================

_CLIP_SESSION = None
_EMB_INDEX: dict | None = None

CLIP_ONNX_PATH = DATA_DIR / "clip_visual.onnx"

# CLIP ViT-L-14 preprocessing constants (matches open_clip's preprocess)
_CLIP_INPUT_SIZE = 224
_CLIP_MEAN = np.array([0.5, 0.5, 0.5], dtype=np.float32)
_CLIP_STD = np.array([0.5, 0.5, 0.5], dtype=np.float32)


def _get_clip_session():
    """Lazy-load CLIP visual encoder as ONNX session."""
    global _CLIP_SESSION
    if _CLIP_SESSION is None:
        if not CLIP_ONNX_PATH.exists():
            print(f"[hash_matcher] ONNX model not found at {CLIP_ONNX_PATH}")
            return None
        try:
            import onnxruntime as ort
            available = ort.get_available_providers()
            if "CUDAExecutionProvider" in available:
                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            else:
                providers = ["CPUExecutionProvider"]
            _CLIP_SESSION = ort.InferenceSession(str(CLIP_ONNX_PATH), providers=providers)
            active = _CLIP_SESSION.get_providers()
            print(f"[hash_matcher] CLIP ONNX loaded (providers: {active})")
        except Exception as e:
            print(f"[hash_matcher] Failed to load CLIP ONNX: {e}")
            return None
    return _CLIP_SESSION


def _clip_preprocess(artwork_cv: np.ndarray) -> np.ndarray:
    """Replicate CLIP preprocessing: resize, center-crop, normalize."""
    # BGR to RGB
    img = cv2.cvtColor(artwork_cv, cv2.COLOR_BGR2RGB)

    # Resize shortest side to 224, bicubic
    h, w = img.shape[:2]
    if h < w:
        new_h, new_w = _CLIP_INPUT_SIZE, int(w * _CLIP_INPUT_SIZE / h)
    else:
        new_h, new_w = int(h * _CLIP_INPUT_SIZE / w), _CLIP_INPUT_SIZE
    img = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    # Center crop to 224x224
    y0 = (new_h - _CLIP_INPUT_SIZE) // 2
    x0 = (new_w - _CLIP_INPUT_SIZE) // 2
    img = img[y0:y0 + _CLIP_INPUT_SIZE, x0:x0 + _CLIP_INPUT_SIZE]

    # To float32 [0, 1], then normalize
    arr = img.astype(np.float32) / 255.0
    arr = (arr - _CLIP_MEAN) / _CLIP_STD

    # HWC -> CHW, add batch dim
    arr = np.transpose(arr, (2, 0, 1))[np.newaxis, ...]
    return arr


def _load_embedding_index() -> dict:
    """Load embedding vectors from the DB. Returns {card_id: embedding_vector}."""
    if not DB_PATH.exists():
        return {}

    conn = sqlite3.connect(str(DB_PATH))
    try:
        cursor = conn.execute("SELECT card_id, embedding FROM card_embeddings")
    except sqlite3.OperationalError:
        conn.close()
        return {}

    embeddings = {}
    for card_id, blob in cursor.fetchall():
        vec = np.frombuffer(blob, dtype=np.float32)
        embeddings[card_id] = vec
    conn.close()
    return embeddings


def _get_embedding_index():
    global _EMB_INDEX
    if _EMB_INDEX is None:
        _EMB_INDEX = _load_embedding_index()
        print(f"[hash_matcher] Embedding index loaded: {len(_EMB_INDEX)} cards")
    return _EMB_INDEX


def _compute_query_embedding(artwork_cv: np.ndarray) -> np.ndarray | None:
    """Compute L2-normalized CLIP embedding for a query artwork via ONNX."""
    session = _get_clip_session()
    if session is None:
        return None

    inp = _clip_preprocess(artwork_cv)
    emb = session.run(None, {"image": inp})[0]

    # L2 normalize
    vec = emb.flatten().astype(np.float32)
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


MIN_EMBEDDING_CONFIDENCE = 0.70

def _embedding_search(artwork_cv: np.ndarray, top_n: int = 10) -> list[dict]:
    """Brute-force CLIP embedding search across all cards."""
    emb_index = _get_embedding_index()
    if not emb_index:
        return []

    query_vec = _compute_query_embedding(artwork_cv)
    if query_vec is None:
        return []

    card_ids = list(emb_index.keys())
    matrix = np.stack([emb_index[cid] for cid in card_ids])
    similarities = matrix @ query_vec

    top_indices = np.argsort(similarities)[::-1][:top_n]

    # If the best match is below threshold, nothing meaningful was detected
    if float(similarities[top_indices[0]]) < MIN_EMBEDDING_CONFIDENCE:
        return []

    index = _get_index()
    id_to_entry = {e.card_id: e for e in index}

    results = []
    for idx in top_indices:
        card_id = card_ids[idx]
        sim = float(similarities[idx])
        if sim < MIN_EMBEDDING_CONFIDENCE:
            break
        entry = id_to_entry.get(card_id)
        if entry is None:
            continue
        results.append({
            "card_id": card_id,
            "name": entry.name,
            "type": entry.card_type,
            "frame_type": entry.frame_type,
            "image_url": entry.image_url,
            "distance": 1.0 - sim,
            "votes": 0,
            "confidence": sim,
            "match_method": "embedding",
        })

    return results


# =============================================================
# Artwork extraction (hardcoded proportions — simple and reliable)
# =============================================================

def extract_artwork(card_img: np.ndarray) -> Image.Image:
    """Extract the artwork region from a warped card image (OpenCV BGR)."""
    h, w = card_img.shape[:2]
    x1 = int(w * ARTWORK_REGION["x"])
    y1 = int(h * ARTWORK_REGION["y"])
    x2 = int(w * (ARTWORK_REGION["x"] + ARTWORK_REGION["w"]))
    y2 = int(h * (ARTWORK_REGION["y"] + ARTWORK_REGION["h"]))

    cropped = card_img[y1:y2, x1:x2]
    return Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB))


# =============================================================
# Main matching API
# =============================================================

def match_artwork(card_img: np.ndarray, top_n: int = 5) -> list[dict]:
    """
    Match a warped card image against the index.
    Uses only neural embedding — confidence = raw cosine similarity.
    """
    index = _get_index()
    if not index:
        return []

    artwork = extract_artwork(card_img)
    artwork_cv = cv2.cvtColor(np.array(artwork), cv2.COLOR_RGB2BGR)

    results = _embedding_search(artwork_cv, top_n=top_n)

    if results:
        print(f"[match] -> {results[0]['name']}: {results[0]['confidence']:.3f}")

    return results


def is_index_available() -> bool:
    index = _get_index()
    return bool(index)
