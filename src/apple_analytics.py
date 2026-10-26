"""Apple Analytics Reports (App Store Connect API): tägliche Berichte für Stabilität und Store-Kennzahlen.

Genutzte Endpunkte (am 21.10.2026 gegen die echte API geprüft, Store-Berichte am 22.10.2026):
- GET /v1/apps/{id}/analyticsReportRequests                   (vorhandene ONGOING-Anfrage; wird hier nie angelegt)
- GET /v1/analyticsReportRequests/{id}/reports?filter[name]=  (Berichte nach Namen, siehe `REPORTS`)
- GET /v1/analyticsReports/{id}/instances?filter[granularity]=DAILY
- GET /v1/analyticsReportInstances/{id}/segments              (vorsignierte Download-URL je Segment, gzip, TSV)

Jeder Bericht ist in `Report` beschrieben: Schlüsselspalten (werden zu Feldern) und Wertspalten (werden summiert).
`Unique Devices`/`Unique Counts` sind nicht über Zeilen addierbar und werden nur dort übernommen, wo Apple sie je
Schlüssel liefert (Abstürze). Apple versieht die Store-Zählungen mit Rauschen (vereinzelt -1) und blendet Zeilen
mit sehr wenigen Geräten aus; die Werte werden unverändert summiert.
"""
from __future__ import annotations

import csv
import gzip
import io
import logging
from dataclasses import dataclass
from typing import Callable, Iterator

from .apple import BASE, AppleClient
from .errors import ToolError

log = logging.getLogger("arr.analytics")


@dataclass(frozen=True)
class Report:
    """Ein Analytics-Bericht: Name bei Apple, Abschnitt in der Datei, Schlüssel- und Wertspalten als (Spalte, Feld)."""

    name: str
    section: str
    keys: tuple[tuple[str, str], ...]
    values: tuple[tuple[str, str], ...]

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(column for column, _ in self.keys + self.values)


_DAY_VERSION_OS_DEVICE = (("Date", "date"), ("App Version", "appVersion"), ("Platform Version", "osVersion"),
                          ("Device", "device"))
CRASHES = Report("App Crashes", "crashes", _DAY_VERSION_OS_DEVICE,
                 (("Crashes", "crashes"), ("Unique Devices", "uniqueDevices")))
SESSIONS = Report("App Sessions Standard", "sessions", _DAY_VERSION_OS_DEVICE,
                  (("Sessions", "sessions"), ("Total Session Duration", "durationSeconds")))
DOWNLOADS = Report("App Downloads Standard", "downloads",
                   (("Date", "date"), ("Download Type", "downloadType"), ("Source Type", "sourceType"),
                    ("Territory", "territory"), ("Device", "device")), (("Counts", "counts"),))
INSTALLS = Report("App Store Installation and Deletion Standard", "installs",
                  (("Date", "date"), ("Event", "event"), ("Territory", "territory"), ("Device", "device")),
                  (("Counts", "counts"),))
ENGAGEMENT = Report("App Store Discovery and Engagement Standard", "engagement",
                    (("Date", "date"), ("Event", "event"), ("Source Type", "sourceType")), (("Counts", "counts"),))
STABILITY_REPORTS = (CRASHES, SESSIONS)
STORE_REPORTS = (DOWNLOADS, INSTALLS, ENGAGEMENT)

# Apple stoppt eine ONGOING-Anfrage, wenn ihre Berichte lange nicht abgerufen wurden; danach kommen keine neuen Tage.
STOPPED_MESSAGE = ("Apple hat die Analytics-Berichtsanfrage wegen Inaktivität gestoppt, es kommen keine neuen Tage "
                   "mehr. In App Store Connect bzw. per API eine neue Anfrage (ONGOING) anlegen.")


class AnalyticsError(ToolError):
    """Analytics-Daten fehlen oder haben ein unerwartetes Format."""


