from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Card

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("")
def get_stats(db: Session = Depends(get_db)):
    """Compute collection statistics."""
    cards = db.scalars(select(Card)).all()

    if not cards:
        return {"empty": True}

    total_unique = len(cards)
    total_copies = sum(c.quantity for c in cards)
    distinct_card_ids = len({c.card_id for c in cards})

    # --- Price helpers ---
    def best_price(c):
        for p in [c.price_cm_median, c.price_cm_avg, c.price_cm_min, c.price_cardmarket]:
            if p is not None:
                return p
        return 0.0

    total_value = sum(best_price(c) * c.quantity for c in cards)

    priced_cards = [c for c in cards if best_price(c) > 0]
    avg_card_value = total_value / total_copies if total_copies else 0

    # --- Distributions (weighted by quantity) ---
    rarity_dist = Counter()
    condition_dist = Counter()
    lang_dist = Counter()
    type_dist = Counter()
    attribute_dist = Counter()
    race_dist = Counter()
    level_dist = Counter()
    archetype_dist = Counter()
    set_dist = Counter()
    frame_type_dist = Counter()

    for c in cards:
        q = c.quantity
        rarity_dist[c.rarity] += q
        condition_dist[c.condition] += q
        lang_dist[c.lang] += q
        type_dist[c.type] += q
        frame_type_dist[c.frame_type] += q
        if c.attribute:
            attribute_dist[c.attribute] += q
        if c.race:
            race_dist[c.race] += q
        if c.level is not None:
            level_dist[str(c.level)] += q
        if c.archetype:
            archetype_dist[c.archetype] += q
        if c.set_code:
            prefix = c.set_code.split("-")[0]
            set_dist[prefix] += q

    # --- Top cards by value ---
    top_valuable = sorted(cards, key=lambda c: best_price(c), reverse=True)[:10]
    top_valuable_data = [
        {
            "name": c.name,
            "set_code": c.set_code,
            "rarity": c.rarity,
            "price": round(best_price(c), 2),
            "quantity": c.quantity,
            "image_url": c.image_url,
            "total_value": round(best_price(c) * c.quantity, 2),
        }
        for c in top_valuable if best_price(c) > 0
    ]

    # --- Value by rarity ---
    value_by_rarity = Counter()
    for c in cards:
        value_by_rarity[c.rarity] += best_price(c) * c.quantity
    value_by_rarity = {k: round(v, 2) for k, v in value_by_rarity.most_common(15)}

    # --- Value by language ---
    value_by_lang = Counter()
    for c in cards:
        value_by_lang[c.lang] += best_price(c) * c.quantity
    value_by_lang = {k: round(v, 2) for k, v in value_by_lang.most_common()}

    # --- ATK/DEF scatter data (for monsters) ---
    atk_def_data = []
    seen_atk_def = set()
    for c in cards:
        if c.atk is not None and c.def_ is not None:
            key = (c.card_id, c.atk, c.def_)
            if key not in seen_atk_def:
                seen_atk_def.add(key)
                atk_def_data.append({
                    "name": c.name,
                    "atk": c.atk,
                    "def": c.def_,
                    "level": c.level,
                })

    # --- Price distribution histogram ---
    price_ranges = {"0": 0, "0.01-0.50": 0, "0.51-1": 0, "1-5": 0, "5-10": 0, "10-25": 0, "25-50": 0, "50-100": 0, "100+": 0}
    for c in cards:
        p = best_price(c)
        q = c.quantity
        if p == 0:
            price_ranges["0"] += q
        elif p <= 0.50:
            price_ranges["0.01-0.50"] += q
        elif p <= 1:
            price_ranges["0.51-1"] += q
        elif p <= 5:
            price_ranges["1-5"] += q
        elif p <= 10:
            price_ranges["5-10"] += q
        elif p <= 25:
            price_ranges["10-25"] += q
        elif p <= 50:
            price_ranges["25-50"] += q
        elif p <= 100:
            price_ranges["50-100"] += q
        else:
            price_ranges["100+"] += q

    # --- Collection growth (cards added over time) ---
    cards_with_date = sorted(
        [(c.created_at.strftime("%Y-%m") if c.created_at else None, c.quantity) for c in cards],
        key=lambda x: x[0] or ""
    )
    growth_by_month = Counter()
    for month, qty in cards_with_date:
        if month:
            growth_by_month[month] += qty

    return {
        "empty": False,
        "overview": {
            "total_unique": total_unique,
            "total_copies": total_copies,
            "distinct_cards": distinct_card_ids,
            "total_value": round(total_value, 2),
            "avg_card_value": round(avg_card_value, 2),
            "priced_count": len(priced_cards),
            "unpriced_count": total_unique - len(priced_cards),
        },
        "distributions": {
            "rarity": dict(rarity_dist.most_common()),
            "condition": dict(condition_dist.most_common()),
            "language": dict(lang_dist.most_common()),
            "type": dict(type_dist.most_common()),
            "attribute": dict(attribute_dist.most_common()),
            "race": dict(race_dist.most_common(20)),
            "level": dict(sorted(level_dist.items(), key=lambda x: int(x[0]))),
            "archetype": dict(archetype_dist.most_common(20)),
            "set": dict(set_dist.most_common(20)),
            "frame_type": dict(frame_type_dist.most_common()),
        },
        "top_valuable": top_valuable_data,
        "value_by_rarity": value_by_rarity,
        "value_by_lang": value_by_lang,
        "price_distribution": price_ranges,
        "atk_def_scatter": atk_def_data,
        "growth_by_month": dict(sorted(growth_by_month.items())),
    }
