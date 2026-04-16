from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Book, BookCard, BookSlot, Card
from ..schemas import (
    BookCardCreate,
    BookCardResponse,
    BookCreate,
    BookResponse,
    BookSlotCreate,
    BookSlotResponse,
    BookUpdate,
)

router = APIRouter(prefix="/api/books", tags=["books"])


def _book_response(book: Book, db: Session) -> dict:
    """Build BookResponse dict with computed fields."""
    cols, rows = book.grid_size.split("x")
    total_slots = int(cols) * int(rows) * book.page_count

    assigned = db.scalar(
        select(func.coalesce(func.sum(BookCard.quantity), 0))
        .where(BookCard.book_id == book.id)
    )

    data = {c.name: getattr(book, c.name) for c in book.__table__.columns}
    data["total_slots"] = total_slots
    data["assigned_cards"] = assigned
    return data


# ── CRUD ───────────────────────────────────────────────────────────────


@router.get("", response_model=list[BookResponse])
def list_books(db: Session = Depends(get_db)):
    books = db.scalars(select(Book).order_by(Book.name)).all()
    return [_book_response(b, db) for b in books]


@router.get("/unassigned")
def unassigned_cards(db: Session = Depends(get_db)):
    """Cards with remaining unassigned quantity."""
    cards = db.scalars(select(Card).order_by(Card.name)).all()
    result = []
    for card in cards:
        assigned = db.scalar(
            select(func.coalesce(func.sum(BookCard.quantity), 0))
            .where(BookCard.card_id == card.id)
        )
        remaining = card.quantity - assigned
        if remaining > 0:
            result.append({
                "card": {c.name: getattr(card, c.name) for c in card.__table__.columns},
                "available": remaining,
            })
    return result


@router.get("/{book_id}/archetype-availability")
def archetype_availability(book_id: int, db: Session = Depends(get_db)):
    """Per-archetype count of cards available for this book (not assigned to other books)."""
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")

    cards = db.scalars(select(Card).where(Card.archetype.isnot(None), Card.archetype != "")).all()

    arch_counts: dict[str, int] = {}
    for card in cards:
        assigned_elsewhere = db.scalar(
            select(func.coalesce(func.sum(BookCard.quantity), 0))
            .where(BookCard.card_id == card.id, BookCard.book_id != book_id)
        )
        remaining = card.quantity - assigned_elsewhere
        if remaining > 0:
            arch = card.archetype
            arch_counts[arch] = arch_counts.get(arch, 0) + remaining

    return [{"archetype": k, "available": v} for k, v in sorted(arch_counts.items())]


@router.post("", response_model=BookResponse, status_code=201)
def create_book(payload: BookCreate, db: Session = Depends(get_db)):
    book = Book(**payload.model_dump())
    db.add(book)
    db.commit()
    db.refresh(book)
    return _book_response(book, db)


