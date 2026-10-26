"""Abruf der Testdaten: Apple TestFlight (Builds, Nutzung, Absturzmeldungen) und Google Play (Testspuren, Absturzraten).

Zwei Abrufarten (`Dataset`), eine je Plattform; der Ablauf ist der gemeinsame Rahmen `Syncer.sync_dataset`.
Zustandsschlüssel `apple-testflight` und `google-testing`.
"""
from __future__ import annotations

from .apple_testflight import fetch_builds, fetch_crashes, fetch_usage, merge_by_id
from .google_testing import fetch_crash_rates, fetch_tracks
from .models import SCHEMA_VERSION, parse_iso
from .sync import Dataset, Result, Syncer

STATE_KEY = "apple-testflight"
GOOGLE_KEY = "google-testing"


def _testflight_doc(store_id: str) -> dict:
    return {"schemaVersion": SCHEMA_VERSION, "platform": "apple", "storeAppId": store_id,
            "source": "App Store Connect API – TestFlight", "builds": [], "crashes": []}


def _fetch_testflight(syncer: Syncer, client, store_id: str, doc: dict, result: Result, app: dict, now: str) -> None:
    """Builds zusammenführen, Nutzung je Build nur bei Änderung übernehmen, Absturzmeldungen ergänzen."""
    # Abgelaufene Builds ändern sich nicht mehr; die Liste wird nur bis zur ersten Seite aus solchen geholt.
    settled = None if syncer.opt.full_sync else {build["id"] for build in doc["builds"] if build.get("expired")}
    result.new += merge_by_id(doc["builds"], fetch_builds(client, store_id, settled))
    for build in doc["builds"]:
        if build.get("expired") and build.get("usage"):
            continue  # abgelaufen: Nutzung nur einmal holen
        usage = fetch_usage(client, build["id"])
        if usage and usage != {k: value for k, value in (build.get("usage") or {}).items() if k != "capturedAt"}:
            build["usage"] = {**usage, "capturedAt": now}
            result.changed = True
    result.new += merge_by_id(doc["crashes"], fetch_crashes(client, store_id))


TESTFLIGHT = Dataset(
    mode="testflight", label="TestFlight", platform="apple", state_key=STATE_KEY, file_name="testflight.json",
    new_doc=_testflight_doc, fetch=_fetch_testflight, total=lambda doc: len(doc["builds"]),
    limitations=("Nutzungszahlen je Build (Installationen, Sitzungen, Abstürze) gelten für den von Apple gemeldeten "
                 "Zeitraum (rund ein Jahr), nicht je Tag.",
                 "Betriebssystem und Gerät gibt es nur bei einzelnen Absturzmeldungen von Testern."))


def _google_doc(package: str) -> dict:
    return {"schemaVersion": SCHEMA_VERSION, "platform": "google", "packageName": package,
            "source": "Google Play – Testspuren und Play Developer Reporting API (nicht live geprüft)",
            "tracks": [], "crashRates": []}


def _fetch_google(syncer: Syncer, client, package: str, doc: dict, result: Result, app: dict, now: str) -> None:
    """Testspuren ersetzen den Stand; Absturzraten je Tag und Versionscode zusammenführen (neuer Wert ersetzt alten)."""
    tracks = fetch_tracks(client, package)
    if tracks and tracks != doc["tracks"]:
        doc["tracks"], doc["tracksCapturedAt"], result.changed = tracks, now, True
    known = {row["id"]: row for row in doc["crashRates"]}
    for row in fetch_crash_rates(client, package, parse_iso(now).date()):
        if row["id"] not in known:
            result.new += 1
        elif known[row["id"]] != row:
            result.updated += 1
        else:
            continue
        known[row["id"]] = row
    if result.new or result.updated:
        doc["crashRates"] = sorted(known.values(), key=lambda row: (row["date"], row["versionCode"]))


GOOGLE_TESTING = Dataset(
    mode="testing", label="Testspuren", platform="google", state_key=GOOGLE_KEY, file_name="google-testing.json",
    new_doc=_google_doc, fetch=_fetch_google, total=lambda doc: len(doc["crashRates"]),
    limitations=("Nicht gegen die echte Google-API geprüft. Die Absturzraten stammen von Google, sind Anteile der "
                 "Nutzer und nicht mit Apple vergleichbar.",
                 "Die Reporting-API trennt nicht nach Test und Produktion; die Zuordnung zur Spur erfolgt über den "
                 "Versionscode.", "Die jüngsten ein bis drei Tage fehlen (Verzögerung bei Google)."))


def run_testing(syncer: Syncer) -> list[Result]:
    """Ruft die Testdaten aller ausgewählten Apps ab. Fehler einer App stoppen die anderen nicht."""
    return syncer.run_datasets([TESTFLIGHT, GOOGLE_TESTING], "Abruf der Testdaten (TestFlight, Google Play Testspuren)")
