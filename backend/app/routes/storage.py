"""Storage management: stats, backup, restore, open data folder."""

import os
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import FileResponse

from ..paths import DATA_DIR, COLLECTION_DB, HASH_DB, IMAGES_DIR, FULL_IMAGES_DIR

router = APIRouter(prefix="/api/storage", tags=["storage"])

BACKUP_DIR = DATA_DIR / "backups"


def _dir_stats(path: Path) -> tuple[int, int]:
    """Return (file_count, total_bytes) for a directory."""
    count = 0
    size = 0
    if path.is_dir():
        for f in path.rglob("*"):
            if f.is_file() and f.name != "_cards.json":
                count += 1
                size += f.stat().st_size
    return count, size


@router.get("/stats")
def get_storage_stats():
    """Return storage statistics: image counts, sizes, DB size."""
    thumb_count, thumb_size = _dir_stats(IMAGES_DIR)
    full_count, full_size = _dir_stats(FULL_IMAGES_DIR)

    db_size = COLLECTION_DB.stat().st_size if COLLECTION_DB.exists() else 0

    # List existing backups
    backups = []
    if BACKUP_DIR.is_dir():
        for f in sorted(BACKUP_DIR.glob("*.zip"), reverse=True):
            backups.append({
                "name": f.name,
                "size": f.stat().st_size,
                "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })

    return {
        "data_dir": str(DATA_DIR),
        "thumb_images": thumb_count,
        "thumb_size": thumb_size,
        "full_images": full_count,
        "full_size": full_size,
        "total_images": thumb_count + full_count,
        "total_images_size": thumb_size + full_size,
        "db_size": db_size,
        "backups": backups,
    }


@router.post("/open-folder")
def open_data_folder():
    """Open the data directory in the system file explorer."""
    path = str(DATA_DIR)
    try:
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/backup")
def create_backup():
    """Create a zip backup of the collection DB and settings."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"yugipy_backup_{timestamp}.zip"
    backup_path = BACKUP_DIR / backup_name

    with zipfile.ZipFile(backup_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Collection database
        if COLLECTION_DB.exists():
            zf.write(COLLECTION_DB, "yugipy.db")

        # Hash database
        if HASH_DB.exists():
            zf.write(HASH_DB, "card_hashes.db")

        # Settings
        settings_file = Path(__file__).resolve().parent.parent.parent / "settings.json"
        if settings_file.exists():
            zf.write(settings_file, "settings.json")

    size = backup_path.stat().st_size
    return {
        "ok": True,
        "name": backup_name,
        "size": size,
        "created": datetime.now().isoformat(),
    }


@router.get("/backup/{name}")
def download_backup(name: str):
    """Download a backup file."""
    path = BACKUP_DIR / name
    if not path.exists() or not path.name.endswith(".zip"):
        return {"error": "Backup not found"}
    return FileResponse(path, filename=name, media_type="application/zip")


@router.delete("/backup/{name}")
def delete_backup(name: str):
    """Delete a backup file."""
    path = BACKUP_DIR / name
    if path.exists() and path.name.endswith(".zip"):
        path.unlink()
        return {"ok": True}
    return {"error": "Backup not found"}


@router.post("/restore")
async def restore_backup(file: UploadFile = File(...)):
    """Restore a backup from an uploaded zip file."""
    if not file.filename.endswith(".zip"):
        return {"ok": False, "error": "File must be a .zip"}

    # Save uploaded file to temp
    content = await file.read()
    tmp = NamedTemporaryFile(delete=False, suffix=".zip")
    try:
        tmp.write(content)
        tmp.close()

        with zipfile.ZipFile(tmp.name, "r") as zf:
            names = zf.namelist()

            if "yugipy.db" not in names:
                return {"ok": False, "error": "Invalid backup: missing yugipy.db"}

            # Restore collection DB
            zf.extract("yugipy.db", DATA_DIR)

            # Restore hash DB if present
            if "card_hashes.db" in names:
                zf.extract("card_hashes.db", DATA_DIR)

            # Restore settings if present
            if "settings.json" in names:
                settings_dir = Path(__file__).resolve().parent.parent.parent
                zf.extract("settings.json", settings_dir)

        return {"ok": True, "restored": names}
    except zipfile.BadZipFile:
        return {"ok": False, "error": "Invalid zip file"}
    finally:
        os.unlink(tmp.name)
