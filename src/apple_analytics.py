"""Apple Analytics Reports (App Store Connect API): Abstürze und Sitzungen für Stabilitätsauswertungen.

Genutzte Endpunkte (am 21.10.2026 gegen die echte API geprüft):
- GET /v1/apps/{id}/analyticsReportRequests                   (vorhandene ONGOING-Anfrage; wird hier nie angelegt)
- GET /v1/analyticsReportRequests/{id}/reports?filter[name]=  (Berichte „App Crashes", „App Sessions Standard")
- GET /v1/analyticsReports/{id}/instances?filter[granularity]=DAILY
- GET /v1/analyticsReportInstances/{id}/segments              (vorsignierte Download-URL je Segment, gzip, TSV)
"""
from __future__ import annotations

import csv
import gzip
import io
import logging
from typing import Iterator

from .apple import BASE, AppleClient
from .errors import ApiError, ToolError

log = logging.getLogger("arr.analytics")

CRASH_REPORT = "App Crashes"
SESSION_REPORT = "App Sessions Standard"
CRASH_COLUMNS = ("Date", "App Version", "Device", "Platform Version", "Crashes", "Unique Devices")
SESSION_COLUMNS = ("Date", "App Version", "Device", "Platform Version", "Sessions", "Total Session Duration")


class AnalyticsError(ToolError):
    """Analytics-Daten fehlen oder haben ein unerwartetes Format."""


class AppleAnalytics:
    """Liest Crash- und Sitzungsberichte einer App über einen bestehenden AppleClient."""

    def __init__(self, client: AppleClient):
        self.client = client

    def report_ids(self, store_app_id: str) -> dict[str, str]:
        """Findet die Berichts-IDs der ONGOING-Anfrage. Legt nichts an."""
        requests = self.client._get(f"{BASE}/v1/apps/{store_app_id}/analyticsReportRequests").get("data", [])
        ongoing = next((r["id"] for r in requests if (r.get("attributes") or {}).get("accessType") == "ONGOING"), None)
        if not ongoing:
            raise AnalyticsError("Keine laufende Analytics-Berichtsanfrage (ONGOING) für diese App. "
                                 "In App Store Connect bzw. per API anlegen; Apple liefert erst danach Daten.")
        ids = {}
        for name in (CRASH_REPORT, SESSION_REPORT):
            data = self.client._get(f"{BASE}/v1/analyticsReportRequests/{ongoing}/reports",
                                    {"filter[name]": name}).get("data", [])
            if not data:
                raise AnalyticsError(f"Bericht „{name}“ ist (noch) nicht verfügbar.")
            ids[name] = data[0]["id"]
        return ids

    def instances(self, report_id: str) -> list[dict]:
        """Alle täglichen Instanzen eines Berichts, älteste Lieferung zuerst."""
        url, params, found = f"{BASE}/v1/analyticsReports/{report_id}/instances", {
            "filter[granularity]": "DAILY", "limit": 200}, []
        while url:
            body = self.client._get(url, params)
            params = None
            found += [{"id": i["id"], "processingDate": (i.get("attributes") or {}).get("processingDate") or ""}
                      for i in body.get("data", [])]
            url = (body.get("links") or {}).get("next")
        return sorted(found, key=lambda i: (i["processingDate"], i["id"]))

    def instance_rows(self, instance_id: str) -> Iterator[dict]:
        """Lädt alle Segmente einer Instanz und liefert die TSV-Zeilen als Dictionaries."""
        body = self.client._get(f"{BASE}/v1/analyticsReportInstances/{instance_id}/segments")
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


def _int(value: str | None) -> int:
    try:
        return int(float(value)) if value not in (None, "") else 0
    except ValueError:
        return 0


def check_columns(rows: list[dict], needed: tuple[str, ...], report: str) -> None:
    """Meldet fehlende Spalten (Apple ändert Formate gelegentlich) statt falsche Zahlen zu liefern."""
    if rows:
        missing = [c for c in needed if c not in rows[0]]
        if missing:
            raise AnalyticsError(f"Bericht „{report}“: Spalten fehlen: {', '.join(missing)}. "
                                 f"Vorhanden: {', '.join(rows[0].keys())}")


def aggregate_crashes(rows: list[dict]) -> list[dict]:
    """Fasst Zeilen auf (Datum, Version, OS, Gerät) zusammen."""
    check_columns(rows, CRASH_COLUMNS, CRASH_REPORT)
    out: dict[tuple, dict] = {}
    for r in rows:
        key = (r["Date"], r["App Version"], r["Platform Version"], r["Device"])
        item = out.setdefault(key, {"date": key[0], "appVersion": key[1], "osVersion": key[2], "device": key[3],
                                    "crashes": 0, "uniqueDevices": 0})
        item["crashes"] += _int(r["Crashes"])
        item["uniqueDevices"] += _int(r["Unique Devices"])
    return list(out.values())


def aggregate_sessions(rows: list[dict]) -> list[dict]:
    """Summiert Sitzungen über Gebiet/Quelle auf (Datum, Version, OS, Gerät). Unique Devices sind nicht addierbar."""
    check_columns(rows, SESSION_COLUMNS, SESSION_REPORT)
    out: dict[tuple, dict] = {}
    for r in rows:
        key = (r["Date"], r["App Version"], r["Platform Version"], r["Device"])
        item = out.setdefault(key, {"date": key[0], "appVersion": key[1], "osVersion": key[2], "device": key[3],
                                    "sessions": 0, "durationSeconds": 0})
        item["sessions"] += _int(r["Sessions"])
        item["durationSeconds"] += _int(r["Total Session Duration"])
    return list(out.values())


def replace_dates(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    """Ersetzt alle Zeilen der in `new_rows` vorkommenden Tage (spätere Lieferung korrigiert frühere)."""
    dates = {r["date"] for r in new_rows}
    kept = [r for r in existing if r["date"] not in dates]
    return sorted(kept + new_rows, key=lambda r: (r["date"], r["appVersion"], r["osVersion"], r["device"]))
