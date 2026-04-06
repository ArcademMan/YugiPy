"""
Artwork-based card matching using neural embeddings (primary),
multi-algorithm perceptual hashing (fallback), BK-Tree for fast lookup,
and ORB feature matching as secondary fallback.

Loads the precomputed hash index and embedding index (from build_index.py)
and provides fast card lookup.
"""

import sqlite3
from pathlib import Path

import cv2
import imagehash
import numpy as np
from PIL import Image
from pybktree import BKTree

from .paths import HASH_DB as DB_PATH, DATA_DIR
from .paths import IMAGES_DIR

# Artwork region on a standard warped Yu-Gi-Oh card (portrait, 590x860)
ARTWORK_REGION = {
    "x": 0.13,
    "y": 0.18,
    "w": 0.74,
    "h": 0.47,
}

HASH_SIZE = 8
MAX_DISTANCE = 10       # strong match
MAX_DISTANCE_WEAK = 20  # possible match, lower confidence

# ORB matching parameters
ORB_FEATURES = 500
ORB_GOOD_MATCH_RATIO = 0.75
ORB_MIN_GOOD_MATCHES = 15


# =============================================================
# Shared normalization (must match build_index.py exactly)
# =============================================================

NORMALIZE_SIZE = 256


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


def _compute_query_hashes(img: Image.Image):
    """Compute all 3 hashes on a normalized image."""
    normalized = normalize_for_hash(img)
    p = imagehash.phash(normalized, hash_size=HASH_SIZE)
    d = imagehash.dhash(normalized, hash_size=HASH_SIZE)
    a = imagehash.average_hash(normalized, hash_size=HASH_SIZE)
    return p, d, a


# =============================================================
# Index entry
# =============================================================

class _CardEntry:
    __slots__ = ("card_id", "name", "card_type", "frame_type", "image_url",
                 "phash", "dhash", "ahash")

    def __init__(self, card_id, name, card_type, frame_type, image_url,
                 phash, dhash, ahash):
        self.card_id = card_id
        self.name = name
        self.card_type = card_type
        self.frame_type = frame_type
        self.image_url = image_url
        self.phash = phash
        self.dhash = dhash
        self.ahash = ahash


# =============================================================
# BK-Tree
# =============================================================

def _hamming_distance(a: imagehash.ImageHash, b: imagehash.ImageHash) -> int:
    return a - b


# =============================================================
# Index loading
# =============================================================

def _load_index() -> tuple[list[_CardEntry], BKTree | None]:
    if not DB_PATH.exists():
        return [], None

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.execute("PRAGMA table_info(card_hashes)")
    columns = {row[1] for row in cursor.fetchall()}
    has_multi_hash = "dhash" in columns and "ahash" in columns

    if has_multi_hash:
        query = "SELECT card_id, name, type, frame_type, image_url, phash, dhash, ahash FROM card_hashes"
    else:
        query = "SELECT card_id, name, type, frame_type, image_url, phash FROM card_hashes"

    cursor = conn.execute(query)
    entries = []
    phash_items = []

    for row in cursor.fetchall():
        try:
            phash = imagehash.hex_to_hash(row[5])
            if has_multi_hash:
                dhash = imagehash.hex_to_hash(row[6])
                ahash = imagehash.hex_to_hash(row[7])
            else:
                dhash = phash
                ahash = phash
            entry = _CardEntry(row[0], row[1], row[2], row[3], row[4],
                               phash, dhash, ahash)
            entries.append(entry)
            phash_items.append(phash)
        except Exception:
            continue

    conn.close()

    bktree = None
    if phash_items:
        bktree = BKTree(_hamming_distance, phash_items)

    return entries, bktree


_INDEX: list[_CardEntry] | None = None
_BKTREE: BKTree | None = None
_PHASH_TO_ENTRIES: dict | None = None


def _get_index():
    global _INDEX, _BKTREE, _PHASH_TO_ENTRIES
    if _INDEX is None:
        _INDEX, _BKTREE = _load_index()
        _PHASH_TO_ENTRIES = {}
        for entry in _INDEX:
            key = str(entry.phash)
            _PHASH_TO_ENTRIES.setdefault(key, []).append(entry)
        print(f"[hash_matcher] Index loaded: {len(_INDEX)} cards, BK-Tree={'yes' if _BKTREE else 'no'}")
    return _INDEX, _BKTREE, _PHASH_TO_ENTRIES


def reload_index():
    global _INDEX, _BKTREE, _PHASH_TO_ENTRIES, _EMB_INDEX, _CLIP_MODEL, _CLIP_PREPROCESS
    _INDEX = None
    _BKTREE = None
    _PHASH_TO_ENTRIES = None
    _EMB_INDEX = None
    _CLIP_MODEL = None
    _CLIP_PREPROCESS = None


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


