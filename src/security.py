"""Sicherheitshilfen: Geheimnisse laden, Logs bereinigen, Dateirechte."""
from __future__ import annotations

import os
import re
from pathlib import Path

from .errors import ConfigError

_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"),
    re.compile(r"(?i)(assertion|access_token|refresh_token|client_secret|private_key)(\"?\s*[=:]\s*\"?)[^\s\"&,}]+"),
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]*"),
]


def redact(text: object) -> str:
    """Entfernt Tokens, JWTs und private Schlüssel aus einem Text (für Logs/Fehlermeldungen)."""
    result = str(text)
    result = _PATTERNS[0].sub("[SCHLÜSSEL ENTFERNT]", result)
    result = _PATTERNS[1].sub(r"\1[ENTFERNT]", result)
    result = _PATTERNS[2].sub(r"\1\2[ENTFERNT]", result)
    result = _PATTERNS[3].sub("[JWT ENTFERNT]", result)
    return result


def read_secret(env_var: str | None, file_path: str | None, label: str) -> str:
    """Liest ein Geheimnis aus einer Umgebungsvariable (Inhalt oder Dateipfad) oder aus einer Datei.

    Die Umgebungsvariable darf entweder den Inhalt selbst oder einen Pfad zu einer Datei enthalten.
    """
    value = os.environ.get(env_var, "").strip() if env_var else ""
    if value:
        if value.startswith("-----") or value.startswith("{"):
            return value
        path = Path(value).expanduser()
        if path.is_file():
            return _read_private_file(path, label)
        raise ConfigError(f"{label}: Umgebungsvariable {env_var} enthält weder Schlüsseltext noch einen vorhandenen Dateipfad.")
    if file_path:
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise ConfigError(f"{label}: Schlüsseldatei nicht gefunden: {file_path}")
        return _read_private_file(path, label)
    hint = f"Umgebungsvariable {env_var}" if env_var else "Umgebungsvariable oder Schlüsseldatei"
    raise ConfigError(f"{label}: Zugangsdaten fehlen. Bitte {hint} setzen.")


def _read_private_file(path: Path, label: str) -> str:
    """Liest eine Schlüsseldatei und warnt nicht – prüft nur, dass sie lesbar ist."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ConfigError(f"{label}: Schlüsseldatei nicht lesbar ({exc.strerror}).") from exc


def restrict_permissions(path: Path, is_dir: bool = False) -> None:
    """Setzt eingeschränkte Rechte (nur Besitzer); Fehler (z. B. Windows) werden ignoriert."""
    try:
        os.chmod(path, 0o700 if is_dir else 0o600)
    except OSError:
        pass
