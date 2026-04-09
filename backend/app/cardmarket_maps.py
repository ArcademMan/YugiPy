import json
from pathlib import Path
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

from .models import Card

_MAPS_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "src" / "data"

_expansions: dict[str, int] = {}
_rarities: dict[str, int] = {}


def _load():
    global _expansions, _rarities
    if not _expansions:
        with open(_MAPS_DIR / "cardmarket_expansions.json", encoding="utf-8") as f:
            _expansions = json.load(f)
    if not _rarities:
        with open(_MAPS_DIR / "cardmarket_rarities.json", encoding="utf-8") as f:
            _rarities = json.load(f)


def _find_expansion_id(set_name: str, lang: str | None) -> int | None:
    """Find the Cardmarket expansion ID, handling name mismatches."""
    # For OCG cards, try the (OCG) variant first
    if lang and lang.upper() in ("JA", "KO"):
        ocg_name = set_name + " (OCG)"
        if ocg_name in _expansions:
            return _expansions[ocg_name]

    # Exact match
    if set_name in _expansions:
        return _expansions[set_name]

    # Fuzzy match: extract keywords and compare
    # Handles "The Dark Emperor Structure Deck" vs "Structure Deck: The Dark Emperor"
    is_ocg = lang and lang.upper() in ("JA", "KO")
    query_words = set(_normalize(set_name).split())
    best_match = None
    best_score = 0
    for cm_name, cm_id in _expansions.items():
        # Skip OCG sets for non-OCG cards and vice versa
        has_ocg_tag = "(OCG)" in cm_name or "(Japanese)" in cm_name or "(Korean)" in cm_name
        if has_ocg_tag and not is_ocg:
            continue
        if not has_ocg_tag and is_ocg:
            continue
        cm_words = set(_normalize(cm_name).split())
        common = query_words & cm_words
        if len(common) >= 2:
            score = len(common) / max(len(query_words), len(cm_words))
            if score > best_score:
                best_score = score
                best_match = cm_id

    return best_match if best_score >= 0.5 else None


def _normalize(name: str) -> str:
    """Normalize a set name for fuzzy matching."""
    import re
    name = name.lower()
    # Remove common prefixes/suffixes and punctuation
    name = re.sub(r"[:\-–—'/]", " ", name)
    # Remove noise words that cause false matches
    name = re.sub(r"\byu gi oh!?\b", "", name)
    name = re.sub(r"\bocg\b", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


_LANG_MAP = {
    "EN": 1, "FR": 2, "DE": 3, "ES": 4,
    "IT": 5, "PT": 6, "JA": 7, "KO": 8,
}


def _find_expansion_by_set_code(set_code: str) -> int | None:
    """Try to find a Cardmarket expansion by the set code prefix (e.g. LDD -> 'Legend of Blue Eyes White Dragon (LDD)')."""
    if not set_code:
        return None
    prefix = set_code.split("-")[0].upper()
    for cm_name, cm_id in _expansions.items():
        # Match "(LDD)" suffix in Cardmarket names
        if cm_name.endswith(f"({prefix})"):
            return cm_id
    return None


def get_cardmarket_url(card: Card, db: Session) -> str | None:
    """Build a Cardmarket search URL that should redirect to the exact card."""
    _load()

    # We need the set_name — fetch from YGOProDeck
    set_name = _get_set_name(card)

    params = {"searchString": card.name}

    exp_id = None
    if set_name:
        exp_id = _find_expansion_id(set_name, card.lang)
    # Fallback: try matching set code prefix directly in Cardmarket names
    if not exp_id and card.set_code:
        exp_id = _find_expansion_by_set_code(card.set_code)
    if exp_id:
        params["idExpansion"] = exp_id

    if card.rarity and card.rarity in _rarities:
        params["idRarity"] = _rarities[card.rarity]

    # Note: language filter is NOT added to search URL as it breaks redirect.
    # Language filtering is done by the extension content script on the card page.

    return f"https://www.cardmarket.com/en/YuGiOh/Products/Search?{urlencode(params)}"


def _get_set_name(card: Card) -> str | None:
    """Get the set name for a card from YGOProDeck API (synchronous)."""
    if not card.set_code:
        return None
    try:
        resp = httpx.get(
            "https://db.ygoprodeck.com/api/v7/cardinfo.php",
            params={"id": card.card_id},
            timeout=5,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            if data:
                for s in data[0].get("card_sets", []):
                    if s.get("set_code") == card.set_code:
                        return s.get("set_name")
    except Exception:
        pass
    return None
