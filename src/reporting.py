"""Berichtserzeugung: liest ausschließlich lokale JSON-Dateien und erzeugt ein eigenständiges HTML."""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .ai_providers import USAGE_SCHEMA
from .config import DEFAULT_SETTINGS, active_ai_provider, ai_settings
from .metrics import AMPEL, ampel_all
from .storage import read_json, read_versioned

TEMPLATE_TOKEN = "/*__REPORT_DATA__*/null"
# Die Vorlage ist zur Pflege in HTML, CSS und JS aufgeteilt (templates/report/); beim Erzeugen wird jede Zeile
# `/*__INCLUDE report/<datei>__*/` durch den Dateiinhalt ersetzt, damit der Bericht eine einzige Datei bleibt.
INCLUDE_RE = re.compile(r"/\*__INCLUDE ([A-Za-z0-9_/-]+\.(?:css|js))__\*/\n")

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
        "Store-Kennzahlen (Apple): Downloads, Installationen, Löschungen und Store-Aufrufe aus den Analytics Reports, erst "
        "ab Einrichtung der Berichtsanfrage. Apple versieht die Zählungen mit Rauschen (vereinzelt negative Werte) und "
        "blendet Zeilen mit sehr wenigen Geräten aus. Aktive Geräte sind nicht addierbar und werden nicht gezeigt.",
        "Durchschnitt und Verteilung aus Rezensionen sind selbst berechnet und keine offiziellen Store-Gesamtbewertungen.",
        "Rezensionen sind keine Zufallsstichprobe: Es schreiben vor allem Begeisterte und Verärgerte (J-förmige Verteilung). "
        "„Die wichtigsten Zahlen je App“ zeigen deshalb neben dem Durchschnitt „Zufrieden minus unzufrieden“, den Anteil "
        "1 ★ und eine faire Note (Bayes-Mittel mit 10 Pseudostimmen zum Plattform-Mittel), damit wenige Rezensionen nicht "
        "überbewertet werden.",
        "Themen und typische Wörter entstehen aus festen Wortlisten (config/themen.json) und Worthäufigkeiten, ohne KI. "
        "Trefferquote als Faustwert 70 bis 80 Prozent; Ironie und Tippfehler werden nicht erkannt. Die Listen sind pflegbar.",
        "„Was ein Update verändert hat“ und „Vergleich nach Version“ ordnen Apple-Rezensionen über das Datum der jeweils aktuellen Store-Version zu "
        "(Zeitfenster), weil Apple keine App-Version je Rezension liefert. Google-Rezensionen tragen die Version direkt.",
        "KI-Analyse (optional): Stimmung, Zusammenfassungen, Maßnahmenvorschläge, Antwortentwürfe und Themenvorschläge stammen von einem Sprachmodell "
        "des in der Konfiguration gewählten Anbieters. Es sind Vorschläge, keine Messwerte; alle Zahlen im Bericht kommen weiter "
        "aus den gespeicherten Daten. Zitate sind gegen den Originaltext geprüft. Gesendet werden Rezensionstexte (abschaltbar), "
        "Sterne, Datum, Version, Sprache, Land und App-Name; nie Nutzernamen oder Zugangsdaten.",
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
        "Store figures (Apple): downloads, installs, deletions and store views from the Analytics Reports, only from the "
        "time the report request was set up. Apple adds noise to the counts (occasionally negative values) and hides rows "
        "with very few devices. Active devices cannot be added up and are not shown.",
        "Average and distribution from reviews are calculated by this tool and are not the official store ratings.",
        "Reviews are not a random sample: mostly the delighted and the annoyed write (J-shaped distribution). “Key figures "
        "per app” therefore show happy minus unhappy, the share of 1 ★ and a fair rating (Bayesian mean with 10 pseudo-votes towards "
        "the platform mean) next to the plain average, so that a handful of reviews is not over-interpreted.",
        "Topics and typical words come from fixed word lists (config/themen.json) and word frequencies, without AI. Rule of "
        "thumb for accuracy: 70 to 80 percent; irony and typos are not recognised. The lists can be edited.",
        "“What an update changed” and “Comparison by version” assign Apple reviews by the date of the current store version (time window) "
        "because Apple provides no app version per review. Google reviews carry the version directly.",
        "AI analysis (optional): sentiment, summaries, suggested measures, reply drafts and topic suggestions come from a language model of the "
        "provider chosen in the configuration. They are suggestions, not measurements; all figures in the report still come "
        "from the stored data. Quotes are checked against the original text. Sent are review texts (can be switched off), "
        "stars, date, version, language, country and app name; never user names or credentials.",
    ],
}

