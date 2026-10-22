"""Markdown-Zusammenfassungen je App und Plattform (Standard: letzte 14 Tage), eigenständig und versandfertig."""
from __future__ import annotations

import re
import zipfile
from datetime import date, timedelta
from pathlib import Path

PLATFORM = {"apple": "Apple (App Store)", "google": "Google (Play Store)"}
BAR = 20  # Zeichen für die Textbalken


def _d(value: str) -> date:
    return date.fromisoformat(value[:10])


def _fmt_date(value: str | None) -> str:
    return _d(value).strftime("%d.%m.%Y") if value else "–"


def _num(value: float | None, digits: int = 2) -> str:
    return "–" if value is None else f"{value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _stars(n: int | None) -> str:
    return "★" * n + "☆" * (5 - n) if isinstance(n, int) and 1 <= n <= 5 else "–"


def _clean(text: str | None) -> str:
    """Neutralisiert HTML und Zeilenumbrüche für sichere Anzeige in Markdown-Viewern."""
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").strip()


def _quote(text: str | None) -> str:
    lines = _clean(text).splitlines() or ["–"]
    return "\n".join("> " + (ln if ln.strip() else "") for ln in lines)


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or "datei"


def _stats(reviews: list[dict]) -> dict:
    dist = {n: 0 for n in range(1, 6)}
    for r in reviews:
        if r.get("rating") in dist:
            dist[r["rating"]] += 1
    rated = sum(dist.values())
    return {"count": len(reviews), "rated": rated, "dist": dist,
            "avg": sum(k * v for k, v in dist.items()) / rated if rated else None,
            "pos": dist[4] + dist[5], "neg": dist[1] + dist[2], "mid": dist[3],
            "noReply": sum(1 for r in reviews if not (r.get("developerReply") or {}).get("text"))}


def _stability(entry: dict, start: str, end: str) -> dict:
    crashes = [r for r in entry["crashes"] if start <= r[0] <= end]
    sessions = [r for r in entry["sessions"] if start <= r[0] <= end]
    by_version: dict[str, dict] = {}
    for rows, idx, key in ((crashes, 4, "crashes"), (sessions, 4, "sessions")):
        for r in rows:
            by_version.setdefault(r[1], {"crashes": 0, "sessions": 0})[key] += r[idx]
    total_c, total_s = sum(v["crashes"] for v in by_version.values()), sum(v["sessions"] for v in by_version.values())
    return {"crashes": total_c, "sessions": total_s, "rate": 1000 * total_c / total_s if total_s else None,
            "versions": by_version}


