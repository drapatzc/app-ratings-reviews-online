"""Apple TestFlight über die App Store Connect API: Builds, Build-Nutzung, Absturzmeldungen.

Gegen die echte API geprüft am 22.10.2026 (15 Apps, nur lesend):
- GET /v1/builds?filter[app]=…&include=preReleaseVersion   Build-Nummer (`version`), Upload-/Ablaufdatum, `expired`,
  `processingState`; die Marketing-Version steht in `preReleaseVersions` (`version`, `platform`). Funktioniert.
  Am 23.10.2026 an 1457 Builds geprüft: `sort=-uploadedDate` liefert neueste zuerst, nach dem ersten abgelaufenen
  Build folgt kein gültiger mehr (Grundlage für den vorzeitigen Abbruch in `fetch_builds`).
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


def fetch_builds(client: AppleClient, store_app_id: str, settled: set[str] | None = None) -> list[dict]:
    """TestFlight-Builds einer App, neueste zuerst, mit Marketing-Version und Plattform.

    `settled`: IDs bereits gespeicherter, abgelaufener Builds. Besteht eine ganze Seite nur aus solchen Builds, ist
    der Rest der Liste (älter, ebenfalls abgelaufen und unverändert) schon bekannt; der Abruf endet dort.
    Ohne `settled` wird die vollständige Liste geholt (erster Lauf, `--full-sync`)."""
    params = {"filter[app]": store_app_id, "limit": PAGE_SIZE, "sort": "-uploadedDate", "include": "preReleaseVersion"}
    out = []
    for body in client.pages(f"{BASE}/v1/builds", params):
        page = body.get("data", [])
        pre = {i["id"]: i.get("attributes") or {} for i in body.get("included", []) if i.get("type") == "preReleaseVersions"}
        for item in page:
            attrs = item.get("attributes") or {}
            rel = (((item.get("relationships") or {}).get("preReleaseVersion") or {}).get("data") or {}).get("id")
            out.append({"id": item["id"], "build": attrs.get("version"), "version": (pre.get(rel) or {}).get("version"),
                        "storePlatform": (pre.get(rel) or {}).get("platform"),
                        "uploadedAt": to_utc_iso(attrs.get("uploadedDate")), "expiresAt": to_utc_iso(attrs.get("expirationDate")),
                        "expired": attrs.get("expired"), "processingState": attrs.get("processingState")})
        if settled and page and all(item["id"] in settled for item in page):
            break
    return out


def fetch_usage(client: AppleClient, build_id: str) -> dict | None:
    """Nutzungszahlen eines Builds (Installationen, Sitzungen, Abstürze, Einladungen, Feedback) oder None."""
    body = client.get(f"{BASE}/v1/builds/{build_id}/metrics/betaBuildUsages")
    for item in body.get("data", []):
        for point in item.get("dataPoints", []):
            values = point.get("values") or {}
            return {"periodStart": point.get("start"), "periodEnd": point.get("end"),
                    **{k: values.get(k) for k in USAGE_FIELDS}}
    return None


def fetch_crashes(client: AppleClient, store_app_id: str) -> list[dict]:
    """Absturzmeldungen von Testern, nur Metadaten (kein Kommentar, keine E-Mail, kein Protokoll)."""
    out = []
    for body in client.pages(f"{BASE}/v1/apps/{store_app_id}/betaFeedbackCrashSubmissions",
                             {"limit": PAGE_SIZE, "include": "build"}):
        for item in body.get("data", []):
            attrs = item.get("attributes") or {}
            build = (((item.get("relationships") or {}).get("build") or {}).get("data") or {}).get("id")
            out.append({"id": item["id"], "createdAt": to_utc_iso(attrs.get("createdDate")), "buildId": build,
                        "osVersion": attrs.get("osVersion"), "device": attrs.get("deviceModel"),
                        "appPlatform": attrs.get("appPlatform")})
    return out


def merge_by_id(existing: list[dict], incoming: list[dict]) -> int:
    """Führt `incoming` in `existing` zusammen (Schlüssel `id`), löscht nichts. Gibt die Zahl neuer Einträge zurück."""
    index = {entry["id"]: entry for entry in existing}
    new = 0
    for row in incoming:
        old = index.get(row["id"])
        if old is None:
            existing.append(row)
            index[row["id"]] = row
            new += 1
        else:
            for k, value in row.items():
                if value is not None or k not in old:
                    old[k] = value
    return new
