import asyncio
import json
import logging

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Card

router = APIRouter(tags=["cardmarket"])

LOG = logging.getLogger("cardmarket")

# Holds the single extension WebSocket connection.
# Can be either a FastAPI WebSocket (WSS via main server)
# or a plain websockets.WebSocketServerProtocol (WS via local relay).
_ext_ws = None
# Pending price requests: card_db_id -> Future
_pending: dict[int, asyncio.Future] = {}

# ── Plain WS relay on localhost (no SSL, for the browser extension) ────

EXT_WS_PORT = 8001


async def _plain_ws_handler(websocket):
    """Handle extension connection on the plain WS relay (port 8001)."""
    global _ext_ws
    _ext_ws = websocket
    LOG.info("Extension connected via plain WS relay (port %d)", EXT_WS_PORT)
    try:
        async for raw in websocket:
            msg = json.loads(raw)
            if msg.get("action") == "price_result":
                card_id = msg.get("card_id")
                fut = _pending.pop(card_id, None)
                if fut and not fut.done():
                    fut.set_result(msg)
    except Exception:
        pass
    finally:
        if _ext_ws is websocket:
            _ext_ws = None
        LOG.info("Extension disconnected from plain WS relay")


async def start_ext_ws_relay():
    """Start a plain (no-TLS) WebSocket server on localhost for the extension."""
    try:
        import websockets
        server = await websockets.serve(
            _plain_ws_handler, "127.0.0.1", EXT_WS_PORT,
        )
        LOG.info("Extension WS relay listening on ws://127.0.0.1:%d", EXT_WS_PORT)
        return server
    except OSError as e:
        LOG.warning("Could not start extension WS relay on port %d: %s", EXT_WS_PORT, e)
        return None

# Bulk sync state
_bulk_running = False
_bulk_cancel = False
_bulk_paused = False
_bulk_progress = {"total": 0, "done": 0, "ok": 0, "skipped": 0, "failed": [], "status": "idle"}


@router.get("/api/extension/status")
def extension_status():
    """Check if the Firefox extension is connected."""
    return {"connected": _ext_ws is not None}


@router.websocket("/ws/cardmarket")
async def ws_extension(websocket: WebSocket):
    """WebSocket endpoint for the Firefox extension."""
    global _ext_ws
    await websocket.accept()
    _ext_ws = websocket
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            if msg.get("action") == "price_result":
                card_id = msg.get("card_id")
                fut = _pending.pop(card_id, None)
                if fut and not fut.done():
                    fut.set_result(msg)
    except WebSocketDisconnect:
        _ext_ws = None