# Themen-Wörterbuch für den Bereich „Themen“ im Bericht; wird nur eingelesen und eingebettet, die Zuordnung läuft im Browser.
DEFAULT_TOPICS_FILE = Path(__file__).resolve().parent.parent / "config" / "themen.json"
# Vorgefertigte Fragen für „Fragen an die Daten (KI)“; wie das Themen-Wörterbuch nur eingelesen und eingebettet.
DEFAULT_QUESTIONS_FILE = Path(__file__).resolve().parent.parent / "config" / "fragen.json"
MAX_PRESET_QUESTIONS = 40


def load_questions(path: Path | None) -> list[dict]:
    """Liest `config/fragen.json` (`questions`: je Eintrag `de` und `en`, Wunsch des Nutzers 24.10.2026: eine von Hand
    änderbare Liste von Fragen, die der Bericht per Klick an den Fragedienst schickt). Einträge ohne Text werden übersprungen,
    höchstens `MAX_PRESET_QUESTIONS`; fehlt die Datei, bleibt die Liste leer und der Knopf erscheint nicht."""
    for candidate in (path, DEFAULT_QUESTIONS_FILE):
        if candidate and candidate.is_file():
            doc = read_json(candidate, {})
            out = []
            for item in doc.get("questions", []):
                if not isinstance(item, dict):
                    continue
                text_de = str(item.get("de") or item.get("en") or "").strip()
                text_en = str(item.get("en") or item.get("de") or "").strip()
                if text_de:
                    out.append({"de": text_de[:500], "en": text_en[:500]})
            return out[:MAX_PRESET_QUESTIONS]
    return []


# Zuordnung eines Themas für die Frage „Liegt es an der App oder am Anbieter?“; Themen ohne Angabe zählen dort nicht.
TOPIC_AREAS = ("app", "anbieter")


def load_topics(path: Path | None) -> dict:
    """Liest `config/themen.json` (`terms` Begriffe, `nicht` Ausschlussphrasen je Thema, beides in Kleinbuchstaben;
    `bereich` optional `app` oder `anbieter`).
    Fehlt die Datei, bleibt die Liste leer und der Bericht zeigt einen Hinweis."""
    for candidate in (path, DEFAULT_TOPICS_FILE):
        if candidate and candidate.is_file():
            doc = read_json(candidate, {})
            topics = [topic for topic in doc.get("topics", []) if isinstance(topic, dict) and topic.get("id") and topic.get("terms")]
            return {"source": candidate.name, "topics": [
                {"id": str(topic["id"]), "de": str(topic.get("de", topic["id"])), "en": str(topic.get("en", topic.get("de", topic["id"]))),
                 "kind": str(topic.get("kind", "thema")),
                 "bereich": topic.get("bereich") if topic.get("bereich") in TOPIC_AREAS else None,
                 "terms": [str(term).lower() for term in topic["terms"] if str(term).strip()],
                 "nicht": [str(term).lower() for term in topic.get("nicht", []) if str(term).strip()]}
                for topic in topics]}
    return {"source": None, "topics": []}

# Zusätzliche Seiten neben index.html; jede Vorlage bekommt CSS, Palettenliste, Skript und Fußzeile aus den gemeinsamen Quellen.
PAGES = ("hilfe", "impressum", "datenschutz")
FOOTER_TOKEN = "<!--__FOOTER__-->"


