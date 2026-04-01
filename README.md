<p align="center">
  <img src="./assets/icon.png" alt="YugiPy" width="180">
</p>

<h1 align="center">YugiPy</h1>

<p align="center">
  <strong>Yu-Gi-Oh! card collection manager with OCR scanning</strong><br>
  Scan cards with your camera, track your collection, sync prices from Cardmarket.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-blue" alt="Platform">
  <img src="https://img.shields.io/badge/python-3.12+-yellow" alt="Python">
  <img src="https://img.shields.io/badge/backend-FastAPI-green" alt="Backend">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="License">
</p>

---

## Features

| Feature | Description |
|---------|-------------|
| **OCR Scanner** | Point your camera at a card to identify it automatically via artwork hash matching |
| **Collection** | Track cards with rarity, condition, language, location, and quantity |
| **Cardmarket Prices** | Sync prices directly from Cardmarket via a Firefox extension (trend, min, avg, median) |
| **Book View** | Browse your collection in a binder-style layout with grouping, sorting, and filtering |
| **Multi-language** | Supports EN, IT, FR, DE, ES, PT, JA, KO with flag icons |
| **Price Display** | Choose which price to show: trend, lowest offer, average, or median of top 5 offers |
| **Bulk Sync** | Update all card prices from Cardmarket at once with progress tracking |
| **Smart Pricing** | Filters offers by card condition and language for accurate valuations |

## Installation

### From source

```bash
git clone https://github.com/arcademman/yugipy.git
cd yugipy
pip install -r requirements.txt
```

### Build the card index

Before scanning cards, you need to build the recognition index:

1. Start the server (see below)
2. Go to **Settings > Card Index**
3. Click **Configure index** and wait for the download + indexing to complete

### Start the server

```bash
python launcher.py
```

Open your browser at the address shown in the terminal.

## Firefox Extension

YugiPy includes a Firefox extension for syncing prices from Cardmarket.

### Install from source (temporary)

1. Open `about:debugging#/runtime/this-firefox` in Firefox
2. Click "Load Temporary Add-on"
3. Select `extension/manifest.json`

### Install signed version

1. Build the zip: the extension files are in `extension/`
2. Upload to [addons.mozilla.org](https://addons.mozilla.org/developers/) for self-distribution signing
3. Install the signed `.xpi` in Firefox

The connection status is shown as a dot in the navigation bar (green = connected, red = disconnected).

## Architecture

```
Browser ──HTTP──▶ FastAPI Backend ──WebSocket──▶ Firefox Extension
   │                    │                              │
   │                    ├── SQLite (collection)        ├── Cardmarket scraping
   │                    ├── YGOProDeck API             └── Price data extraction
   │                    └── Hash index (OCR)
   │
   └── Static frontend (vanilla JS)
```

## Project Structure

```
yugipy/
├── backend/          # FastAPI backend
│   ├── app/
│   │   ├── routes/   # API endpoints (cards, scan, cardmarket, settings)
│   │   ├── models.py # SQLAlchemy models
│   │   └── schemas.py
│   └── alembic/      # Database migrations
├── frontend/         # Static web frontend
│   ├── index.html
│   ├── js/app.js
│   ├── css/style.css
│   └── flags/        # Country flag icons
├── extension/        # Firefox extension for Cardmarket
│   ├── manifest.json
│   ├── background.js
│   └── content.js
└── launcher.py       # Server launcher (HTTP/HTTPS)
```

## License

[MIT](LICENSE)
