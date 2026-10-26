"""Stufe 2: Stabilität (Apple Analytics, Absturz- und Sitzungsberichte) nach `stability-metrics.json`.

Abruf über `apple_analytics` (Endpunkte und Prüfdatum dort); Zustandsschlüssel `apple-stability` in `state.json`.
Der Ablauf (Frische, Laden, Zähler, Schreiben, Zustand) ist der gemeinsame Rahmen `Syncer.sync_dataset`.
"""
from __future__ import annotations

from .apple_analytics import STABILITY_REPORTS, STOPPED_MESSAGE, AnalyticsError, AppleAnalytics
from .models import SCHEMA_VERSION
from .sync import Dataset, Result, Syncer

ANALYTICS_WORDING = "{new} neue Tagesberichte · {total} Zeilen gesamt"


def _new_doc(store_id: str) -> dict:
    return {"schemaVersion": SCHEMA_VERSION, "platform": "apple", "storeAppId": store_id,
            "source": "App Store Connect API – Analytics Reports", "reports": [report.name for report in STABILITY_REPORTS],
            "instances": [], "crashes": [], "sessions": []}


def _fetch(syncer: Syncer, client, store_id: str, doc: dict, result: Result, app: dict, now: str) -> None:
    """Neue Tagesinstanzen beider Berichte in `doc` übernehmen; eine gestoppte Anfrage ist ein Fehler."""
    analytics = AppleAnalytics(client, syncer.cache)
    for _ in analytics.load_new_days(store_id, STABILITY_REPORTS, doc, syncer.opt.full_sync, syncer.progress,
                                     f"{app['name']} · Stabilität"):
        result.new += 1
    if analytics.stopped(store_id):
        raise AnalyticsError(STOPPED_MESSAGE)


STABILITY = Dataset(
    mode="stability", label="Stabilität", platform="apple", state_key="apple-stability",
    file_name="stability-metrics.json", new_doc=_new_doc, fetch=_fetch,
    total=lambda doc: len(doc["crashes"]) + len(doc["sessions"]),
    limitations=("Apple blendet Zeilen mit sehr wenigen Geräten aus (Datenschutz); Summen können daher zu niedrig sein.",
                 "Daten ab Einrichtung der Berichtsanfrage; kein Rückblick."),
    wording=ANALYTICS_WORDING)


def run_stability(syncer: Syncer) -> list[Result]:
    """Ruft Absturz- und Sitzungsdaten für alle ausgewählten Apple-Apps ab."""
    return syncer.run_datasets([STABILITY], "Abruf der Stabilitätsdaten (Apple Analytics)")
