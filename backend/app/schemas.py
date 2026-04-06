from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CardBase(BaseModel):
    card_id: int
    name: str
    set_code: str | None = None
    type: str
    frame_type: str
    description: str
    atk: int | None = None
    def_: int | None = None
    level: int | None = None
    race: str | None = None
    attribute: str | None = None
    archetype: str | None = None
    image_url: str | None = None
    price_cardmarket: float | None = None
    price_tcgplayer: float | None = None

    model_config = ConfigDict(populate_by_name=True)


class CardCreate(CardBase):
    quantity: int = 1
    rarity: str
    condition: str
    lang: str
    location: list[str] | None = None


class CardUpdate(BaseModel):
    quantity: int | None = None
    rarity: str | None = None
    condition: str | None = None
    lang: str | None = None
    location: list[str] | None = None
    price_cardmarket: float | None = None
    price_manual: bool | None = None
    set_code: str | None = None
    image_url: str | None = None


class CardSplit(BaseModel):
    """Split one copy off an existing card entry with different attributes."""
    quantity: int = 1  # how many to split off
    rarity: str | None = None
    condition: str | None = None
    lang: str | None = None
    location: list[str] | None = None
    set_code: str | None = None


class CardResponse(CardBase):
    id: int
    quantity: int
    rarity: str
    condition: str
    lang: str
    location: list[str] | None = None
    price_manual: bool = False
    price_source: str | None = None
    price_cm_min: float | None = None
    price_cm_avg: float | None = None
    price_cm_median: float | None = None
    price_updated_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CardSet(BaseModel):
    set_name: str
    set_code: str
    set_rarity: str = ""
    set_price: float | None = None


class ScanCandidate(CardBase):
    sets: list[CardSet] = []


class ScanResult(BaseModel):
    extracted_text: str
    candidates: list[ScanCandidate]
