from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .routes import cards, cardmarket, scan, settings, setup

app = FastAPI(title="YugiPy", version="1.0.0")

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

# Serve frontend static files
frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
