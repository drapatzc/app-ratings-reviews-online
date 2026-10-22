"""Berichtserzeugung: liest ausschließlich lokale JSON-Dateien und erzeugt ein eigenständiges HTML."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .storage import read_json, read_versioned

TEMPLATE_TOKEN = "/*__REPORT_DATA__*/null"

LIMITATIONS = {
    "de": [
        "Apple: Die App Store Connect API liefert Rezensionen mit Text, aber ohne App-Version, Betriebssystem, "
        "Gerät und Sprache. Reine Sternebewertungen ohne Text und die Sterne-Verteilung sind nicht abrufbar.",
        "Apple: Nachträgliche Änderungen alter Rezensionen werden nur bei vollständigen Synchronisationen erkannt.",
        "Google: Die Play Developer API liefert nur Rezensionen der letzten 7 Tage und nur Rezensionen mit Text. "
        "Ältere Daten stammen aus regelmäßigen Läufen oder einem Play-Console-CSV-Import.",
        "Google: Es gibt kein Erstellungsdatum; als Datum dient der Zeitpunkt der letzten Änderung (frühester erfasster Wert).",
        "Stabilität (Apple): Daten aus den Analytics Reports erst ab Einrichtung der Berichtsanfrage; Apple blendet Zeilen "
        "mit sehr wenigen Geräten aus, Summen und Raten sind daher Näherungswerte. Absturzrate = Abstürze je 1000 Sitzungen "
        "(nur Apple, nicht mit Google vergleichbar).",
        "Durchschnitt und Verteilung aus Rezensionen sind selbst berechnet und keine offiziellen Store-Gesamtbewertungen.",
    ],
    "en": [
        "Apple: The App Store Connect API returns reviews with text but without app version, operating system, device "
        "or language. Star-only ratings without text and the star distribution cannot be retrieved.",
        "Apple: Later edits of old reviews are only detected during full synchronisations.",
        "Google: The Play Developer API returns only reviews from the last 7 days and only reviews with text. Older data "
        "comes from regular runs or a Play Console CSV import.",
        "Google: There is no creation date; the time of the last modification is used (earliest value captured).",
        "Stability (Apple): Analytics report data exists only from the time the report request was set up; Apple hides "
        "rows with very few devices, so totals and rates are approximations. Crash rate = crashes per 1,000 sessions "
        "(Apple only, not comparable with Google).",
        "Average and distribution from reviews are calculated by this tool and are not the official store ratings.",
    ],
}

# Zusätzliche Seiten neben index.html; jede Vorlage bekommt CSS, Palettenliste, Skript und Fußzeile aus den gemeinsamen Quellen.
PAGES = ("hilfe", "impressum", "datenschutz")
FOOTER_TOKEN = "<!--__FOOTER__-->"


def _between(text: str, start: str, end: str) -> str:
    a = text.index(start) + len(start)
    return text[a:text.index(end, a)]


def footer_html(year: int) -> str:
    """Gemeinsame Fußzeile aller Seiten (zweisprachig, Sprache wählt das CSS über html[lang])."""
    return (f'<footer><div>© {year} OneTwoApps · <a href="mailto:support@onetwoapps.com">support@onetwoapps.com</a></div>'
            '<div class="flinks"><a href="hilfe.html"><span lang="de">Hilfe</span><span lang="en">Help</span></a>'
            '<a href="impressum.html"><span lang="de">Impressum</span><span lang="en">Legal notice</span></a>'
            '<a href="datenschutz.html"><span lang="de">Datenschutz</span><span lang="en">Privacy</span></a></div>'
            '<div><span lang="de">Erzeugt aus lokalen JSON-Daten · keine externen Ressourcen · keine Datenübertragung</span>'
            '<span lang="en">Generated from local JSON data · no external resources · no data transfer</span></div></footer>')


def render_page(name: str, template_dir: Path, year: int) -> str:
    """Textseite (hilfe, impressum, datenschutz) mit dem CSS und den Paletten aus report.html zusammensetzen."""
    base = (template_dir / "report.html").read_text(encoding="utf-8")
    style = _between(base, "<style>\n", "</style>")
    palettes = "[" + _between(base, "const PALETTES = [", "];") + "]"
    script = (template_dir / "seite.js").read_text(encoding="utf-8").replace("/*__PALETTES__*/[]", palettes)
    page = (template_dir / f"{name}.html").read_text(encoding="utf-8")
    for token in ("/*__STYLE__*/", "/*__PAGE_STYLE__*/", "/*__PAGE_SCRIPT__*/", FOOTER_TOKEN):
        if token not in page:
            raise ValueError(f"Vorlage {name}.html enthält den Platzhalter {token} nicht.")
    return (page.replace("/*__STYLE__*/", style)
            .replace("/*__PAGE_STYLE__*/", (template_dir / "seite.css").read_text(encoding="utf-8"))
            .replace("/*__PAGE_SCRIPT__*/", script)
            .replace(FOOTER_TOKEN, footer_html(year)))


def _safe_json(data) -> str:
    """JSON für die Einbettung in <script>: neutralisiert </script>, <!-- und Zeilentrenner."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    for char, escaped in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"),
                          (" ", "\\u2028"), (" ", "\\u2029")):
        text = text.replace(char, escaped)
    return text


