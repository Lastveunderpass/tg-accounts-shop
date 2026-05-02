from __future__ import annotations

import asyncio
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from src.config import get_settings
from src.logger import get_logger

logger = get_logger("backup")


def _db_path_from_url(url: str) -> Path | None:
    if not url.startswith("sqlite"):
        return None
    after_scheme = url.split(":///", 1)[-1]
    return Path(after_scheme)


async def run_sqlite_backup() -> Path | None:
    settings = get_settings()
    db_path = _db_path_from_url(settings.database_url)
    if db_path is None or not db_path.exists():
        logger.warning("backup_skipped_no_db", path=str(db_path))
        return None

    backups_dir = Path("data") / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
    dst = backups_dir / f"db-{ts}.sqlite3"

    proc = await asyncio.create_subprocess_exec(
        "sqlite3",
        str(db_path),
        f".backup '{dst}'",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _out, err = await proc.communicate()
    if proc.returncode != 0:
        logger.error("backup_failed", returncode=proc.returncode, err=err.decode(errors="ignore"))
        # fallback: просто скопировать файл (не идеально, но лучше чем ничего)
        try:
            shutil.copy2(db_path, dst)
        except Exception as e:
            logger.error("backup_fallback_copy_failed", error=str(e))
            return None

    logger.info("backup_created", path=str(dst), size=dst.stat().st_size if dst.exists() else 0)
    rotate(backups_dir, settings.backup_retention_days)
    return dst


def rotate(backups_dir: Path, retention_days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    removed = 0
    for f in backups_dir.glob("db-*.sqlite3*"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=UTC)
            if mtime < cutoff:
                f.unlink()
                removed += 1
        except OSError:
            continue
    if removed:
        logger.info("backup_rotated", removed=removed)
    return removed
