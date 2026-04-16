"""Auto-migrate the SQLite database at startup.

Inspects the actual schema and applies any needed changes so that it
matches the current SQLAlchemy models.  No Alembic dependency at runtime.
"""

import logging
import re
import shutil
import sqlite3
from pathlib import Path

from sqlalchemy import Engine

log = logging.getLogger(__name__)

# Columns that make up the variant identity — must match the model's UniqueConstraint.
_VARIANT_COLS = {"card_id", "rarity", "condition", "lang", "set_code", "image_url"}

# The definitive CREATE TABLE DDL — single source of truth for rebuilds.
_CARDS_DDL = """\
CREATE TABLE cards (
    id INTEGER NOT NULL PRIMARY KEY,
    card_id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    set_code VARCHAR(20) NOT NULL DEFAULT '',
    quantity INTEGER NOT NULL DEFAULT 1,
    rarity VARCHAR(50) NOT NULL,
    condition VARCHAR(20) NOT NULL,
    lang VARCHAR(5) NOT NULL,
    location JSON,
    type VARCHAR(100) NOT NULL,
    frame_type VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    atk INTEGER,
    def INTEGER,
    level INTEGER,
    race VARCHAR(50),
    attribute VARCHAR(20),
    archetype VARCHAR(100),
    image_url TEXT NOT NULL DEFAULT '',
    price_cardmarket FLOAT,
    price_tcgplayer FLOAT,
    price_manual INTEGER NOT NULL DEFAULT 0,
    price_source VARCHAR(20),
    price_cm_min FLOAT,
    price_cm_avg FLOAT,
    price_cm_median FLOAT,
    price_updated_at DATETIME,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uq_card_variant UNIQUE (card_id, rarity, condition, lang, set_code, image_url)
)"""


def run_migrations(engine: Engine) -> None:
    """Inspect the DB and apply schema fixes to match current models."""
    db_path = str(engine.url).replace("sqlite:///", "")
    if not Path(db_path).exists():
        return  # Brand-new DB; create_all will handle it

    conn = sqlite3.connect(db_path, isolation_level=None)
    try:
        if not _table_exists(conn, "cards"):
            return  # create_all will handle it

        _ensure_columns(conn)
        _ensure_books_columns(conn)
        _migrate_book_slots(conn)
        _normalize_image_urls(conn)

        if _needs_constraint_rebuild(conn):
            _backup_db(db_path)
            _rebuild_table(conn)
    except Exception:
        log.exception("Auto-migration failed — DB was not modified (backup available)")
    finally:
        conn.close()


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _get_column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cursor.fetchall()}


