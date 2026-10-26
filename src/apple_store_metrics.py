"""Apple Analytics Reports: Downloads, Installationen/Löschungen und Store-Aufrufe (Datei `store-metrics.json`).

Genutzte Berichte der bestehenden ONGOING-Anfrage (am 22.10.2026 gegen die echte API geprüft, Spalten in
`apple_analytics.STORE_REPORTS`, 36 Tagesinstanzen ab 17.09.2026 für eine Beispiel-App):
- „App Downloads Standard“: Date, Download Type (First-time download, Redownload, Restore, Auto-update,
  Manual update), Source Type, Territory, Device, Counts
- „App Store Installation and Deletion Standard“: Date, Event (Install, Delete), Territory, Device, Counts
- „App Store Discovery and Engagement Standard“: Date, Event (Impression, Page view, Tap), Source Type, Counts
Endpunkte und Aggregation wie in `apple_analytics.py`; Zustandsschlüssel `apple-store-metrics`. Eine von Apple
gestoppte Anfrage ist auch hier ein Fehler (es kämen keine neuen Tage mehr).
"""
from __future__ import annotations

from .apple_analytics import STOPPED_MESSAGE, STORE_REPORTS, AnalyticsError, AppleAnalytics
from .models import SCHEMA_VERSION
from .stability_sync import ANALYTICS_WORDING
from .sync import Dataset, Result, Syncer

STATE_KEY = "apple-store-metrics"
FILE_NAME = "store-metrics.json"


def _new_doc(store_id: str) -> dict:
    return {"schemaVersion": SCHEMA_VERSION, "platform": "apple", "storeAppId": store_id,
            "source": "App Store Connect API – Analytics Reports", "reports": [report.name for report in STORE_REPORTS],
            "instances": [], "downloads": [], "installs": [], "engagement": []}


def _fetch(syncer: Syncer, client, store_id: str, doc: dict, result: Result, app: dict, now: str) -> None:
    analytics = AppleAnalytics(client, syncer.cache)
    for _ in analytics.load_new_days(store_id, STORE_REPORTS, doc, syncer.opt.full_sync, syncer.progress,
                                     f"{app['name']} · Store-Kennzahlen"):
        result.new += 1
    if analytics.stopped(store_id):
        raise AnalyticsError(STOPPED_MESSAGE)


STORE_METRICS = Dataset(
    mode="store", label="Store-Kennzahlen", platform="apple", state_key=STATE_KEY, file_name=FILE_NAME,
    new_doc=_new_doc, fetch=_fetch, total=lambda doc: sum(len(doc[report.section]) for report in STORE_REPORTS),
    limitations=("Apple versieht die Zählungen mit Rauschen (vereinzelt negative Werte) und blendet Zeilen mit sehr "
                 "wenigen Geräten aus; Summen sind Näherungen.",
                 "Daten ab Einrichtung der Berichtsanfrage; kein Rückblick. Aktive Geräte sind nicht addierbar und "
                 "werden nicht gespeichert."),
    wording=ANALYTICS_WORDING)


def run_store_metrics(syncer: Syncer) -> list[Result]:
    """Ruft Downloads, Installationen und Store-Aufrufe für alle ausgewählten Apple-Apps ab."""
    return syncer.run_datasets([STORE_METRICS],
                               "Abruf der Store-Kennzahlen (Apple Analytics: Downloads, Installationen, Store-Aufrufe)")