def build_app_markdown(data: dict, app: dict, until: str, days: int) -> str:
    """Markdown für eine App/Plattform: Kennzahlen, Verteilung, Stabilität (Apple) und alle Rezensionen im Zeitraum."""
    end = _d(until)
    start, prev_start, prev_end = end - timedelta(days=days - 1), end - timedelta(days=2 * days - 1), end - timedelta(days=days)
    s_iso, e_iso = start.isoformat(), end.isoformat()
    mine = [r for r in data["reviews"] if r["customerId"] == app["customerId"] and r["appId"] == app["appId"]
            and r["platform"] == app["platform"]]
    current = sorted((r for r in mine if r.get("createdAt") and s_iso <= r["createdAt"][:10] <= e_iso),
                     key=lambda r: r["createdAt"], reverse=True)
    previous = [r for r in mine if r.get("createdAt") and prev_start.isoformat() <= r["createdAt"][:10] <= prev_end.isoformat()]
    st, pst = _stats(current), _stats(previous)
    out = [f"# {app['appName']} – {PLATFORM[app['platform']]}", "",
           f"**Zeitraum:** {start:%d.%m.%Y} – {end:%d.%m.%Y} ({days} Tage) · **Datenstand:** {_fmt_date(data.get('dataAsOf'))} "
           f"· **Kunde:** {app['customerName']}", "",
           "## Auf einen Blick", "", "| Kennzahl | Dieser Zeitraum | Vorheriger Zeitraum |", "|---|---:|---:|",
           f"| Neue Rezensionen | {_int(st['count'])} | {_int(pst['count'])} |",
           f"| Ø Sterne (aus Rezensionen berechnet) | {_num(st['avg'])} | {_num(pst['avg'])} |",
           f"| Positiv (4–5 ★) | {st['pos']} | {pst['pos']} |", f"| Neutral (3 ★) | {st['mid']} | {pst['mid']} |",
           f"| Negativ (1–2 ★) | {st['neg']} | {pst['neg']} |",
           f"| Ohne Entwicklerantwort | {st['noReply']} | {pst['noReply']} |", ""]
    official = [x for x in data["ratings"] if x.get("origin") == "store-official" and x["customerId"] == app["customerId"]
                and x["appId"] == app["appId"] and x["platform"] == app["platform"] and (x.get("total") or 0) > 0]
    if official:
        latest = {}
        for x in official:
            latest[x["country"]] = x
        out += ["**Offizielle Store-Gesamtbewertung** (alle Zeiträume, je Land): " + " · ".join(
            f"{c}: {_num(x['average'])} ★ ({_int(x['total'])})" for c, x in sorted(latest.items())), ""]
    out += ["## Verteilung der Sterne", "", "| Sterne | Anzahl | |", "|---|---:|---|"]
    top = max(st["dist"].values()) or 1
    for n in range(5, 0, -1):
        out.append(f"| {n} ★ | {st['dist'][n]} | {'█' * round(BAR * st['dist'][n] / top)} |")
    out.append("")
    stab = next((x for x in data.get("stability", []) if x["customerId"] == app["customerId"] and x["appId"] == app["appId"]
                 and x["platform"] == app["platform"]), None)
    if stab:
        cur, prv = _stability(stab, s_iso, e_iso), _stability(stab, prev_start.isoformat(), prev_end.isoformat())
        out += ["## Stabilität (Apple Analytics)", "", "| Kennzahl | Dieser Zeitraum | Vorheriger Zeitraum |", "|---|---:|---:|",
                f"| Sitzungen | {_int(cur['sessions'])} | {_int(prv['sessions'])} |",
                f"| Abstürze | {_int(cur['crashes'])} | {_int(prv['crashes'])} |",
                f"| Abstürze je 1000 Sitzungen | {_num(cur['rate'])} | {_num(prv['rate'])} |", ""]
        if cur["versions"]:
            out += ["| App-Version | Sitzungen | Abstürze | je 1000 Sitzungen | Hinweis |", "|---|---:|---:|---:|---|"]
            for v, x in sorted(cur["versions"].items(), key=lambda kv: -kv[1]["sessions"])[:10]:
                rate = 1000 * x["crashes"] / x["sessions"] if x["sessions"] else None
                note = "keine Sitzungsdaten, keine Rate" if not x["sessions"] else ("kleine Stichprobe (< 5 Abstürze)" if x["crashes"] < 5 else "")
                out.append(f"| {v} | {_int(x['sessions'])} | {x['crashes']} | {_num(rate)} | {note} |")
            out.append("")
        if not cur["sessions"] and not cur["crashes"]:
            out += ["_Keine Stabilitätsdaten in diesem Zeitraum._", ""]
    elif app["platform"] == "apple":
        out += ["## Stabilität (Apple Analytics)", "", "_Noch nicht abgerufen (`./ratings.sh stability`)._", ""]
    out += [f"## Rezensionen ({len(current)})", ""]
    if not current:
        out += ["_Keine Rezensionen in diesem Zeitraum._", ""]
    for r in current:
        meta = [_fmt_date(r["createdAt"])] + [f"{lab} {_clean(str(r[k]))}" for k, lab in (
            ("country", "Land"), ("language", "Sprache"), ("appVersion", "Version"), ("osVersion", "OS"), ("device", "Gerät"))
            if r.get(k)]
        out += [f"### {_stars(r.get('rating'))} {_clean(r.get('title')) or '(ohne Titel)'}", "", " · ".join(meta), "", _quote(r.get("text")), ""]
        reply = r.get("developerReply") or {}
        if reply.get("text"):
            out += [f"**Antwort des Entwicklers** ({_fmt_date(reply.get('repliedAt'))}):", "", _quote(reply["text"]), ""]
    out += ["---", "", "_Hinweise: Ø Sterne und Verteilung sind aus den erfassten Rezensionen berechnet und nicht die offizielle "
            "Store-Gesamtbewertung. " + (
                "Apple liefert pro Rezension weder App-Version noch Betriebssystem oder Gerät." if app["platform"] == "apple"
                else "Google liefert über die API nur Rezensionen der letzten 7 Tage; ältere stammen aus früheren Läufen/CSV-Importen.")
            + " Abstürze: Apple blendet Zeilen mit sehr wenigen Geräten aus; Raten sind Näherungen._", ""]
    return "\n".join(out)


