from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, Float, DateTime, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (
        UniqueConstraint("card_id", "rarity", "condition", "lang", "set_code", "image_url", name="uq_card_variant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Card identity
    card_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255))
    set_code: Mapped[str] = mapped_column(String(20), nullable=False, default="", server_default="")

    # Collection-specific
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    rarity: Mapped[str] = mapped_column(String(50))
    condition: Mapped[str] = mapped_column(String(20))
    lang: Mapped[str] = mapped_column(String(5))
    location: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Cached metadata (avoid re-fetching from YGOProDeck)
    type: Mapped[str] = mapped_column(String(100))
    frame_type: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(Text)
    atk: Mapped[int | None] = mapped_column(Integer, nullable=True)
    def_: Mapped[int | None] = mapped_column("def", Integer, nullable=True)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    race: Mapped[str | None] = mapped_column(String(50), nullable=True)
    attribute: Mapped[str | None] = mapped_column(String(20), nullable=True)
    archetype: Mapped[str | None] = mapped_column(String(100), nullable=True)
    image_url: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    price_cardmarket: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_tcgplayer: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_manual: Mapped[bool] = mapped_column(Integer, default=False, server_default="0")
    price_source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "ygoprodeck", "cardmarket", None
    price_cm_min: Mapped[float | None] = mapped_column(Float, nullable=True)  # Lowest offer price
    price_cm_avg: Mapped[float | None] = mapped_column(Float, nullable=True)  # Average of first 5 offers
    price_cm_median: Mapped[float | None] = mapped_column(Float, nullable=True)  # Median of first 5 offers
    price_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    grid_size: Mapped[str] = mapped_column(String(5), default="3x3")
    page_count: Mapped[int] = mapped_column(Integer, default=20)
    group_by: Mapped[str] = mapped_column(String(20), default="archetype")
    new_page: Mapped[bool] = mapped_column(Boolean, default=True)
    show_prices: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_rules: Mapped[list | None] = mapped_column(JSON, nullable=True)
    filter_langs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    filter_conditions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    filter_archetypes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    filter_sets: Mapped[list | None] = mapped_column(JSON, nullable=True)
    min_price: Mapped[float] = mapped_column(Float, default=0)
    max_copies: Mapped[int] = mapped_column(Integer, default=0)
    copies_mode: Mapped[str] = mapped_column(String(10), default="entry")
    group_duplicates: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class BookSlot(Base):
    """Pinned card position within its group."""
    __tablename__ = "book_slots"
    __table_args__ = (
        UniqueConstraint("book_id", "group_key", "position", name="uq_book_slot_pos"),
        UniqueConstraint("book_id", "card_id", name="uq_book_slot_card"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"))
    group_key: Mapped[str] = mapped_column(String(200), default="")
    position: Mapped[int] = mapped_column(Integer)
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey("cards.id", ondelete="CASCADE"))


class BookCard(Base):
    """Card assigned/consumed by a book."""
    __tablename__ = "book_cards"
    __table_args__ = (
        UniqueConstraint("book_id", "card_id", name="uq_book_card"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    book_id: Mapped[int] = mapped_column(Integer, ForeignKey("books.id", ondelete="CASCADE"))
    card_id: Mapped[int] = mapped_column(Integer, ForeignKey("cards.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
