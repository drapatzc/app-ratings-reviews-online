"""Benachrichtigung nach dem Tageslauf: neue 1–2-★-Rezensionen, Ampelwechsel und Absturzsprünge per E-Mail, Slack
oder Webhook.

Läuft als letzter Schritt von `./ratings.sh daily` (nach Abruf, KI-Analyse und Bericht) über den Einstieg `notify.py`.
Liest nur den vorhandenen Datenbestand (`reporting.build_dataset`), ruft keine Store- oder KI-API auf und erfindet nichts: Die
Ampel kommt aus `metrics.ampel_all`, die KI-Sätze aus `ai-analysis.json` (Feld `issue` je Rezension, Marke „KI“ mit
Anbieter und Modell in der Fußzeile), Zahlen nie von der KI.

Idempotenz: `data/notify-state.json` merkt sich den Zeitpunkt der letzten Meldung, die Ampelstufe je App und ob zuletzt
ein Absturzgrund vorlag. Ein Vorfall wird deshalb nur einmal gemeldet, auch wenn `daily` mehrfach am Tag läuft. Der
Zustand wird nur fortgeschrieben, wenn mindestens ein Kanal zugestellt hat; sonst wird beim nächsten Lauf erneut versucht.

Netz: Slack und Webhook gehen über `http.HttpClient` (nur HTTPS). E-Mail ist die einzige Nicht-HTTP-Verbindung des
Projekts (`smtplib`, TLS über `ssl.create_default_context`; `security: "none"` nur für 127.0.0.1/localhost, siehe
`config._validate_channel`). Geheimnisse (SMTP-Passwort, Webhook-Adresse, Signaturschlüssel) kommen ausschließlich aus
Umgebungsvariablen (`security.read_env_secret`); jede Fehlermeldung läuft durch `security.redact`.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable

from .config import Config
from .errors import ConfigError, NotifyError, ToolError
from .http import HttpClient
from .metrics import reason_text
from .models import utc_now
from .reporting import build_dataset
from .security import read_env_secret, redact
from .storage import read_versioned, write_json

log = logging.getLogger("arr")

STATE_SCHEMA = 1
STATE_FILE = "notify-state.json"      # im Datenordner; Schema siehe `empty_state`
PAYLOAD_SCHEMA = 1                    # Schema des Webhook-JSON (`Message.payload`)
MAX_REVIEW_TEXT = 300                 # Zeichen Rezensionstext je Eintrag in der Nachricht
MAX_TITLE = 80                        # Zeichen Titel je Eintrag
CRASH_CODES = ("crash", "crashUp")    # Ampelgründe, die als Absturzsprung gelten
LEVEL_NAMES = {"de": ("grün", "gelb", "rot"), "en": ("green", "yellow", "red")}
PLATFORM_NAMES = {"apple": "Apple", "google": "Google"}
SIGNATURE_HEADER = "X-Ratings-Signature"
USER_AGENT_EVENT = "X-Ratings-Event"


def txt(lang: str, de_text: str, en_text: str) -> str:
    """Text in der Sprache der Nachricht (`notify.language`)."""
    return de_text if lang == "de" else en_text


@dataclass
class Event:
    """Ein meldenswerter Vorfall. `kind`: negativeReview, ampelChange oder crashJump."""

    kind: str
    app: dict                                  # customerId, appId, appName, customerName, platform
    review: dict | None = None                 # bei negativeReview: die Rezension aus reviews.json
    ai_issue: str | None = None                # KI-Kernaussage zur Rezension (ai-analysis.json, Feld issue), sonst None
    ai_urgency: str | None = None              # KI-Dringlichkeit (niedrig/mittel/hoch), sonst None
    before: int | None = None                  # Ampelstufe vorher (ampelChange)
    after: int | None = None                   # Ampelstufe jetzt (ampelChange, crashJump)
    reasons: list[dict] = field(default_factory=list)  # strukturierte Gründe aus `metrics.ampel`

    @property
    def key(self) -> str:
        """Schlüssel `kunde/app/plattform` wie in `metrics.ampel_all`."""
        return f"{self.app['customerId']}/{self.app['appId']}/{self.app['platform']}"


@dataclass
class Message:
    """Fertige Nachricht: Betreff und Klartext (E-Mail, Slack) sowie strukturierter Inhalt (Webhook)."""

    subject: str
    text: str
    payload: dict


def empty_state() -> dict:
    """Leerer Zustand: noch nie gemeldet, keine bekannten Ampelstufen."""
    return {"schemaVersion": STATE_SCHEMA, "lastRunAt": None, "ampel": {}, "crash": {}, "lastMessageAt": None}


def load_state(data_dir: Path) -> dict:
    """Liest `notify-state.json`; fehlt die Datei, beginnt der Zustand leer (erster Lauf)."""
    state = read_versioned(data_dir / STATE_FILE, STATE_SCHEMA, empty_state)
    return {**empty_state(), **state}


def next_state(state: dict, dataset: dict, now: str, sent: bool) -> dict:
    """Zustand nach diesem Lauf: aktuelle Ampelstufen und Absturzgründe je App, Zeitpunkt des Laufs."""
    ampel = dataset.get("ampel") or {}
    return {"schemaVersion": STATE_SCHEMA, "lastRunAt": now,
            "ampel": {key: int(value["level"]) for key, value in ampel.items()},
            "crash": {key: any(reason["code"] in CRASH_CODES for reason in value["reasons"]) for key, value in ampel.items()},
            "lastMessageAt": now if sent else state.get("lastMessageAt")}


def collect_events(dataset: dict, state: dict, notify_cfg: dict) -> list[Event]:
    """Vergleicht den Datenbestand mit dem gemerkten Zustand und liefert die Vorfälle seit dem letzten Lauf.

    Erster Lauf (`lastRunAt` fehlt) mit `quietOnFirstRun`: keine Vorfälle, nur der Stand wird gemerkt.
    - negativeReview: Rezension mit höchstens 2 ★, deren `firstSeenAt` nach dem letzten Lauf liegt.
    - ampelChange: Stufe höher als gemerkt oder zurück auf grün (eine Besserung von rot auf gelb wird nicht gemeldet).
    - crashJump: Absturzgrund (`crash`/`crashUp`) neu dabei, ohne dass sich die Stufe geändert hat.
    """
    last_run = state.get("lastRunAt")
    if not last_run and notify_cfg.get("quietOnFirstRun", True):
        return []
    triggers = notify_cfg.get("triggers") or {}
    # Wettbewerber (customers[].competitors) werden nie gemeldet (Entscheidung des Nutzers, 25.10.2026)
    apps = {f"{app['customerId']}/{app['appId']}/{app['platform']}": app for app in dataset.get("apps", [])
            if not app.get("competitor")}
    ai_by_key: dict[str, dict] = {f"{doc['customerId']}/{doc['appId']}/{doc['platform']}": doc
                                  for doc in dataset.get("ai", [])}
    events: list[Event] = []
    if triggers.get("negativeReviews", True):
        fresh = [review for review in dataset.get("reviews", [])
                 if (review.get("rating") or 9) <= 2 and review.get("firstSeenAt") and not review.get("competitor")
                 and (not last_run or review["firstSeenAt"] > last_run)]
        fresh.sort(key=lambda review: (review.get("createdAt") or "", review["id"]), reverse=True)
        for review in fresh:
            key = f"{review['customerId']}/{review['appId']}/{review['platform']}"
            app = apps.get(key) or {"customerId": review["customerId"], "appId": review["appId"],
                                    "platform": review["platform"], "appName": review.get("appName", review["appId"]),
                                    "customerName": review.get("customerName", "")}
            analysis = (ai_by_key.get(key) or {}).get("reviews", {}).get(review["id"]) or {}
            events.append(Event("negativeReview", app, review=review, ai_issue=analysis.get("issue") or None,
                                ai_urgency=analysis.get("urgency")))
    known_levels, known_crash = state.get("ampel") or {}, state.get("crash") or {}
    for key, value in (dataset.get("ampel") or {}).items():
        app = apps.get(key)
        if not app:
            continue
        level, reasons = int(value["level"]), value["reasons"]
        before = known_levels.get(key)
        changed = before is not None and level != before and (level > before or level == 0)
        if changed and triggers.get("ampelChange", True):
            events.append(Event("ampelChange", app, before=before, after=level, reasons=reasons))
            continue
        crash_now = any(reason["code"] in CRASH_CODES for reason in reasons)
        if crash_now and not known_crash.get(key, False) and triggers.get("crashJump", True):
            events.append(Event("crashJump", app, after=level,
                                reasons=[reason for reason in reasons if reason["code"] in CRASH_CODES]))
    return events


def _short(text: Any, limit: int) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1].rstrip() + "…"


def _app_label(app: dict) -> str:
    return f"{app.get('appName') or app['appId']} ({PLATFORM_NAMES.get(app['platform'], app['platform'])})"


def _day(value: str | None) -> str:
    return (value or "")[:10] or "?"


def _review_lines(event: Event, lang: str) -> list[str]:
    review = event.review or {}
    meta = [f"{review.get('rating')} ★", _day(review.get("createdAt"))]
    if review.get("country"):
        meta.append(str(review["country"]))
    if review.get("appVersion"):
        meta.append(f"Version {review['appVersion']}")
    lines = [f"- {_app_label(event.app)}, {', '.join(meta)}"]
    title, text = _short(review.get("title"), MAX_TITLE), _short(review.get("text"), MAX_REVIEW_TEXT)
    if title:
        lines.append(f"  „{title}“" if lang == "de" else f"  “{title}”")
    if text:
        lines.append(f"  {text}")
    if event.ai_issue:
        urgency = f" ({txt(lang, 'Dringlichkeit', 'urgency')} {event.ai_urgency})" if event.ai_urgency else ""
        lines.append(f"  KI: {event.ai_issue}{urgency}" if lang == "de" else f"  AI: {event.ai_issue}{urgency}")
    return lines


def compose(events: list[Event], dataset: dict, notify_cfg: dict, report_link: str, now: str) -> Message:
    """Baut Betreff, Klartext und Webhook-JSON. Nutzernamen kommen nie vor (werden nicht gespeichert)."""
    lang = notify_cfg.get("language", "de")
    limit = int(notify_cfg.get("maxReviewsPerMessage", 10))
    negatives = [event for event in events if event.kind == "negativeReview"]
    changes = [event for event in events if event.kind == "ampelChange"]
    crashes = [event for event in events if event.kind == "crashJump"]
    names = LEVEL_NAMES[lang]
    parts: list[str] = []
    if negatives:
        parts.append(txt(lang, f"{len(negatives)} neue 1–2 ★", f"{len(negatives)} new 1–2 ★"))
    for event in changes:
        parts.append(f"{txt(lang, 'Ampel', 'status')} {names[event.after]}: {event.app.get('appName') or event.app['appId']}")
    for event in crashes:
        parts.append(f"{txt(lang, 'Abstürze', 'crashes')}: {event.app.get('appName') or event.app['appId']}")
    subject = txt(lang, "Bewertungen: ", "App reviews: ") + " · ".join(parts[:4]) + (" …" if len(parts) > 4 else "")

    lines: list[str] = []
    if changes:
        lines += [txt(lang, "AMPEL", "STATUS")]
        for event in changes:
            why = "; ".join(reason_text(reason, lang) for reason in event.reasons) or txt(lang, "keine offenen Gründe", "no open reasons")
            lines.append(f"- {_app_label(event.app)}: {names[event.before]} → {names[event.after]} – {why}")
        lines.append("")
    if crashes:
        lines += [txt(lang, "ABSTÜRZE", "CRASHES")]
        for event in crashes:
            lines.append(f"- {_app_label(event.app)}: {'; '.join(reason_text(reason, lang) for reason in event.reasons)}")
        lines.append("")
    if negatives:
        lines += [txt(lang, "NEUE 1–2-★-REZENSIONEN", "NEW 1–2-★ REVIEWS")]
        for event in negatives[:limit]:
            lines += _review_lines(event, lang)
        if len(negatives) > limit:
            lines.append(txt(lang, f"… und {len(negatives) - limit} weitere, siehe Bericht.",
                            f"… and {len(negatives) - limit} more, see the report."))
        lines.append("")
    lines.append(txt(lang, f"Bericht: {report_link}", f"Report: {report_link}"))
    ai_docs = {(doc.get("provider"), doc.get("model")) for doc in dataset.get("ai", []) if doc.get("provider")}
    if any(event.ai_issue for event in negatives) and ai_docs:
        providers = ", ".join(f"{provider} ({model})" for provider, model in sorted(ai_docs, key=str))
        lines.append(txt(lang, f"Sätze mit „KI:“ stammen aus der gespeicherten KI-Analyse ({providers}); Zahlen stammen nie von der KI.",
                        f"Lines marked “AI:” come from the stored AI analysis ({providers}); numbers never come from the AI."))
    lines.append(txt(lang, f"Erzeugt von app-ratings-reviews am {now[:10]} um {now[11:16]} UTC.",
                    f"Generated by app-ratings-reviews on {now[:10]} at {now[11:16]} UTC."))
    text = "\n".join(lines).strip() + "\n"
    payload = {"schemaVersion": PAYLOAD_SCHEMA, "generatedAt": now, "reportUrl": report_link, "subject": subject, "text": text,
               "events": [_event_json(event, lang) for event in events]}
    return Message(subject=subject, text=text, payload=payload)


def _event_json(event: Event, lang: str) -> dict:
    """Strukturierter Vorfall für den Webhook: nur Felder, die auch der Bericht zeigt."""
    row: dict[str, Any] = {"kind": event.kind, "customerId": event.app["customerId"], "appId": event.app["appId"],
                           "appName": event.app.get("appName"), "platform": event.app["platform"]}
    if event.review is not None:
        review = event.review
        row["review"] = {"id": review["id"], "rating": review.get("rating"), "createdAt": review.get("createdAt"),
                         "country": review.get("country"), "appVersion": review.get("appVersion"),
                         "title": _short(review.get("title"), MAX_TITLE), "text": _short(review.get("text"), MAX_REVIEW_TEXT)}
        row["ai"] = {"issue": event.ai_issue, "urgency": event.ai_urgency} if event.ai_issue else None
    if event.kind in ("ampelChange", "crashJump"):
        row["ampel"] = {"before": event.before, "after": event.after,
                        "reasons": [{**reason, "text": reason_text(reason, lang)} for reason in event.reasons]}
    return row


def test_message(notify_cfg: dict, report_link: str, now: str) -> Message:
    """Testnachricht für `--test`: prüft Zugänge und Zustellung, ohne Daten zu lesen oder den Zustand zu ändern."""
    lang = notify_cfg.get("language", "de")
    subject = txt(lang, "Bewertungen: Testnachricht", "App reviews: test message")
    text = txt(lang, f"Die Benachrichtigung ist eingerichtet. Echte Meldungen kommen nach dem Tageslauf, wenn es neue "
                    f"1–2-★-Rezensionen, einen Ampelwechsel oder einen Absturzsprung gibt.\nBericht: {report_link}\n"
                    f"Gesendet am {now[:10]} um {now[11:16]} UTC.\n",
              f"Notifications are set up. Real messages arrive after the daily run when there are new 1–2-★ reviews, "
              f"a status change or a crash jump.\nReport: {report_link}\nSent on {now[:10]} at {now[11:16]} UTC.\n")
    return Message(subject=subject, text=text, payload={"schemaVersion": PAYLOAD_SCHEMA, "generatedAt": now, "test": True,
                                                        "reportUrl": report_link, "subject": subject, "text": text, "events": []})


# ---------------------------------------------------------------- Kanäle

SmtpFactory = Callable[[str, str, int, float], Any]  # (security, host, port, timeout) → SMTP-Verbindung


def default_smtp_factory(security: str, host: str, port: int, timeout: float) -> Any:
    """Öffnet die SMTP-Verbindung: `ssl` sofort verschlüsselt, sonst Klartext (STARTTLS folgt in `EmailChannel.send`)."""
    if security == "ssl":
        return smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context())
    return smtplib.SMTP(host, port, timeout=timeout)


class EmailChannel:
    """E-Mail über SMTP. Passwort aus `passwordEnvironmentVariable`; ohne username wird nicht angemeldet (lokaler Relay)."""

    name = "email"

    def __init__(self, cfg: dict, smtp_factory: SmtpFactory | None = None, timeout: float = 30):
        self.cfg = cfg
        self.factory = smtp_factory or default_smtp_factory
        self.timeout = timeout

    def describe(self) -> str:
        return f"E-Mail an {', '.join(self.cfg.get('to') or [])} über {self.cfg.get('host')}"

    def send(self, message: Message) -> None:
        cfg = self.cfg
        security = cfg.get("security", "starttls")
        password = read_env_secret(cfg["passwordEnvironmentVariable"], "SMTP") if cfg.get("username") else None
        mail = EmailMessage()
        mail["Subject"] = message.subject
        mail["From"] = cfg["from"]
        mail["To"] = ", ".join(cfg["to"])
        mail.set_content(message.text)
        try:
            smtp = self.factory(security, cfg["host"], int(cfg.get("port", 587)), self.timeout)
        except (OSError, smtplib.SMTPException) as exc:
            raise NotifyError(f"SMTP-Verbindung zu {cfg['host']} fehlgeschlagen: {redact(exc)}") from exc
        try:
            if security == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            if cfg.get("username"):
                smtp.login(cfg["username"], password)
            smtp.send_message(mail)
        except (OSError, smtplib.SMTPException) as exc:
            raise NotifyError(f"E-Mail konnte nicht gesendet werden ({cfg['host']}): {redact(exc)}") from exc
        finally:
            try:
                smtp.quit()
            except (OSError, smtplib.SMTPException):
                pass


class SlackChannel:
    """Slack Incoming Webhook: POST mit `{"text": …}`; Antwort ist der Klartext `ok`, deshalb `as_bytes`."""

    name = "slack"

    def __init__(self, cfg: dict, client: HttpClient):
        self.cfg = cfg
        self.client = client

    def describe(self) -> str:
        return f"Slack-Webhook aus {self.cfg.get('webhookUrlEnvironmentVariable')}"

    def send(self, message: Message) -> None:
        url = read_env_secret(self.cfg.get("webhookUrlEnvironmentVariable"), "Slack-Webhook")
        if not url.startswith("https://"):
            raise ConfigError("Slack-Webhook: die Adresse muss mit https:// beginnen.")
        try:
            self.client.request_json("POST", url, json_body={"text": f"*{message.subject}*\n{message.text}"}, as_bytes=True)
        except ToolError as exc:
            raise NotifyError(f"Slack-Webhook abgelehnt: {redact(exc)}") from exc


class WebhookChannel:
    """Generischer Webhook: POST des JSON aus `Message.payload`; mit Signaturschlüssel kommt `X-Ratings-Signature`
    (`sha256=<HMAC über den Body wie gesendet>`), damit der Empfänger die Herkunft prüfen kann."""

    name = "webhook"

    def __init__(self, cfg: dict, client: HttpClient):
        self.cfg = cfg
        self.client = client

    def describe(self) -> str:
        return f"Webhook aus {self.cfg.get('urlEnvironmentVariable')}"

    def send(self, message: Message) -> None:
        url = read_env_secret(self.cfg.get("urlEnvironmentVariable"), "Webhook")
        if not url.startswith("https://"):
            raise ConfigError("Webhook: die Adresse muss mit https:// beginnen.")
        headers = {USER_AGENT_EVENT: "test" if message.payload.get("test") else "notify"}
        if self.cfg.get("secretEnvironmentVariable"):
            secret = read_env_secret(self.cfg["secretEnvironmentVariable"], "Webhook-Signatur")
            body = json.dumps(message.payload).encode()  # identisch mit der Serialisierung in http.request_json
            headers[SIGNATURE_HEADER] = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        try:
            self.client.request_json("POST", url, headers=headers, json_body=message.payload, as_bytes=True)
        except ToolError as exc:
            raise NotifyError(f"Webhook abgelehnt: {redact(exc)}") from exc


def build_channels(cfg: Config, transport=None, smtp_factory: SmtpFactory | None = None) -> list:
    """Alle freigeschalteten Kanäle in der Reihenfolge der Konfiguration."""
    timeout = float(cfg.settings.get("requestTimeoutSeconds", 30))
    client = HttpClient(timeout=timeout, max_retries=int(cfg.settings.get("maxRetries", 3)), transport=transport)
    channels = []
    for entry in cfg.notify.get("channels", []):
        if not entry.get("enabled"):
            continue
        if entry["type"] == "email":
            channels.append(EmailChannel(entry, smtp_factory, timeout))
        elif entry["type"] == "slack":
            channels.append(SlackChannel(entry, client))
        else:
            channels.append(WebhookChannel(entry, client))
    return channels


def report_link(cfg: Config) -> str:
    """Adresse des Berichts: `settings.reportUrl`, sonst der lokale Pfad der HTML-Datei."""
    return cfg.settings.get("reportUrl") or str(cfg.report_dir / "index.html")


def deliver(channels: list, message: Message) -> int:
    """Sendet an jeden Kanal; ein Fehler stoppt die anderen nicht. Liefert die Anzahl erfolgreicher Zustellungen."""
    delivered = 0
    for channel in channels:
        try:
            channel.send(message)
            delivered += 1
            log.info("Zugestellt: %s", channel.describe())
        except ToolError as exc:
            log.error("%s: %s", channel.describe(), redact(exc))
    return delivered


def run_notify(cfg: Config, *, dry_run: bool = False, test: bool = False, transport=None,
               smtp_factory: SmtpFactory | None = None, clock: Callable[[], str] | None = None,
               out: Callable[[str], None] = print) -> int:
    """Der ganze Schritt: Zustand laden, Vorfälle sammeln, Nachricht bauen, zustellen, Zustand schreiben.

    - `dry_run`: Nachricht nur ausgeben, nichts senden, Zustand nicht ändern.
    - `test`: Testnachricht an alle Kanäle, Datenbestand bleibt ungelesen, Zustand unverändert.
    Rückgabe 0 bei Erfolg oder nichts zu melden, 1 wenn mindestens ein Kanal fehlschlug (Zustand wird trotzdem
    fortgeschrieben, sobald ein Kanal zugestellt hat; schlagen alle fehl, bleibt er und der Lauf wird wiederholt).
    """
    notify_cfg = cfg.notify
    now = (clock or utc_now)()
    link = report_link(cfg)
    if not notify_cfg.get("enabled"):
        if test or dry_run:
            raise ConfigError("Benachrichtigung ist ausgeschaltet (notify.enabled in config/config.json).")
        log.info("Benachrichtigung aus (notify.enabled false).")
        return 0
    channels = build_channels(cfg, transport, smtp_factory)
    if test:
        if not channels:
            raise ConfigError("Kein Kanal freigeschaltet (notify.channels[].enabled).")
        delivered = deliver(channels, test_message(notify_cfg, link, now))
        out(f"Testnachricht: {delivered} von {len(channels)} Kanälen zugestellt.")
        return 0 if delivered == len(channels) else 1
    dataset = build_dataset(cfg.data_dir, cfg.raw, topics_file=cfg.base_dir / "config" / "themen.json")
    state = load_state(cfg.data_dir)
    events = collect_events(dataset, state, notify_cfg)
    if not events:
        reason = "erster Lauf, Stand gemerkt" if not state.get("lastRunAt") else "keine neuen Vorfälle"
        log.info("Nichts zu melden (%s).", reason)
        if not dry_run:
            write_json(cfg.data_dir / STATE_FILE, next_state(state, dataset, now, sent=False))
        else:
            out(f"Probelauf: nichts zu melden ({reason}).")
        return 0
    message = compose(events, dataset, notify_cfg, link, now)
    if dry_run:
        out(f"Probelauf: {len(events)} Vorfälle, Betreff: {message.subject}\n\n{message.text}")
        out("Kanäle: " + (", ".join(channel.describe() for channel in channels) or "keiner freigeschaltet") + " (nichts gesendet)")
        return 0
    if not channels:
        log.warning("%d Vorfälle, aber kein Kanal freigeschaltet (notify.channels[].enabled); Stand wird gemerkt.", len(events))
        write_json(cfg.data_dir / STATE_FILE, next_state(state, dataset, now, sent=False))
        return 0
    delivered = deliver(channels, message)
    if delivered:
        write_json(cfg.data_dir / STATE_FILE, next_state(state, dataset, now, sent=True))
    else:
        log.error("Kein Kanal hat zugestellt; der Stand bleibt, der nächste Lauf meldet erneut.")
    out(f"Benachrichtigung: {len(events)} Vorfälle, {delivered} von {len(channels)} Kanälen zugestellt.")
    return 0 if delivered == len(channels) else 1
