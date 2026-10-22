"""Sichere JSON-Persistenz: atomare Schreibvorgänge, Sperren, Erkennung beschädigter Dateien."""
from __future__ import annotations

import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator

from .errors import StorageError
from .security import restrict_permissions

try:  # POSIX
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]


def read_json(path: Path, default: Any = None) -> Any:
    """Liest eine JSON-Datei. Fehlt sie, wird `default` geliefert.

    Eine beschädigte Datei löst StorageError aus und wird NICHT überschrieben.
    """
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StorageError(
            f"Beschädigte JSON-Datei: {path} ({exc}). Die Datei wurde nicht verändert. "
            "Bitte aus einem Backup wiederherstellen oder manuell prüfen."
        ) from exc
    except OSError as exc:
        raise StorageError(f"Datei nicht lesbar: {path} ({exc.strerror})") from exc


def write_json(path: Path, data: Any) -> None:
    """Schreibt JSON atomar: temporäre Datei im Zielordner, fsync, dann os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        restrict_permissions(Path(tmp_name))
        os.replace(tmp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def read_versioned(path: Path, schema_version: int, default_factory) -> dict:
    """Liest eine versionierte Datei und prüft die Schema-Version."""
    data = read_json(path)
    if data is None:
        return default_factory()
    if not isinstance(data, dict) or "schemaVersion" not in data:
        raise StorageError(f"Unerwartete Struktur (kein schemaVersion): {path}")
    if data["schemaVersion"] > schema_version:
        raise StorageError(
            f"{path} wurde mit einer neueren Schema-Version ({data['schemaVersion']}) erzeugt als "
            f"von diesem Programm unterstützt ({schema_version}). Bitte Programm aktualisieren."
        )
    return data


@contextlib.contextmanager
def run_lock(lock_path: Path) -> Iterator[None]:
    """Exklusive, nicht blockierende Sperre gegen parallele collect.py-Läufe."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+")
    try:
        if fcntl is not None:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise StorageError("Ein anderer collect.py-Lauf ist aktiv (Sperre " + str(lock_path) + ").") from exc
        yield
    finally:
        if fcntl is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()
