"""Markdown-Zusammenfassungen je App und Plattform (Standard: letzte 14 Tage), eigenständig und versandfertig."""
from __future__ import annotations

import re
import zipfile
from datetime import date, timedelta
from pathlib import Path

from .metrics import ampel, fair_rating, reason_text, same_app, stats as _stats
from .storage import atomic_target, write_text

PLATFORM = {"apple": "Apple (App Store)", "google": "Google (Play Store)"}
BAR = 20  # Zeichen für die Textbalken
LEVEL = {0: "grün", 1: "gelb", 2: "rot"}  # Ampelstufe als Wort (nie nur Farbe)


# Einschätzung der KI-Zusammenfassung (Werte aus src/ai_analysis.py) als Text
AI_ASSESSMENT = {"produkt": "Produktproblem", "update": "Update-Problem", "anbieter": "Anbieter / Service",
                 "keine": "keine nennenswerte Kritik", "unklar": "unklar"}


def _day(value: str) -> date:
    return date.fromisoformat(value[:10])


def _fmt_date(value: str | None) -> str:
    return _day(value).strftime("%d.%m.%Y") if value else "–"


def _num(value: float | None, digits: int = 2) -> str:
    return "–" if value is None else f"{value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _stars(stars: int | None) -> str:
    return "★" * stars + "☆" * (5 - stars) if isinstance(stars, int) and 1 <= stars <= 5 else "–"