def _backup_db(db_path: str) -> None:
    """Create a backup copy before destructive schema changes."""
    backup = db_path + ".bak"
    shutil.copy2(db_path, backup)
    log.info("Database backed up to %s", backup)


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Add any missing columns to the cards table."""
    existing = _get_column_names(conn, "cards")

    new_columns = {
        "set_code": "VARCHAR(20) NOT NULL DEFAULT ''",
        "price_manual": "INTEGER NOT NULL DEFAULT 0",
        "price_source": "VARCHAR(20)",
        "price_cm_min": "FLOAT",
        "price_cm_avg": "FLOAT",
        "price_cm_median": "FLOAT",
        "price_updated_at": "DATETIME",
    }

    for col, definition in new_columns.items():
        if col not in existing:
            log.info("Adding column cards.%s", col)
            conn.execute(f"ALTER TABLE cards ADD COLUMN {col} {definition}")


def _ensure_books_columns(conn: sqlite3.Connection) -> None:
    """Add any missing columns to the books table."""
    if not _table_exists(conn, "books"):
        return
    existing = _get_column_names(conn, "books")
    new_columns = {
        "filter_archetypes": "JSON",
        "group_duplicates": "INTEGER DEFAULT 0",
    }
    for col, definition in new_columns.items():
        if col not in existing:
            log.info("Adding column books.%s", col)
            conn.execute(f"ALTER TABLE books ADD COLUMN {col} {definition}")


def _migrate_book_slots(conn: sqlite3.Connection) -> None:
    """Migrate book_slots from absolute (page, slot) to relative (group_key, position)."""
    if not _table_exists(conn, "book_slots"):
        return
    cols = _get_column_names(conn, "book_slots")
    if "group_key" in cols:
        return  # already migrated
    log.info("Migrating book_slots to group-relative positions")
    conn.execute("DROP TABLE book_slots")
    conn.execute("""
        CREATE TABLE book_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            group_key VARCHAR(200) NOT NULL DEFAULT '',
            position INTEGER NOT NULL,
            card_id INTEGER NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
            UNIQUE(book_id, group_key, position),
            UNIQUE(book_id, card_id)
        )
    """)


def _normalize_image_urls(conn: sqlite3.Connection) -> None:
    """Convert proxied image URLs (/api/cards/img/ID) to canonical form.

    If normalizing would create a duplicate variant, merge the cards first.
    """
    # Find proxied rows
    proxied = conn.execute(
        "SELECT id, image_url FROM cards WHERE image_url LIKE '%/api/cards/img/%'"
    ).fetchall()
    if not proxied:
        return

    merged = 0
    normalized = 0
    for row_id, old_url in proxied:
        # Extract image ID and build canonical URL
        img_id = old_url.rsplit("/", 1)[-1]
        canonical = f"https://images.ygoprodeck.com/images/cards/{img_id}.jpg"

        # Check if a card with the canonical URL already exists for this variant
        conflict = conn.execute("""
            SELECT existing.id FROM cards existing
            JOIN cards proxied ON proxied.id = ?
            WHERE existing.card_id = proxied.card_id
              AND existing.rarity = proxied.rarity
              AND existing.condition = proxied.condition
              AND existing.lang = proxied.lang
              AND existing.set_code = proxied.set_code
              AND existing.image_url = ?
              AND existing.id != ?
        """, (row_id, canonical, row_id)).fetchone()

        if conflict:
            # Merge: add quantity to existing, delete proxied
            conn.execute(
                "UPDATE cards SET quantity = quantity + (SELECT quantity FROM cards WHERE id = ?) WHERE id = ?",
                (row_id, conflict[0])
            )
            conn.execute("DELETE FROM cards WHERE id = ?", (row_id,))
            merged += 1
        else:
            conn.execute("UPDATE cards SET image_url = ? WHERE id = ?", (canonical, row_id))
            normalized += 1

    if merged or normalized:
        log.info("Image URLs: %d normalized, %d merged", normalized, merged)


def _needs_constraint_rebuild(conn: sqlite3.Connection) -> bool:
    """Check if the unique constraint matches the expected variant columns."""
    ddl = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='cards'"
    ).fetchone()[0]

    match = re.search(r"UNIQUE\s*\(([^)]+)\)", ddl, re.IGNORECASE)
    if not match:
        return True  # No unique constraint at all
    constraint_cols = {c.strip().strip('"') for c in match.group(1).split(",")}
    return constraint_cols != _VARIANT_COLS


def _rebuild_table(conn: sqlite3.Connection) -> None:
    """Rebuild cards table with the correct constraint.

    Uses SQLite's recommended procedure:
    1. Create new table (_cards_new)
    2. Copy data from old table
    3. Drop old table
    4. Rename new table to 'cards'
    5. Recreate indexes

    All within a single transaction so it's atomic.
    """
    log.info("Rebuilding cards table to update variant constraint")

    # Clean up leftover temp table from a previous failed attempt
    if _table_exists(conn, "_cards_new"):
        conn.execute("DROP TABLE _cards_new")

    # Normalise NULLs in variant columns before copy
    conn.execute("UPDATE cards SET set_code = '' WHERE set_code IS NULL")
    conn.execute("UPDATE cards SET image_url = '' WHERE image_url IS NULL")

    # Figure out which columns to copy (intersection of old and new)
    old_columns = _get_column_names(conn, "cards")

    # Create the new table with a temp name
    conn.execute(_CARDS_DDL.replace("CREATE TABLE cards", "CREATE TABLE _cards_new"))

    new_columns = _get_column_names(conn, "_cards_new")
    common = sorted(old_columns & new_columns)
    cols = ", ".join(common)

    # Atomic swap: BEGIN -> copy -> drop old -> rename new -> indexes -> COMMIT
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(f"INSERT INTO _cards_new ({cols}) SELECT {cols} FROM cards")
        conn.execute("DROP TABLE cards")
        conn.execute("ALTER TABLE _cards_new RENAME TO cards")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_cards_card_id ON cards (card_id)")
        conn.execute("COMMIT")
        log.info("Cards table rebuilt successfully")
    except Exception:
        conn.execute("ROLLBACK")
        # Clean up the temp table if it's still there
        if _table_exists(conn, "_cards_new"):
            conn.execute("DROP TABLE _cards_new")
        raise
