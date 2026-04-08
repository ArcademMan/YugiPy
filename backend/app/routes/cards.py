import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Card
from ..paths import FULL_IMAGES_DIR
from ..schemas import CardCreate, CardResponse, CardSplit, CardUpdate

router = APIRouter(prefix="/api/cards", tags=["cards"])

YGOPRODECK_API = "https://db.ygoprodeck.com/api/v7/cardinfo.php"

_PROXY_RE = re.compile(r".*/api/cards/img/(\d+)$")


def _normalize_image_url(url: str | None) -> str:
    """Convert proxied URLs like /api/cards/img/12345 to the canonical form."""
    if not url:
        return ""
    m = _PROXY_RE.match(url)
    if m:
        return f"https://images.ygoprodeck.com/images/cards/{m.group(1)}.jpg"
    return url


@router.get("/img/{card_image_id}")
async def get_card_image(card_image_id: int):
    """Serve a card image from local cache, or download from YGOProDeck and cache it."""
    FULL_IMAGES_DIR.mkdir(exist_ok=True)
    local = FULL_IMAGES_DIR / f"{card_image_id}.jpg"
    if local.exists():
        return FileResponse(local, media_type="image/jpeg")
    # Download, cache locally, and serve
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://images.ygoprodeck.com/images/cards/{card_image_id}.jpg")
            resp.raise_for_status()
            local.write_bytes(resp.content)
            return FileResponse(local, media_type="image/jpeg")
    except Exception:
        return RedirectResponse(f"https://images.ygoprodeck.com/images/cards/{card_image_id}.jpg")


@router.get("", response_model=list[CardResponse])
def list_cards(
    rarity: str | None = Query(None),
    condition: str | None = Query(None),
    lang: str | None = Query(None),
    q: str | None = Query(None, description="Search card name"),
    db: Session = Depends(get_db),
):
    """List all cards in the collection, with optional filters."""
    stmt = select(Card).order_by(Card.name)
    if rarity:
        stmt = stmt.where(Card.rarity == rarity)
    if condition:
        stmt = stmt.where(Card.condition == condition)
    if lang:
        stmt = stmt.where(Card.lang == lang)
    if q:
        stmt = stmt.where(
            Card.name.ilike(f"%{q}%") | Card.set_code.ilike(f"%{q}%")
        )
    return db.scalars(stmt).all()