def _calc_prices(prices: list[float]) -> dict:
    """Calculate min, avg, median from a sorted list of prices."""
    if not prices:
        return {"min": None, "avg": None, "median": None}
    prices.sort()
    p_min = round(prices[0], 2)
    top5 = prices[:5]
    p_avg = round(sum(top5) / len(top5), 2)
    p_median = round(top5[len(top5) // 2], 2)
    return {"min": p_min, "avg": p_avg, "median": p_median}


def _process_result(card: Card, result: dict, db: Session) -> dict:
    """Process scraping result: extract trend and min/avg/median price, save to DB."""
    trend = result.get("trend")
    offers = result.get("offers", [])

    cond_prices = []
    lang_prices = []
    for offer in offers:
        price = offer.get("price")
        if price is None:
            continue
        if card.lang and offer.get("lang") and offer["lang"] != card.lang:
            continue
        lang_prices.append(price)
        if offer.get("condition") == card.condition:
            cond_prices.append(price)

    calc = _calc_prices(cond_prices)
    if calc["min"] is None:
        calc = _calc_prices(lang_prices)

    if trend is not None:
        card.price_cardmarket = trend
        card.price_manual = False
        card.price_source = "cardmarket"
    if calc["min"] is not None:
        card.price_cm_min = calc["min"]
        card.price_cm_avg = calc["avg"]
        card.price_cm_median = calc["median"]
    if trend is not None or calc["min"] is not None:
        from datetime import datetime, timezone
        card.price_updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(card)

    return {
        "trend": trend,
        "cm_min": calc["min"],
        "cm_avg": calc["avg"],
        "cm_median": calc["median"],
    }


async def _send_scrape(card_db_id: int, url: str, card: Card) -> dict:
    """Send a scrape request to the extension and wait for result."""
    if _ext_ws is None:
        return {"error": "extension_not_connected"}

    loop = asyncio.get_event_loop()
    fut = loop.create_future()
    _pending[card_db_id] = fut

    payload = json.dumps({
        "action": "scrape_price",
        "card_id": card_db_id,
        "url": url,
        "condition": card.condition,
        "lang": card.lang,
    })
    if hasattr(_ext_ws, "send_text"):
        await _ext_ws.send_text(payload)
    else:
        await _ext_ws.send(payload)

    try:
        result = await asyncio.wait_for(fut, timeout=20)
    except asyncio.TimeoutError:
        _pending.pop(card_db_id, None)
        return {"error": "timeout"}

    return result


async def _scrape_one(card_db_id: int, card: Card, db: Session) -> dict:
    """Scrape card price. If no offers found for the desired language, retry with language filter."""
    from ..cardmarket_maps import get_cardmarket_url, _LANG_MAP

    url = get_cardmarket_url(card, db)
    if not url:
        return {"error": "cannot_build_url"}

    result = await _send_scrape(card_db_id, url, card)

    if result.get("error"):
        return {"error": result["error"]}
    if result.get("cloudflare"):
        return {"error": "cloudflare"}
    if result.get("not_found"):
        return {"error": "not_found"}

    # Check if we got offers matching the card's language
    offers = result.get("offers", [])
    has_lang_offers = any(o.get("lang") == card.lang for o in offers)

    if not has_lang_offers and card.lang and result.get("pageUrl"):
        # Retry with language filter on the actual card page URL
        lang_id = _LANG_MAP.get(card.lang)
        if lang_id:
            page_url = result["pageUrl"].split("?")[0]
            retry_url = f"{page_url}?language={lang_id}"
            LOG.info("No %s offers found, retrying with language filter: %s", card.lang, retry_url)
            retry_result = await _send_scrape(card_db_id, retry_url, card)

            if not retry_result.get("error") and not retry_result.get("cloudflare") and not retry_result.get("not_found"):
                # Merge: keep trend from first result, offers from retry
                retry_result["trend"] = retry_result.get("trend") or result.get("trend")
                result = retry_result

    return _process_result(card, result, db)


@router.post("/api/cards/{card_db_id}/cm-price")
async def fetch_cardmarket_price(card_db_id: int, db: Session = Depends(get_db)):
    """Ask the extension to scrape the Cardmarket price for a card."""
    card = db.get(Card, card_db_id)
    if not card:
        return {"error": "card_not_found"}

    result = await _scrape_one(card_db_id, card, db)
    return result


@router.post("/api/cm-bulk/start")
async def bulk_start(db: Session = Depends(get_db)):
    """Start bulk price sync from Cardmarket."""
    global _bulk_running, _bulk_cancel, _bulk_paused, _bulk_progress

    if _bulk_running:
        return {"error": "already_running"}
    if _ext_ws is None:
        return {"error": "extension_not_connected"}

    cards = db.scalars(select(Card)).all()
    _bulk_running = True
    _bulk_cancel = False
    _bulk_paused = False
    _bulk_progress = {
        "total": len(cards),
        "done": 0,
        "ok": 0,
        "skipped": 0,
        "failed": [],
        "status": "running",
    }

    # Run in background
    asyncio.create_task(_bulk_worker([c.id for c in cards]))
    return _bulk_progress


async def _bulk_worker(card_ids: list[int]):
    global _bulk_running, _bulk_cancel, _bulk_paused, _bulk_progress
    from ..database import SessionLocal

    try:
        for card_id in card_ids:
            # Check cancel
            if _bulk_cancel:
                _bulk_progress["status"] = "cancelled"
                break

            # Wait while paused
            while _bulk_paused and not _bulk_cancel:
                _bulk_progress["status"] = "paused"
                await asyncio.sleep(1)

            if _bulk_cancel:
                _bulk_progress["status"] = "cancelled"
                break

            _bulk_progress["status"] = "running"

            db = SessionLocal()
            try:
                card = db.get(Card, card_id)
                if not card:
                    _bulk_progress["done"] += 1
                    _bulk_progress["skipped"] += 1
                    continue

                result = await _scrape_one(card_id, card, db)

                if result.get("error") == "cloudflare":
                    _bulk_paused = True
                    _bulk_progress["status"] = "cloudflare"
                    # Wait for user to resume
                    while _bulk_paused and not _bulk_cancel:
                        await asyncio.sleep(1)
                    if _bulk_cancel:
                        _bulk_progress["status"] = "cancelled"
                        break
                    # Retry this card
                    result = await _scrape_one(card_id, card, db)

                if result.get("error"):
                    _bulk_progress["failed"].append({
                        "id": card_id,
                        "name": card.name,
                        "error": result["error"],
                    })
                else:
                    _bulk_progress["ok"] += 1

                _bulk_progress["done"] += 1
            finally:
                db.close()

            # Delay between requests
            await asyncio.sleep(4)

        if _bulk_progress["status"] != "cancelled":
            _bulk_progress["status"] = "done"
    except Exception as e:
        _bulk_progress["status"] = f"error: {e}"
    finally:
        _bulk_running = False


@router.get("/api/cm-bulk/status")
async def bulk_status():
    return _bulk_progress


@router.post("/api/cm-bulk/stop")
async def bulk_stop():
    global _bulk_cancel
    _bulk_cancel = True
    return {"ok": True}


@router.post("/api/cm-bulk/resume")
async def bulk_resume():
    global _bulk_paused
    _bulk_paused = False
    return {"ok": True}