def _embedding_rerank(artwork_cv: np.ndarray, candidates: list[dict]) -> list[dict]:
    """Rerank hash-match candidates using neural embedding similarity."""
    session = _get_embedding_session()
    if session is None:
        return candidates

    emb_index = _get_embedding_index()
    if not emb_index:
        return candidates

    query_vec = _compute_query_embedding(session, artwork_cv)

    for r in candidates:
        cid = r["card_id"]
        if cid in emb_index:
            sim = float(np.dot(emb_index[cid], query_vec))
            r["emb_similarity"] = sim
            # Boost distance: high embedding similarity reduces distance
            r["distance"] *= (1.0 - 0.5 * max(0, sim))
            r["confidence"] = max(r.get("confidence", 0), sim)
        else:
            r["emb_similarity"] = 0.0

    candidates.sort(key=lambda x: x["distance"])
    return candidates


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

    index, _, _ = _get_index()
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
# Multi-hash matching
# =============================================================

def _score_entry(entry: _CardEntry, q_phash, q_dhash, q_ahash) -> tuple[float, int]:
    d_p = q_phash - entry.phash
    d_d = q_dhash - entry.dhash
    d_a = q_ahash - entry.ahash

    votes = sum(1 for d in (d_p, d_d, d_a) if d <= MAX_DISTANCE)
    combined = d_p * 0.5 + d_d * 0.3 + d_a * 0.2

    return combined, votes


def _match_single(artwork: Image.Image, index: list[_CardEntry],
                  bktree: BKTree | None,
                  phash_to_entries: dict,
                  debug: bool = False) -> list[dict]:
    q_phash, q_dhash, q_ahash = _compute_query_hashes(artwork)

    candidate_entries: list[_CardEntry] = []

    if bktree is not None:
        results = bktree.find(q_phash, MAX_DISTANCE_WEAK)
        seen_ids = set()
        for dist, phash_match in results:
            for entry in phash_to_entries.get(str(phash_match), []):
                if entry.card_id not in seen_ids:
                    seen_ids.add(entry.card_id)
                    candidate_entries.append(entry)
    else:
        for entry in index:
            if q_phash - entry.phash <= MAX_DISTANCE_WEAK:
                candidate_entries.append(entry)

    if debug:
        # Brute-force: find the actual closest entries in the entire index
        all_dists = [(q_phash - e.phash, e.name) for e in index]
        all_dists.sort(key=lambda x: x[0])
        top5 = all_dists[:5]
        print(f"[debug] BK-Tree candidates: {len(candidate_entries)}, "
              f"brute-force top5 phash distances: {[(d, n) for d, n in top5]}")

    scored = []
    for entry in candidate_entries:
        combined, votes = _score_entry(entry, q_phash, q_dhash, q_ahash)

        if votes >= 2 or combined <= MAX_DISTANCE_WEAK:
            confidence = max(0.0, 1.0 - combined / MAX_DISTANCE_WEAK)
            scored.append({
                "card_id": entry.card_id,
                "name": entry.name,
                "type": entry.card_type,
                "frame_type": entry.frame_type,
                "image_url": entry.image_url,
                "distance": combined,
                "votes": votes,
                "confidence": confidence,
            })

    scored.sort(key=lambda x: (-x["votes"], x["distance"]))
    return scored


# =============================================================
# ORB feature matching (fallback for ambiguous hash matches)
# =============================================================

def _orb_match(artwork: Image.Image, candidate_ids: list[int]) -> list[tuple[int, int]]:
    query_cv = cv2.cvtColor(np.array(artwork), cv2.COLOR_RGB2GRAY)
    orb = cv2.ORB_create(nfeatures=ORB_FEATURES)
    bf = cv2.BFMatcher(cv2.NORM_HAMMING)

    kp_q, des_q = orb.detectAndCompute(query_cv, None)
    if des_q is None or len(kp_q) < 5:
        return []

    results = []
    for card_id in candidate_ids:
        img_path = IMAGES_DIR / f"{card_id}.jpg"
        if not img_path.exists():
            continue

        try:
            ref_img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
            if ref_img is None:
                continue
            kp_r, des_r = orb.detectAndCompute(ref_img, None)
            if des_r is None or len(kp_r) < 5:
                continue

            matches = bf.knnMatch(des_q, des_r, k=2)
            good = [m for m, n in matches if m.distance < ORB_GOOD_MATCH_RATIO * n.distance]
            results.append((card_id, len(good)))
        except Exception:
            continue

    results.sort(key=lambda x: x[1], reverse=True)
    return results


# =============================================================
# Main matching API
# =============================================================

def match_artwork(card_img: np.ndarray, top_n: int = 5) -> list[dict]:
    """
    Match a warped card image against the index.
    Uses only neural embedding — confidence = raw cosine similarity.
    """
    index, _, _ = _get_index()
    if not index:
        return []

    artwork = extract_artwork(card_img)
    artwork_cv = cv2.cvtColor(np.array(artwork), cv2.COLOR_RGB2BGR)

    results = _embedding_search(artwork_cv, top_n=top_n)

    if results:
        print(f"[match] -> {results[0]['name']}: {results[0]['confidence']:.3f}")

    return results


def is_index_available() -> bool:
    index, _, _ = _get_index()
    return bool(index)
