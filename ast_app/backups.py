"""Automatic local and optional external database backups."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path


def _prune(folder: Path, retention_days: int, today: date) -> None:
    cutoff = today - timedelta(days=max(1, retention_days))
    for path in folder.glob("AST-Auto-????-??-??.sqlite3"):
        try:
            stamp = datetime.strptime(path.stem.removeprefix("AST-Auto-"), "%Y-%m-%d").date()
        except ValueError:
            continue
        if stamp < cutoff:
            path.unlink()


def run_automatic_backups(db, local_folder, external_folder="", retention_days=30, today=None):
    """Create one verified backup per day and prune only AST automatic files."""
    today = today or date.today()
    created = []
    local = Path(local_folder)
    local.mkdir(parents=True, exist_ok=True)
    local_path = local / f"{db.path.stem}-{today.isoformat()}.sqlite3"
    if not local_path.exists():
        db.backup(local_path)
        created.append(local_path)
    if str(external_folder).strip():
        external = Path(external_folder).expanduser()
        external.mkdir(parents=True, exist_ok=True)
        external_path = external / f"AST-Auto-{today.isoformat()}.sqlite3"
        if not external_path.exists():
            db.backup(external_path)
            created.append(external_path)
        _prune(external, int(retention_days), today)
    return created
