"""Einheitliches Datenmodell (Schema-Version 1), Normalisierung und stabile Änderungs-Hashes."""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1

# Felder, die fachlich zur Rezension gehören. Abrufzeitpunkte und Rohdaten gehören bewusst NICHT dazu.
CONTENT_FIELDS = ("rating", "title", "text", "language", "country", "appVersion", "buildNumber",
                  "operatingSystem", "osVersion", "device", "updatedAt", "developerReply")


def iso_z(moment: datetime) -> str:
    """Zeitpunkt als UTC-ISO `YYYY-MM-DDTHH:MM:SSZ` (Sekundenauflösung); naive Werte gelten als UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str) -> datetime:
    """Liest `YYYY-MM-DDTHH:MM:SSZ` (oder mit Offset) als zeitzonenbewusstes datetime. Ungültig → ValueError."""
    moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def utc_now() -> str:
    """Aktuelle Zeit als ISO-8601 UTC (Sekundenauflösung)."""
    return iso_z(datetime.now(timezone.utc))


def to_utc_iso(value: Any) -> str | None:
    """Normalisiert Zeitangaben (ISO mit Offset, Epoch-Sekunden/-Millis) nach UTC `YYYY-MM-DDTHH:MM:SSZ`."""
    if value in (None, ""):
        return None
    try:
        if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
            number = float(value)
            number = number / 1000 if number > 1e11 else number
            moment = datetime.fromtimestamp(number, timezone.utc)
        else:
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def review_key(platform: str, store_app_id: str, review_id: str) -> str:
    """Eindeutiger Schlüssel: platform + storeAppId + reviewId."""
    return f"{platform}:{store_app_id}:{review_id}"


def content_state(review: dict) -> dict:
    """Fachlich relevanter Zustand einer Rezension (ohne Abruf-Metadaten und raw)."""
    return {name: review.get(name) for name in CONTENT_FIELDS}


def content_hash(review: dict) -> str:
    """Stabiler SHA-256-Hash über den fachlichen Zustand (Schlüsselreihenfolge unabhängig)."""
    canonical = json.dumps(content_state(review), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def snapshot(review: dict) -> dict:
    """Kompakte Kopie für die Änderungshistorie (ohne raw)."""
    state = copy.deepcopy(content_state(review))
    state["createdAt"] = review.get("createdAt")
    return state


def changed_fields(old: dict, new: dict) -> list[str]:
    """Namen der Felder, in denen sich zwei Rezensionen fachlich unterscheiden."""
    return [name for name in CONTENT_FIELDS if old.get(name) != new.get(name)]


def new_review(customer_id: str, app_id: str, platform: str, store_app_id: str, review_id: str, **fields: Any) -> dict:
    """Erzeugt eine Rezension mit allen Modellfeldern; nicht gelieferte Felder sind None."""
    review = {
        "id": review_key(platform, store_app_id, review_id),
        "customerId": customer_id, "appId": app_id, "platform": platform,
        "storeAppId": store_app_id, "reviewId": review_id,
        "rating": None, "title": None, "text": None, "language": None, "country": None,
        "appVersion": None, "buildNumber": None, "operatingSystem": None, "osVersion": None, "device": None,
        "createdAt": None, "updatedAt": None, "developerReply": None,
        "firstSeenAt": None, "lastSeenAt": None, "raw": {},
    }
    review.update(fields)
    return review


def validate_review(review: dict) -> list[str]:
    """Datenqualitätsprüfung: liefert Auffälligkeiten (die Rezension wird trotzdem gespeichert)."""
    issues = []
    rating = review.get("rating")
    if not isinstance(rating, int) or not 1 <= rating <= 5:
        issues.append("Sternebewertung fehlt oder liegt außerhalb 1–5")
    if not review.get("createdAt"):
        issues.append("Erstellungsdatum fehlt")
    if review.get("createdAt") and review.get("updatedAt") and review["updatedAt"] < review["createdAt"]:
        issues.append("Änderungsdatum liegt vor Erstellungsdatum")
    return issues
