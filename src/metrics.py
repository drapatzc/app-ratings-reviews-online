"""Kennzahlen ohne Netz und ohne Dateien: faire Note, „Zufrieden minus unzufrieden“, Intervall und Ampel je App.

Einzige Quelle der Ampelregeln: `build_dataset` legt das Ergebnis als `ampel` in den Bericht, `markdown.py` nutzt
dieselben Funktionen. Die Formeln für faire Note, Saldo und Intervall gibt es zusätzlich im Bericht (`core.js`),
weil sie dort dem Filter folgen; `test_metrics.py` prüft, dass beide Seiten gleich rechnen.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

# Pseudostimmen der fairen Note (Bayes-Mittel), wie `BAYES_C` im Bericht
BAYES_C = 10
# Grenzen wie `ZONE` im Bericht: Store-Note, Absturzrate je 1000 Sitzungen, Mindestsitzungen für Absturzregeln
ZONE = {"stars": 4, "rate": 2, "minSessions": 500}
# Ampelregeln (Vorschlag, siehe TODO.md): Fenster in Tagen ab Datenstand, Schwellen und Faktoren
AMPEL = {"days": 30, "negDays": 7, "redNeg": 3, "minStore": 20, "doubled": 2, "raised": 1.5, "minRate": 1}


def stats(reviews: list[dict]) -> dict:
    """Anzahl, Sterneverteilung, Durchschnitt, positiv/neutral/negativ und Rezensionen ohne Antwort."""
    dist = {star: 0 for star in range(1, 6)}
    for review in reviews:
        if review.get("rating") in dist:
            dist[review["rating"]] += 1
    rated = sum(dist.values())
    return {"count": len(reviews), "rated": rated, "dist": dist,
            "avg": sum(k * value for k, value in dist.items()) / rated if rated else None,
            "pos": dist[4] + dist[5], "neg": dist[1] + dist[2], "mid": dist[3],
            "noReply": sum(1 for review in reviews if not (review.get("developerReply") or {}).get("text"))}


def bayes_avg(total: float, count: int, prior: float | None, pseudo: int = BAYES_C) -> float | None:
    """Faire Note: (C·m + Σ Sterne) / (C + n); ohne Vergleichsmittel `prior` zählt der eigene Schnitt."""
    if not count:
        return None
    mean = total / count if prior is None else prior
    return (pseudo * mean + total) / (pseudo + count)


def net_score(figures: dict) -> float | None:
    """Anteil 4–5 ★ minus Anteil 1–2 ★ in Prozentpunkten (−100 … +100)."""
    return 100 * (figures["pos"] - figures["neg"]) / figures["rated"] if figures["rated"] else None


def ci_half(reviews: list[dict]) -> float | None:
    """Halbe Breite des 95-%-Intervalls um den Durchschnitt (1,96 · s / √n), ab zwei bewerteten Rezensionen."""
    values = [review["rating"] for review in reviews if review.get("rating") in (1, 2, 3, 4, 5)]
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return 1.96 * math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1)) / math.sqrt(len(values))


def fair_rating(app_reviews: list[dict], platform_reviews: list[dict]) -> dict:
    """Faire Note, Saldo und Intervall einer App; Vergleichsmittel ist der Schnitt aller Rezensionen der Plattform."""
    figures = stats(app_reviews)
    total = sum(review["rating"] for review in app_reviews if review.get("rating") in (1, 2, 3, 4, 5))
    return {"rated": figures["rated"], "avg": figures["avg"], "fair": bayes_avg(total, figures["rated"], stats(platform_reviews)["avg"]),
            "net": net_score(figures), "ci": ci_half(app_reviews)}


def days_before(day: str, days: int) -> str:
    """ISO-Tag `days` Tage vor `day`."""
    return (date.fromisoformat(day[:10]) - timedelta(days=days)).isoformat()


def crash_rate(entry: dict | None, start: str, end: str) -> dict | None:
    """Abstürze, Sitzungen und Rate je 1000 Sitzungen im Fenster [start, end) oder None ohne Zeilen.
    Zeilen sind `[Tag, Version, OS, Gerät, Wert, …]` wie im Dataset des Berichts."""
    if not entry:
        return None
    crashes = sum(row[4] for row in entry["crashes"] if start <= row[0] < end)
    sessions = sum(row[4] for row in entry["sessions"] if start <= row[0] < end)
    if not any(start <= row[0] < end for row in entry["crashes"] + entry["sessions"]):
        return None
    return {"crashes": crashes, "sessions": sessions, "rate": 1000 * crashes / sessions if sessions > 0 else None}


def same_app(entry: dict, app: dict) -> bool:
    """True, wenn `entry` (Rezension, Stand, Stabilitätseintrag) zu derselben App und Plattform wie `app` gehört."""
    return (entry["customerId"] == app["customerId"] and entry["appId"] == app["appId"]
            and entry["platform"] == app["platform"])


def ampel(data: dict, app: dict, as_of: str) -> dict:
    """Ampel einer App: `level` 0 grün, 1 gelb, 2 rot, `reasons` als Liste strukturierter Gründe.

    rot: ≥ 3 × 1–2 ★ in 7 Tagen, Absturzrate ≥ 2 je 1000 oder verdoppelt gegenüber den 30 Tagen davor;
    gelb: 1–2 × 1–2 ★ in 7 Tagen, offene 1–2 ★ ohne Antwort (30 Tage), Absturzrate × 1,5 oder Store-Note unter 4 ★
    (ab 20 Bewertungen). Absturzregeln erst ab 500 Sitzungen im Fenster. Rezensionen ohne Datum zählen nicht.
    """
    d30, d60, day7 = days_before(as_of, AMPEL["days"]), days_before(as_of, 2 * AMPEL["days"]), days_before(as_of, AMPEL["negDays"])
    mine = [review for review in data["reviews"] if same_app(review, app)]
    day = lambda review: (review.get("createdAt") or "")[:10]  # noqa: E731
    neg_recent = [review for review in mine if (review.get("rating") or 9) <= 2 and day(review) >= day7]
    open_neg = [review for review in mine if day(review) >= d30 and (review.get("rating") or 9) <= 2
                and not (review.get("developerReply") or {}).get("text")]
    snaps: dict[str, dict] = {}
    for entry in data.get("ratings", []):
        if entry.get("origin") == "store-official" and same_app(entry, app) and (entry.get("total") or 0) > 0:
            if entry["country"] not in snaps or entry["capturedAt"] > snaps[entry["country"]]["capturedAt"]:
                snaps[entry["country"]] = entry
    store = max(snaps.values(), key=lambda entry: entry["total"], default=None)
    stab = next((entry for entry in data.get("stability", []) if same_app(entry, app)), None)
    now, prev = crash_rate(stab, d30, "9999"), crash_rate(stab, d60, d30)
    level, reasons = 0, []

    def flag(lvl: int, reason: dict) -> None:
        nonlocal level
        level = max(level, lvl)
        reasons.append(reason)

    if neg_recent:
        flag(2 if len(neg_recent) >= AMPEL["redNeg"] else 1, {"code": "neg", "count": len(neg_recent), "days": AMPEL["negDays"]})
    if open_neg:
        flag(1, {"code": "open", "count": len(open_neg)})
    if now and now["sessions"] >= ZONE["minSessions"] and now["rate"] is not None:
        factor = (now["rate"] / prev["rate"] if prev and prev["rate"] and now["rate"] >= AMPEL["minRate"] else None)
        if now["rate"] >= ZONE["rate"]:
            flag(2, {"code": "crash", "rate": now["rate"]})
        elif factor is not None and factor >= AMPEL["doubled"]:
            flag(2, {"code": "crashUp", "before": prev["rate"], "rate": now["rate"]})
        elif factor is not None and factor >= AMPEL["raised"]:
            flag(1, {"code": "crashUp", "before": prev["rate"], "rate": now["rate"]})
    if store and store["total"] >= AMPEL["minStore"] and store["average"] < ZONE["stars"]:
        flag(1, {"code": "store", "stars": ZONE["stars"]})
    return {"level": level, "reasons": reasons}


def ampel_all(data: dict) -> dict[str, dict]:
    """Ampel für jede App im Dataset, Schlüssel `kunde/app/plattform`, Fenster ab `dataAsOf` (sonst heute)."""
    as_of = (data.get("dataAsOf") or date.today().isoformat())[:10]
    return {f"{item['customerId']}/{item['appId']}/{item['platform']}": ampel(data, item, as_of) for item in data["apps"]}


def reason_text(reason: dict, lang: str = "de") -> str:
    """Grund als Text, gleich formuliert wie im Bericht; `lang` de (Standard, Markdown) oder en (Benachrichtigung)."""
    num = lambda values: f"{values:.2f}".replace(".", "," if lang == "de" else ".")  # noqa: E731
    code = reason["code"]
    if code == "neg":
        return (f"{reason['count']} × 1–2 ★ in {reason['days']} Tagen" if lang == "de"
                else f"{reason['count']} × 1–2 ★ in {reason['days']} days")
    if code == "open":
        return f"{reason['count']} ohne Antwort" if lang == "de" else f"{reason['count']} without reply"
    if code == "crash":
        return (f"Abstürze {num(reason['rate'])} je 1000" if lang == "de"
                else f"crashes {num(reason['rate'])} per 1000")
    if code == "crashUp":
        return (f"Abstürze {num(reason['before'])} → {num(reason['rate'])}" if lang == "de"
                else f"crashes {num(reason['before'])} → {num(reason['rate'])}")
    return f"Store unter {reason['stars']} ★" if lang == "de" else f"store below {reason['stars']} ★"