def footer_html(year: int) -> str:
    """Gemeinsame Fußzeile aller Seiten (zweisprachig, Sprache wählt das CSS über html[lang])."""
    return (f'<footer><div>© {year} OneTwoApps · <a href="mailto:support@onetwoapps.com">support@onetwoapps.com</a></div>'
            '<div class="flinks"><a href="hilfe.html"><span lang="de">Hilfe</span><span lang="en">Help</span></a>'
            '<a href="impressum.html"><span lang="de">Impressum</span><span lang="en">Legal notice</span></a>'
            '<a href="datenschutz.html"><span lang="de">Datenschutz</span><span lang="en">Privacy</span></a></div>'
            '<div><span lang="de">Erzeugt aus lokalen JSON-Daten · keine externen Ressourcen · keine Datenübertragung</span>'
            '<span lang="en">Generated from local JSON data · no external resources · no data transfer</span></div></footer>')


def load_template(template_path: Path) -> str:
    """Liest `report.html` und setzt die Teildateien aus `templates/report/` an ihren Platzhaltern ein.

    Nur Pfade unterhalb des Vorlagenordners; fehlt eine Datei, bricht die Erzeugung mit einer klaren Meldung ab."""
    base = template_path.parent.resolve()

    def part(match: re.Match) -> str:
        file = (base / match.group(1)).resolve()
        if base not in file.parents or not file.is_file():
            raise ValueError(f"Vorlage {template_path.name}: Teildatei {match.group(1)} fehlt.")
        text = file.read_text(encoding="utf-8")
        return text if text.endswith("\n") else text + "\n"
    html = INCLUDE_RE.sub(part, template_path.read_text(encoding="utf-8"))
    if "/*__INCLUDE" in html:
        raise ValueError(f"Vorlage {template_path.name}: ungültiger Platzhalter für eine Teildatei.")
    return html


def render_page(name: str, template_dir: Path, year: int) -> str:
    """Textseite (hilfe, impressum, datenschutz) mit dem CSS aus report.html zusammensetzen."""
    style = (template_dir / "report" / "report.css").read_text(encoding="utf-8")
    script = (template_dir / "seite.js").read_text(encoding="utf-8")
    page = (template_dir / f"{name}.html").read_text(encoding="utf-8")
    for token in ("/*__STYLE__*/", "/*__PAGE_STYLE__*/", "/*__PAGE_SCRIPT__*/", FOOTER_TOKEN):
        if token not in page:
            raise ValueError(f"Vorlage {name}.html enthält den Platzhalter {token} nicht.")
    return (page.replace("/*__STYLE__*/", style)
            .replace("/*__PAGE_STYLE__*/", (template_dir / "seite.css").read_text(encoding="utf-8"))
            .replace("/*__PAGE_SCRIPT__*/", script)
            .replace(FOOTER_TOKEN, footer_html(year)))


# Grenzen der Wettbewerber (nur Apple, öffentlicher Feed); im Bericht nur mit vorhandenen Wettbewerbern (`hasCompetitors`)
COMPETITOR_LIMITATIONS = {
    "de": ["Wettbewerber: nur Apple. Quelle ist der öffentliche Apple-Feed für Kundenrezensionen (jüngste 500 je Land) und der iTunes "
           "Lookup; ältere Rezensionen sind nicht abrufbar, es gibt keine Entwicklerantworten, keine Sprache, kein Gerät, keine Abstürze, "
           "Downloads oder Sitzungen fremder Apps. Für Google Play gibt es keine öffentliche Quelle, deshalb keine Wettbewerber dort."],
    "en": ["Competitors: Apple only. The source is Apple’s public customer review feed (newest 500 per country) and the iTunes Lookup; "
           "older reviews cannot be retrieved, there are no developer replies, no language, no device, no crashes, downloads or sessions "
           "of third-party apps. Google Play offers no public source, so there are no competitors there."],
}


