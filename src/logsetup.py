"""Logging für die Einstiege (`collect.py`, `ki.py`): farbige Terminalausgabe plus Logdatei.

Terminal: Stufe aus `settings.logLevel` bzw. `--log-level`. Datei: immer DEBUG, damit sich nach einem Fehler nachlesen
lässt, was passiert ist (z. B. der Anfang einer nicht lesbaren KI-Antwort, Wiederholungen, Timeouts), ohne den Lauf mit
DEBUG wiederholen zu müssen. Die Datei liegt unter `<Datenordner>/logs/<einstieg>.log`, rotiert bei 2 MB (fünf alte
Dateien bleiben) und hat Rechte 0600. Jede Zeile läuft durch `security.redact`, Schlüssel und Tokens stehen also nie im
Log; Rezensionstexte können dort stehen (Debug-Stufe), deshalb gehört der Ordner wie `data/` nicht ins Repository.
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .security import redact
from .ui import paint

log = logging.getLogger("arr")
LOG_DIR_NAME = "logs"        # Unterordner im Datenordner
LOG_MAX_BYTES = 2_000_000    # Größe, ab der rotiert wird (Bytes)
LOG_BACKUPS = 5              # Anzahl alter Dateien, die bleiben


class _TerminalFormat(logging.Formatter):
    """Terminalzeile: Fehler rot, Warnungen gelb mit ⚠, Debug gedimmt, Überschriften (▶/■) hervorgehoben."""

    def format(self, record: logging.LogRecord) -> str:
        msg = redact(record.getMessage())
        if record.levelno >= logging.ERROR:
            return paint(f"  {msg}", "31")
        if record.levelno >= logging.WARNING:
            return paint(f"  ⚠ {msg}", "33")
        if record.levelno == logging.DEBUG:
            return paint(f"    {msg}", "2")
        return paint(msg, "1", "35") if msg[:1] in ("▶", "■") else "  " + msg


class _FileFormat(logging.Formatter):
    """Dateizeile: Zeitstempel, Stufe, Logger, Text (ohne Farben, mit `redact`)."""

    def format(self, record: logging.LogRecord) -> str:
        return f"{self.formatTime(record, '%Y-%m-%d %H:%M:%S')} {record.levelname:<7} {record.name}: {redact(record.getMessage())}"


def log_file_path(data_dir: Path, name: str) -> Path:
    """Pfad der Logdatei eines Einstiegs (`collect`, `ki`) unter dem Datenordner."""
    return data_dir / LOG_DIR_NAME / f"{name}.log"


def setup_logging(level: str, data_dir: Path | None = None, name: str = "collect") -> Path | None:
    """Richtet Terminal- und Datei-Logging ein.

    - Parameter level: Stufe für das Terminal (DEBUG, INFO, WARNING, ERROR); die Datei bekommt immer DEBUG.
    - Parameter data_dir: Datenordner; None → keine Logdatei (Tests, --status ohne Konfiguration).
    - Parameter name: Dateiname ohne Endung, z. B. `collect` oder `ki`.
    - Returns: Pfad der Logdatei oder None, wenn keine geschrieben wird (auch wenn der Ordner nicht anlegbar ist)."""
    terminal = logging.StreamHandler(sys.stdout)
    terminal.setFormatter(_TerminalFormat())
    terminal.setLevel(level.upper())
    handlers: list[logging.Handler] = [terminal]
    path = None
    if data_dir is not None:
        path = log_file_path(data_dir, name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8")
            os.chmod(path, 0o600)
            handler.setFormatter(_FileFormat())
            handler.setLevel(logging.DEBUG)
            handlers.append(handler)
        except OSError as exc:
            path = None
            terminal.handle(logging.LogRecord("arr", logging.WARNING, __file__, 0, "Logdatei nicht beschreibbar: %s", (exc,), None))
    log.handlers[:] = handlers
    log.setLevel(logging.DEBUG)   # Handler filtern; der Logger selbst lässt alles durch
    return path