def _clean(text: str | None) -> str:
    """Neutralisiert HTML und Zeilenumbrüche für sichere Anzeige in Markdown-Viewern."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").strip()


def _quote(text: str | None) -> str:
    lines = _clean(text).splitlines() or ["–"]
    return "\n".join("> " + (line if line.strip() else "") for line in lines)


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "datei"


def _stability(entry: dict, start: str, end: str) -> dict:
    """Abstürze, Sitzungen und Rate im Zeitraum [start, end], dazu je App-Version. Zeilen: [Tag, Version, OS, Gerät, Wert, …]."""
    by_version: dict[str, dict] = {}
    for key in ("crashes", "sessions"):
        for row in entry[key]:
            if start <= row[0] <= end:
                by_version.setdefault(row[1], {"crashes": 0, "sessions": 0})[key] += row[4]
    total_c = sum(value["crashes"] for value in by_version.values())
    total_s = sum(value["sessions"] for value in by_version.values())
    return {"crashes": total_c, "sessions": total_s, "rate": 1000 * total_c / total_s if total_s else None,
            "versions": by_version}


def _in_period(reviews: list[dict], start: str, end: str) -> list[dict]:
    """Rezensionen mit Erstellungsdatum im Zeitraum [start, end] (ISO-Tage), neueste zuerst."""
    return sorted((review for review in reviews if review.get("createdAt") and start <= review["createdAt"][:10] <= end),
                  key=lambda review: review["createdAt"], reverse=True)


def _figures(data: dict, app: dict, start: str, end: str) -> dict:
    """Gemeinsame Zahlen einer App für Einzeldatei und Übersicht: Rezensionen, Statistik, faire Note, Ampel,
    Stabilität im Zeitraum [start, end]."""
    mine = [review for review in data["reviews"] if same_app(review, app)]
    current = _in_period(mine, start, end)
    stab = next((entry for entry in data.get("stability", []) if same_app(entry, app)), None)
    return {"mine": mine, "current": current, "stats": _stats(current),
            "fair": fair_rating(mine, [review for review in data["reviews"] if review["platform"] == app["platform"]]),
            "ampel": _ampel_of(data, app), "stability": stab,
            "stability_now": _stability(stab, start, end) if stab else None}


def build_app_markdown(data: dict, app: dict, until: str, days: int) -> str:
    """Markdown für eine App/Plattform: Kennzahlen, Verteilung, Stabilität (Apple) und alle Rezensionen im Zeitraum."""
    end = _day(until)
    start, prev_start, prev_end = end - timedelta(days=days - 1), end - timedelta(days=2 * days - 1), end - timedelta(days=days)
    s_iso, e_iso = start.isoformat(), end.isoformat()
    fig = _figures(data, app, s_iso, e_iso)
    mine, current, figures, fair, amp = fig["mine"], fig["current"], fig["stats"], fig["fair"], fig["ampel"]
    pst = _stats(_in_period(mine, prev_start.isoformat(), prev_end.isoformat()))
    out = [f"# {app['appName']} – {PLATFORM[app['platform']]}", "",
           f"**Zeitraum:** {start:%d.%m.%Y} – {end:%d.%m.%Y} ({days} Tage) · **Datenstand:** {_fmt_date(data.get('dataAsOf'))} "
           f"· **Kunde:** {app['customerName']}", "",
           "## Auf einen Blick", "", "| Kennzahl | Dieser Zeitraum | Vorheriger Zeitraum |", "|---|---:|---:|",
           f"| Neue Rezensionen | {_int(figures['count'])} | {_int(pst['count'])} |",
           f"| Ø Sterne (aus Rezensionen berechnet) | {_num(figures['avg'])} | {_num(pst['avg'])} |",
           f"| Positiv (4–5 ★) | {figures['pos']} | {pst['pos']} |", f"| Neutral (3 ★) | {figures['mid']} | {pst['mid']} |",
           f"| Negativ (1–2 ★) | {figures['neg']} | {pst['neg']} |",
           f"| Ohne Entwicklerantwort | {figures['noReply']} | {pst['noReply']} |", "",
           f"**Ampel (letzte 30 Tage, wie im Bericht):** {LEVEL[amp['level']]}"
           + (" – " + ", ".join(reason_text(entry) for entry in amp["reasons"]) if amp["reasons"] else " – nichts zu tun"), "",
           f"**Faire Note (aus {_int(fair['rated'])} Rezension{'' if fair['rated'] == 1 else 'en'}):** {_num(fair['fair'])} ★"
           + (f" ± {_num(fair['ci'])}" if fair["ci"] is not None else "")
           + f" · **Zufrieden minus unzufrieden:** {_signed(fair['net'])}", ""]
    official = [entry for entry in data["ratings"] if entry.get("origin") == "store-official" and same_app(entry, app)
                and (entry.get("total") or 0) > 0]
    if official:
        latest = {entry["country"]: entry for entry in official}  # Stände sind chronologisch: der letzte je Land gewinnt
        out += ["**Offizielle Store-Gesamtbewertung** (alle Zeiträume, je Land): " + " · ".join(
            f"{country}: {_num(entry['average'])} ★ ({_int(entry['total'])})" for country, entry in sorted(latest.items())), ""]
    out += ["## Verteilung der Sterne", "", "| Sterne | Anzahl | |", "|---|---:|---|"]
    top = max(figures["dist"].values()) or 1
    for star in range(5, 0, -1):
        out.append(f"| {star} ★ | {figures['dist'][star]} | {'█' * round(BAR * figures['dist'][star] / top)} |")
    out.append("")
    stab = fig["stability"]
    if stab:
        cur, prv = fig["stability_now"], _stability(stab, prev_start.isoformat(), prev_end.isoformat())
        out += ["## Stabilität (Apple Analytics)", "", "| Kennzahl | Dieser Zeitraum | Vorheriger Zeitraum |", "|---|---:|---:|",
                f"| Sitzungen | {_int(cur['sessions'])} | {_int(prv['sessions'])} |",
                f"| Abstürze | {_int(cur['crashes'])} | {_int(prv['crashes'])} |",
                f"| Abstürze je 1000 Sitzungen | {_num(cur['rate'])} | {_num(prv['rate'])} |", ""]
        if cur["versions"]:
            out += ["| App-Version | Sitzungen | Abstürze | je 1000 Sitzungen | Hinweis |", "|---|---:|---:|---:|---|"]
            for version, entry in sorted(cur["versions"].items(), key=lambda pair: -pair[1]["sessions"])[:10]:
                rate = 1000 * entry["crashes"] / entry["sessions"] if entry["sessions"] else None
                note = ("keine Sitzungsdaten, keine Rate" if not entry["sessions"]
                        else "kleine Stichprobe (< 5 Abstürze)" if entry["crashes"] < 5 else "")
                out.append(f"| {version} | {_int(entry['sessions'])} | {entry['crashes']} | {_num(rate)} | {note} |")
            out.append("")
        if not cur["sessions"] and not cur["crashes"]:
            out += ["_Keine Stabilitätsdaten in diesem Zeitraum._", ""]
    elif app["platform"] == "apple":
        out += ["## Stabilität (Apple Analytics)", "", "_Noch nicht abgerufen (`./ratings.sh stability`)._", ""]
    ai_doc = next((entry for entry in data.get("ai", []) if same_app(entry, app)), None)
    if ai_doc and ai_doc.get("summary") and ai_doc["summary"].get("text"):
        summary = ai_doc["summary"]
        out += ["## Was sagen die Nutzer? (KI)", "", _clean(summary["text"]), "",
                f"**Hauptlob:** {_clean(summary.get('praise')) or '–'} · **Hauptkritik:** {_clean(summary.get('criticism')) or '–'} "
                f"· **Einschätzung:** {AI_ASSESSMENT.get(summary.get('assessment'), 'unklar')}", ""]
        for quote in (summary.get("quotes") or [])[:3]:
            out.append(f"> „{_clean(quote.get('text'))}“ · {_stars(quote.get('rating'))} · {_fmt_date(quote.get('createdAt'))}")
        if summary.get("quotes"):
            out.append("")
        out += [f"_Text eines Sprachmodells ({ai_doc.get('provider')}, {ai_doc.get('model')}, erzeugt {_fmt_date(summary.get('generatedAt'))}); "
                "Vorschlag, kein Messwert. Zitate gegen den Originaltext geprüft._", ""]
    out += [f"## Rezensionen ({len(current)})", ""]
    if not current:
        out += ["_Keine Rezensionen in diesem Zeitraum._", ""]
    for review in current:
        meta = [_fmt_date(review["createdAt"])] + [f"{lab} {_clean(str(review[k]))}" for k, lab in (
            ("country", "Land"), ("language", "Sprache"), ("appVersion", "Version"), ("osVersion", "OS"), ("device", "Gerät"))
            if review.get(k)]
        out += [f"### {_stars(review.get('rating'))} {_clean(review.get('title')) or '(ohne Titel)'}", "",
                " · ".join(meta), "", _quote(review.get("text")), ""]
        reply = review.get("developerReply") or {}
        if reply.get("text"):
            out += [f"**Antwort des Entwicklers** ({_fmt_date(reply.get('repliedAt'))}):", "", _quote(reply["text"]), ""]
    out += ["---", "", "_Hinweise: Ø Sterne und Verteilung sind aus den erfassten Rezensionen berechnet und nicht die offizielle "
            "Store-Gesamtbewertung. " + (
                "Apple liefert pro Rezension weder App-Version noch Betriebssystem oder Gerät." if app["platform"] == "apple"
                else "Google liefert über die API nur Rezensionen der letzten 7 Tage; ältere stammen aus früheren Läufen/CSV-Importen.")
            + " Abstürze: Apple blendet Zeilen mit sehr wenigen Geräten aus; Raten sind Näherungen._", ""]
    return "\n".join(out)


def _signed(value: float | None) -> str:
    return "–" if value is None else ("+" if value > 0 else "") + _num(value, 0)


def _ampel_of(data: dict, app: dict) -> dict:
    """Ampel aus dem Dataset (`ampel`, von `build_dataset`), sonst neu berechnet; Fenster ab `dataAsOf`."""
    key = f"{app['customerId']}/{app['appId']}/{app['platform']}"
    return (data.get("ampel") or {}).get(key) or ampel(data, app, (data.get("dataAsOf") or date.today().isoformat())[:10])


def build_rivals(data: dict, rivals: list[dict], until: str, days: int) -> list[str]:
    """Abschnitt „Wettbewerber“ für die Übersicht: eine Zeile je fremder App (nur Apple, öffentlicher Feed); leer ohne
    Wettbewerber, damit die Übersicht ohne sie unverändert bleibt."""
    if not rivals:
        return []
    end = _day(until)
    s_iso = (end - timedelta(days=days - 1)).isoformat()
    out = ["", "## Wettbewerber", "", "| App | Hersteller | Ampel | Warum | Neue Rezensionen | Ø Sterne | Negativ | Store-Note |",
           "|---|---|---|---|---:|---:|---:|---:|"]
    for app in sorted(rivals, key=lambda item: item["appName"].lower()):
        fig = _figures(data, app, s_iso, until)
        figures, amp = fig["stats"], fig["ampel"]
        snaps = [snap for snap in data.get("ratings", []) if snap.get("origin") == "store-official" and same_app(snap, app)
                 and (snap.get("total") or 0) > 0]
        store = max(snaps, key=lambda snap: (snap["capturedAt"], snap["total"]), default=None)
        out.append(f"| {app['appName']} | {app.get('vendor') or '–'} | {LEVEL[amp['level']]} | "
                   f"{', '.join(reason_text(entry) for entry in amp['reasons']) or '–'} | {figures['count']} | "
                   f"{_num(figures['avg'])} | {figures['neg']} | {_num(store['average']) if store else '–'} |")
    out += ["", "_Wettbewerber: fremde Apple-Apps aus dem öffentlichen Apple-Feed (jüngste 500 Rezensionen je Land) und dem "
            "iTunes Lookup, ohne Entwicklerantworten, Abstürze oder Downloads. Keine eigene Datei je App; sie werden nicht "
            "benachrichtigt._", ""]
    return out


def build_overview(data: dict, rows: list[dict], until: str, days: int, rivals: list[dict] | None = None) -> str:
    """Übersichtstabelle über alle Apps/Plattformen; darunter, nur wenn vorhanden, der Abschnitt „Wettbewerber“."""
    end = _day(until)
    out = [f"# Übersicht: letzte {days} Tage", "", f"**Zeitraum:** {end - timedelta(days=days - 1):%d.%m.%Y} – {end:%d.%m.%Y} · "
           f"**Datenstand:** {_fmt_date(data.get('dataAsOf'))}", "",
           "| App | Plattform | Ampel | Warum | Neue Rezensionen | Ø Sterne | Faire Note | Negativ | Ohne Antwort "
           "| Abstürze je 1000 Sitzungen | Datei |",
           "|---|---|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for row in sorted(rows, key=lambda row: -row["level"]):
        out.append(f"| {row['name']} | {row['platform']} | {LEVEL[row['level']]} | {row['why'] or '–'} | {row['count']} | "
                   f"{_num(row['avg'])} | {_num(row['fair'])} | {row['neg']} | {row['noReply']} | "
                   f"{_num(row['rate'])} | [{row['file']}]({row['file']}) |")
    out += ["", f"_Spalten Neue Rezensionen bis Abstürze: letzte {days} Tage. Ampel: feste 30 Tage ab Datenstand, gleiche "
            "Regeln wie im Bericht (rot = handeln, gelb = ansehen, grün = nichts zu tun). Faire Note: alle erfassten "
            "Rezensionen, zum Plattform-Mittel geglättet. Ø Sterne aus Rezensionen berechnet, nicht die offizielle "
            "Store-Bewertung._", ""]
    out += build_rivals(data, rivals or [], until, days)
    return "\n".join(out)


def write_markdown(data: dict, out_dir: Path, days: int = 14, until: str | None = None, make_zip: bool = False) -> list[Path]:
    """Schreibt je App/Plattform eine Datei sowie `00-uebersicht.md`; optional ein ZIP zum Versenden."""
    until = until or (data.get("dataAsOf") or date.today().isoformat())[:10]
    end = _day(until)
    s_iso = (end - timedelta(days=days - 1)).isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    files, rows = [], []
    rivals = [app for app in data["apps"] if app.get("competitor")]  # eigener Abschnitt in der Übersicht, keine Einzeldatei
    for app in sorted(data["apps"], key=lambda item: (item["appName"].lower(), item["platform"])):
        if app.get("competitor"):
            continue
        name = f"{_slug(app['appName'])}-{app['platform']}.md"
        write_text(out_dir / name, build_app_markdown(data, app, until, days))   # atomar, die alte Datei bleibt bis zum Ersetzen lesbar
        files.append(out_dir / name)
        fig = _figures(data, app, s_iso, until)
        figures, amp = fig["stats"], fig["ampel"]
        rows.append({"name": app["appName"], "platform": app["platform"].capitalize(), "count": figures["count"],
                     "avg": figures["avg"], "level": amp["level"],
                     "why": ", ".join(reason_text(entry) for entry in amp["reasons"]),
                     "fair": fig["fair"]["fair"], "neg": figures["neg"], "noReply": figures["noReply"], "file": name,
                     "rate": fig["stability_now"]["rate"] if fig["stability_now"] else None})
    overview = out_dir / "00-uebersicht.md"
    write_text(overview, build_overview(data, rows, until, days, rivals))
    files.insert(0, overview)
    for old in out_dir.glob("*.md"):  # Reste früherer Läufe (nicht mehr vorhandene Apps) erst nach dem Schreiben der neuen entfernen
        if old not in files:
            old.unlink()
    if make_zip:
        zip_path = out_dir.parent / f"zusammenfassung-{until}.zip"
        with atomic_target(zip_path) as tmp, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in files:
                archive.write(file, arcname=file.name)
        files.append(zip_path)
    return files
