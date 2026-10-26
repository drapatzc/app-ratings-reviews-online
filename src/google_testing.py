"""Google Play: Testspuren und Absturzraten je Versionscode.

NICHT GEGEN DIE ECHTE API GEPRÜFT (Stand 22.10.2026): Es gibt keine Android-App und keine Google-Zugangsdaten zum Prüfen.
Aufbau nach der Google-Dokumentation, getestet nur gegen Attrappen. Vor dem Produktivbetrieb mit einer echten App prüfen
(TODO.md).
- Testspuren: androidpublisher v3 `POST applications/{pkg}/edits` (legt einen kurzlebigen Edit an), `GET …/edits/{id}/tracks`
  (tracks[].track = internal | alpha | beta | production, releases[].name/status/versionCodes/userFraction),
  danach `DELETE …/edits/{id}` (der Edit wird immer wieder gelöscht, es wird nichts veröffentlicht oder geändert).
- Absturzraten: playdeveloperreporting v1beta1 `POST apps/{pkg}/crashRateMetricSet:query` mit Dimension `versionCode` und den
  Metriken crashRate, userPerceivedCrashRate, distinctUsers; tägliche Werte (Zeitzone America/Los_Angeles). Raten sind
  Anteile zwischen 0 und 1. Die Reporting-API trennt NICHT nach Test und Produktion; die Zuordnung zur Spur geschieht über
  den Versionscode.
Berechtigungen: Service Account mit „App-Informationen anzeigen" und „Statistiken zur App-Qualität" (Scope
playdeveloperreporting zusätzlich zu androidpublisher).
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from urllib.parse import quote

from .auth import authorized_json
from .errors import ToolError
from .google import BASE, GoogleClient

log = logging.getLogger("arr.googletesting")
REPORTING = "https://playdeveloperreporting.googleapis.com/v1beta1/apps"
METRICS = ("crashRate", "userPerceivedCrashRate", "distinctUsers")
WINDOW_DAYS = 30


def fetch_tracks(client: GoogleClient, package: str) -> list[dict]:
    """Testspuren mit Releases. Legt einen Edit an und löscht ihn in jedem Fall wieder."""
    base = f"{BASE}/{quote(package, safe='.')}/edits"
    edit = authorized_json(client.http, client.tokens, "POST", base, json_body={})
    edit_id = edit.get("id")
    if not edit_id:
        return []
    try:
        body = authorized_json(client.http, client.tokens, "GET", f"{base}/{edit_id}/tracks")
    finally:
        try:
            authorized_json(client.http, client.tokens, "DELETE", f"{base}/{edit_id}")
        except ToolError as exc:  # Aufräumen darf den Abruf nicht kippen
            log.warning("Edit %s konnte nicht gelöscht werden: %s", edit_id, type(exc).__name__)
    out = []
    for track in body.get("tracks", []):
        releases = [{"name": release.get("name"), "status": release.get("status"),
                     "versionCodes": [str(code) for code in release.get("versionCodes", [])], "userFraction": release.get("userFraction")}
                    for release in track.get("releases", [])]
        out.append({"track": track.get("track"), "releases": releases})
    return out


def _ymd(day: date) -> dict:
    return {"year": day.year, "month": day.month, "day": day.day}


def fetch_crash_rates(client: GoogleClient, package: str, today: date) -> list[dict]:
    """Tägliche Absturzraten je Versionscode der letzten 30 Tage (die jüngsten ein bis drei Tage fehlen noch)."""
    tokens = getattr(client, "reporting_tokens", None) or client.tokens
    url = f"{REPORTING}/{quote(package, safe='.')}/crashRateMetricSet:query"
    end = today - timedelta(days=1)
    body = {"timelineSpec": {"aggregationPeriod": "DAILY", "startTime": {**_ymd(end - timedelta(days=WINDOW_DAYS)),
                                                                          "timeZone": {"id": "America/Los_Angeles"}},
                             "endTime": {**_ymd(end), "timeZone": {"id": "America/Los_Angeles"}}},
            "dimensions": ["versionCode"], "metrics": list(METRICS), "pageSize": 1000}
    out = []
    while True:
        resp = authorized_json(client.http, tokens, "POST", url, json_body=body)
        for row in resp.get("rows", []):
            start = row.get("startTime") or {}
            version = next((dim.get("stringValue") or str(dim.get("int64Value")) for dim in row.get("dimensions", [])
                            if dim.get("dimension") == "versionCode"), None)
            values = {metric.get("metric"): metric.get("decimalValue", {}).get("value") for metric in row.get("metrics", [])}
            if not start or version is None:
                continue
            out.append({"id": f"{start.get('year')}-{int(start.get('month', 0)):02d}-{int(start.get('day', 0)):02d}|{version}",
                        "date": f"{start.get('year')}-{int(start.get('month', 0)):02d}-{int(start.get('day', 0)):02d}",
                        "versionCode": version,
                        **{k: (float(values[k]) if values.get(k) is not None else None) for k in METRICS}})
        token = resp.get("nextPageToken")
        if not token:
            return out
        body = {**body, "pageToken": token}
