import logging
from contextlib import asynccontextmanager
from pathlib import Path


class _QuietRouteFilter(logging.Filter):
    _SUPPRESSED = ("/api/ocr-preview", "/api/extension/status")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(route in msg for route in self._SUPPRESSED)


logging.getLogger("uvicorn.access").addFilter(_QuietRouteFilter())

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .routes import cards, cardmarket, scan, settings, setup, stats

# Create tables if they don't exist (first-time setup)
from . import models  # noqa: ensure models are registered
Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start plain WS relay for the browser extension (no SSL required)
    server = await cardmarket.start_ext_ws_relay()
    yield
    if server:
        server.close()
        await server.wait_closed()


app = FastAPI(title="YugiPy", version="1.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scan.router)
app.include_router(cards.router)
app.include_router(cardmarket.router)
app.include_router(settings.router)
app.include_router(setup.router)
app.include_router(stats.router)

# Serve frontend static files
frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