@router.get("/{card_db_id}", response_model=CardResponse)
async def get_card(card_db_id: int, db: Session = Depends(get_db)):
    """Get a single card by database ID. Refreshes price from YGOProDeck."""
    card = db.get(Card, card_db_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    # Refresh price from YGOProDeck (prefer set-specific price for this rarity)
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(YGOPRODECK_API, params={"id": card.card_id})
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    api_card = data[0]
                    generic_prices = api_card.get("card_prices", [{}])[0]
                    generic_cm = _safe_float(generic_prices.get("cardmarket_price"))
                    new_tcp = _safe_float(generic_prices.get("tcgplayer_price"))

                    # Look for set-specific price matching this card's rarity
                    specific_price = None
                    for s in api_card.get("card_sets", []):
                        if s.get("set_rarity") == card.rarity:
                            sp = _safe_float(s.get("set_price"))
                            if sp:
                                specific_price = sp
                                break

                    card.price_cardmarket = specific_price if specific_price else generic_cm
                    if new_tcp is not None:
                        card.price_tcgplayer = new_tcp
                    db.commit()
                    db.refresh(card)
    except Exception:
        pass  # If API fails, return cached price

    return card


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return f if f > 0 else None
    except (ValueError, TypeError):
        return None


@router.post("", response_model=CardResponse, status_code=201)
def add_card(payload: CardCreate, db: Session = Depends(get_db)):
    """Add a card to the collection.

    Matches on (card_id, rarity, condition, lang, set_code, image_url).
    If a match exists, increments quantity.
    """
    existing = db.scalars(
        select(Card).where(
            Card.card_id == payload.card_id,
            Card.rarity == payload.rarity,
            Card.condition == payload.condition,
            Card.lang == payload.lang,
            Card.set_code == (payload.set_code or ""),
            Card.image_url == _normalize_image_url(payload.image_url),
        )
    ).first()

    if existing:
        existing.quantity += payload.quantity
        db.commit()
        db.refresh(existing)
        return existing

    data = payload.model_dump()
    data["set_code"] = data.get("set_code") or ""
    data["image_url"] = _normalize_image_url(data.get("image_url"))
    card = Card(**data)
    db.add(card)
    db.commit()
    db.refresh(card)
    return card


@router.put("/{card_db_id}", response_model=CardResponse)
def update_card(card_db_id: int, payload: CardUpdate, db: Session = Depends(get_db)):
    """Update card details (quantity, rarity, condition, lang, location)."""
    card = db.get(Card, card_db_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    updates = payload.model_dump(exclude_unset=True)

    # Check if changing a variant key would collide with an existing
    # variant — if so, merge quantities automatically.
    variant_keys = {"rarity", "condition", "lang", "set_code", "image_url"}
    if updates.keys() & variant_keys:
        new_rarity = updates.get("rarity", card.rarity)
        new_condition = updates.get("condition", card.condition)
        new_lang = updates.get("lang", card.lang)
        new_set_code = updates.get("set_code", card.set_code) or ""
        new_image_url = _normalize_image_url(updates.get("image_url", card.image_url))

        existing = db.scalars(
            select(Card).where(
                Card.card_id == card.card_id,
                Card.rarity == new_rarity,
                Card.condition == new_condition,
                Card.lang == new_lang,
                Card.set_code == new_set_code,
                Card.image_url == new_image_url,
                Card.id != card.id,
            )
        ).first()

        if existing:
            # Merge: add quantity to the existing variant, delete the source
            existing.quantity += card.quantity
            if "location" in updates:
                existing.location = updates["location"]
            db.delete(card)
            db.commit()
            db.refresh(existing)
            return existing

    for field, value in updates.items():
        if field == "set_code":
            value = value or ""
        elif field == "image_url":
            value = _normalize_image_url(value)
        setattr(card, field, value)
    db.commit()
    db.refresh(card)
    return card


@router.post("/{card_db_id}/split", response_model=CardResponse, status_code=201)
def split_card(card_db_id: int, payload: CardSplit, db: Session = Depends(get_db)):
    """Split copies off an existing card with different attributes.

    Decrements the source card quantity, creates a new entry (or merges
    with an existing one that matches the new attributes).
    """
    source = db.get(Card, card_db_id)
    if not source:
        raise HTTPException(status_code=404, detail="Card not found")

    if payload.quantity >= source.quantity:
        raise HTTPException(
            status_code=400,
            detail=f"Non puoi separare {payload.quantity} copie da una carta con {source.quantity} copie",
        )

    # Determine the new attributes (use source's value if not overridden)
    new_rarity = payload.rarity if payload.rarity is not None else source.rarity
    new_condition = payload.condition if payload.condition is not None else source.condition
    new_lang = payload.lang if payload.lang is not None else source.lang
    new_location = payload.location if payload.location is not None else source.location
    new_set_code = payload.set_code if payload.set_code is not None else source.set_code
    new_set_code = new_set_code or ""
    new_image_url = _normalize_image_url(
        payload.image_url if payload.image_url is not None else source.image_url
    )

    # Check if the split would create an identical card
    if (new_rarity == source.rarity and new_condition == source.condition
            and new_lang == source.lang and new_set_code == source.set_code
            and new_image_url == source.image_url):
        raise HTTPException(
            status_code=400,
            detail="Devi cambiare almeno un attributo (rarità, condizione, lingua o artwork)",
        )

    # Decrement source
    source.quantity -= payload.quantity

    # Find or create target
    existing = db.scalars(
        select(Card).where(
            Card.card_id == source.card_id,
            Card.rarity == new_rarity,
            Card.condition == new_condition,
            Card.lang == new_lang,
            Card.set_code == new_set_code,
            Card.image_url == new_image_url,
            Card.id != source.id,
        )
    ).first()

    if existing:
        existing.quantity += payload.quantity
        db.commit()
        db.refresh(existing)
        result = existing
    else:
        # Copy all metadata from source
        new_card = Card(
            card_id=source.card_id,
            name=source.name,
            type=source.type,
            frame_type=source.frame_type,
            description=source.description,
            atk=source.atk,
            def_=source.def_,
            level=source.level,
            race=source.race,
            attribute=source.attribute,
            archetype=source.archetype,
            image_url=new_image_url,
            price_cardmarket=source.price_cardmarket,
            price_tcgplayer=source.price_tcgplayer,
            quantity=payload.quantity,
            rarity=new_rarity,
            condition=new_condition,
            lang=new_lang,
            set_code=new_set_code,
            location=new_location,
        )
        db.add(new_card)
        db.commit()
        db.refresh(new_card)
        result = new_card

    # Clean up source if empty
    if source.quantity <= 0:
        db.delete(source)
        db.commit()

    return result


@router.delete("/{card_db_id}", status_code=204)
def delete_card(card_db_id: int, db: Session = Depends(get_db)):
    """Remove a card from the collection."""
    card = db.get(Card, card_db_id)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    db.delete(card)
    db.commit()
