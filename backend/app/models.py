from datetime import datetime, timezone

from sqlalchemy import Integer, String, Text, Float, DateTime, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (
        UniqueConstraint("card_id", "rarity", "condition", "lang", name="uq_card_variant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Card identity
    card_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(255))
    set_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

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
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_cardmarket: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_tcgplayer: Mapped[float | None] = mapped_column(Float, nullable=True)
    price_manual: Mapped[bool] = mapped_column(Integer, default=False, server_default="0")
    price_source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "ygoprodeck", "cardmarket", None
    price_cm_min: Mapped[float | None] = mapped_column(Float, nullable=True)  # Lowest offer price
    price_cm_avg: Mapped[float | None] = mapped_column(Float, nullable=True)  # Average of first 5 offers
    price_cm_median: Mapped[float | None] = mapped_column(Float, nullable=True)  # Median of first 5 offers

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