class AppleAnalytics:
    """Liest die täglichen Berichte einer App über einen bestehenden AppleClient. Kennt keine Dateien."""

    def __init__(self, client: AppleClient, cache: dict | None = None):
        """`cache`: geteiltes Wörterbuch eines Laufs (`Syncer.cache`); merkt sich die ONGOING-Anfrage je App, damit
        Stabilität und Store-Kennzahlen sie nicht je einmal abfragen."""
        self.client = client
        self.cache = cache if cache is not None else {}

    def report_ids(self, store_app_id: str, reports: tuple[Report, ...]) -> dict[str, str]:
        """Findet die Berichts-IDs der ONGOING-Anfrage (Schlüssel: Berichtsname). Legt nichts an."""
        key = ("analytics-ongoing", store_app_id)
        if key not in self.cache:
            requests = self.client.get(f"{BASE}/v1/apps/{store_app_id}/analyticsReportRequests").get("data", [])
            found = next((request for request in requests
                          if (request.get("attributes") or {}).get("accessType") == "ONGOING"), None)
            self.cache[key] = found["id"] if found else None
            if found and (found.get("attributes") or {}).get("stoppedDueToInactivity"):
                self.cache[("analytics-stopped", store_app_id)] = True
                log.warning("Analytics-Anfrage für App %s wurde von Apple wegen Inaktivität gestoppt", store_app_id)
        ongoing = self.cache[key]
        if not ongoing:
            raise AnalyticsError("Keine laufende Analytics-Berichtsanfrage (ONGOING) für diese App. "
                                 "In App Store Connect bzw. per API anlegen; Apple liefert erst danach Daten.")
        ids = {}
        for report in reports:
            data = self.client.get(f"{BASE}/v1/analyticsReportRequests/{ongoing}/reports",
                                   {"filter[name]": report.name}).get("data", [])
            if not data:
                raise AnalyticsError(f"Bericht „{report.name}“ ist (noch) nicht verfügbar.")
            ids[report.name] = data[0]["id"]
        return ids

    def stopped(self, store_app_id: str) -> bool:
        """True, wenn Apple die ONGOING-Anfrage wegen Inaktivität gestoppt hat (nach `report_ids`)."""
        return bool(self.cache.get(("analytics-stopped", store_app_id)))

    def instances(self, report_id: str) -> list[dict]:
        """Alle täglichen Instanzen eines Berichts, älteste Lieferung zuerst."""
        found = []
        for body in self.client.pages(f"{BASE}/v1/analyticsReports/{report_id}/instances",
                                      {"filter[granularity]": "DAILY", "limit": 200}):
            found += [{"id": i["id"], "processingDate": (i.get("attributes") or {}).get("processingDate") or ""}
                      for i in body.get("data", [])]
        return sorted(found, key=lambda i: (i["processingDate"], i["id"]))

    def instance_rows(self, instance_id: str) -> Iterator[dict]:
        """Lädt alle Segmente einer Instanz und liefert die TSV-Zeilen als Dictionaries."""
        body = self.client.get(f"{BASE}/v1/analyticsReportInstances/{instance_id}/segments")
        for segment in body.get("data", []):
            url = (segment.get("attributes") or {}).get("url")
            if not url:
                continue
            payload = self.client.http.request_json("GET", url, as_bytes=True)  # vorsigniert: ohne Authorization
            try:
                payload = gzip.decompress(payload)
            except OSError:
                pass  # bereits unkomprimiert
            text = payload.decode("utf-8-sig", errors="replace")
            yield from csv.DictReader(io.StringIO(text), delimiter="\t")

    def load_new_days(self, store_app_id: str, reports: tuple[Report, ...], doc: dict, reload: bool,
                      progress: Callable[[str, int, int], None], label: str) -> Iterator[str]:
        """Holt alle noch nicht verarbeiteten Tagesinstanzen und ersetzt die betroffenen Tage in `doc`.

        Liefert nach jeder verarbeiteten Instanz deren ID, damit der Aufrufer mitzählen kann; bricht der Abruf
        mittendrin ab, stehen die bis dahin verarbeiteten Tage bereits in `doc`. `doc["instances"]` merkt sich die
        verarbeiteten IDs; mit `reload` werden alle Instanzen neu geholt (Tage ersetzt, Liste ohne Dubletten).
        """
        ids = self.report_ids(store_app_id, reports)
        known = set(doc["instances"])
        todo = [(inst, report) for report in reports for inst in self.instances(ids[report.name])
                if reload or inst["id"] not in known]
        for done, (inst, report) in enumerate(todo):
            progress(label, done, len(todo))
            rows = aggregate(report, list(self.instance_rows(inst["id"])))
            doc[report.section] = replace_days(report, doc[report.section], rows)
            if inst["id"] not in known:
                doc["instances"].append(inst["id"])
                known.add(inst["id"])
            yield inst["id"]
        if todo:
            progress("", 0, 0)  # Fortschrittszeile entfernen


def _int(value: str | None) -> int:
    try:
        return int(float(value)) if value not in (None, "") else 0
    except ValueError:
        return 0


def check_columns(rows: list[dict], needed: tuple[str, ...], report: str) -> None:
    """Meldet fehlende Spalten (Apple ändert Formate gelegentlich) statt falsche Zahlen zu liefern."""
    if rows:
        missing = [column for column in needed if column not in rows[0]]
        if missing:
            raise AnalyticsError(f"Bericht „{report}“: Spalten fehlen: {', '.join(missing)}. "
                                 f"Vorhanden: {', '.join(rows[0].keys())}")


def aggregate(report: Report, rows: list[dict]) -> list[dict]:
    """Summiert die Wertspalten über alle übrigen Spalten auf die Schlüsselspalten des Berichts."""
    check_columns(rows, report.columns, report.name)
    out: dict[tuple, dict] = {}
    for row in rows:
        key = tuple(row[column] for column, _ in report.keys)
        item = out.setdefault(key, {**{field: value for (_, field), value in zip(report.keys, key)},
                                    **{field: 0 for _, field in report.values}})
        for column, field in report.values:
            item[field] += _int(row[column])
    return list(out.values())


def replace_days(report: Report, existing: list[dict], new_rows: list[dict]) -> list[dict]:
    """Ersetzt alle Zeilen der in `new_rows` vorkommenden Tage (spätere Lieferung korrigiert frühere)."""
    dates = {row["date"] for row in new_rows}
    kept = [row for row in existing if row["date"] not in dates]
    return sorted(kept + new_rows, key=lambda row: tuple(str(row.get(field)) for _, field in report.keys))
