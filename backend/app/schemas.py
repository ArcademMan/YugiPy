from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CardBase(BaseModel):
    card_id: int
    name: str
    set_code: str = ""
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
    image_url: str | None = None


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


# ── Books ──────────────────────────────────────────────────────────────


class BookCreate(BaseModel):
    name: str
    grid_size: str = "3x3"
    page_count: int = 20
    group_by: str = "archetype"
    new_page: bool = True
    show_prices: bool = False
    group_duplicates: bool = False
    sort_rules: list[str] | None = None
    filter_langs: list[str] | None = None
    filter_conditions: list[str] | None = None
    filter_archetypes: list[str] | None = None
    filter_sets: list[str] | None = None
    min_price: float = 0
    max_copies: int = 0
    copies_mode: str = "entry"


class BookUpdate(BaseModel):
    name: str | None = None
    grid_size: str | None = None
    page_count: int | None = None
    group_by: str | None = None
    new_page: bool | None = None
    show_prices: bool | None = None
    group_duplicates: bool | None = None
    sort_rules: list[str] | None = None
    filter_langs: list[str] | None = None
    filter_conditions: list[str] | None = None
    filter_archetypes: list[str] | None = None
    filter_sets: list[str] | None = None
    min_price: float | None = None
    max_copies: int | None = None
    copies_mode: str | None = None


class BookResponse(BaseModel):
    id: int
    name: str
    grid_size: str
    page_count: int
    group_by: str
    new_page: bool
    show_prices: bool
    group_duplicates: bool
    sort_rules: list[str] | None = None
    filter_langs: list[str] | None = None
    filter_conditions: list[str] | None = None
    filter_archetypes: list[str] | None = None
    filter_sets: list[str] | None = None
    min_price: float
    max_copies: int
    copies_mode: str
    total_slots: int = 0
    assigned_cards: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BookSlotCreate(BaseModel):
    group_key: str = ""
    position: int
    card_id: int


class BookSlotResponse(BaseModel):
    id: int
    book_id: int
    group_key: str
    position: int
    card_id: int

    model_config = ConfigDict(from_attributes=True)


class BookCardCreate(BaseModel):
    card_id: int
    quantity: int = 1


class BookCardResponse(BaseModel):
    id: int
    book_id: int
    card_id: int
    quantity: int

    model_config = ConfigDict(from_attributes=True)
