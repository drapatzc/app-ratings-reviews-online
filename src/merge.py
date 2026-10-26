"""Zusammenführen ohne Netz und ohne Dateien: Rezensionen (Duplikatschutz, Änderungshistorie), Versionen und
Bewertungs-Momentaufnahmen. Einzige Merge-Logik des Projekts; `sync`, `csv_import` und Tests nutzen sie."""
from __future__ import annotations

import hashlib

from .models import SCHEMA_VERSION, changed_fields, content_hash, snapshot, validate_review


def merge_reviews(existing: dict[str, dict], incoming, history: list[dict], now: str) -> dict[str, int]:
    """Führt `incoming` in `existing` (Schlüssel = Rezensions-ID) zusammen. Idempotent.

    Neue werden ergänzt, geänderte ersetzt (alter Zustand → `history`), identische nur als gesehen markiert.
    """
    history_ids = {entry["changeId"] for entry in history}
    stats = {"new": 0, "updated": 0, "unchanged": 0, "invalid": 0}
    for review in incoming:
        key = review["id"]
        if validate_review(review):
            stats["invalid"] += 1
        old = existing.get(key)
        if old is None:
            review["firstSeenAt"] = review["lastSeenAt"] = now
            existing[key] = review
            stats["new"] += 1
            continue
        review["createdAt"] = min(filter(None, (old.get("createdAt"), review.get("createdAt"))), default=None)
        old_hash, new_hash = content_hash(old), content_hash(review)
        old["lastSeenAt"] = now
        if old_hash == new_hash:
            old["createdAt"] = review["createdAt"]
            stats["unchanged"] += 1
            continue
        change_id = hashlib.sha256(f"{key}|{old_hash}|{new_hash}".encode()).hexdigest()[:32]
        if change_id not in history_ids:
            history.append({"changeId": change_id, "id": key, "reviewId": old["reviewId"], "detectedAt": now,
                            "changedFields": changed_fields(old, review),
                            "previous": snapshot(old), "new": snapshot(review)})
            history_ids.add(change_id)
        review["firstSeenAt"], review["lastSeenAt"] = old.get("firstSeenAt") or now, now
        existing[key] = review
        stats["updated"] += 1
    return stats


def build_versions(platform: str, store_app_id: str, reviews: dict[str, dict], store_versions: list[dict],
                   previous: dict, now: str) -> dict:
    """Erzeugt versions.json: Versionen aus Store-Metadaten und aus Rezensionen, mit zugehörigen Rezensions-IDs."""
    entries: dict[tuple, dict] = {}
    for item in previous.get("versions", []):
        entries[(item["version"], item.get("build"))] = item
    for item in store_versions:
        key = (item["version"], item.get("build"))
        entry = entries.setdefault(key, {**item, "platform": platform, "firstSeenAt": now,
                                         "source": "store-api", "reviewIds": []})
        for name in ("releasedAt", "createdAt", "state", "storePlatform"):
            if item.get(name) is not None:
                entry[name] = item[name]
    ids: dict[tuple, list[str]] = {}
    for review in reviews.values():
        if review.get("appVersion") or review.get("buildNumber"):
            ids.setdefault((review.get("appVersion"), review.get("buildNumber")), []).append(review["id"])
    for key, rids in ids.items():
        entries.setdefault(key, {"version": key[0], "build": key[1], "platform": platform, "releasedAt": None,
                                 "firstSeenAt": now, "source": "reviews", "reviewIds": []})
    for key, entry in entries.items():
        entry["reviewIds"] = sorted(ids.get(key, []))
    ordered = sorted(entries.values(), key=lambda entry: (str(entry["version"]), str(entry.get("build"))))
    return {"schemaVersion": SCHEMA_VERSION, "platform": platform, "storeAppId": store_app_id, "versions": ordered}


def derived_distribution(reviews: dict[str, dict]) -> dict:
    """Sterneverteilung aus gesammelten Rezensionen (KEINE offizielle Store-Gesamtbewertung)."""
    counts = {str(i): 0 for i in range(1, 6)}
    for review in reviews.values():
        if str(review.get("rating")) in counts:
            counts[str(review["rating"])] += 1
    total = sum(counts.values())
    average = round(sum(int(k) * value for k, value in counts.items()) / total, 3) if total else None
    return {"total": total, "average": average, "distribution": counts}


def update_ratings_history(history: dict, reviews: dict[str, dict], store_summaries: list[dict], now: str) -> bool:
    """Hängt Momentaufnahmen nur bei geänderten Werten an. Gibt True zurück, wenn etwas hinzukam."""
    snaps = history.setdefault("snapshots", [])
    changed = False

    def last(origin: str, country: str | None) -> dict | None:
        return next((snap for snap in reversed(snaps) if snap["origin"] == origin and snap.get("country") == country), None)

    derived = derived_distribution(reviews)
    prev = last("derived-from-collected-reviews", None)
    if derived["total"] and (prev is None or (prev["total"], prev["distribution"]) != (derived["total"],
                                                                                     derived["distribution"])):
        snaps.append({"capturedAt": now, "origin": "derived-from-collected-reviews", "source": "reviews.json",
                      "country": None, "appVersion": None, **derived})
        changed = True
    for summary in store_summaries:
        prev = last("store-official", summary["country"])
        values = (summary["averageRating"], summary["ratingCount"])
        if prev is None or (prev["average"], prev["total"]) != values:
            snaps.append({"capturedAt": now, "origin": "store-official", "source": "itunes-lookup",
                          "country": summary["country"], "appVersion": summary.get("currentVersion"),
                          "total": summary["ratingCount"], "average": summary["averageRating"],
                          "distribution": summary.get("distribution"),
                          "currentVersion": {"average": summary.get("averageRatingCurrentVersion"),
                                             "total": summary.get("ratingCountCurrentVersion")}})
            changed = True
    return changed