def _safe_json(data) -> str:
    """JSON für die Einbettung in <script>: neutralisiert </script>, <!-- und Zeilentrenner."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    for char, escaped in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026"),
                          (" ", "\\u2028"), (" ", "\\u2029")):
        text = text.replace(char, escaped)
    return text


def _audience(app: dict) -> int | None:
    """Größe der Zielgruppe aus der Konfiguration (`audience`), nur ganze Zahlen ab 1; sonst None (nie geschätzt)."""
    value = app.get("audience")
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else None


def build_dataset(data_dir: Path, config: dict | None = None, only_customer: str | None = None, only_app: str | None = None,
                  only_platform: str | None = None, topics_file: Path | None = None,
                  questions_file: Path | None = None) -> dict:
    """Liest alle Kunden/Apps/Plattformen aus `data_dir`. Verändert nichts und ruft keine API auf.

    `topics_file`: Themen-Wörterbuch (Standard `config/themen.json` im Projekt), `questions_file`: vorgefertigte Fragen für
    den Fragedienst (Standard `config/fragen.json`, Datensatz `aiPresetQuestions`). `ratingChanges` sind die Sterne-Änderungen
    aus `review-history.json` als `[id, detectedAt, vorher, nachher]` für den Bereich „Antworten des Supports“.
    """
    names, rating_changes = {}, []
    for customer in (config or {}).get("customers", []):
        rivals = [entry for entry in (customer.get("competitors") or []) if isinstance(entry, dict) and entry.get("id")]
        names[customer["id"]] = {"name": customer.get("name", customer["id"]),
                                 "apps": {app["id"]: app.get("name", app["id"]) for app in customer.get("apps", [])},
                                 "audience": {app["id"]: _audience(app) for app in customer.get("apps", [])},
                                 "competitors": {entry["id"]: entry.get("name", entry["id"]) for entry in rivals},
                                 "vendors": {entry["id"]: entry.get("vendor") for entry in rivals},
                                 "rivalAudience": {entry["id"]: _audience(entry) for entry in rivals}}
    state = read_versioned(data_dir / "state.json", 1, lambda: {"schemaVersion": 1, "customers": {}})
    sync_history = read_json(data_dir / "sync-history.json", {"runs": []})
    reviews, apps, ratings, versions, stability, store, testflight, google_testing = [], [], [], [], [], [], [], []
    ai_docs: list[dict] = []
    root = data_dir / "customers"
    for customer_dir in sorted(root.iterdir()) if root.is_dir() else []:
        cid = customer_dir.name
        if only_customer and cid != only_customer:
            continue
        cname = names.get(cid, {}).get("name", cid)
        # Eigene Apps unter apps/, Wettbewerber (nur Apple, öffentliche Quellen) getrennt unter competitors/
        app_dirs = [(path, False) for path in (sorted((customer_dir / "apps").iterdir()) if (customer_dir / "apps").is_dir() else [])]
        app_dirs += [(path, True) for path in (sorted((customer_dir / "competitors").iterdir())
                                               if (customer_dir / "competitors").is_dir() else [])]
        for app_dir, rival in app_dirs:
            aid = app_dir.name
            if only_app and aid != only_app:
                continue
            group = "competitors" if rival else "apps"
            aname = names.get(cid, {}).get(group, {}).get(aid, aid)
            for platform in ("apple", "google"):
                if only_platform and only_platform != "all" and platform != only_platform:
                    continue
                pdir = app_dir / platform
                if not pdir.is_dir():
                    continue
                def optional(name: str) -> dict | None:
                    """Datei des Plattformordners oder None, wenn sie fehlt (beschädigt → StorageError)."""
                    return read_versioned(pdir / name, 1, lambda: None)

                doc = read_versioned(pdir / "reviews.json", 1, lambda: {"schemaVersion": 1, "reviews": []})
                profile = doc.get("profile") if rival and isinstance(doc.get("profile"), dict) else None
                if rival and aid not in names.get(cid, {}).get("competitors", {}) and profile and profile.get("trackName"):
                    aname = profile["trackName"]  # nicht (mehr) konfiguriert: Name aus dem Steckbrief des Stores
                ident = {"customerId": cid, "appId": aid, "appName": aname, "platform": platform}
                if rival:
                    ident["competitor"] = True
                tkey = "apple-competitors" if rival else platform
                tstate = ((state["customers"].get(cid) or {}).get(group, {}).get(aid) or {}).get(tkey) or {}
                reviews += [{**row, "customerName": cname, "appName": aname, **({"competitor": True} if rival else {})}
                            for row in doc["reviews"]]
                apps.append({**ident, "customerName": cname, "storeAppId": doc.get("storeAppId"),
                             "audience": names.get(cid, {}).get("rivalAudience" if rival else "audience", {}).get(aid),
                             "reviewCount": len(doc["reviews"]), "status": tstate.get("status", "never_synced"),
                             "lastSuccessfulSync": tstate.get("lastSuccessfulSync"),
                             "lastAttempt": tstate.get("lastAttempt"), "lastError": tstate.get("lastError"),
                             "dataGaps": tstate.get("dataGaps", []),
                             **({"vendor": names.get(cid, {}).get("vendors", {}).get(aid) or (profile or {}).get("sellerName"),
                                 "profile": profile, "limitations": doc.get("limitations", [])} if rival else {})})
                # Kennzahlen kompakt als Zeilen-Arrays, Reihenfolge der Felder wie in der Datei
                if stab_doc := optional("stability-metrics.json"):
                    stability.append({
                        **ident,
                        "crashes": [[row["date"], row["appVersion"], row["osVersion"], row["device"], row["crashes"],
                                     row["uniqueDevices"]] for row in stab_doc["crashes"]],
                        "sessions": [[row["date"], row["appVersion"], row["osVersion"], row["device"], row["sessions"],
                                      row["durationSeconds"]] for row in stab_doc["sessions"]],
                        "limitations": stab_doc.get("limitations", [])})
                if store_doc := optional("store-metrics.json"):
                    store.append({**ident,
                                  "downloads": [[row["date"], row["downloadType"], row["sourceType"], row["territory"],
                                                 row["device"], row["counts"]] for row in store_doc["downloads"]],
                                  "installs": [[row["date"], row["event"], row["territory"], row["device"], row["counts"]]
                                               for row in store_doc["installs"]],
                                  "engagement": [[row["date"], row["event"], row["sourceType"], row["counts"]]
                                                 for row in store_doc["engagement"]]})
                if tf_doc := optional("testflight.json"):
                    testflight.append({"customerId": cid, "appId": aid, "appName": aname, "builds": tf_doc["builds"],
                                       "crashes": tf_doc["crashes"], "limitations": tf_doc.get("limitations", [])})
                if gt_doc := optional("google-testing.json"):
                    google_testing.append({"customerId": cid, "appId": aid, "appName": aname, "tracks": gt_doc["tracks"],
                                           "tracksCapturedAt": gt_doc.get("tracksCapturedAt"),
                                           "crashRates": gt_doc["crashRates"], "limitations": gt_doc.get("limitations", [])})
                if ai_doc := optional("ai-analysis.json"):
                    ai_docs.append({**ident, "provider": ai_doc.get("provider"), "model": ai_doc.get("model"),
                                    "language": ai_doc.get("language"), "reviews": ai_doc.get("reviews") or {},
                                    "summary": ai_doc.get("summary"), "drafts": ai_doc.get("drafts") or {},
                                    "limitations": ai_doc.get("limitations", [])})
                for change in (optional("review-history.json") or {}).get("changes", []):
                    if "rating" in (change.get("changedFields") or []):
                        rating_changes.append([change.get("id"), change.get("detectedAt"),
                                               (change.get("previous") or {}).get("rating"),
                                               (change.get("new") or {}).get("rating")])
                ratings += [{**snap, **ident} for snap in (optional("ratings-history.json") or {}).get("snapshots", [])]
                versions += [{key: value for key, value in entry.items() if key != "reviewIds"}
                             | {"reviewCount": len(entry.get("reviewIds", [])), "customerId": cid, "appId": aid}
                             for entry in (optional("versions.json") or {}).get("versions", [])]
    reviews.sort(key=lambda row: (row.get("createdAt") or "", row["id"]), reverse=True)
    stamps = [app["lastSuccessfulSync"] or app["lastAttempt"] for app in apps if app["lastSuccessfulSync"] or app["lastAttempt"]]
    as_of = max(stamps) if stamps else max((row["createdAt"] for row in reviews if row.get("createdAt")), default=None)
    dataset = {"schemaVersion": 1, "dataAsOf": as_of, "apps": apps, "reviews": reviews, "ratings": ratings,
            "versions": versions, "stability": stability, "storeMetrics": store, "testflight": testflight, "googleTesting": google_testing,
            "topics": load_topics(topics_file), "ratingChanges": rating_changes,
            "scope": {"customer": only_customer, "app": only_app,
                      "platform": only_platform if only_platform != "all" else None,
                      "appName": next((app["appName"] for app in apps), None) if only_app else None}, "limitations": LIMITATIONS,
            "lastRun": (sync_history.get("runs") or [None])[-1],
            "refresh": {"minRefreshMinutes": ((config or {}).get("settings") or {}).get(
                "minRefreshMinutes", DEFAULT_SETTINGS["minRefreshMinutes"])}}
    dataset["ampel"] = ampel_all(dataset)  # Ampel je App, einzige Quelle der Regeln (metrics.py)
    # Wettbewerber: nur wenn welche vorliegen, zeigt der Bericht Reiter, Badges und Vergleich; sonst bleibt alles wie ohne
    dataset["hasCompetitors"] = any(app.get("competitor") for app in apps)
    if dataset["hasCompetitors"]:  # Grenzen der Wettbewerber-Quelle nur zeigen, wenn es Wettbewerber gibt
        dataset["limitations"] = {"de": LIMITATIONS["de"] + list(COMPETITOR_LIMITATIONS["de"]),
                                  "en": LIMITATIONS["en"] + list(COMPETITOR_LIMITATIONS["en"])}
    dataset["ampelRules"] = AMPEL  # Fenster und Faktoren auch für die Update-Karte im Bericht
    # KI-Analyse: je App/Plattform die Ergebnisse, dazu Fragen und Verbrauch; `aiEnabled` sagt dem Bericht, ob der Reiter
    # erscheinen soll (aktiver Anbieter oder vorhandene Analysen), `aiFeatures`, welche Bereiche gewünscht sind.
    ai_cfg = ai_settings((config or {}).get("ai"))
    questions = read_versioned(data_dir / "ai-questions.json", 1, lambda: {"schemaVersion": 1, "questions": []})
    usage = read_versioned(data_dir / "ai-usage.json", USAGE_SCHEMA, lambda: {"schemaVersion": USAGE_SCHEMA, "months": {}})
    dataset["ai"] = ai_docs
    dataset["aiQuestions"] = questions.get("questions", [])
    dataset["aiUsage"] = {"months": usage.get("months", {}), "monthlyTokenLimit": ai_cfg["monthlyTokenLimit"]}
    dataset["aiEnabled"] = bool(ai_docs) or active_ai_provider(ai_cfg)[0] is not None
    dataset["aiFeatures"] = ai_cfg["features"]
    dataset["aiSendText"] = bool(ai_cfg["sendReviewText"])
    # Lokaler Fragedienst (ki.py serve): Port und Token nur, wenn er beim Erzeugen läuft; render_html erweitert dann die CSP
    from .ai_service import running_service  # spät importiert: ai_service → ai_ask → reporting
    dataset["aiService"] = running_service(data_dir) if ai_cfg["features"].get("questions") else None
    dataset["aiPresetQuestions"] = load_questions(questions_file) if ai_cfg["features"].get("questions") else []
    return dataset


CSP_IMG = "img-src data:\""  # Ende der Content-Security-Policy in report.html; davor wird connect-src eingefügt


def render_html(dataset: dict, template_path: Path, year: int | None = None) -> str:
    """Setzt die Daten sicher in die Vorlage ein. Läuft der lokale Fragedienst (`aiService`), erlaubt die CSP zusätzlich
    genau diesen Port auf 127.0.0.1; sonst bleibt der Bericht ohne jede Netzfreigabe."""
    template = load_template(template_path)
    if TEMPLATE_TOKEN not in template or FOOTER_TOKEN not in template:
        raise ValueError("Vorlage enthält den Platzhalter nicht.")
    service = dataset.get("aiService")
    if service and isinstance(service.get("port"), int):
        if CSP_IMG not in template:
            raise ValueError("Vorlage enthält die erwartete Content-Security-Policy nicht.")
        template = template.replace(CSP_IMG, f"img-src data:; connect-src http://127.0.0.1:{service['port']}\"", 1)
    return template.replace(TEMPLATE_TOKEN, _safe_json(dataset)).replace(FOOTER_TOKEN, footer_html(year or date.today().year))
