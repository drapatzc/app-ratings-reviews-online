"""Apple TestFlight über die App Store Connect API: Builds, Build-Nutzung, Absturzmeldungen.

Gegen die echte API geprüft am 22.10.2026 (15 Apps, nur lesend):
- GET /v1/builds?filter[app]=…&include=preReleaseVersion   Build-Nummer (`version`), Upload-/Ablaufdatum, `expired`,
  `processingState`; die Marketing-Version steht in `preReleaseVersions` (`version`, `platform`). Funktioniert.
- GET /v1/builds/{id}/metrics/betaBuildUsages              `dataPoints[].values`: installCount, crashCount,
  sessionCount, inviteCount, feedbackCount über einen Zeitraum (`start`/`end`, rund ein Jahr). Funktioniert. Es gibt
  keine Aufteilung nach Betriebssystem oder Gerät und keine Tageswerte.
- GET /v1/apps/{id}/betaFeedbackCrashSubmissions           Einzelne Absturzmeldungen von Testern. Der Endpunkt
  antwortet, lieferte aber bei allen Apps 0 Einträge. NICHT GEPRÜFT: die Attributnamen (createdDate, deviceModel,
  osVersion, appPlatform) und die Beziehung `build`; fehlende Felder bleiben `null`.
- NICHT verwendet: /v1/apps/{id}/metrics/betaTesterUsages (verlangt einen Pflichtparameter, Antwort HTTP 400).
Datenschutz: keine Tester-Namen, E-Mail-Adressen, Kommentare oder Absturzprotokolle werden übernommen.
"""
from __future__ import annotations

import logging

from .apple import BASE, PAGE_SIZE, AppleClient
from .models import to_utc_iso

log = logging.getLogger("arr.testflight")
USAGE_FIELDS = ("installCount", "crashCount", "sessionCount", "inviteCount", "feedbackCount")


def _pages(client: AppleClient, url: str, params: dict | None):
    page = 0
    while url:
        body = client._get(url, params if page == 0 else None)
        page += 1
        yield body
        url = (body.get("links") or {}).get("next")


def fetch_builds(client: AppleClient, store_app_id: str) -> list[dict]:
    """Alle TestFlight-Builds einer App, neueste zuerst, mit Marketing-Version und Plattform."""
    params = {"filter[app]": store_app_id, "limit": PAGE_SIZE, "sort": "-uploadedDate", "include": "preReleaseVersion"}
    out = []
    for body in _pages(client, f"{BASE}/v1/builds", params):
        pre = {i["id"]: i.get("attributes") or {} for i in body.get("included", []) if i.get("type") == "preReleaseVersions"}
        for item in body.get("data", []):
            a = item.get("attributes") or {}
            rel = (((item.get("relationships") or {}).get("preReleaseVersion") or {}).get("data") or {}).get("id")
            out.append({"id": item["id"], "build": a.get("version"), "version": (pre.get(rel) or {}).get("version"),
                        "storePlatform": (pre.get(rel) or {}).get("platform"),
                        "uploadedAt": to_utc_iso(a.get("uploadedDate")), "expiresAt": to_utc_iso(a.get("expirationDate")),
                        "expired": a.get("expired"), "processingState": a.get("processingState")})
    return out


def fetch_usage(client: AppleClient, build_id: str) -> dict | None:
    """Nutzungszahlen eines Builds (Installationen, Sitzungen, Abstürze, Einladungen, Feedback) oder None."""
    body = client._get(f"{BASE}/v1/builds/{build_id}/metrics/betaBuildUsages")
    for item in body.get("data", []):
        for point in item.get("dataPoints", []):
            values = point.get("values") or {}
            return {"periodStart": point.get("start"), "periodEnd": point.get("end"),
                    **{k: values.get(k) for k in USAGE_FIELDS}}
    return None


def fetch_crashes(client: AppleClient, store_app_id: str) -> list[dict]:
    """Absturzmeldungen von Testern, nur Metadaten (kein Kommentar, keine E-Mail, kein Protokoll)."""
    out = []
    for body in _pages(client, f"{BASE}/v1/apps/{store_app_id}/betaFeedbackCrashSubmissions",
                       {"limit": PAGE_SIZE, "include": "build"}):
        for item in body.get("data", []):
            a = item.get("attributes") or {}
            build = (((item.get("relationships") or {}).get("build") or {}).get("data") or {}).get("id")
            out.append({"id": item["id"], "createdAt": to_utc_iso(a.get("createdDate")), "buildId": build,
                        "osVersion": a.get("osVersion"), "device": a.get("deviceModel"),
                        "appPlatform": a.get("appPlatform")})
    return out


def merge_by_id(existing: list[dict], incoming: list[dict]) -> int:
    """Führt `incoming` in `existing` zusammen (Schlüssel `id`), löscht nichts. Gibt die Zahl neuer Einträge zurück."""
    index = {e["id"]: e for e in existing}
    new = 0
    for row in incoming:
        old = index.get(row["id"])
        if old is None:
            existing.append(row)
            index[row["id"]] = row
            new += 1
        else:
            for k, v in row.items():
                if v is not None or k not in old:
                    old[k] = v
    return new
