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
    # API-Schlüssel der KI-Anbieter (OpenAI/Perplexity/xAI/Anthropic mit Präfix, Google mit "AIza") und der Header x-api-key
    re.compile(r"\b(?:sk|pplx|xai|gsk)-[A-Za-z0-9_\-]{8,}|\bAIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)(x-api-key[\"']?\s*[=:]\s*[\"']?)[^\s\"',}]+"),
    # Slack Incoming Webhook: der Pfad hinter /services/ ist das Geheimnis (Benachrichtigung, `src/notify.py`)
    re.compile(r"(hooks\.slack\.com/services/)[A-Za-z0-9/_\-]+"),
]


def redact(text: object) -> str:
    """Entfernt Tokens, JWTs und private Schlüssel aus einem Text (für Logs/Fehlermeldungen)."""
    result = str(text)
    result = _PATTERNS[0].sub("[SCHLÜSSEL ENTFERNT]", result)
    result = _PATTERNS[1].sub(r"\1[ENTFERNT]", result)
    result = _PATTERNS[2].sub(r"\1\2[ENTFERNT]", result)
    result = _PATTERNS[3].sub("[JWT ENTFERNT]", result)
    result = _PATTERNS[5].sub(r"\1[ENTFERNT]", result)  # erst der Header, dann die nackten Schlüssel
    result = _PATTERNS[4].sub("[API-SCHLÜSSEL ENTFERNT]", result)
    result = _PATTERNS[6].sub(r"\1[ENTFERNT]", result)
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


def read_api_key(env_var: str | None, label: str) -> str:
    """Liest einen API-Schlüssel (KI-Anbieter) aus einer Umgebungsvariable; der Wert ist der Schlüssel selbst.

    Anders als `read_secret` wird kein Dateipfad akzeptiert: Ein Schlüssel ist eine einzelne Zeile ohne Leerzeichen.
    Fehlt die Variable oder ist sie leer, gibt es einen `ConfigError` mit Handlungsanweisung."""
    if not env_var:
        raise ConfigError(f"{label}: apiKeyEnvironmentVariable fehlt in der Konfiguration.")
    value = os.environ.get(env_var, "").strip()
    if not value:
        raise ConfigError(f"{label}: Umgebungsvariable {env_var} ist nicht gesetzt oder leer.")
    if any(char.isspace() for char in value) or len(value) < 8:
        raise ConfigError(f"{label}: Umgebungsvariable {env_var} enthält keinen gültigen API-Schlüssel.")
    return value


def read_env_secret(env_var: str | None, label: str) -> str:
    """Liest ein beliebiges Geheimnis (SMTP-Passwort, Webhook-Adresse) aus einer Umgebungsvariable.

    Anders als `read_api_key` ohne Formatprüfung, weil Passwörter Leerzeichen enthalten dürfen; nur leer ist ein Fehler."""
    if not env_var:
        raise ConfigError(f"{label}: Name der Umgebungsvariable fehlt in der Konfiguration.")
    value = os.environ.get(env_var, "")
    if not value.strip():
        raise ConfigError(f"{label}: Umgebungsvariable {env_var} ist nicht gesetzt oder leer.")
    return value.strip()


def has_api_key(env_var: str | None) -> bool:
    """True, wenn die Umgebungsvariable einen brauchbaren Schlüssel enthält (ohne Fehler, für die Anbieterwahl)."""
    try:
        read_api_key(env_var, "")
        return True
    except ConfigError:
        return False


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