def build_overview(data: dict, rows: list[dict], until: str, days: int) -> str:
    """Übersichtstabelle über alle Apps/Plattformen."""
    end = _d(until)
    out = [f"# Übersicht: letzte {days} Tage", "", f"**Zeitraum:** {end - timedelta(days=days - 1):%d.%m.%Y} – {end:%d.%m.%Y} · "
           f"**Datenstand:** {_fmt_date(data.get('dataAsOf'))}", "",
           "| App | Plattform | Neue Rezensionen | Ø Sterne | Negativ | Ohne Antwort | Abstürze je 1000 Sitzungen | Datei |",
           "|---|---|---:|---:|---:|---:|---:|---|"]
    for r in rows:
        out.append(f"| {r['name']} | {r['platform']} | {r['count']} | {_num(r['avg'])} | {r['neg']} | {r['noReply']} | "
                   f"{_num(r['rate'])} | [{r['file']}]({r['file']}) |")
    out += ["", "_Ø Sterne aus Rezensionen berechnet, nicht die offizielle Store-Bewertung._", ""]
    return "\n".join(out)


def write_markdown(data: dict, out_dir: Path, days: int = 14, until: str | None = None, make_zip: bool = False) -> list[Path]:
    """Schreibt je App/Plattform eine Datei sowie `00-uebersicht.md`; optional ein ZIP zum Versenden."""
    until = until or (data.get("dataAsOf") or date.today().isoformat())[:10]
    end = _d(until)
    s_iso = (end - timedelta(days=days - 1)).isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.md"):  # nur Dateien dieses Werkzeugs im Zielordner ersetzen
        old.unlink()
    files, rows = [], []
    for app in sorted(data["apps"], key=lambda a: (a["appName"].lower(), a["platform"])):
        name = f"{_slug(app['appName'])}-{app['platform']}.md"
        (out_dir / name).write_text(build_app_markdown(data, app, until, days), encoding="utf-8")
        files.append(out_dir / name)
        revs = [r for r in data["reviews"] if r["customerId"] == app["customerId"] and r["appId"] == app["appId"]
                and r["platform"] == app["platform"] and r.get("createdAt") and s_iso <= r["createdAt"][:10] <= until]
        st = _stats(revs)
        stab = next((x for x in data.get("stability", []) if x["customerId"] == app["customerId"]
                     and x["appId"] == app["appId"] and x["platform"] == app["platform"]), None)
        rows.append({"name": app["appName"], "platform": app["platform"].capitalize(), "count": st["count"], "avg": st["avg"],
                     "neg": st["neg"], "noReply": st["noReply"], "file": name,
                     "rate": _stability(stab, s_iso, until)["rate"] if stab else None})
    overview = out_dir / "00-uebersicht.md"
    overview.write_text(build_overview(data, rows, until, days), encoding="utf-8")
    files.insert(0, overview)
    for f in files:
        f.chmod(0o600)
    if make_zip:
        zip_path = out_dir.parent / f"zusammenfassung-{until}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in files:
                z.write(f, arcname=f.name)
        files.append(zip_path)
    return files
