"""Freitextfragen an die gespeicherten Rezensionen (KI-Funktion `questions`, standardmäßig aus, kostet je Frage).

Ablauf: Rezensionen der Auswahl laden (Kunde, App, Plattform; dazu `selection`: mehrere Apps, Zeitraum, Sterne und, aus
dem Bericht, die IDs der gerade gefilterten Rezensionen, damit alle Filter des Berichts gelten; Wunsch des Nutzers
24.10.2026), die jüngsten `ai.maxReviewsPerQuestion` nummeriert an den aktiven Anbieter senden, Antwort mit Belegen zurück. Zitate werden gegen den Originaltext geprüft; ohne Beleg wird
die Antwort als „unklar“ markiert. Fragen und Antworten landen in `data/ai-questions.json`, damit der Bericht sie
zeigt (die letzten `MAX_QUESTIONS`). Nichts davon ruft Store-APIs auf.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .ai_analysis import clip_text, fit_budget, make_client, quote_in_text
from .ai_providers import QUESTIONS_TARGET, AiClient
from .config import Config
from .errors import ConfigError
from .models import utc_now
from .reporting import build_dataset
from .storage import read_versioned, write_json

log = logging.getLogger("arr.ai")

MAX_QUESTIONS = 100     # gespeicherte Fragen (älteste fallen weg)
MAX_QUESTION_LEN = 500  # Zeichen je Frage
CONFIDENCES = ("sicher", "hinweis", "unklar")
MAX_SELECTED_IDS = 3000   # Rezensions-IDs, die der Bericht als Auswahl mitschicken darf
MAX_SCOPE_LABEL = 300     # Zeichen der Auswahlbeschreibung aus dem Bericht (Filter-Kärtchen)


def _str_or_none(value, limit: int = 100) -> str | None:
    text = str(value or "").strip()
    return text[:limit] or None


def normalize_selection(raw: dict | None) -> dict:
    """Auswahl aus Bericht oder Kommandozeile in feste Form bringen; unbekannte Felder fallen weg, Listen werden begrenzt.

    Felder: `apps` (Schlüssel `kunde/app`), `from`/`to` (JJJJ-MM-TT), `ratingMin`/`ratingMax` (1–5), `reviewIds`
    (nur aus dem Bericht: die dort gefilterten Rezensionen), `label` (Beschreibung der gesetzten Filter für die Anzeige)."""
    raw = raw if isinstance(raw, dict) else {}
    day = lambda value: value if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) else None  # noqa: E731
    star = lambda value: int(value) if isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 5 else None  # noqa: E731
    apps = [item for item in (_str_or_none(item) for item in (raw.get("apps") or [])[:200]) if item and "/" in item]
    ids = [item for item in (_str_or_none(item, 200) for item in (raw.get("reviewIds") or [])[:MAX_SELECTED_IDS]) if item]
    return {"apps": apps, "from": day(raw.get("from")), "to": day(raw.get("to")), "ratingMin": star(raw.get("ratingMin")),
            "ratingMax": star(raw.get("ratingMax")), "reviewIds": ids if raw.get("reviewIds") is not None else None,
            "label": _str_or_none(raw.get("label"), MAX_SCOPE_LABEL)}


def apply_selection(reviews: list[dict], selection: dict) -> list[dict]:
    """Rezensionen auf die Auswahl beschränken (Apps, Zeitraum, Sterne, IDs aus dem Bericht). Reihenfolge bleibt."""
    apps, ids = set(selection["apps"]), (set(selection["reviewIds"]) if selection["reviewIds"] is not None else None)
    out = []
    for review in reviews:
        if apps and f"{review.get('customerId')}/{review.get('appId')}" not in apps:
            continue
        day = (review.get("createdAt") or "")[:10]
        if selection["from"] and day < selection["from"] or selection["to"] and day > selection["to"]:
            continue
        rating = review.get("rating") or 0
        if selection["ratingMin"] and rating < selection["ratingMin"] or selection["ratingMax"] and rating > selection["ratingMax"]:
            continue
        if ids is not None and review.get("id") not in ids:
            continue
        out.append(review)
    return out


def _system(language: str) -> str:
    if language == "en":
        return ("You answer questions about app store reviews for the product team. Use only the reviews given; never "
                "invent facts or numbers. Answer only with valid JSON: {\"answer\": \"...\", \"confidence\": \"sicher|hinweis|"
                "unklar\", \"quotes\": [{\"n\": 1, \"text\": \"verbatim excerpt\"}]}. Keep the answer under 120 words, in English. "
                "\"sicher\" only if several reviews support the answer, \"hinweis\" for few, \"unklar\" if the reviews do not "
                "answer the question.")
    return ("Du beantwortest Fragen zu App-Store-Rezensionen für das Produktteam. Nutze nur die übergebenen Rezensionen, "
            "erfinde nie Fakten oder Zahlen. Antworte ausschließlich mit gültigem JSON: {\"answer\": \"...\", \"confidence\": "
            "\"sicher|hinweis|unklar\", \"quotes\": [{\"n\": 1, \"text\": \"wörtlicher Ausschnitt\"}]}. Antwort unter 120 Wörtern, "
            "auf Deutsch. \"sicher\" nur, wenn mehrere Rezensionen die Antwort stützen, \"hinweis\" bei wenigen, \"unklar\", "
            "wenn die Rezensionen die Frage nicht beantworten.")


def _lines(reviews: list[dict], send_text: bool, review_chars: int) -> str:
    lines = []
    for number, review in enumerate(reviews, 1):
        meta = [f"n={number}", f"app={review.get('appName')}", f"store={review.get('platform')}",
                f"sterne={review.get('rating')}", f"datum={(review.get('createdAt') or '')[:10]}"]
        if review.get("competitor"):
            meta.insert(2, "wettbewerber=ja")  # fremde App: die KI soll sie nicht als eigene behandeln
        if review.get("appVersion"):
            meta.append(f"version={review['appVersion']}")
        body = ""
        if send_text:
            title = clip_text(review.get("title") or "", 200)
            text = clip_text(review.get("text") or "", max(50, review_chars - len(title)))
            body = " | " + (f"titel: {title} | " if title else "") + f"text: {text or '(kein Text)'}"
        lines.append("[" + ", ".join(meta) + "]" + body)
    return "\n".join(lines)


def questions_path(data_dir: Path) -> Path:
    return data_dir / "ai-questions.json"


def load_questions(data_dir: Path) -> dict:
    """Gespeicherte Fragen und Antworten (leer, wenn noch keine gestellt wurde)."""
    return read_versioned(questions_path(data_dir), 1, lambda: {"schemaVersion": 1, "questions": []})


def delete_question(data_dir: Path, asked_at: str, question: str | None = None) -> int:
    """Löscht gespeicherte Fragen mit diesem Zeitstempel (und, falls angegeben, diesem Fragetext). Liefert die Anzahl.

    Fragen sind eigene Eingaben, kein Datenbestand aus den Stores; sie dürfen deshalb ohne Backup entfernt werden."""
    doc = load_questions(data_dir)
    before = len(doc["questions"])
    doc["questions"] = [entry for entry in doc["questions"]
                        if not (entry.get("askedAt") == asked_at and (question is None or entry.get("question") == question))]
    removed = before - len(doc["questions"])
    if removed:
        write_json(questions_path(data_dir), doc)
    return removed


def clear_questions(data_dir: Path) -> int:
    """Löscht alle gespeicherten Fragen; liefert die Anzahl."""
    doc = load_questions(data_dir)
    count = len(doc["questions"])
    if count:
        write_json(questions_path(data_dir), {"schemaVersion": 1, "questions": []})
    return count


def ask(cfg: Config, question: str, only_customer: str | None = None, only_app: str | None = None,
        only_platform: str | None = None, transport=None, save: bool = True, client: AiClient | None = None,
        selection: dict | None = None) -> dict:
    """Stellt eine Frage an die Rezensionen der Auswahl und liefert `{question, answer, confidence, quotes, …}`.

    - Parameter selection: zusätzliche Auswahl (`normalize_selection`): mehrere Apps, Zeitraum, Sterne, Rezensions-IDs aus
      dem Bericht (dann gelten exakt die Filter des Berichts, auch Thema, Suche, Stimmung), Beschreibung für die Anzeige.
    - Raises: `ConfigError`, wenn `ai.features.questions` aus ist, kein Anbieter aktiv ist oder die Frage leer ist.
    """
    question = re.sub(r"\s+", " ", question or "").strip()
    if not question:
        raise ConfigError("Die Frage ist leer.")
    if len(question) > MAX_QUESTION_LEN:
        raise ConfigError(f"Die Frage ist länger als {MAX_QUESTION_LEN} Zeichen.")
    if not cfg.ai["features"].get("questions"):
        raise ConfigError("Freitextfragen sind ausgeschaltet. In config/config.json ai.features.questions auf true setzen "
                          "(jede Frage kostet eine Anfrage beim Anbieter).")
    client = client or make_client(cfg, transport)
    client.target = QUESTIONS_TARGET  # Verbrauch und Kosten der Fragen getrennt von den Analysen je Kasse
    selection = normalize_selection(selection)
    dataset = build_dataset(cfg.data_dir, cfg.raw, only_customer, only_app, only_platform)
    available = apply_selection(dataset["reviews"], selection)  # bereits absteigend nach Datum
    if not available:
        raise ConfigError("Für diese Auswahl sind keine Rezensionen gespeichert." if not dataset["reviews"]
                          else "Keine Rezension entspricht der Auswahl (Apps, Zeitraum, Sterne, Filter des Berichts).")
    send_text, review_chars = bool(cfg.ai["sendReviewText"]), int(cfg.ai["maxReviewChars"])
    # Jüngste zuerst, begrenzt durch Stückzahl und Zeichenbudget; die Antwort nennt, wie viele gelesen wurden
    reviews = fit_budget(available[:int(cfg.ai["maxReviewsPerQuestion"])], int(cfg.ai["maxCharsPerRequest"]), send_text, review_chars)
    prompt = f"Frage: {question}\n\nRezensionen:\n{_lines(reviews, send_text, review_chars)}"
    answer = client.complete_json(_system(cfg.ai["language"]), prompt)
    if not isinstance(answer, dict):
        answer = {}
    quotes = []
    for item in (answer.get("quotes") or [])[:10]:
        if not isinstance(item, dict):
            continue
        try:
            review = reviews[int(item.get("n")) - 1] if 1 <= int(item.get("n")) <= len(reviews) else None
        except (TypeError, ValueError):
            review = None
        text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()[:300]
        if review and text and quote_in_text(text, f"{review.get('title') or ''} {review.get('text') or ''}"):
            quotes.append({"reviewId": review["id"], "appName": review.get("appName"), "rating": review.get("rating"),
                           "createdAt": review.get("createdAt"), "text": text})
    confidence = str(answer.get("confidence") or "").strip().lower()
    if confidence not in CONFIDENCES:
        confidence = "unklar"
    if send_text and not quotes and confidence != "unklar":
        confidence = "unklar"  # ohne wörtlichen Beleg keine sichere Aussage
    entry = {"askedAt": utc_now(), "question": question, "answer": re.sub(r"\s+", " ", str(answer.get("answer") or "")).strip()[:2000],
             "confidence": confidence, "quotes": quotes, "reviewCount": len(reviews), "availableCount": len(available),
             "scope": {"customer": only_customer, "app": only_app,
                       "platform": only_platform if only_platform != "all" else None,
                       "apps": selection["apps"], "from": selection["from"], "to": selection["to"],
                       "ratingMin": selection["ratingMin"], "ratingMax": selection["ratingMax"],
                       "label": selection["label"], "selected": len(available)},
             "provider": client.provider.name, "model": client.model,
             "inputTokens": client.last_usage.input_tokens, "outputTokens": client.last_usage.output_tokens}
    if save:
        doc = load_questions(cfg.data_dir)
        doc["questions"] = (doc["questions"] + [entry])[-MAX_QUESTIONS:]
        write_json(questions_path(cfg.data_dir), doc)
    return entry
