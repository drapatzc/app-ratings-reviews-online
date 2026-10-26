"""Öffentliche Apple-Quellen ohne Anmeldung: Kundenrezensionen (RSS-Feed) und Bewertungsübersicht (iTunes Lookup).

Dient dem Abruf fremder Apps (Wettbewerber); eigene Apps laufen weiter über `apple.py` (App Store Connect API).
Beide Endpunkte wurden am 25.10.2026 live geprüft:
- GET https://itunes.apple.com/{cc}/rss/customerreviews/page={n}/id={appId}/sortby=mostrecent/json
  `feed.entry[]` mit `id.label` (Rezensions-ID), `im:rating.label` (1–5 als Text), `im:version.label`,
  `title.label`, `content.label`, `updated.label` (ISO mit Zeitzonenversatz), `author.name.label` (wird verworfen),
  `im:voteSum`, `im:voteCount`. 50 Einträge je Seite, höchstens 10 Seiten je Land (Seite 11 → HTTP 400 „page depth
  is limited to 10“), also maximal 500 Rezensionen je Land. Ohne Rezensionen fehlt `feed.entry` ganz.
  Keine Entwicklerantworten, keine Sprache, kein Gerät; die App-Version steht dabei.
- GET https://itunes.apple.com/lookup?id={appId}&country={cc}
  wie in `apple.fetch_rating_summary`, zusätzlich `trackName`, `sellerName`, `description`, `releaseNotes`,
  `primaryGenreName`, `trackViewUrl` für den Steckbrief.
"""
from __future__ import annotations

import logging
from typing import Iterator

from .errors import ApiError
from .http import HttpClient
from .models import new_review, to_utc_iso

log = logging.getLogger("arr.apple_public")

RSS_URL = "https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
LOOKUP_URL = "https://itunes.apple.com/lookup"
MAX_PAGES = 10          # Apple begrenzt den Feed auf 10 Seiten je Land (live geprüft 25.10.2026)
PAGE_SIZE = 50          # Einträge je Seite laut Feed
MAX_DESCRIPTION = 4000  # Zeichen der Store-Beschreibung im Steckbrief


def _label(node: object) -> str | None:
    """Textwert eines Feed-Knotens (`{"label": …}`); fehlt er, None."""
    if isinstance(node, dict):
        value = node.get("label")
        return str(value) if value not in (None, "") else None
    return None


class ApplePublicClient:
    """Liest öffentliche Apple-Daten ohne Token; `http` zählt die Aufrufe wie bei den anderen Clients."""

    def __init__(self, http: HttpClient):
        self.http = http

    def fetch_reviews(self, customer_id: str, app_id: str, store_app_id: str, countries: list[str],
                      known_ids: set[str] | None = None, stop_on_known: bool = True) -> Iterator[dict]:
        """Liefert normalisierte Rezensionen je Land, neueste zuerst, höchstens `MAX_PAGES` Seiten je Land.

        Mit `stop_on_known` endet ein Land nach der ersten Seite, die keine unbekannte Rezension enthält
        (inkrementeller Lauf); ohne (vollständiger Lauf) werden alle Seiten gelesen."""
        known = known_ids or set()
        for country in countries:
            code = country.lower()
            for page in range(1, MAX_PAGES + 1):
                body = self.http.request_json("GET", RSS_URL.format(country=code, page=page, app_id=store_app_id))
                entries = (body.get("feed") or {}).get("entry") if isinstance(body, dict) else None
                if isinstance(entries, dict):  # ein einzelner Eintrag kommt als Objekt statt Liste
                    entries = [entries]
                if not entries:
                    break
                fresh = 0
                for entry in entries:
                    review = normalize_entry(customer_id, app_id, store_app_id, entry, country.upper())
                    if review is None:
                        continue
                    if review["id"] not in known:
                        fresh += 1
                    yield review
                if len(entries) < PAGE_SIZE or (stop_on_known and known and not fresh):
                    break

    def fetch_lookup(self, store_app_id: str, country: str) -> dict | None:
        """Ein Lookup je Land: Bewertungsübersicht (`summary`, Format wie `apple.fetch_rating_summary`) und
        Steckbrief (`profile`: Name, Hersteller, Version, Beschreibung, Genre, Store-Adresse). None ohne Treffer."""
        body = self.http.request_json("GET", LOOKUP_URL, params={"id": store_app_id, "country": country.lower()})
        results = body.get("results") or [] if isinstance(body, dict) else []
        if not results:
            return None
        item = results[0]
        summary = {"country": country.upper(), "averageRating": item.get("averageUserRating"),
                   "ratingCount": item.get("userRatingCount"), "distribution": None,
                   "currentVersion": item.get("version"),
                   "currentVersionReleasedAt": to_utc_iso(item.get("currentVersionReleaseDate")),
                   "averageRatingCurrentVersion": item.get("averageUserRatingForCurrentVersion"),
                   "ratingCountCurrentVersion": item.get("userRatingCountForCurrentVersion")}
        profile = {"trackName": item.get("trackName"), "sellerName": item.get("sellerName"),
                   "version": item.get("version"), "releasedAt": to_utc_iso(item.get("currentVersionReleaseDate")),
                   "genre": item.get("primaryGenreName"), "storeUrl": item.get("trackViewUrl"),
                   "description": (item.get("description") or "")[:MAX_DESCRIPTION] or None,
                   "releaseNotes": (item.get("releaseNotes") or "")[:MAX_DESCRIPTION] or None,
                   "country": country.upper()}
        return {"summary": summary, "profile": profile}


def normalize_entry(customer_id: str, app_id: str, store_app_id: str, entry: dict, country: str) -> dict | None:
    """Wandelt einen Feed-Eintrag in das einheitliche Modell um; Nutzername und Profiladresse werden verworfen."""
    if not isinstance(entry, dict):
        return None
    review_id = _label(entry.get("id"))
    if not review_id:
        return None
    rating_text = _label(entry.get("im:rating"))
    try:
        rating = int(rating_text) if rating_text else None
    except ValueError:
        rating = None
    raw = {"id": review_id, "voteSum": _label(entry.get("im:voteSum")), "voteCount": _label(entry.get("im:voteCount")),
           "updated": _label(entry.get("updated"))}
    return new_review(
        customer_id, app_id, "apple", store_app_id, review_id,
        rating=rating, title=_label(entry.get("title")), text=_label(entry.get("content")),
        country=country, appVersion=_label(entry.get("im:version")),
        createdAt=to_utc_iso(_label(entry.get("updated"))), raw=raw)


def feed_error_hint(exc: ApiError) -> str:
    """Erklärender Zusatz für typische Feed-Fehler (unbekannte App-ID oder Land liefert HTTP 400/404)."""
    if getattr(exc, "status", None) in (400, 404):
        return " (App-ID oder Ländercode prüfen; der Feed kennt nur veröffentlichte Apps je Land)"
    return ""
