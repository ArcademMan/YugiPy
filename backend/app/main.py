import logging
from contextlib import asynccontextmanager
from pathlib import Path


class _QuietRouteFilter(logging.Filter):
    _SUPPRESSED = ("/api/ocr-preview", "/api/extension/status")

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(route in msg for route in self._SUPPRESSED)


logging.getLogger("uvicorn.access").addFilter(_QuietRouteFilter())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .routes import cards, cardmarket, scan, settings, setup, stats, storage

# Auto-migrate existing DBs, then create_all for brand-new ones.
from . import models  # noqa: ensure models are registered
from .migrate import run_migrations
run_migrations(engine)
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
app.include_router(storage.router)

# Serve frontend static files (Vite build output)
frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
app.mount("/assets", StaticFiles(directory=str(frontend_dir / "assets")), name="assets")
app.mount("/flags", StaticFiles(directory=str(frontend_dir / "flags")), name="flags")


# SPA catch-all: serve index.html for any non-API route (Vue Router history mode)
@app.get("/{full_path:path}")
async def spa_fallback(request: Request, full_path: str):
    # Try to serve the exact file first
    file_path = frontend_dir / full_path
    if full_path and file_path.is_file():
        return FileResponse(file_path)
    # Otherwise serve index.html for client-side routing
    return FileResponse(frontend_dir / "index.html")