@router.get("/{book_id}", response_model=BookResponse)
def get_book(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    return _book_response(book, db)


@router.put("/{book_id}", response_model=BookResponse)
def update_book(book_id: int, payload: BookUpdate, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(book, field, value)
    db.commit()
    db.refresh(book)
    return _book_response(book, db)


@router.delete("/{book_id}", status_code=204)
def delete_book(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    db.delete(book)
    db.commit()


@router.delete("/{book_id}/reset", status_code=204)
def reset_book(book_id: int, db: Session = Depends(get_db)):
    """Remove all card assignments and pins from a book."""
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    db.execute(BookSlot.__table__.delete().where(BookSlot.book_id == book_id))
    db.execute(BookCard.__table__.delete().where(BookCard.book_id == book_id))
    db.commit()


# ── Card assignment (consumption) ──────────────────────────────────────


@router.get("/{book_id}/cards", response_model=list[BookCardResponse])
def list_book_cards(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    return db.scalars(
        select(BookCard).where(BookCard.book_id == book_id)
    ).all()


@router.post("/{book_id}/cards", response_model=BookCardResponse, status_code=201)
def assign_card(book_id: int, payload: BookCardCreate, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")

    card = db.get(Card, payload.card_id)
    if not card:
        raise HTTPException(404, "Card not found")

    # Check available quantity
    already_assigned = db.scalar(
        select(func.coalesce(func.sum(BookCard.quantity), 0))
        .where(BookCard.card_id == payload.card_id)
    )
    available = card.quantity - already_assigned
    if payload.quantity > available:
        raise HTTPException(
            400,
            f"Only {available} copies available ({card.quantity} total, {already_assigned} assigned)",
        )

    # Upsert: if already assigned to this book, add quantity
    existing = db.scalars(
        select(BookCard).where(
            BookCard.book_id == book_id,
            BookCard.card_id == payload.card_id,
        )
    ).first()

    if existing:
        existing.quantity += payload.quantity
        db.commit()
        db.refresh(existing)
        return existing

    bc = BookCard(book_id=book_id, card_id=payload.card_id, quantity=payload.quantity)
    db.add(bc)
    db.commit()
    db.refresh(bc)
    return bc


@router.delete("/{book_id}/cards/{card_id}", status_code=204)
def unassign_card(book_id: int, card_id: int, db: Session = Depends(get_db)):
    bc = db.scalars(
        select(BookCard).where(
            BookCard.book_id == book_id,
            BookCard.card_id == card_id,
        )
    ).first()
    if not bc:
        raise HTTPException(404, "Card not assigned to this book")
    # Also remove any pins for this card
    db.execute(
        BookSlot.__table__.delete().where(
            BookSlot.book_id == book_id,
            BookSlot.card_id == card_id,
        )
    )
    db.delete(bc)
    db.commit()


# ── Bulk assign (auto-fill) ───────────────────────────────────────────


@router.post("/{book_id}/auto-assign", response_model=list[BookCardResponse])
def auto_assign(book_id: int, db: Session = Depends(get_db)):
    """Reset and reassign cards to this book based on current filter settings."""
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")

    # Preserve pinned cards — collect their card_ids and existing assignments
    pinned_card_ids = set(
        db.scalars(
            select(BookSlot.card_id).where(BookSlot.book_id == book_id)
        ).all()
    )

    # Clear non-pinned assignments only
    if pinned_card_ids:
        db.execute(
            BookCard.__table__.delete().where(
                BookCard.book_id == book_id,
                BookCard.card_id.notin_(pinned_card_ids),
            )
        )
    else:
        db.execute(BookCard.__table__.delete().where(BookCard.book_id == book_id))
    db.flush()

    # Build card query with book filters
    stmt = select(Card).order_by(Card.name)
    if book.filter_langs:
        stmt = stmt.where(Card.lang.in_(book.filter_langs))
    if book.filter_conditions:
        stmt = stmt.where(Card.condition.in_(book.filter_conditions))
    if book.filter_archetypes:
        stmt = stmt.where(Card.archetype.in_(book.filter_archetypes))

    cards = db.scalars(stmt).all()

    # Filter by set prefix if needed
    if book.filter_sets:
        cards = [c for c in cards if any(
            (c.set_code or "").startswith(s) for s in book.filter_sets
        )]

    # Collect existing pinned assignments to avoid duplicates
    existing_assigned = set(
        db.scalars(
            select(BookCard.card_id).where(BookCard.book_id == book_id)
        ).all()
    )

    results = list(
        db.scalars(select(BookCard).where(BookCard.book_id == book_id)).all()
    )

    for card in cards:
        if card.id in existing_assigned:
            continue

        # How many already assigned to OTHER books
        globally_assigned = db.scalar(
            select(func.coalesce(func.sum(BookCard.quantity), 0))
            .where(BookCard.card_id == card.id, BookCard.book_id != book_id)
        )
        available = card.quantity - globally_assigned
        if available <= 0:
            continue

        # Respect max_copies
        max_copies = book.max_copies if book.max_copies > 0 else available
        to_assign = min(available, max_copies)

        bc = BookCard(book_id=book_id, card_id=card.id, quantity=to_assign)
        db.add(bc)
        results.append(bc)

    db.commit()
    for bc in results:
        db.refresh(bc)
    return results


# ── Slots (pins) ───────────────────────────────────────────────────────


@router.get("/{book_id}/slots", response_model=list[BookSlotResponse])
def list_slots(book_id: int, db: Session = Depends(get_db)):
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")
    return db.scalars(
        select(BookSlot).where(BookSlot.book_id == book_id)
    ).all()


@router.put("/{book_id}/slots", response_model=list[BookSlotResponse])
def set_slots(book_id: int, slots: list[BookSlotCreate], db: Session = Depends(get_db)):
    """Bulk set pinned slots. Replaces all existing pins."""
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")

    # Clear existing pins
    db.execute(BookSlot.__table__.delete().where(BookSlot.book_id == book_id))

    new_slots = []
    for s in slots:
        bs = BookSlot(
            book_id=book_id, group_key=s.group_key,
            position=s.position, card_id=s.card_id,
        )
        db.add(bs)
        new_slots.append(bs)

    db.commit()
    for bs in new_slots:
        db.refresh(bs)
    return new_slots


@router.post("/{book_id}/slots", response_model=BookSlotResponse, status_code=201)
def pin_slot(book_id: int, payload: BookSlotCreate, db: Session = Depends(get_db)):
    """Pin a single card to a specific position within its group."""
    book = db.get(Book, book_id)
    if not book:
        raise HTTPException(404, "Book not found")

    # Card must be assigned to this book
    bc = db.scalars(
        select(BookCard).where(
            BookCard.book_id == book_id,
            BookCard.card_id == payload.card_id,
        )
    ).first()
    if not bc:
        raise HTTPException(400, "Card is not assigned to this book")

    # Remove any existing pin at this group+position or for this card
    db.execute(
        BookSlot.__table__.delete().where(
            BookSlot.book_id == book_id,
            (
                (BookSlot.group_key == payload.group_key)
                & (BookSlot.position == payload.position)
            )
            | (BookSlot.card_id == payload.card_id),
        )
    )

    bs = BookSlot(
        book_id=book_id, group_key=payload.group_key,
        position=payload.position, card_id=payload.card_id,
    )
    db.add(bs)
    db.commit()
    db.refresh(bs)
    return bs


@router.delete("/{book_id}/slots/{slot_id}", status_code=204)
def unpin_slot(book_id: int, slot_id: int, db: Session = Depends(get_db)):
    bs = db.get(BookSlot, slot_id)
    if not bs or bs.book_id != book_id:
        raise HTTPException(404, "Slot not found")
    db.delete(bs)
    db.commit()


