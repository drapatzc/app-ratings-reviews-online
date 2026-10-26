"""Wettbewerber: Rezensionen und Bewertungsübersicht fremder Apple-Apps aus öffentlichen Quellen (`apple_public`).

Ziele sind die Einträge `customers[].competitors` der Konfiguration (nur Apple; für Google gibt es keinen
offiziellen öffentlichen Weg). Ablage getrennt von den eigenen Apps unter `data/customers/<kunde>/competitors/<id>/apple/`
mit denselben Dateien wie bei eigenen Apps (`reviews.json` samt Steckbrief `profile`, `review-history.json`,
`ratings-history.json`), Zustandsschlüssel `apple-competitors`. Zusammenführen ausschließlich über `merge.merge_reviews`;
der Ablauf (Frische, Laden, Zähler, Probelauf, Schreiben, Zustand) ist der gemeinsame Rahmen `Syncer.sync_dataset`.
"""
from __future__ import annotations

import logging

from .apple_public import ApplePublicClient, feed_error_hint
from .config import competitors as config_competitors
from .errors import ApiError, ConfigError, ToolError
from .merge import merge_reviews, update_ratings_history
from .models import SCHEMA_VERSION
from .security import redact
from .storage import read_versioned, write_json
from .sync import Dataset, Result, Syncer, target_dir

log = logging.getLogger("arr.competitors")

SOURCE = "Apple RSS-Feed für Kundenrezensionen und iTunes Lookup (öffentlich, ohne Anmeldung)"
LIMITATIONS = (
    "Wettbewerber: nur die jüngsten 500 Rezensionen je Land aus dem öffentlichen Apple-Feed; ältere sind nicht abrufbar, "
    "der Bestand wächst nur durch regelmäßige Läufe.",
    "Wettbewerber: keine Entwicklerantworten, keine Sprache, kein Gerät; die App-Version steht an der Rezension.",
    "Wettbewerber: keine Stabilitäts- und Store-Kennzahlen (Abstürze, Downloads), weil diese nur dem Eigentümer zugänglich sind.",
    "Wettbewerber: nur Apple. Google bietet keine öffentliche Schnittstelle für Rezensionen fremder Apps.",
)


def _new_doc(store_id: str) -> dict:
    return {"schemaVersion": SCHEMA_VERSION, "platform": "apple", "storeAppId": store_id, "competitor": True,
            "source": SOURCE, "profile": None, "reviews": []}


def _client(syncer: Syncer, customer: dict) -> ApplePublicClient:
    """Ein Client je Lauf (ohne Zugangsdaten), für alle Kunden derselbe."""
    if "apple_public" not in syncer.cache:
        syncer.cache["apple_public"] = ApplePublicClient(syncer.public_http())
    return syncer.cache["apple_public"]


def _fetch(syncer: Syncer, client: ApplePublicClient, store_id: str, doc: dict, result: Result, app: dict,
           now: str) -> None:
    """Feed je Land lesen, zusammenführen, Bewertungsübersicht und Steckbrief aktualisieren. Was bis zu einem Fehler
    geholt wurde, bleibt in `doc` (Status `partial`); Lookup-Fehler sind nur Warnungen."""
    cid, aid = result.customer, result.app
    countries = [str(code) for code in (app["platforms"]["apple"].get("countries") or [])]
    directory = target_dir(syncer.cfg.data_dir, cid, aid, "apple", competitor=True)
    history_doc = read_versioned(directory / "review-history.json", SCHEMA_VERSION,
                                 lambda: {"schemaVersion": SCHEMA_VERSION, "changes": []})
    ratings_doc = read_versioned(directory / "ratings-history.json", SCHEMA_VERSION,
                                 lambda: {"schemaVersion": SCHEMA_VERSION, "snapshots": []})
    existing = {review["id"]: review for review in doc.get("reviews", [])}
    fetched: list[dict] = []
    seen: set[str] = set()
    error: ToolError | None = None
    try:
        for review in client.fetch_reviews(cid, aid, store_id, countries, set(existing), not syncer.opt.full_sync):
            if review["id"] in seen:  # dieselbe Rezension in zwei Länder-Feeds: der erste Treffer zählt
                continue
            seen.add(review["id"])
            fetched.append(review)
    except ApiError as exc:
        error = ApiError(f"{exc}{feed_error_hint(exc)}", exc.status)
    except ToolError as exc:
        error = exc
    stats = merge_reviews(existing, fetched, history_doc["changes"], now)
    result.new, result.updated, result.unchanged = stats["new"], stats["updated"], stats["unchanged"]
    result.quality_issues = stats["invalid"]
    doc["reviews"] = sorted(existing.values(), key=lambda review: (review.get("createdAt") or "", review["id"]),
                            reverse=True)
    summaries, profile = [], None
    if error is None:
        try:
            for country in countries:
                lookup = client.fetch_lookup(store_id, country)
                if lookup:
                    summaries.append(lookup["summary"])
                    profile = profile or lookup["profile"]
        except ToolError as exc:  # Nebenabruf darf den Hauptabruf nicht entwerten
            result.errors.append(f"Nebenabruf (Bewertungsübersicht): {redact(exc)}")
    if syncer.opt.dry_run:
        if error:
            raise error
        return
    if profile and profile != doc.get("profile"):
        doc["profile"] = {**profile, "capturedAt": now}
        result.changed = True
    if result.new or result.updated:
        write_json(directory / "review-history.json", history_doc)
    if update_ratings_history(ratings_doc, existing, summaries, now):
        write_json(directory / "ratings-history.json", ratings_doc)
        result.changed = True
    if error:
        raise error


COMPETITORS = Dataset(
    mode="competitors", label="Wettbewerber", platform="apple", state_key="apple-competitors", file_name="reviews.json",
    new_doc=_new_doc, fetch=_fetch, total=lambda doc: len(doc.get("reviews", [])), limitations=LIMITATIONS,
    client=_client, targets="competitors")


def configured(syncer: Syncer) -> bool:
    """True, wenn mindestens ein aktiver Kunde einen aktiven Wettbewerber eingetragen hat."""
    return any(entry.get("enabled", True) for customer in syncer.cfg.customers if customer.get("enabled", True)
               for entry in config_competitors(customer))


def run_competitors(syncer: Syncer, required: bool = True) -> list[Result]:
    """Ruft Rezensionen und Bewertungsübersicht aller ausgewählten Wettbewerber ab. Ohne Eintrag in der Konfiguration:
    mit `required` ein Konfigurationsfehler mit Anleitung, sonst (Teil von `all`/`daily`) still keine Ziele."""
    if not configured(syncer):
        if required:
            raise ConfigError("Keine Wettbewerber eingetragen. In config/config.json je Kunde unter \"competitors\" fremde "
                              "Apple-Apps mit id, name, apple.appId und apple.countries eintragen (Vorlage: "
                              "config/config.example.json, Anleitung: README.md). Wettbewerber gibt es nur für Apple; "
                              "Google bietet keine öffentliche Quelle.")
        log.info("Wettbewerber: keine eingetragen, Abruf übersprungen.")
        return []
    return syncer.run_datasets([COMPETITORS], "Abruf der Wettbewerber (öffentlicher Apple-Feed)")
