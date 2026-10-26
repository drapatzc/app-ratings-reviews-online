"""Sicherungskopie des Datenordners vor jedem Lauf, die Daten ändert (Wunsch des Nutzers, 26.10.2026).

Vor `collect.py` (außer `--dry-run`, `--status`, `--list-apps`) wird `data/` als ZIP unter `settings.backupDirectory` abgelegt, damit
bei einem Fehler der alte Stand wieder verwendet werden kann. Das ZIP enthält alle Dateien von `data/` außer `logs/` mit dem Ordnernamen als Präfix;
zum Wiederherstellen genügt es, es im Projektordner zu entpacken (siehe BETRIEB.md). Konfiguration und Schlüssel sind nicht enthalten.
"""
from __future__ import annotations

import logging
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .logsetup import LOG_DIR_NAME
from .storage import atomic_target

log = logging.getLogger("arr.backup")

#: Dateien, die nie gesichert werden: Sperrdatei und angefangene Schreibvorgänge.
_SKIP_NAMES = {".lock"}


def _skip(path: Path, data_dir: Path) -> bool:
    """True für Sperrdatei, temporäre Dateien (`.name.…tmp`) des atomaren Schreibens und den Logordner `logs/` (Logs sind keine Daten)."""
    relative = path.relative_to(data_dir)
    return (path.name in _SKIP_NAMES or (path.name.startswith(".") and path.name.endswith(".tmp"))
            or relative.parts[0] == LOG_DIR_NAME)


def backup_name(data_dir: Path, stamp: str) -> str:
    """Dateiname `<Ordnername>-<UTC-Zeitstempel>.zip`, z. B. `data-2026-10-26T061500Z.zip`."""
    return f"{data_dir.name}-{stamp}.zip"


def prune(backup_dir: Path, data_dir: Path, keep: int) -> list[Path]:
    """Löscht die ältesten Sicherungen dieses Datenordners, sodass höchstens `keep` bleiben (0 = alle behalten).

    Es werden nur Dateien nach dem Namensmuster dieses Werkzeugs berührt, nie fremde Dateien.
    - Returns: die gelöschten Dateien.
    """
    if keep <= 0:
        return []
    pattern = re.compile(re.escape(data_dir.name) + r"-\d{4}-\d{2}-\d{2}T\d{6}Z(?:-\d+)?\.zip$")
    mine = sorted(path for path in backup_dir.iterdir() if path.is_file() and pattern.match(path.name))
    removed = mine[:-keep] if len(mine) > keep else []
    for path in removed:
        path.unlink()
    return removed


def backup_data(data_dir: Path, backup_dir: Path, keep: int = 30, clock: Callable[[], datetime] | None = None) -> Path | None:
    """Packt `data_dir` in ein ZIP unter `backup_dir` und gibt dessen Pfad zurück; None, wenn es nichts zu sichern gibt.

    Das ZIP wird atomar geschrieben (nie ein halbes ZIP), hat die Rechte 0600 und trägt die Dateien als `<Ordnername>/…`.
    Danach werden Sicherungen über `keep` hinaus entfernt.
    - Parameter data_dir: Datenordner (Standard `data/`).
    - Parameter backup_dir: Zielordner der Sicherungen.
    - Parameter keep: Anzahl der zu behaltenden Sicherungen, 0 = unbegrenzt.
    - Parameter clock: Uhr für den Zeitstempel (Tests).
    - Throws: OSError, wenn das ZIP nicht geschrieben werden kann (der Aufrufer bricht den Lauf dann ab).
    """
    inside = backup_dir.resolve()   # liegt der Sicherungsordner in data/, wird er nicht mit gesichert
    files = sorted(path for path in data_dir.rglob("*")
                   if path.is_file() and not _skip(path, data_dir) and inside not in path.resolve().parents) if data_dir.is_dir() else []
    if not files:
        log.info("Sicherung übersprungen: %s ist leer oder fehlt (erster Lauf).", data_dir)
        return None
    stamp = (clock or (lambda: datetime.now(timezone.utc)))().strftime("%Y-%m-%dT%H%M%SZ")
    backup_dir.mkdir(parents=True, exist_ok=True)
    target, number = backup_dir / backup_name(data_dir, stamp), 1
    while target.exists():  # mehrere Läufe in derselben Sekunde
        number += 1
        target = backup_dir / backup_name(data_dir, f"{stamp}-{number}")
    with atomic_target(target) as tmp, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, arcname=str(Path(data_dir.name) / path.relative_to(data_dir)))
    removed = prune(backup_dir, data_dir, keep)
    log.info("Sicherung: %s (%d Dateien, %.1f MB)%s", target, len(files), target.stat().st_size / 1_000_000,
             f"; {len(removed)} ältere entfernt (settings.backupKeep = {keep})" if removed else "")
    return target
