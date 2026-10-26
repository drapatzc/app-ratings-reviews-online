"""Laden und Validieren der JSON-Konfiguration; CLI-Parameter überschreiben Konfigurationswerte."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from .errors import ConfigError
from .http import is_local_url
from .security import has_api_key

SCHEMA_VERSION = 1
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PLATFORMS = ("apple", "google")
# Wettbewerber (25.10.2026): fremde Apps je Kunde aus öffentlichen Apple-Quellen (RSS-Feed, iTunes Lookup), ohne Zugang.
# Für Google gibt es keinen offiziellen öffentlichen Weg, deshalb nur Apple. Ländercodes wie im App Store (ISO 3166-1 alpha-2).
COUNTRY_RE = re.compile(r"^[A-Za-z]{2}$")
# KI-Anbieter in der Reihenfolge, in der sie die Dokumentation nennt; Endpunkte und Formate stehen in `ai_providers.py`.
AI_PROVIDERS = ("openai", "gemini", "anthropic", "perplexity", "xai", "local")
# Frühere Namen, die weiter gelesen werden (26.10.2026: „ollama“ ist jetzt ein Beispiel für den Anbieter „local“).
AI_PROVIDER_ALIASES = {"ollama": "local"}
# Lokale Anbieter (25.10.2026): kein Schlüssel nötig, eigene `url` erlaubt (nur zum eigenen Rechner oder https), Kosten 0.
# Muss zu `Provider.local` in `ai_providers.py` passen (Test prüft das).
AI_LOCAL_PROVIDERS = ("local",)
# Standardmodell je Anbieter (Stand 24.10.2026, Modellseiten der Anbieter); in der Konfiguration überschreibbar.
AI_DEFAULT_MODELS = {"openai": "gpt-6-luna", "gemini": "gemini-3.8-flash", "anthropic": "claude-sonnet-5-5",
                     "perplexity": "openai/gpt-5.6-terra", "xai": "grok-4.7", "local": "llama3.1:8b"}
# Einzelne KI-Funktionen; `questions` (Freitextfragen) ist aus, weil jede Frage Kosten verursacht.
AI_FEATURES = ("summary", "sentiment", "themes", "versions", "comparison", "replyDrafts", "measures", "questions")
DEFAULT_AI: dict[str, Any] = {
    "providers": [],              # geordnete Liste; der erste freigeschaltete Anbieter mit Schlüssel ist aktiv
    "language": "de",             # Sprache der KI-Ergebnisse: de oder en
    "maxReviewsPerRequest": 60,   # Rezensionen je Anfrage (Stimmung je Rezension), zusätzlich begrenzt durch maxCharsPerRequest
    "maxCharsPerRequest": 120_000,  # Zeichen Rezensionstext je Anfrage (ca. 30 000 Tokens); Stapel werden danach gebildet
    "maxReviewChars": 1_500,      # Zeichen je Rezension (Titel plus Text); längere werden gekürzt und markiert
    "summaryReviews": 80,         # jüngste Rezensionen, auf denen die Zusammenfassung einer App beruht
    "maxReviewsPerQuestion": 300, # jüngste Rezensionen der Auswahl, die eine Freitextfrage mitbekommt
    "monthlyTokenLimit": 2_000_000,  # harte Grenze je Kalendermonat über alle Anfragen (Eingabe + Ausgabe)
    "requestTimeoutSeconds": 180,  # Wartezeit je KI-Anfrage; Sprachmodelle brauchen für 60 Rezensionen oft 30–90 s
    "sendReviewText": True,       # False: nur Sterne, Datum, Version und Themen verlassen den Rechner (Analyse wird dürftig)
    "servicePort": 8765,          # Port des lokalen Fragedienstes (ki.py serve), nur 127.0.0.1; 0 = freier Port
    "analyzeCompetitors": True,   # auch Wettbewerber-Apps (customers[].competitors) analysieren; nie Antwortentwürfe
    "features": {name: name != "questions" for name in AI_FEATURES},
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "outputDirectory": "./data",
    "reportDirectory": "./reports",
    "backupDirectory": "./backups",   # Sicherungs-ZIPs von data/ vor jedem Lauf, der Daten ändert (src/backup.py)
    "backupKeep": 30,             # so viele neueste Sicherungen bleiben, ältere werden entfernt; 0 = alle behalten
    "defaultStartDate": None,
    "defaultEndDate": None,
    "requestTimeoutSeconds": 30,
    "maxRetries": 3,
    "incrementalSync": True,
    "overlapDays": 7,
    "minRefreshMinutes": 30,
    "fullSyncIntervalDays": 30,
    "fetchAppleVersions": True,
    "logLevel": "INFO",
    "reportUrl": None,            # Adresse des bereitgestellten Berichts für Links in Benachrichtigungen; null = lokaler Pfad
}

# Benachrichtigung nach dem Tageslauf (`notify.py`, `src/notify.py`): Kanäle und Auslöser, Geheimnisse nur aus Umgebungsvariablen.
NOTIFY_CHANNELS = ("email", "slack", "webhook")
NOTIFY_TRIGGERS = ("negativeReviews", "ampelChange", "crashJump")
NOTIFY_SMTP_SECURITY = ("starttls", "ssl", "none")
DEFAULT_NOTIFY: dict[str, Any] = {
    "enabled": False,             # ohne true endet notify.py sofort mit 0 (auch in `daily`)
    "language": "de",             # Sprache der Nachricht: de oder en
    "quietOnFirstRun": True,      # erster Lauf merkt sich nur den Stand (sonst würde jede alte 1–2-★-Rezension gemeldet)
    "maxReviewsPerMessage": 10,   # mehr neue 1–2-★-Rezensionen werden gezählt, aber nicht einzeln aufgeführt
    "triggers": {name: True for name in NOTIFY_TRIGGERS},
    "channels": [],               # Liste von {type ∈ NOTIFY_CHANNELS, enabled, …}; alle freigeschalteten werden bedient
}


@dataclass
class Config:
    """Validierte Konfiguration. `base_dir` ist der Ordner, relativ zu dem Pfade aufgelöst werden."""

    settings: dict[str, Any]
    customers: list[dict[str, Any]]
    base_dir: Path
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    ai: dict[str, Any] = field(default_factory=lambda: ai_settings(None))  # KI-Block mit Defaults, siehe `ai_settings`
    notify: dict[str, Any] = field(default_factory=lambda: notify_settings(None))  # Benachrichtigung, siehe `notify_settings`

    @property
    def data_dir(self) -> Path:
        return self._resolve(self.settings["outputDirectory"])

    @property
    def report_dir(self) -> Path:
        return self._resolve(self.settings["reportDirectory"])

    @property
    def backup_dir(self) -> Path:
        return self._resolve(self.settings["backupDirectory"])

    def _resolve(self, value: str) -> Path:
        path = Path(value).expanduser()
        return path if path.is_absolute() else (self.base_dir / path).resolve()


def ai_settings(block: Any) -> dict[str, Any]:
    """KI-Block der Konfiguration mit allen Defaults aufgefüllt (fehlt der Block, ist die KI aus)."""
    user = block if isinstance(block, dict) else {}
    merged = {**DEFAULT_AI, **user}
    merged["features"] = {**DEFAULT_AI["features"], **(user.get("features") if isinstance(user.get("features"), dict) else {})}
    merged["providers"] = [dict(provider) for provider in user.get("providers", []) if isinstance(provider, dict)]
    for provider in merged["providers"]:
        provider["name"] = AI_PROVIDER_ALIASES.get(provider.get("name"), provider.get("name"))
        provider.setdefault("enabled", False)
        provider.setdefault("model", AI_DEFAULT_MODELS.get(str(provider.get("name")), ""))
    return merged


def notify_settings(block: Any) -> dict[str, Any]:
    """Block `notify` mit allen Defaults aufgefüllt (fehlt der Block, ist die Benachrichtigung aus)."""
    user = block if isinstance(block, dict) else {}
    merged = {**DEFAULT_NOTIFY, **user}
    triggers = user.get("triggers") if isinstance(user.get("triggers"), dict) else {}
    merged["triggers"] = {**DEFAULT_NOTIFY["triggers"], **triggers}
    merged["channels"] = [dict(channel) for channel in user.get("channels", []) if isinstance(channel, dict)]
    for channel in merged["channels"]:
        channel.setdefault("enabled", False)
    return merged


def active_ai_provider(ai_cfg: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """Wählt den aktiven KI-Anbieter: der erste in der Liste, der `enabled` ist und dessen Umgebungsvariable einen
    Schlüssel enthält. Liefert (Anbieter oder None, Begründung je übergangenem Anbieter für Log und Status)."""
    notes: list[str] = []
    chosen = None
    for provider in ai_cfg.get("providers", []):
        name = provider.get("name", "?")
        if not provider.get("enabled"):
            notes.append(f"{name}: ausgeschaltet (enabled false)")
        elif name not in AI_LOCAL_PROVIDERS and not has_api_key(provider.get("apiKeyEnvironmentVariable")):
            notes.append(f"{name}: Umgebungsvariable {provider.get('apiKeyEnvironmentVariable') or '?'} ohne Schlüssel")
        elif chosen is None:
            chosen = provider
            notes.append(f"{name}: aktiv (erster freigeschalteter Anbieter mit Schlüssel)" if name not in AI_LOCAL_PROVIDERS
                         else f"{name}: aktiv (lokal, ohne Schlüssel)")
        else:
            notes.append(f"{name}: freigeschaltet, aber nicht genutzt (steht hinter {chosen['name']})")
    return chosen, notes


def parse_date(value: Any, label: str) -> date | None:
    """Parst YYYY-MM-DD; None bleibt None."""
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ConfigError(f"{label}: ungültiges Datum '{value}' (erwartet YYYY-MM-DD).") from exc


def base_dir_of(path: Path) -> Path:
    """Projektordner zu einer Konfigurationsdatei: liegt sie in `config/`, dessen Elternordner, sonst ihr Ordner."""
    parent = path.resolve().parent
    return parent.parent if parent.name == "config" else parent


def load_config(path: Path, overrides: dict[str, Any] | None = None, strict: bool = True) -> Config:
    """Lädt `path`, wendet CLI-Overrides auf `settings` an und validiert alles.

    `strict=False` (Bericht): nur lesen, Fehler in Kunden oder Zugängen stören nicht; Kunden ohne Liste sind leer."""
    if not path.is_file():
        raise ConfigError(f"Konfiguration nicht gefunden: {path}. Vorlage: config/config.example.json")
    text = path.read_text(encoding="utf-8")
    if "PRIVATE KEY-----" in text or '"private_key"' in text:
        raise ConfigError("Die Konfiguration enthält anscheinend einen privaten Schlüssel. "
                          "Schlüssel gehören in Umgebungsvariablen oder geschützte Dateien, nicht in die JSON-Konfiguration.")
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Konfiguration ist kein gültiges JSON: {exc}") from exc
    user_settings = raw.get("settings") if isinstance(raw, dict) else None
    settings = {**DEFAULT_SETTINGS, **(user_settings if isinstance(user_settings, dict) else {})}
    for key, value in (overrides or {}).items():
        if value is not None:
            settings[key] = value
    ai_cfg = ai_settings(raw.get("ai") if isinstance(raw, dict) else None)
    notify_cfg = notify_settings(raw.get("notify") if isinstance(raw, dict) else None)
    if not strict:
        customers = raw.get("customers") if isinstance(raw, dict) else None
        return Config(settings=settings, customers=customers if isinstance(customers, list) else [],
                      base_dir=base_dir_of(path), raw=raw if isinstance(raw, dict) else {}, ai=ai_cfg, notify=notify_cfg)
    errors = validate(raw, settings)
    if errors:
        raise ConfigError("Konfiguration fehlerhaft:\n  - " + "\n  - ".join(errors))
    return Config(settings=settings, customers=raw["customers"], base_dir=base_dir_of(path), raw=raw, ai=ai_cfg,
                  notify=notify_cfg)


def validate(raw: Any, settings: dict[str, Any]) -> list[str]:
    """Liefert eine Liste verständlicher Fehlermeldungen (leer = gültig)."""
    errors: list[str] = []
    if not isinstance(raw, dict):
        return ["Wurzel muss ein JSON-Objekt sein."]
    if raw.get("schemaVersion") != SCHEMA_VERSION:
        errors.append(f"schemaVersion muss {SCHEMA_VERSION} sein (gefunden: {raw.get('schemaVersion')!r}).")
    for key in ("defaultStartDate", "defaultEndDate"):
        try:
            parse_date(settings.get(key), f"settings.{key}")
        except ConfigError as exc:
            errors.append(str(exc))
    for key, minimum in (("requestTimeoutSeconds", 1), ("maxRetries", 0), ("overlapDays", 0),
                         ("minRefreshMinutes", 0), ("fullSyncIntervalDays", 0), ("backupKeep", 0)):
        value = settings.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value < minimum:
            errors.append(f"settings.{key} muss eine Zahl >= {minimum} sein.")
    if not isinstance(settings.get("backupDirectory"), str) or not settings["backupDirectory"].strip():
        errors.append("settings.backupDirectory muss ein Ordnerpfad sein (z. B. ./backups).")
    if str(settings.get("logLevel", "")).upper() not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        errors.append("settings.logLevel muss DEBUG, INFO, WARNING oder ERROR sein.")
    report_url = settings.get("reportUrl")
    if report_url is not None and not (isinstance(report_url, str) and re.match(r"https?://\S+$", report_url)):
        errors.append("settings.reportUrl muss null oder eine Adresse mit http:// oder https:// sein.")
    errors += _validate_ai(raw.get("ai"))
    errors += _validate_notify(raw.get("notify"))
    customers = raw.get("customers")
    if not isinstance(customers, list) or not customers:
        errors.append("customers muss eine nicht leere Liste sein.")
        return errors
    seen_customers: set[str] = set()
    for cindex, customer in enumerate(customers):
        where = f"customers[{cindex}]"
        if not isinstance(customer, dict):
            errors.append(f"{where} muss ein Objekt sein.")
            continue
        cid = customer.get("id")
        if not isinstance(cid, str) or not ID_RE.match(cid):
            errors.append(f"{where}.id fehlt oder enthält ungültige Zeichen (erlaubt: Buchstaben, Ziffern, . _ -).")
            continue
        where = f"Kunde '{cid}'"
        if cid in seen_customers:
            errors.append(f"{where}: id doppelt vorhanden.")
        seen_customers.add(cid)
        if not customer.get("name"):
            errors.append(f"{where}: name fehlt.")
        creds = customer.get("credentials") or {}
        apps = customer.get("apps")
        if not isinstance(apps, list) or not apps:
            errors.append(f"{where}: apps muss eine nicht leere Liste sein.")
            continue
        seen_apps: set[str] = set()
        for aindex, app in enumerate(apps):
            aid = app.get("id") if isinstance(app, dict) else None
            if not isinstance(aid, str) or not ID_RE.match(aid):
                errors.append(f"{where}.apps[{aindex}].id fehlt oder ist ungültig.")
                continue
            awhere = f"{where}, App '{aid}'"
            if aid in seen_apps:
                errors.append(f"{awhere}: id doppelt vorhanden.")
            seen_apps.add(aid)
            if not app.get("name"):
                errors.append(f"{awhere}: name fehlt.")
            audience = app.get("audience")  # optional: Größe der Zielgruppe für die Reichweite im Bericht
            if audience is not None and (not isinstance(audience, int) or isinstance(audience, bool) or audience < 1):
                errors.append(f"{awhere}: audience (Größe der Zielgruppe) muss eine ganze Zahl ab 1 oder null sein.")
            platforms = app.get("platforms")
            if not isinstance(platforms, dict) or not platforms:
                errors.append(f"{awhere}: platforms fehlt.")
                continue
            for pname, pcfg in platforms.items():
                if pname not in PLATFORMS:
                    errors.append(f"{awhere}: unbekannte Plattform '{pname}' (erlaubt: apple, google).")
                    continue
                if not isinstance(pcfg, dict):
                    errors.append(f"{awhere}.{pname} muss ein Objekt sein.")
                    continue
                if not pcfg.get("enabled", True):
                    continue
                errors += _validate_platform(awhere, pname, pcfg, creds, bool(customer.get("enabled", True)
                                                                          and app.get("enabled", True)))
        errors += _validate_competitors(where, customer.get("competitors"), seen_apps)
    return errors


def competitors(customer: dict) -> list[dict]:
    """Wettbewerber-Einträge eines Kunden (`competitors`, optional); fehlt der Block, leer."""
    block = customer.get("competitors")
    return [entry for entry in block if isinstance(entry, dict)] if isinstance(block, list) else []


def _validate_competitors(where: str, block: Any, app_ids: set[str]) -> list[str]:
    """Prüft den optionalen Block `competitors` eines Kunden: eigene IDs (auch gegenüber `apps` eindeutig), Name,
    numerische Apple-App-ID und mindestens ein Land. `google` ist nicht erlaubt, weil es keine öffentliche Quelle gibt."""
    if block is None:
        return []
    if not isinstance(block, list):
        return [f"{where}: competitors muss eine Liste sein."]
    errors: list[str] = []
    seen: set[str] = set()
    for index, entry in enumerate(block):
        cwhere = f"{where}.competitors[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{cwhere} muss ein Objekt sein.")
            continue
        ident = entry.get("id")
        if not isinstance(ident, str) or not ID_RE.match(ident):
            errors.append(f"{cwhere}.id fehlt oder ist ungültig.")
            continue
        cwhere = f"{where}, Wettbewerber '{ident}'"
        if ident in seen or ident in app_ids:
            errors.append(f"{cwhere}: id doppelt vorhanden (auch gegenüber apps muss sie eindeutig sein).")
        seen.add(ident)
        if not entry.get("name"):
            errors.append(f"{cwhere}: name fehlt.")
        audience = entry.get("audience")
        if audience is not None and (not isinstance(audience, int) or isinstance(audience, bool) or audience < 1):
            errors.append(f"{cwhere}: audience muss eine ganze Zahl ab 1 oder null sein.")
        if "google" in entry:
            errors.append(f"{cwhere}: google wird nicht unterstützt. Google bietet keine öffentliche Schnittstelle für "
                          "Rezensionen fremder Apps; Wettbewerber gibt es nur für Apple.")
        apple = entry.get("apple")
        if not isinstance(apple, dict):
            errors.append(f"{cwhere}: apple fehlt (Objekt mit appId und countries).")
            continue
        if not re.fullmatch(r"\d{5,15}", str(apple.get("appId", ""))):
            errors.append(f"{cwhere}.apple.appId fehlt oder ist keine numerische App-Store-ID.")
        countries = apple.get("countries")
        if (not isinstance(countries, list) or not countries
                or not all(isinstance(code, str) and COUNTRY_RE.match(code) for code in countries)):
            errors.append(f"{cwhere}.apple.countries muss eine nicht leere Liste zweistelliger Ländercodes sein "
                          "(z. B. [\"DE\", \"AT\", \"CH\"]); der öffentliche Feed liefert Rezensionen nur je Land.")
    return errors


def _validate_platform(where: str, pname: str, pcfg: dict, creds: dict, active: bool) -> list[str]:
    errors: list[str] = []
    if pname == "apple":
        if not re.fullmatch(r"\d{5,15}", str(pcfg.get("appId", ""))):
            errors.append(f"{where}.apple.appId fehlt oder ist keine numerische App-Store-ID.")
        if active:
            apple = creds.get("apple") or {}
            for key in ("issuerId", "keyId"):
                if not apple.get(key):
                    errors.append(f"{where}: credentials.apple.{key} fehlt.")
            if not (apple.get("privateKeyEnvironmentVariable") or apple.get("privateKeyFile")):
                errors.append(f"{where}: credentials.apple.privateKeyEnvironmentVariable (oder privateKeyFile) fehlt.")
    else:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z0-9_]+)+", str(pcfg.get("packageName", ""))):
            errors.append(f"{where}.google.packageName fehlt oder ist ungültig (z. B. com.example.app).")
        if active:
            google = creds.get("google") or {}
            if not (google.get("serviceAccountEnvironmentVariable") or google.get("serviceAccountFile")):
                errors.append(f"{where}: credentials.google.serviceAccountEnvironmentVariable "
                              "(oder serviceAccountFile) fehlt.")
    return errors


def _validate_ai(block: Any) -> list[str]:
    """Prüft den optionalen Block `ai` (KI-Analyse). Fehlt er, ist die KI aus und alles gültig."""
    if block is None:
        return []
    if not isinstance(block, dict):
        return ["ai muss ein Objekt sein."]
    errors: list[str] = []
    providers = block.get("providers", [])
    if not isinstance(providers, list):
        errors.append("ai.providers muss eine Liste sein.")
        providers = []
    seen: set[str] = set()
    for index, provider in enumerate(providers):
        where = f"ai.providers[{index}]"
        if not isinstance(provider, dict):
            errors.append(f"{where} muss ein Objekt sein.")
            continue
        name = AI_PROVIDER_ALIASES.get(provider.get("name"), provider.get("name"))
        if name not in AI_PROVIDERS:
            errors.append(f"{where}.name muss einer von {', '.join(AI_PROVIDERS)} sein (gefunden: {name!r}).")
            continue
        if name in seen:
            errors.append(f"{where}: Anbieter '{name}' steht doppelt in der Liste.")
        seen.add(name)
        if not isinstance(provider.get("enabled", False), bool):
            errors.append(f"{where}.enabled muss true oder false sein.")
        if "model" in provider and (not isinstance(provider["model"], str) or not provider["model"].strip()):
            errors.append(f"{where}.model muss ein nicht leerer Text sein.")
        env_var = provider.get("apiKeyEnvironmentVariable")
        env_ok = isinstance(env_var, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env_var)
        if name in AI_LOCAL_PROVIDERS:
            if env_var is not None and not env_ok:   # optional, aber wenn gesetzt, dann ein Variablenname
                errors.append(f"{where}.apiKeyEnvironmentVariable ist kein Variablenname (beim lokalen Anbieter optional).")
        elif not env_ok:
            errors.append(f"{where}.apiKeyEnvironmentVariable fehlt oder ist kein Variablenname (z. B. OPENAI_API_KEY).")
        label = provider.get("label")
        if label is not None and (not isinstance(label, str) or not label.strip() or len(label) > 40):
            errors.append(f"{where}.label muss ein nicht leerer Text mit höchstens 40 Zeichen sein (z. B. \"LM Studio\").")
        elif label is not None and name not in AI_LOCAL_PROVIDERS:
            errors.append(f"{where}.label ist nur beim lokalen Anbieter ({', '.join(AI_LOCAL_PROVIDERS)}) erlaubt.")
        url = provider.get("url")
        if url is not None:
            if name not in AI_LOCAL_PROVIDERS:
                errors.append(f"{where}.url ist nur beim lokalen Anbieter ({', '.join(AI_LOCAL_PROVIDERS)}) erlaubt; die "
                              "Endpunkte der Cloud-Anbieter sind fest.")
            elif not isinstance(url, str) or not (url.startswith("https://") or (url.startswith("http://") and is_local_url(url))):
                errors.append(f"{where}.url muss https sein oder http zu 127.0.0.1, localhost oder ::1 "
                              "(z. B. http://127.0.0.1:11434/v1/chat/completions).")
        for key in ("apiKey", "api_key", "key", "token"):
            if provider.get(key):
                errors.append(f"{where}.{key}: Schlüssel gehören in Umgebungsvariablen, nie in die Konfiguration.")
        prices = [provider.get(key) for key in ("priceInputPerMillion", "priceOutputPerMillion")]
        if any(price is not None for price in prices):
            if any(price is None or isinstance(price, bool) or not isinstance(price, (int, float)) or price < 0 for price in prices):
                errors.append(f"{where}: priceInputPerMillion und priceOutputPerMillion gehören zusammen und sind Zahlen >= 0 "
                              "(US-Dollar je Million Tokens).")
    if block.get("language", "de") not in ("de", "en"):
        errors.append("ai.language muss de oder en sein.")
    for key, minimum in (("maxReviewsPerRequest", 1), ("summaryReviews", 1), ("maxReviewsPerQuestion", 1),
                         ("monthlyTokenLimit", 1), ("maxCharsPerRequest", 1000), ("maxReviewChars", 100),
                         ("requestTimeoutSeconds", 1)):
        value = block.get(key, DEFAULT_AI[key])
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            errors.append(f"ai.{key} muss eine ganze Zahl >= {minimum} sein.")
    port = block.get("servicePort", DEFAULT_AI["servicePort"])
    if not isinstance(port, int) or isinstance(port, bool) or not 0 <= port <= 65535:
        errors.append("ai.servicePort muss eine ganze Zahl zwischen 0 und 65535 sein.")
    if not isinstance(block.get("sendReviewText", True), bool):
        errors.append("ai.sendReviewText muss true oder false sein.")
    if not isinstance(block.get("analyzeCompetitors", True), bool):
        errors.append("ai.analyzeCompetitors muss true oder false sein.")
    features = block.get("features", {})
    if not isinstance(features, dict):
        errors.append("ai.features muss ein Objekt sein.")
    else:
        for key, value in features.items():
            if key not in AI_FEATURES:
                errors.append(f"ai.features.{key}: unbekannte Funktion (erlaubt: {', '.join(AI_FEATURES)}).")
            elif not isinstance(value, bool):
                errors.append(f"ai.features.{key} muss true oder false sein.")
    return errors


ENV_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
# Felder, die ein Geheimnis in die Datei holen würden; sie werden abgelehnt, das Geheimnis gehört in die Umgebungsvariable.
NOTIFY_FORBIDDEN = ("password", "webhookUrl", "url", "secret", "token", "apiKey")


def _validate_notify(block: Any) -> list[str]:
    """Prüft den optionalen Block `notify` (Benachrichtigung). Fehlt er, ist sie aus und alles gültig."""
    if block is None:
        return []
    if not isinstance(block, dict):
        return ["notify muss ein Objekt sein."]
    errors: list[str] = []
    for key in ("enabled", "quietOnFirstRun"):
        if not isinstance(block.get(key, DEFAULT_NOTIFY[key]), bool):
            errors.append(f"notify.{key} muss true oder false sein.")
    if block.get("language", "de") not in ("de", "en"):
        errors.append("notify.language muss de oder en sein.")
    limit = block.get("maxReviewsPerMessage", DEFAULT_NOTIFY["maxReviewsPerMessage"])
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        errors.append("notify.maxReviewsPerMessage muss eine ganze Zahl >= 1 sein.")
    triggers = block.get("triggers", {})
    if not isinstance(triggers, dict):
        errors.append("notify.triggers muss ein Objekt sein.")
    else:
        for key, value in triggers.items():
            if key not in NOTIFY_TRIGGERS:
                errors.append(f"notify.triggers.{key}: unbekannter Auslöser (erlaubt: {', '.join(NOTIFY_TRIGGERS)}).")
            elif not isinstance(value, bool):
                errors.append(f"notify.triggers.{key} muss true oder false sein.")
    channels = block.get("channels", [])
    if not isinstance(channels, list):
        return errors + ["notify.channels muss eine Liste sein."]
    for index, channel in enumerate(channels):
        where = f"notify.channels[{index}]"
        if not isinstance(channel, dict):
            errors.append(f"{where} muss ein Objekt sein.")
            continue
        kind = channel.get("type")
        if kind not in NOTIFY_CHANNELS:
            errors.append(f"{where}.type muss einer von {', '.join(NOTIFY_CHANNELS)} sein (gefunden: {kind!r}).")
            continue
        if not isinstance(channel.get("enabled", False), bool):
            errors.append(f"{where}.enabled muss true oder false sein.")
        for key in NOTIFY_FORBIDDEN:
            if channel.get(key):
                errors.append(f"{where}.{key}: Geheimnisse gehören in Umgebungsvariablen, nie in die Konfiguration.")
        errors += _validate_channel(where, kind, channel)
    return errors


def _env_name_ok(value: Any) -> bool:
    return isinstance(value, str) and ENV_NAME_RE.fullmatch(value) is not None


def _validate_channel(where: str, kind: str, channel: dict) -> list[str]:
    """Pflichtfelder je Kanaltyp: E-Mail braucht Server und Empfänger, Slack und Webhook die Variable mit der Adresse."""
    errors: list[str] = []
    if kind == "email":
        if not isinstance(channel.get("host"), str) or not channel["host"].strip():
            errors.append(f"{where}.host (SMTP-Server) fehlt.")
        port = channel.get("port", 587)
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            errors.append(f"{where}.port muss eine ganze Zahl zwischen 1 und 65535 sein.")
        security = channel.get("security", "starttls")
        if security not in NOTIFY_SMTP_SECURITY:
            errors.append(f"{where}.security muss einer von {', '.join(NOTIFY_SMTP_SECURITY)} sein.")
        elif security == "none" and str(channel.get("host", "")).strip() not in ("127.0.0.1", "localhost", "::1"):
            errors.append(f"{where}.security none ist nur für 127.0.0.1 oder localhost erlaubt (sonst gehen Passwort und "
                          "Rezensionstexte unverschlüsselt über das Netz).")
        recipients = channel.get("to")
        if not isinstance(recipients, list) or not recipients or not all(
                isinstance(item, str) and "@" in item for item in recipients):
            errors.append(f"{where}.to muss eine nicht leere Liste von E-Mail-Adressen sein.")
        sender = channel.get("from")
        if not isinstance(sender, str) or "@" not in sender:
            errors.append(f"{where}.from (Absenderadresse) fehlt.")
        env_var = channel.get("passwordEnvironmentVariable")
        if env_var is not None and not _env_name_ok(env_var):
            errors.append(f"{where}.passwordEnvironmentVariable ist kein Variablenname (z. B. RATINGS_SMTP_PASSWORD).")
        if channel.get("username") and env_var is None:
            errors.append(f"{where}: username ohne passwordEnvironmentVariable (Passwort kommt nur aus der Umgebung).")
    elif kind == "slack":
        if not _env_name_ok(channel.get("webhookUrlEnvironmentVariable")):
            errors.append(f"{where}.webhookUrlEnvironmentVariable fehlt oder ist kein Variablenname "
                          "(z. B. RATINGS_SLACK_WEBHOOK).")
    else:
        if not _env_name_ok(channel.get("urlEnvironmentVariable")):
            errors.append(f"{where}.urlEnvironmentVariable fehlt oder ist kein Variablenname (z. B. RATINGS_WEBHOOK_URL).")
        secret_var = channel.get("secretEnvironmentVariable")
        if secret_var is not None and not _env_name_ok(secret_var):
            errors.append(f"{where}.secretEnvironmentVariable ist kein Variablenname oder null.")
    return errors
