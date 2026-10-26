"""KI-Analyse der Rezensionen: Stimmung je Rezension, Zusammenfassung je App, Maßnahmenliste, Antwortentwürfe,
Themenvorschläge.

Zwei `Dataset`s (Apple und Google, Schlüssel `apple-ai`/`google-ai`, Datei `ai-analysis.json`) laufen über den
gemeinsamen Rahmen `Syncer.sync_dataset`. Statt eines Store-Clients bekommt der Abruf einen `AiClient`
(`ai_providers.py`), gewählt über `config.active_ai_provider`. Gesendet werden nur neue oder geänderte Rezensionen
(Vergleich über `models.content_hash`); die Zusammenfassung wird nur neu erzeugt, wenn sich ihre Grundlage ändert.

Größe je Anfrage: Stapel werden nach `ai.maxCharsPerRequest` Zeichen gebildet (nicht nur nach Stückzahl), einzelne
Texte auf `ai.maxReviewChars` gekürzt und markiert. Passt die Grundlage einer Zusammenfassung nicht in eine Anfrage,
läuft sie in zwei Stufen: je Stapel eine Teil-Zusammenfassung, dann eine Verdichtung (`summarize`, `_reduce_prompt`).

Was den Rechner verlässt: Rezensionstext und Titel (abschaltbar über `ai.sendReviewText`), Sterne, Datum, App-Version,
Sprache, Land, App-Name und ob eine Entwicklerantwort existiert. Die Maßnahmenliste (`_measures_prompt`) bekommt keine
Texte, sondern nur Zählungen aus den vorherigen Antworten der KI (Häufungen, Kernaussagen, Wünsche mit Anzahl und
Sterne-Schnitt). Nie: Nutzernamen (werden ohnehin nicht gespeichert), IDs der Rezensionen (nur laufende Nummern),
Zugangsdaten, Store-Kennzahlen.

Alle Texte der KI sind Vorschläge und tragen im Bericht die Marke „KI“. Zitate werden gegen den Originaltext geprüft
und verworfen, wenn sie dort nicht wörtlich vorkommen.
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Callable

from .ai_providers import AiClient, UsageLedger, fmt_usd, price_for
from .config import AI_LOCAL_PROVIDERS, active_ai_provider
from .errors import ConfigError
from .http import HttpClient
from .models import SCHEMA_VERSION, content_hash
from .security import has_api_key, read_api_key
from .storage import read_versioned
from .sync import Dataset, Result, Syncer, target_dir
from .ui import fmt_int, table

log = logging.getLogger("arr.ai")

AI_WORDING = "{new} neue Analysen · {total} Rezensionen analysiert"
SENTIMENTS = ("begeistert", "zufrieden", "wunsch", "veraergert", "resigniert", "unklar")
URGENCIES = ("hoch", "mittel", "niedrig")
ASSESSMENTS = ("produkt", "update", "anbieter", "keine", "unklar")
OWNERS = ("entwicklung", "support", "anbieter", "store", "produkt")   # Zuständigkeit einer Maßnahme
EFFECTS = ("hoch", "mittel", "niedrig")                                # erwartete Wirkung auf die Bewertungen
MAX_MEASURES = 5            # Maßnahmen je App
MAX_FACT_ROWS = 12          # Kernaussagen bzw. Wünsche, die die Maßnahmenanfrage höchstens bekommt
DRAFT_BATCH = 10            # Antwortentwürfe je Anfrage
MAX_SHORT = 90              # Zeichen für Kurztexte der KI (Kernaussage, Thema, Titel einer Häufung)
MAX_LONG = 1200             # Zeichen für Zusammenfassung und Entwürfe
MAX_THEMES_PER_REVIEW = 4
MAX_QUOTES = 5
MAX_SUGGESTIONS = 8
LIMITATIONS = ("KI-Texte sind Vorschläge eines Sprachmodells, keine Messwerte; Zahlen im Bericht stammen weiter aus den Daten.",
               "Zitate werden gegen den Originaltext geprüft; Aussagen ohne Beleg erscheinen nicht.",
               "Es werden nur neue oder geänderte Rezensionen gesendet; ältere Analysen bleiben, bis sich der Text ändert.")


# ----------------------------------------------------------------------------------------------------------
# Anbieter-Client (je Lauf einer, für alle Ziele)
# ----------------------------------------------------------------------------------------------------------

def make_client(cfg, transport=None, sleep=None, clock=None, dry_run: bool = False) -> AiClient:
    """Baut den Client für den aktiven Anbieter oder wirft `ConfigError` mit der Begründung je Anbieter."""
    provider, notes = active_ai_provider(cfg.ai)
    for note in notes:
        log.info("KI-Anbieter %s", note)
    if provider is None:
        raise ConfigError("Kein KI-Anbieter aktiv (" + "; ".join(notes or ["ai.providers ist leer"]) + "). In "
                          "config/config.json unter ai.providers einen Anbieter mit \"enabled\": true eintragen und seinen "
                          "Schlüssel in der genannten Umgebungsvariable setzen.")
    local = provider["name"] in AI_LOCAL_PROVIDERS
    key = ""   # lokaler Anbieter: Schlüssel nur, wenn eine Umgebungsvariable genannt und gefüllt ist (z. B. Proxy davor)
    if not local or has_api_key(provider.get("apiKeyEnvironmentVariable")):
        key = read_api_key(provider.get("apiKeyEnvironmentVariable"), f"KI-Anbieter {provider['name']}")
    if local and cfg.ai["requestTimeoutSeconds"] < 300:
        log.info("KI-Anbieter %s läuft lokal: ein Stapel braucht auf einem Laptop oft mehrere Minuten; ai.requestTimeoutSeconds "
                 "steht auf %d s, empfohlen sind 600.", provider["name"], cfg.ai["requestTimeoutSeconds"])
    # Eigener, längerer Timeout: ein Sprachmodell antwortet auf 60 Rezensionen oft erst nach 30–90 s, der Store-Timeout
    # (settings.requestTimeoutSeconds, 30 s) würde abbrechen und die Anfrage wiederholen, die der Anbieter trotzdem berechnet
    http = HttpClient(cfg.ai["requestTimeoutSeconds"], cfg.settings["maxRetries"], transport, sleep)
    ledger = UsageLedger(cfg.data_dir / "ai-usage.json", int(cfg.ai["monthlyTokenLimit"]), clock)
    price = price_for(provider, provider["name"], provider["model"])
    if price is None:
        log.info("KI-Modell %s/%s steht nicht in der Modellliste (./ratings.sh ai-models): Kosten werden nicht geschätzt, bis "
                 "priceInputPerMillion/priceOutputPerMillion in config.json stehen.", provider["name"], provider["model"])
    return AiClient(http, provider["name"], provider["model"], key, ledger, dry_run, price, provider.get("url"),
                    provider.get("label"))


def ai_client(syncer: Syncer, customer: dict) -> AiClient:
    """Liefert den je Lauf gemeinsamen KI-Client (für alle Kunden derselbe Anbieter)."""
    if "ai_client" not in syncer.cache:
        syncer.cache["ai_client"] = make_client(syncer.cfg, syncer.transport, syncer.sleep, syncer.clock, syncer.opt.dry_run)
    return syncer.cache["ai_client"]


# ----------------------------------------------------------------------------------------------------------
# Dokument
# ----------------------------------------------------------------------------------------------------------

def _new_doc(platform: str):
    def make(store_id: str) -> dict:
        return {"schemaVersion": SCHEMA_VERSION, "platform": platform, "storeAppId": store_id,
                "source": "KI-Analyse der gespeicherten Rezensionen", "reviews": {}, "summary": None, "drafts": {}}
    return make


def _total(doc: dict) -> int:
    return len(doc.get("reviews") or {})


def _short(value: Any, limit: int = MAX_SHORT) -> str | None:
    """Kurztext der KI: nur Strings, Leerraum zusammengezogen, hart begrenzt; sonst None."""
    if not isinstance(value, str):
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text[:limit] or None


def _choice(value: Any, allowed: tuple[str, ...], fallback: str) -> str:
    text = str(value or "").strip().lower().replace("ä", "ae")
    return text if text in allowed else fallback


def _norm(text: str) -> str:
    return re.sub(r"[^\w]+", " ", text.lower()).strip()


def quote_in_text(quote: str, text: str) -> bool:
    """True, wenn das Zitat (ohne Satzzeichen und Groß-/Kleinschreibung) wörtlich im Text vorkommt."""
    needle, hay = _norm(quote), _norm(text)
    return bool(needle) and len(needle) >= 8 and needle in hay


# ----------------------------------------------------------------------------------------------------------
# Prompts
# ----------------------------------------------------------------------------------------------------------

def _system(language: str, app_name: str, platform: str) -> str:
    store = "App Store (Apple)" if platform == "apple" else "Google Play"
    if language == "en":
        return (f"You analyse user reviews of the app \"{app_name}\" from the {store} for the product team. "
                "Answer only with valid JSON, no explanations, no Markdown. Use only the given reviews; never invent "
                "facts, numbers or quotes. Quotes must be verbatim excerpts from the given texts. Write all free text "
                "in English, short and factual.")
    return (f"Du wertest Nutzerrezensionen der App „{app_name}“ aus dem {store} für das Produktteam aus. "
            "Antworte ausschließlich mit gültigem JSON, ohne Erklärungen und ohne Markdown. Nutze nur die übergebenen "
            "Rezensionen; erfinde nie Fakten, Zahlen oder Zitate. Zitate müssen wörtliche Ausschnitte der übergebenen "
            "Texte sein. Alle Freitexte auf Deutsch, kurz und sachlich.")


CUT_MARK = " […gekürzt]"


def clip_text(text: str, limit: int) -> str:
    """Kürzt einen Rezensionstext auf `limit` Zeichen und markiert die Kürzung, damit die KI das weiß."""
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[:max(0, limit - len(CUT_MARK))].rstrip() + CUT_MARK


def review_size(review: dict, send_text: bool, max_chars: int) -> int:
    """Zeichen, die eine Rezension in einer Anfrage belegt (Zeile mit Metadaten plus gekürztem Text)."""
    body = len(clip_text(f"{review.get('title') or ''} {review.get('text') or ''}", max_chars)) if send_text else 0
    return 80 + body


def chunks_by_size(reviews: list[dict], max_items: int, max_chars: int, send_text: bool, review_chars: int):
    """Stapel, die weder `max_items` Rezensionen noch `max_chars` Zeichen überschreiten (eine Rezension passt immer)."""
    batch: list[dict] = []
    size = 0
    for review in reviews:
        needed = review_size(review, send_text, review_chars)
        if batch and (len(batch) >= max_items or size + needed > max_chars):
            yield batch
            batch, size = [], 0
        batch.append(review)
        size += needed
    if batch:
        yield batch


def fit_budget(reviews: list[dict], max_chars: int, send_text: bool, review_chars: int) -> list[dict]:
    """Die ersten (jüngsten) Rezensionen, die zusammen in eine Anfrage passen; mindestens eine."""
    out: list[dict] = []
    size = 0
    for review in reviews:
        needed = review_size(review, send_text, review_chars)
        if out and size + needed > max_chars:
            break
        out.append(review)
        size += needed
    return out


def _review_lines(reviews: list[dict], send_text: bool, review_chars: int = 1_500) -> str:
    """Rezensionen als nummerierte Zeilen; `n` ist die laufende Nummer (die Review-ID verlässt den Rechner nicht).
    Texte länger als `review_chars` werden gekürzt und markiert."""
    lines = []
    for number, review in enumerate(reviews, 1):
        meta = [f"n={number}", f"sterne={review.get('rating')}", f"datum={(review.get('createdAt') or '')[:10]}"]
        if review.get("appVersion"):
            meta.append(f"version={review['appVersion']}")
        if review.get("language"):
            meta.append(f"sprache={review['language']}")
        if review.get("country"):
            meta.append(f"land={review['country']}")
        meta.append("antwort=" + ("ja" if (review.get("developerReply") or {}).get("text") else "nein"))
        body = ""
        if send_text:
            title = clip_text(review.get("title") or "", 200)
            text = clip_text(review.get("text") or "", max(50, review_chars - len(title)))
            body = " | " + (f"titel: {title} | " if title else "") + f"text: {text or '(kein Text)'}"
        lines.append("[" + ", ".join(meta) + "]" + body)
    return "\n".join(lines)


def _sentiment_prompt(language: str, reviews: list[dict], send_text: bool, review_chars: int = 1_500) -> str:
    rules = ("Für jede Rezension ein Objekt: n (Nummer), sentiment (begeistert | zufrieden | wunsch | veraergert | "
             "resigniert; resigniert = droht Wechsel oder hat aufgegeben), urgency (hoch | mittel | niedrig), "
             "issue (Kernaussage in höchstens 8 Wörtern, bei Lob das Gelobte), themes (1 bis 4 Schlagwörter, je 1 bis 3 Wörter), "
             "mismatch (true, wenn die Sterne dem Text widersprechen, z. B. 3 Sterne aber verärgert), "
             "churn (true, wenn Wechsel oder Löschen angedroht wird), version (im Text genannte App-Version oder null). "
             "Antwort: {\"reviews\": [...]}.") if language == "de" else (
             "One object per review: n (number), sentiment (begeistert | zufrieden | wunsch | veraergert | resigniert; "
             "resigniert = threatens to leave or has given up), urgency (hoch | mittel | niedrig), issue (core statement "
             "in at most 8 words, for praise what is praised), themes (1 to 4 keywords of 1 to 3 words), mismatch (true if "
             "the stars contradict the text, e.g. 3 stars but angry), churn (true if leaving or deleting is threatened), "
             "version (app version mentioned in the text or null). Answer: {\"reviews\": [...]}.")
    return rules + "\n\nRezensionen:\n" + _review_lines(reviews, send_text, review_chars)


def _summary_prompt(language: str, reviews: list[dict], send_text: bool, known_topics: list[str],
                    review_chars: int = 1_500) -> str:
    if language == "de":
        rules = ("Fasse diese Rezensionen für die Geschäftsführung zusammen. Antwort als JSON-Objekt mit: "
                 "summary (genau drei Sätze: was gelobt wird, was bemängelt wird, was sich zuletzt verändert hat), "
                 "praise (Hauptlob, höchstens 8 Wörter), criticism (Hauptkritik, höchstens 8 Wörter), "
                 "assessment (produkt = Problem liegt in der App selbst | update = seit einer bestimmten Version | "
                 "anbieter = Service, Freischaltung, Abläufe des Anbieters | keine = keine nennenswerte Kritik | unklar), "
                 "assessmentReason (ein Satz), "
                 "urgent (Liste von Häufungen, je title (höchstens 8 Wörter), count (Anzahl Rezensionen), sinceVersion "
                 "(Version oder null), ns (Nummern der Rezensionen)), "
                 "quotes (bis zu 5 wörtliche, kurze Zitate als {n, text}, die Lob und Kritik belegen), "
                 "newThemes (bis zu 8 Themen, die in den Rezensionen vorkommen und nicht in der Liste bekannter Themen stehen, "
                 "je de, en, terms (3 bis 8 Suchbegriffe in Kleinbuchstaben, Wortanfänge wie „anmeld“), count). "
                 f"Bekannte Themen: {', '.join(known_topics) or 'keine'}.")
        if not send_text:
            rules += " Es liegen nur Sterne, Datum und Version vor, keine Texte: beschreibe nur den Verlauf der Sterne, quotes und newThemes bleiben leer."
    else:
        rules = ("Summarise these reviews for management. Answer as a JSON object with: summary (exactly three sentences: "
                 "what is praised, what is criticised, what changed recently), praise (main praise, at most 8 words), "
                 "criticism (main criticism, at most 8 words), assessment (produkt = problem lies in the app itself | "
                 "update = since a specific version | anbieter = service, activation, provider processes | keine = no "
                 "notable criticism | unklar), assessmentReason (one sentence), urgent (list of clusters, each title (at most "
                 "8 words), count, sinceVersion (version or null), ns (review numbers)), quotes (up to 5 short verbatim quotes "
                 "as {n, text} backing praise and criticism), newThemes (up to 8 themes present in the reviews and missing "
                 "from the known list, each de, en, terms (3 to 8 lower-case search terms, word starts), count). "
                 f"Known themes: {', '.join(known_topics) or 'none'}.")
        if not send_text:
            rules += " Only stars, date and version are available, no texts: describe the star trend only; quotes and newThemes stay empty."
    return rules + "\n\nRezensionen:\n" + _review_lines(reviews, send_text, review_chars)


def _reduce_prompt(language: str, parts: list[dict], quotes: list[dict]) -> str:
    """Zweite Stufe bei großen Grundlagen: Teil-Zusammenfassungen zu einer Gesamtaussage verdichten. Zitate stehen
    nummeriert bereit (bereits gegen den Originaltext geprüft); die KI wählt nur per Nummer aus."""
    if language == "de":
        rules = ("Die folgenden Teil-Zusammenfassungen beschreiben jeweils einen Stapel von Rezensionen derselben App, von neu nach "
                 "alt. Verdichte sie zu einer Gesamtaussage. Antwort als JSON-Objekt mit: summary (genau drei Sätze: Lob, Kritik, "
                 "was sich zuletzt verändert hat), praise (höchstens 8 Wörter), criticism (höchstens 8 Wörter), assessment "
                 "(produkt | update | anbieter | keine | unklar), assessmentReason (ein Satz), urgent (Häufungen über alle Stapel, "
                 "je title, count = Summe, sinceVersion oder null), quotes (bis zu 5 Nummern aus der Zitatliste als {n}), "
                 "newThemes (höchstens 8, zusammengeführt, je de, en, terms, count = Summe).")
    else:
        rules = ("The following partial summaries each describe one batch of reviews of the same app, from newest to oldest. "
                 "Condense them into one overall statement. Answer as a JSON object with: summary (exactly three sentences: praise, "
                 "criticism, what changed recently), praise (at most 8 words), criticism (at most 8 words), assessment (produkt | "
                 "update | anbieter | keine | unklar), assessmentReason (one sentence), urgent (clusters across all batches, each "
                 "title, count = sum, sinceVersion or null), quotes (up to 5 numbers from the quote list as {n}), newThemes (at most "
                 "8, merged, each de, en, terms, count = sum).")
    lines = []
    for index, part in enumerate(parts, 1):
        lines.append(f"[Stapel {index}, {part['count']} Rezensionen, {part['from']} bis {part['to']}] {part['text']} | Lob: {part['praise']} | "
                     f"Kritik: {part['criticism']} | Einschätzung: {part['assessment']} ({part['assessmentReason']}) | "
                     f"Häufungen: {part['urgent']} | Themenvorschläge: {part['themes']}")
    quote_lines = [f"[n={index}] „{quote['text']}“ ({quote['rating']} ★)" for index, quote in enumerate(quotes, 1)]
    return rules + "\n\nTeil-Zusammenfassungen:\n" + "\n".join(lines) + "\n\nZitatliste:\n" + ("\n".join(quote_lines) or "(keine)")


def _draft_prompt(language: str, reviews: list[dict]) -> str:
    if language == "de":
        rules = ("Schreibe für jede dieser negativen Rezensionen einen Antwortentwurf für den Support (höchstens 350 Zeichen, "
                 "in der Sprache der Rezension, höflich, konkret, ohne Floskeln, ohne Versprechen zu Terminen, keine Namen, "
                 "keine Platzhalter außer [Kontakt] für den Kontaktweg). Antwort: {\"drafts\": [{\"n\": 1, \"text\": \"...\"}]}.")
    else:
        rules = ("Write a support reply draft for each of these negative reviews (at most 350 characters, in the language of "
                 "the review, polite, concrete, no filler, no promised dates, no names, no placeholders except [Kontakt] for "
                 "the contact channel). Answer: {\"drafts\": [{\"n\": 1, \"text\": \"...\"}]}.")
    return rules + "\n\nRezensionen:\n" + _review_lines(reviews, True)


def measure_facts(summary: dict, entries: list[dict]) -> dict:
    """Zählungen für die Maßnahmenanfrage aus den schon vorhandenen KI-Antworten einer App (keine Texte, keine IDs):
    Häufungen der Zusammenfassung, häufigste Kernaussagen negativer oder dringender Rezensionen mit Sterne-Schnitt, Wünsche,
    Zahl der Abwanderungsdrohungen und der Sterne-Text-Widersprüche. `entries` sind die Stimmungs-Einträge (mit `rating`)."""
    issues: dict[str, dict] = {}
    wishes: dict[str, int] = {}
    churn = mismatch = negative = 0
    for entry in entries:
        rating = entry.get("rating") or 0
        key = _norm(entry.get("issue") or "")
        if entry.get("churn"):
            churn += 1
        if entry.get("mismatch"):
            mismatch += 1
        if entry.get("sentiment") == "wunsch" and key:
            wishes[key] = wishes.get(key, 0) + 1
        bad = entry.get("sentiment") in ("veraergert", "resigniert") or entry.get("urgency") == "hoch" or 0 < rating <= 2
        if not bad:
            continue
        negative += 1
        if key:
            row = issues.setdefault(key, {"issue": entry.get("issue"), "count": 0, "stars": 0, "rated": 0})
            row["count"] += 1
            if rating:
                row["stars"] += rating
                row["rated"] += 1
    top = sorted(issues.values(), key=lambda row: -row["count"])[:MAX_FACT_ROWS]
    return {"reviews": len(entries), "negative": negative, "churn": churn, "mismatch": mismatch,
            "clusters": [{"title": item["title"], "count": item["count"], "sinceVersion": item.get("sinceVersion")}
                         for item in (summary.get("urgent") or [])],
            "issues": [{"issue": row["issue"], "count": row["count"],
                        "avgStars": round(row["stars"] / row["rated"], 1) if row["rated"] else None} for row in top],
            "wishes": [{"issue": issue, "count": count} for issue, count in
                       sorted(wishes.items(), key=lambda item: -item[1])[:MAX_FACT_ROWS]]}


def _measures_prompt(language: str, facts: dict) -> str:
    """Maßnahmenliste: bekommt nur Zählungen aus früheren KI-Antworten (Häufungen, Kernaussagen, Wünsche), keine Texte.
    Die KI nennt je Maßnahme die Kernaussagen, auf die sie sich stützt; die Anteile rechnet danach das Skript."""
    if language == "de":
        rules = ("Leite aus diesen Zählungen zu den Rezensionen einer App höchstens 5 konkrete Maßnahmen ab, die die Bewertungen "
                 "am ehesten verbessern, wichtigste zuerst. Antwort als JSON-Objekt {\"measures\": [...]}, je Maßnahme: "
                 "title (höchstens 12 Wörter, beginnt mit einem Verb), reason (ein Satz, warum sie wirkt), "
                 "owner (entwicklung = Code der App | support = Antworten und Hilfe | anbieter = Abläufe des Anbieters wie "
                 "Freischaltung oder Service | store = Beschreibung, Bilder, Name im Store | produkt = fehlende Funktion), "
                 "effect (hoch | mittel | niedrig), issues (Liste der Kernaussagen oder Häufungen aus den Zählungen, wörtlich "
                 "übernommen, auf die sich die Maßnahme stützt). Keine Zahlen im Text, keine Termine, nichts erfinden.")
    else:
        rules = ("From these counts about one app's reviews, derive at most 5 concrete measures most likely to improve the "
                 "ratings, most important first. Answer as a JSON object {\"measures\": [...]}, per measure: title (at most "
                 "12 words, starting with a verb), reason (one sentence why it works), owner (entwicklung = app code | "
                 "support = replies and help | anbieter = the provider's processes such as activation or service | store = "
                 "description, images, name in the store | produkt = missing feature), effect (hoch | mittel | niedrig), "
                 "issues (list of the core statements or clusters from the counts, copied verbatim, that the measure rests "
                 "on). No numbers in the text, no dates, invent nothing.")
    lines = [f"Rezensionen analysiert: {facts['reviews']}, davon negativ oder dringend: {facts['negative']}, "
             f"Abwanderung angedroht: {facts['churn']}, Sterne widersprechen dem Text: {facts['mismatch']}"]
    lines.append("Häufungen: " + ("; ".join(f"{item['title']} ({item['count']}" + (f", seit {item['sinceVersion']}" if item.get("sinceVersion") else "") + ")"
                                           for item in facts["clusters"]) or "keine"))
    lines.append("Kernaussagen negativer Rezensionen: " + ("; ".join(
        f"{row['issue']} ({row['count']}" + (f", Ø {row['avgStars']} ★" if row.get("avgStars") is not None else "") + ")" for row in facts["issues"]) or "keine"))
    lines.append("Wünsche: " + ("; ".join(f"{row['issue']} ({row['count']})" for row in facts["wishes"]) or "keine"))
    return rules + "\n\nZählungen:\n" + "\n".join(lines)


def _map_measures(answer: Any, facts: dict, entries: list[dict], summary: dict, now: str) -> list[dict]:
    """Maßnahmen prüfen: Zuständigkeit und Wirkung nur aus den Listen, höchstens 5; `issues` nur, wenn sie wörtlich in den
    Zählungen vorkamen. Daraus zählt das Skript die betroffenen Rezensionen (IDs aus Kernaussagen und Häufungen) und den
    Anteil an den negativen Rezensionen; die KI liefert keine Zahlen."""
    rows = answer.get("measures") if isinstance(answer, dict) else answer
    known_issues = {_norm(row["issue"]): row["issue"] for row in facts["issues"]} | {_norm(row["issue"]): row["issue"] for row in facts["wishes"]}
    known_clusters = {_norm(item["title"]): item for item in (summary.get("urgent") or [])}
    ids_by_issue: dict[str, set] = {}
    for entry in entries:
        key = _norm(entry.get("issue") or "")
        if key and entry.get("id"):
            ids_by_issue.setdefault(key, set()).add(entry["id"])
    out = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not _short(row.get("title")):
            continue
        ids: set = set()
        issues = []
        for item in (row.get("issues") or [])[:10]:
            key = _norm(str(item or ""))
            if key in known_issues:
                issues.append(known_issues[key])
                ids |= ids_by_issue.get(key, set())
            elif key in known_clusters:
                issues.append(known_clusters[key]["title"])
                ids |= set(known_clusters[key].get("reviewIds") or [])
        out.append({"title": _short(row.get("title")), "reason": _short(row.get("reason"), 300),
                    "owner": _choice(row.get("owner"), OWNERS, "produkt"), "effect": _choice(row.get("effect"), EFFECTS, "mittel"),
                    "issues": issues, "reviewIds": sorted(ids), "reviewCount": len(ids),
                    "negShare": round(100 * len(ids) / facts["negative"]) if facts["negative"] and ids else None,
                    "generatedAt": now})
        if len(out) >= MAX_MEASURES:
            break
    return out


def measures(client: AiClient, system: str, language: str, summary: dict, entries: list[dict], now: str) -> list[dict]:
    """Maßnahmenliste einer App aus Zusammenfassung und Stimmungs-Einträgen; eine Anfrage ohne Rezensionstexte."""
    facts = measure_facts(summary, entries)
    if not facts["reviews"]:
        return []
    return _map_measures(client.complete_json(system, _measures_prompt(language, facts)), facts, entries, summary, now)


# ----------------------------------------------------------------------------------------------------------
# Abruf
# ----------------------------------------------------------------------------------------------------------

def _load_reviews(syncer: Syncer, result: Result) -> list[dict]:
    path = target_dir(syncer.cfg.data_dir, result.customer, result.app, result.platform,
                      competitor=result.competitor) / "reviews.json"
    doc = read_versioned(path, SCHEMA_VERSION, lambda: {"schemaVersion": SCHEMA_VERSION, "reviews": []})
    reviews = [review for review in doc.get("reviews", []) if review.get("id")]
    reviews.sort(key=lambda review: (review.get("createdAt") or "", review["id"]), reverse=True)
    return reviews


def _pending_sentiment(doc: dict, reviews: list[dict], hashes: dict[str, str]) -> list[dict]:
    return [review for review in reviews if (doc["reviews"].get(review["id"]) or {}).get("hash") != hashes[review["id"]]]


def _pending_drafts(doc: dict, reviews: list[dict], hashes: dict[str, str]) -> list[dict]:
    return [review for review in reviews
            if (review.get("rating") or 0) <= 2 and not (review.get("developerReply") or {}).get("text")
            and (doc["drafts"].get(review["id"]) or {}).get("hash") != hashes[review["id"]]]


def _basis_hash(reviews: list[dict], hashes: dict[str, str]) -> str:
    joined = "|".join(f"{review['id']}:{hashes[review['id']]}" for review in reviews)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


def _map_sentiment(answer: Any, reviews: list[dict], now: str) -> dict[str, dict]:
    rows = answer.get("reviews") if isinstance(answer, dict) else answer
    out: dict[str, dict] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("n"))
        except (TypeError, ValueError):
            continue
        if not 1 <= index <= len(reviews):
            continue
        review = reviews[index - 1]
        themes = [theme for theme in (_short(item, 40) for item in (row.get("themes") or [])[:MAX_THEMES_PER_REVIEW]) if theme]
        out[review["id"]] = {
            "sentiment": _choice(row.get("sentiment"), SENTIMENTS, "unklar"),
            "urgency": _choice(row.get("urgency"), URGENCIES, "niedrig"),
            "issue": _short(row.get("issue")), "themes": themes,
            "mismatch": bool(row.get("mismatch")), "churn": bool(row.get("churn")),
            "version": _short(row.get("version"), 20), "analyzedAt": now}
    return out


def _map_summary(answer: Any, reviews: list[dict], now: str) -> dict:
    """Zusammenfassung prüfen: Zitate nur, wenn sie wörtlich im genannten Text stehen; Listen begrenzt."""
    if not isinstance(answer, dict):
        answer = {}
    by_number = {number: review for number, review in enumerate(reviews, 1)}

    def review_of(value: Any) -> dict | None:
        try:
            return by_number.get(int(value))
        except (TypeError, ValueError):
            return None

    quotes = []
    for item in (answer.get("quotes") or [])[:MAX_QUOTES * 2]:
        if not isinstance(item, dict):
            continue
        review, text = review_of(item.get("n")), _short(item.get("text"), 300)
        if review and text and quote_in_text(text, f"{review.get('title') or ''} {review.get('text') or ''}"):
            quotes.append({"reviewId": review["id"], "text": text, "rating": review.get("rating"),
                           "createdAt": review.get("createdAt")})
        if len(quotes) >= MAX_QUOTES:
            break
    urgent = []
    for item in (answer.get("urgent") or [])[:10]:
        if not isinstance(item, dict) or not _short(item.get("title")):
            continue
        ids = [review["id"] for review in (review_of(number) for number in (item.get("ns") or [])[:200]) if review]
        try:
            count = int(item.get("count") or len(ids))
        except (TypeError, ValueError):
            count = len(ids)
        urgent.append({"title": _short(item.get("title")), "count": max(count, len(ids)),
                       "sinceVersion": _short(item.get("sinceVersion"), 20), "reviewIds": ids})
    suggestions = []
    for item in (answer.get("newThemes") or [])[:MAX_SUGGESTIONS]:
        if not isinstance(item, dict):
            continue
        name_de = _short(item.get("de"), 40)
        terms = [term for term in (_short(term, 30) for term in (item.get("terms") or [])[:8]) if term]
        if name_de and terms:
            try:
                count = int(item.get("count") or 0)
            except (TypeError, ValueError):
                count = 0
            suggestions.append({"de": name_de, "en": _short(item.get("en"), 40) or name_de,
                                "terms": [term.lower() for term in terms], "count": count})
    return {"generatedAt": now, "text": _short(answer.get("summary"), MAX_LONG),
            "praise": _short(answer.get("praise")), "criticism": _short(answer.get("criticism")),
            "assessment": _choice(answer.get("assessment"), ASSESSMENTS, "unklar"),
            "assessmentReason": _short(answer.get("assessmentReason"), 300),
            "quotes": quotes, "urgent": urgent, "themeSuggestions": suggestions}


def summarize(client: AiClient, system: str, language: str, basis: list[dict], send_text: bool, known: list[str],
              ai_cfg: dict, now: str, progress: Callable[[int, int], None] | None = None) -> dict:
    """Zusammenfassung einer App. Passt die Grundlage in eine Anfrage, eine Stufe; sonst je Stapel eine Teil-
    Zusammenfassung und eine zweite Anfrage, die die Teile verdichtet (Zitate nur aus den geprüften Teilergebnissen)."""
    max_chars, review_chars = int(ai_cfg["maxCharsPerRequest"]), int(ai_cfg["maxReviewChars"])
    batches = list(chunks_by_size(basis, len(basis), max_chars, send_text, review_chars))
    if len(batches) == 1:
        summary = _map_summary(client.complete_json(system, _summary_prompt(language, basis, send_text, known, review_chars)), basis, now)
        summary["stages"] = 1
        return summary
    parts, quotes = [], []
    for index, batch in enumerate(batches, 1):
        part = _map_summary(client.complete_json(system, _summary_prompt(language, batch, send_text, known, review_chars)), batch, now)
        quotes += part["quotes"]
        parts.append({"count": len(batch), "from": (batch[-1].get("createdAt") or "")[:10], "to": (batch[0].get("createdAt") or "")[:10],
                      "text": part["text"] or "", "praise": part["praise"] or "–", "criticism": part["criticism"] or "–",
                      "assessment": part["assessment"], "assessmentReason": part["assessmentReason"] or "",
                      "urgent": "; ".join(f"{item['title']} ({item['count']}, seit {item['sinceVersion'] or '?'})" for item in part["urgent"]) or "keine",
                      "themes": "; ".join(f"{item['de']} ({item['count']}; {', '.join(item['terms'])})" for item in part["themeSuggestions"]) or "keine",
                      "urgentItems": part["urgent"]})
        if progress:
            progress(index, len(batches))
    answer = client.complete_json(system, _reduce_prompt(language, parts, quotes))
    if not isinstance(answer, dict):
        answer = {}
    chosen = []
    for item in (answer.get("quotes") or [])[:MAX_QUOTES]:
        try:
            number = int(item.get("n") if isinstance(item, dict) else item)
        except (TypeError, ValueError):
            continue
        if 1 <= number <= len(quotes) and quotes[number - 1] not in chosen:
            chosen.append(quotes[number - 1])
    # Häufungen: Review-IDs aus den Teilstufen über gleichen Titel zusammenführen
    by_title: dict[str, list[str]] = {}
    for part in parts:
        for item in part["urgentItems"]:
            by_title.setdefault(_norm(item["title"]), []).extend(item["reviewIds"])
    merged = _map_summary({**answer, "quotes": []}, [], now)
    for item in merged["urgent"]:
        item["reviewIds"] = by_title.get(_norm(item["title"]), [])
        item["count"] = max(item["count"], len(item["reviewIds"]))
    merged["quotes"] = chosen
    merged["stages"] = 2
    merged["batches"] = len(batches)
    return merged


def _map_drafts(answer: Any, reviews: list[dict], language: str, now: str) -> dict[str, dict]:
    rows = answer.get("drafts") if isinstance(answer, dict) else answer
    out: dict[str, dict] = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            index = int(row.get("n"))
        except (TypeError, ValueError):
            continue
        text = _short(row.get("text"), MAX_LONG)
        if 1 <= index <= len(reviews) and text:
            review = reviews[index - 1]
            lang = (review.get("language") or "").split("-")[0].split("_")[0].lower() or language
            out[review["id"]] = {"text": text, "language": lang, "generatedAt": now}
    return out


def _fetch(syncer: Syncer, client: AiClient, store_id: str, doc: dict, result: Result, app: dict, now: str) -> None:
    """Neue oder geänderte Rezensionen analysieren, Zusammenfassung und Entwürfe aktualisieren. Was bis zu einem
    Fehler fertig wurde, bleibt in `doc` (Status `partial`)."""
    ai_cfg = syncer.cfg.ai
    language, send_text, features = ai_cfg["language"], bool(ai_cfg["sendReviewText"]), ai_cfg["features"]
    reviews = _load_reviews(syncer, result)
    hashes = {review["id"]: content_hash(review) for review in reviews}
    doc.setdefault("reviews", {})
    doc.setdefault("drafts", {})
    doc["provider"], doc["model"], doc["language"] = client.provider.name, client.model, language
    system = _system(language, app["name"], result.platform)
    client.target = app["name"]  # Verbrauch und Kosten je Kasse/App im Verbrauchsbuch
    pending = _pending_sentiment(doc, reviews, hashes) if features.get("sentiment") and send_text else []
    # Wettbewerber: keine Antwortentwürfe und keine Maßnahmen (fremde App, man antwortet nicht und handelt nicht für sie)
    rival = bool(app.get("competitor"))
    drafts = _pending_drafts(doc, reviews, hashes) if features.get("replyDrafts") and send_text and not rival else []
    basis = reviews[:int(ai_cfg["summaryReviews"])]
    basis_hash = _basis_hash(basis, hashes)
    summary_due = bool(features.get("summary") and basis and (doc.get("summary") or {}).get("basisHash") != basis_hash)
    # Maßnahmen: mit jeder neuen Zusammenfassung, oder einmal nachgeholt, wenn eine Zusammenfassung ohne Maßnahmen vorliegt
    measures_due = bool(features.get("measures") and features.get("sentiment") and send_text and not rival
                        and (summary_due or (doc.get("summary") and "measures" not in doc["summary"])))
    if syncer.opt.dry_run:
        result.new = len(pending) + len(drafts) + (1 if summary_due else 0) + (1 if measures_due else 0)
        log.info("Probelauf: %d Rezensionen zur Stimmung, %d Antwortentwürfe, Zusammenfassung %s, Maßnahmen %s – nichts gesendet",
                 len(pending), len(drafts), "fällig" if summary_due else "aktuell", "fällig" if measures_due else "aktuell")
        return
    done = 0
    max_chars, review_chars = int(ai_cfg["maxCharsPerRequest"]), int(ai_cfg["maxReviewChars"])
    for chunk in chunks_by_size(pending, int(ai_cfg["maxReviewsPerRequest"]), max_chars, send_text, review_chars):
        mapped = _map_sentiment(client.complete_json(system, _sentiment_prompt(language, chunk, send_text, review_chars)), chunk, now)
        for review in chunk:
            entry = mapped.get(review["id"])
            if entry:
                doc["reviews"][review["id"]] = {**entry, "hash": hashes[review["id"]]}
                result.new += 1
        done += len(chunk)
        syncer.progress(f"{app['name']} · KI-Stimmung", done, len(pending))
    if summary_due:
        known = [topic.get("de") or topic["id"] for topic in syncer.cache.get("ai_topics", [])]
        summary = summarize(client, system, language, basis, send_text, known, ai_cfg, now,
                            lambda done_batches, total: syncer.progress(f"{app['name']} · KI-Zusammenfassung", done_batches, total))
        doc["summary"] = {**summary, "basisHash": basis_hash, "basedOn": [review["id"] for review in basis],
                          "provider": client.provider.name, "model": client.model}
        result.new += 1
    if measures_due and doc.get("summary"):
        entries = [{**doc["reviews"][review["id"]], "id": review["id"], "rating": review.get("rating")}
                   for review in basis if review["id"] in doc["reviews"]]
        doc["summary"]["measures"] = measures(client, system, language, doc["summary"], entries, now)
        result.new += 1
    for chunk in chunks_by_size(drafts, DRAFT_BATCH, max_chars, True, review_chars):
        mapped = _map_drafts(client.complete_json(system, _draft_prompt(language, chunk)), chunk, language, now)
        for review in chunk:
            entry = mapped.get(review["id"])
            if entry:
                doc["drafts"][review["id"]] = {**entry, "hash": hashes[review["id"]], "provider": client.provider.name,
                                               "model": client.model}
                result.new += 1
    result.changed = result.changed or bool(result.new)


def _dataset(platform: str, targets: str = "apps") -> Dataset:
    return Dataset(mode="ai", label="KI-Analyse", platform=platform, state_key=f"{platform}-ai",
                   file_name="ai-analysis.json", new_doc=_new_doc(platform), fetch=_fetch, total=_total,
                   limitations=LIMITATIONS, wording=AI_WORDING, client=ai_client, targets=targets)


AI_APPLE = _dataset("apple")
AI_GOOGLE = _dataset("google")
AI_COMPETITORS = _dataset("apple", targets="competitors")  # nur mit ai.analyzeCompetitors und eingetragenen Wettbewerbern


def run_ai(syncer: Syncer, topics: list[dict] | None = None) -> list[Result]:
    """KI-Analyse für alle ausgewählten Apps (Apple und Google). `topics` sind die bekannten Themen aus
    `config/themen.json`, damit die KI nur neue vorschlägt."""
    syncer.cache["ai_topics"] = topics or []
    client = ai_client(syncer, {})  # prüft Anbieter und Schlüssel vor dem ersten Ziel
    datasets = [AI_APPLE, AI_GOOGLE]
    if syncer.cfg.ai.get("analyzeCompetitors", True) and syncer.targets(competitors=True):
        datasets.append(AI_COMPETITORS)
    results = syncer.run_datasets(datasets, f"KI-Analyse der Rezensionen ({client.label}, {client.model})")
    log_costs(client)
    return results


def cost_rows(ledger: UsageLedger) -> list[list[str]]:
    """Zeilen „Ziel, Anfragen, Tokens rein, Tokens raus, Kosten“ für den laufenden Prozess, teuerste zuerst, plus Summe."""
    rows = []
    for name, entry in sorted(ledger.run.items(), key=lambda item: (-item[1]["costUsd"], item[0])):
        rows.append([name, fmt_int(entry["requests"]), fmt_int(entry["inputTokens"]), fmt_int(entry["outputTokens"]),
                     fmt_usd(entry["costUsd"]) + (" (+?)" if entry["unpricedRequests"] else "")])
    total = ledger.run_total()
    rows.append(["Gesamt", fmt_int(total["requests"]), fmt_int(total["inputTokens"]), fmt_int(total["outputTokens"]),
                 fmt_usd(total["costUsd"]) + (" (+?)" if total["unpricedRequests"] else "")])
    return rows


def log_costs(client: AiClient) -> None:
    """Kosten dieses Laufs je Kasse/App und gesamt sowie der Monatsstand, als Tabelle ins Log (INFO)."""
    ledger = client.ledger
    if not ledger.run:
        return
    if client.price is None:
        price_note = "Preis unbekannt, Kosten nicht geschätzt"
    else:
        price_note = (f"{fmt_usd(client.price.input_per_million)} rein / {fmt_usd(client.price.output_per_million)} raus "
                      f"je Mio. Tokens, Quelle {client.price.source}")
    log.info("▶ KI-Kosten dieses Laufs (%s/%s, %s%s)", client.provider.name, client.model, price_note,
             ", Probelauf: nicht gespeichert" if client.dry_run else "")
    for line in table(["Kasse / App", "Anfragen", "Tokens rein", "Tokens raus", "Kosten"], cost_rows(ledger),
                      ["left", "right", "right", "right", "right"]).splitlines():
        log.info("%s", line)
    month = ledger.month_entry()
    log.info("Monat %s bisher: %s Anfragen · %s Tokens · %s%s · Limit %s Tokens", ledger.month(),
             fmt_int(int(month.get("requests", 0))), fmt_int(ledger.used()), fmt_usd(ledger.month_cost()),
             " (+? ohne Preis)" if month.get("unpricedRequests") else "", fmt_int(ledger.limit))
