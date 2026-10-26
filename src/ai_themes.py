"""Themenvorschläge der KI prüfen und nach Bestätigung in `config/themen.json` übernehmen.

Die KI schlägt in der Zusammenfassung je App Themen vor (`summary.themeSuggestions` in `ai-analysis.json`), die in den
Rezensionen vorkommen und noch nicht in `themen.json` stehen. Dieses Modul sammelt die Vorschläge über alle Apps,
fasst gleichnamige zusammen, blendet bekannte und abgelehnte aus und schreibt ein bestätigtes Thema als neuen Eintrag
in die Themenliste (`kind` „thema“, Begriffe wie von der KI vorgeschlagen, vom Nutzer vorher gesehen). Nichts passiert
ohne ausdrückliche Bestätigung; abgelehnte Vorschläge merkt sich `data/ai-themes.json`.
"""
from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path

from .errors import ConfigError
from .storage import read_json, read_versioned, write_json

TOPIC_KIND = "thema"


def _slug(name: str) -> str:
    """Themen-ID aus dem deutschen Namen: Kleinbuchstaben, Umlaute aufgelöst, Bindestriche."""
    text = unicodedata.normalize("NFKD", name.lower().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss"))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text)).strip("-") or "thema"


def _key(name: str) -> str:
    return _slug(name)


def ignored_path(data_dir: Path) -> Path:
    return data_dir / "ai-themes.json"


def load_ignored(data_dir: Path) -> dict:
    return read_versioned(ignored_path(data_dir), 1, lambda: {"schemaVersion": 1, "ignored": []})


def suggestions(data_dir: Path, themen_path: Path) -> list[dict]:
    """Vorschläge über alle Apps, zusammengeführt nach Name, ohne bekannte und abgelehnte Themen.

    Jeder Eintrag: `de`, `en`, `terms` (Vereinigung), `count` (Summe), `apps` (App-IDs mit dem Vorschlag), `id` (Vorschlag)."""
    known: set[str] = set()
    if themen_path.is_file():
        for topic in read_json(themen_path, {}).get("topics", []):
            if isinstance(topic, dict):
                known.update(_key(str(topic.get(field))) for field in ("id", "de", "en") if topic.get(field))
    ignored = {_key(name) for name in load_ignored(data_dir).get("ignored", [])}
    merged: dict[str, dict] = {}
    root = data_dir / "customers"
    for path in sorted(root.glob("*/apps/*/*/ai-analysis.json")) if root.is_dir() else []:
        doc = read_versioned(path, 1, lambda: None) or {}
        app_id = path.parent.parent.name
        for item in ((doc.get("summary") or {}).get("themeSuggestions") or []):
            name = str(item.get("de") or "").strip()
            key = _key(name)
            if not name or key in known or key in ignored:
                continue
            entry = merged.setdefault(key, {"id": key, "de": name, "en": str(item.get("en") or name), "terms": [],
                                            "count": 0, "apps": []})
            entry["count"] += int(item.get("count") or 0)
            entry["terms"] = sorted(set(entry["terms"]) | {str(term).lower() for term in item.get("terms") or []})
            if app_id not in entry["apps"]:
                entry["apps"].append(app_id)
    return sorted(merged.values(), key=lambda entry: (-entry["count"], entry["de"]))


def accept(themen_path: Path, suggestion: dict, bereich: str | None = None) -> str:
    """Schreibt den Vorschlag als neues Thema nach `themen.json`; liefert die vergebene ID.

    - Raises: `ConfigError`, wenn die Datei fehlt oder die ID schon vergeben ist.
    """
    if not themen_path.is_file():
        raise ConfigError(f"Themenliste nicht gefunden: {themen_path}")
    doc = read_json(themen_path, {})
    topics = doc.setdefault("topics", [])
    topic_id = _slug(suggestion["de"])
    if any(topic.get("id") == topic_id for topic in topics if isinstance(topic, dict)):
        raise ConfigError(f"Thema '{topic_id}' steht bereits in {themen_path.name}.")
    topic = {"id": topic_id, "de": suggestion["de"], "en": suggestion.get("en") or suggestion["de"], "kind": TOPIC_KIND,
             "terms": sorted({str(term).lower() for term in suggestion.get("terms", []) if str(term).strip()}),
             "quelle": "KI-Vorschlag, vom Nutzer bestätigt"}
    if bereich in ("app", "anbieter"):
        topic["bereich"] = bereich
    topics.append(topic)
    write_json(themen_path, doc)
    try:
        os.chmod(themen_path, 0o644)  # Themenliste ist versionierte Konfiguration, kein Geheimnis
    except OSError:
        pass
    return topic_id


def ignore(data_dir: Path, name: str) -> None:
    """Merkt einen abgelehnten Vorschlag, damit er nicht wieder erscheint."""
    doc = load_ignored(data_dir)
    if name not in doc["ignored"]:
        doc["ignored"].append(name)
        write_json(ignored_path(data_dir), doc)