def build_dataset(data_dir: Path, config: dict | None = None, only_customer: str | None = None, only_app: str | None = None,
                  only_platform: str | None = None) -> dict:
    """Liest alle Kunden/Apps/Plattformen aus `data_dir`. Verändert nichts und ruft keine API auf."""
    names = {}
    for customer in (config or {}).get("customers", []):
        names[customer["id"]] = {"name": customer.get("name", customer["id"]),
                                 "apps": {a["id"]: a.get("name", a["id"]) for a in customer.get("apps", [])}}
    state = read_versioned(data_dir / "state.json", 1, lambda: {"schemaVersion": 1, "customers": {}})
    sync_history = read_json(data_dir / "sync-history.json", {"runs": []})
    reviews, apps, ratings, versions, stability, testflight, google_testing = [], [], [], [], [], [], []
    root = data_dir / "customers"
    for customer_dir in sorted(root.iterdir()) if root.is_dir() else []:
        cid = customer_dir.name
        if only_customer and cid != only_customer:
            continue
        cname = names.get(cid, {}).get("name", cid)
        for app_dir in sorted((customer_dir / "apps").iterdir()) if (customer_dir / "apps").is_dir() else []:
            aid = app_dir.name
            if only_app and aid != only_app:
                continue
            aname = names.get(cid, {}).get("apps", {}).get(aid, aid)
            for platform in ("apple", "google"):
                if only_platform and only_platform != "all" and platform != only_platform:
                    continue
                pdir = app_dir / platform
                if not pdir.is_dir():
                    continue
                doc = read_versioned(pdir / "reviews.json", 1, lambda: {"schemaVersion": 1, "reviews": []})
                tstate = ((state["customers"].get(cid) or {}).get("apps", {}).get(aid) or {}).get(platform) or {}
                for r in doc["reviews"]:
                    reviews.append({**{k: v for k, v in r.items()}, "customerName": cname, "appName": aname})
                apps.append({"customerId": cid, "customerName": cname, "appId": aid, "appName": aname,
                             "platform": platform, "storeAppId": doc.get("storeAppId"),
                             "reviewCount": len(doc["reviews"]), "status": tstate.get("status", "never_synced"),
                             "lastSuccessfulSync": tstate.get("lastSuccessfulSync"),
                             "lastAttempt": tstate.get("lastAttempt"), "lastError": tstate.get("lastError"),
                             "dataGaps": tstate.get("dataGaps", [])})
                sm = read_versioned(pdir / "stability-metrics.json", 1, lambda: None) if (
                    pdir / "stability-metrics.json").is_file() else None
                if sm:
                    stability.append({
                        "customerId": cid, "appId": aid, "appName": aname, "platform": platform,
                        "crashes": [[r["date"], r["appVersion"], r["osVersion"], r["device"], r["crashes"],
                                     r["uniqueDevices"]] for r in sm["crashes"]],
                        "sessions": [[r["date"], r["appVersion"], r["osVersion"], r["device"], r["sessions"],
                                      r["durationSeconds"]] for r in sm["sessions"]],
                        "limitations": sm.get("limitations", [])})
                if platform == "apple" and (pdir / "testflight.json").is_file():
                    tf = read_versioned(pdir / "testflight.json", 1, lambda: None)
                    if tf:
                        testflight.append({"customerId": cid, "appId": aid, "appName": aname, "builds": tf["builds"],
                                           "crashes": tf["crashes"], "limitations": tf.get("limitations", [])})
                if platform == "google" and (pdir / "google-testing.json").is_file():
                    gt = read_versioned(pdir / "google-testing.json", 1, lambda: None)
                    if gt:
                        google_testing.append({"customerId": cid, "appId": aid, "appName": aname, "tracks": gt["tracks"],
                                               "tracksCapturedAt": gt.get("tracksCapturedAt"), "crashRates": gt["crashRates"],
                                               "limitations": gt.get("limitations", [])})
                rh = read_versioned(pdir / "ratings-history.json", 1, lambda: {"schemaVersion": 1, "snapshots": []})
                ratings += [{**s, "customerId": cid, "appId": aid, "appName": aname, "platform": platform}
                            for s in rh["snapshots"]]
                vd = read_versioned(pdir / "versions.json", 1, lambda: {"schemaVersion": 1, "versions": []})
                versions += [{k: v for k, v in e.items() if k != "reviewIds"} | {"reviewCount": len(e.get("reviewIds", []))}
                             | {"customerId": cid, "appId": aid} for e in vd["versions"]]
    reviews.sort(key=lambda r: (r.get("createdAt") or "", r["id"]), reverse=True)
    stamps = [a["lastSuccessfulSync"] or a["lastAttempt"] for a in apps if a["lastSuccessfulSync"] or a["lastAttempt"]]
    as_of = max(stamps) if stamps else max((r["createdAt"] for r in reviews if r.get("createdAt")), default=None)
    return {"schemaVersion": 1, "dataAsOf": as_of, "apps": apps, "reviews": reviews, "ratings": ratings,
            "versions": versions, "stability": stability, "testflight": testflight, "googleTesting": google_testing,
            "scope": {"customer": only_customer, "app": only_app,
                      "platform": only_platform if only_platform != "all" else None,
                      "appName": next((a["appName"] for a in apps), None) if only_app else None}, "limitations": LIMITATIONS,
            "lastRun": (sync_history.get("runs") or [None])[-1]}


def render_html(dataset: dict, template_path: Path, year: int | None = None) -> str:
    """Setzt die Daten sicher in die Vorlage ein."""
    template = template_path.read_text(encoding="utf-8")
    if TEMPLATE_TOKEN not in template or FOOTER_TOKEN not in template:
        raise ValueError("Vorlage enthält den Platzhalter nicht.")
    return template.replace(TEMPLATE_TOKEN, _safe_json(dataset)).replace(FOOTER_TOKEN, footer_html(year or date.today().year))
