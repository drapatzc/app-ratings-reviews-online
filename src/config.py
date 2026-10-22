"""Laden und Validieren der JSON-Konfiguration; CLI-Parameter überschreiben Konfigurationswerte."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .errors import ConfigError

SCHEMA_VERSION = 1
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PLATFORMS = ("apple", "google")

DEFAULT_SETTINGS: dict[str, Any] = {
    "outputDirectory": "./data",
    "reportDirectory": "./reports",
    "defaultStartDate": None,
    "defaultEndDate": None,
    "requestTimeoutSeconds": 30,
    "maxRetries": 3,
    "incrementalSync": True,
    "overlapDays": 7,
    "minRefreshMinutes": 30,
    "fullSyncIntervalDays": 30,
    "fetchAppleVersions": True,
    "logLevel": "INFO",
}


@dataclass
class Config:
    """Validierte Konfiguration. `base_dir` ist der Ordner, relativ zu dem Pfade aufgelöst werden."""

    settings: dict[str, Any]
    customers: list[dict[str, Any]]
    base_dir: Path
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def data_dir(self) -> Path:
        return self._resolve(self.settings["outputDirectory"])

    @property
    def report_dir(self) -> Path:
        return self._resolve(self.settings["reportDirectory"])

    def _resolve(self, value: str) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else (self.base_dir / path).resolve()


def parse_date(value: Any, label: str) -> date | None:
    """Parst YYYY-MM-DD; None bleibt None."""
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ConfigError(f"{label}: ungültiges Datum '{value}' (erwartet YYYY-MM-DD).") from exc


def load_config(path: Path, overrides: dict[str, Any] | None = None) -> Config:
    """Lädt `path`, wendet CLI-Overrides auf `settings` an und validiert alles."""
    if not path.is_file():
        raise ConfigError(f"Konfiguration nicht gefunden: {path}. Vorlage: config/config.example.json")
    text = path.read_text(encoding="utf-8")
    if "PRIVATE KEY-----" in text or '"private_key"' in text:
        raise ConfigError("Die Konfiguration enthält anscheinend einen privaten Schlüssel. "
                          "Schlüssel gehören in Umgebungsvariablen oder geschützte Dateien, nicht in die JSON-Konfiguration.")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Konfiguration ist kein gültiges JSON: {exc}") from exc
    user_settings = raw.get("settings") if isinstance(raw, dict) else None
    settings = {**DEFAULT_SETTINGS, **(user_settings if isinstance(user_settings, dict) else {})}
    for key, value in (overrides or {}).items():
        if value is not None:
            settings[key] = value
    errors = validate(raw, settings)
    if errors:
        raise ConfigError("Konfiguration fehlerhaft:\n  - " + "\n  - ".join(errors))
    parent = path.resolve().parent
    base_dir = parent.parent if parent.name == "config" else parent
    return Config(settings=settings, customers=raw["customers"], base_dir=base_dir, raw=raw)


def validate(raw: Any, settings: dict[str, Any]) -> list[str]:
    """Liefert eine Liste verständlicher Fehlermeldungen (leer = gültig)."""
    errors: list[str] = []
    if not isinstance(raw, dict):
        return ["Wurzel muss ein JSON-Objekt sein."]
    if raw.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"schemaVersion muss {SCHEMA_VERSION} sein (gefunden: {raw.get('schemaVersion')!r}).")
    for key in ("defaultStartDate", "defaultEndDate"):
        try:
            parse_date(settings.get(key), f"settings.{key}")
        except ConfigError as exc:
            errors.append(str(exc))
    for key, minimum in (("requestTimeoutSeconds", 1), ("maxRetries", 0), ("overlapDays", 0),
                         ("minRefreshMinutes", 0), ("fullSyncIntervalDays", 0)):
        value = settings.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < minimum:
            errors.append(f"settings.{key} muss eine Zahl >= {minimum} sein.")
    if str(settings.get("logLevel", "")).upper() not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        errors.append("settings.logLevel muss DEBUG, INFO, WARNING oder ERROR sein.")
    customers = raw.get("customers")
    if not isinstance(customers, list) or not customers:
        errors.append("customers muss eine nicht leere Liste sein.")
        return errors
    seen_customers: set[str] = set()
    for ci, customer in enumerate(customers):
        where = f"customers[{ci}]"
        if not isinstance(customer, dict):
            errors.append(f"{where} muss ein Objekt sein.")
            continue
        cid = customer.get("id")
        if not isinstance(cid, str) or not ID_RE.match(cid):
            errors.append(f"{where}.id fehlt oder enthält ungültige Zeichen (erlaubt: Buchstaben, Ziffern, . _ -).")
            continue
        where = f"Kunde '{cid}'"
        if cid in seen_customers:
            errors.append(f"{where}: id doppelt vorhanden.")
        seen_customers.add(cid)
        if not customer.get("name"):
            errors.append(f"{where}: name fehlt.")
        creds = customer.get("credentials") or {}
        apps = customer.get("apps")
        if not isinstance(apps, list) or not apps:
            errors.append(f"{where}: apps muss eine nicht leere Liste sein.")
            continue
        seen_apps: set[str] = set()
        for ai, app in enumerate(apps):
            aid = app.get("id") if isinstance(app, dict) else None
            if not isinstance(aid, str) or not ID_RE.match(aid):
                errors.append(f"{where}.apps[{ai}].id fehlt oder ist ungültig.")
                continue
            awhere = f"{where}, App '{aid}'"
            if aid in seen_apps:
                errors.append(f"{awhere}: id doppelt vorhanden.")
            seen_apps.add(aid)
            if not app.get("name"):
                errors.append(f"{awhere}: name fehlt.")
            platforms = app.get("platforms")
            if not isinstance(platforms, dict) or not platforms:
                errors.append(f"{awhere}: platforms fehlt.")
                continue
            for pname, pcfg in platforms.items():
                if pname not in PLATFORMS:
                    errors.append(f"{awhere}: unbekannte Plattform '{pname}' (erlaubt: apple, google).")
                    continue
                if not isinstance(pcfg, dict):
                    errors.append(f"{awhere}.{pname} muss ein Objekt sein.")
                    continue
                if not pcfg.get("enabled", True):
                    continue
                errors += _validate_platform(awhere, pname, pcfg, creds, bool(customer.get("enabled", True)
                                                                          and app.get("enabled", True)))
    return errors


def _validate_platform(where: str, pname: str, pcfg: dict, creds: dict, active: bool) -> list[str]:
    errors: list[str] = []
    if pname == "apple":
        if not re.fullmatch(r"\d{5,15}", str(pcfg.get("appId", ""))):
            errors.append(f"{where}.apple.appId fehlt oder ist keine numerische App-Store-ID.")
        if active:
            apple = creds.get("apple") or {}
            for key in ("issuerId", "keyId"):
                if not apple.get(key):
                    errors.append(f"{where}: credentials.apple.{key} fehlt.")
            if not (apple.get("privateKeyEnvironmentVariable") or apple.get("privateKeyFile")):
                errors.append(f"{where}: credentials.apple.privateKeyEnvironmentVariable (oder privateKeyFile) fehlt.")
    else:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+", str(pcfg.get("packageName", ""))):
            errors.append(f"{where}.google.packageName fehlt oder ist ungültig (z. B. com.example.app).")
        if active:
            google = creds.get("google") or {}
            if not (google.get("serviceAccountEnvironmentVariable") or google.get("serviceAccountFile")):
                errors.append(f"{where}: credentials.google.serviceAccountEnvironmentVariable "
                              "(oder serviceAccountFile) fehlt.")
    return errors
