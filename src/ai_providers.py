"""KI-Anbieter: ein Client für OpenAI, Google Gemini, Anthropic Claude, Perplexity, xAI Grok und lokal (Ollama, LM Studio, llama.cpp u. a.).

Alle sechs nehmen eine Systemanweisung und einen Nutzertext an und liefern Text zurück; nur das Anfrageformat
unterscheidet sich. Drei Formate reichen (`PROVIDERS`):

- `responses`  OpenAI Responses API (`POST /v1/responses`, Felder `instructions`, `input`, `max_output_tokens`;
               Antwort `output[].content[].text`, Verbrauch `usage.input_tokens`/`output_tokens`). xAI und
               Perplexity (Agent API) verwenden dieselbe Form.
- `chat`       Chat Completions (`messages`, Antwort `choices[0].message.content`, Verbrauch `usage.prompt_tokens`/
               `completion_tokens`); Gemini über seinen OpenAI-kompatiblen Endpunkt, ebenso der Anbieter `local`
               (lokal, Vorgabe Ollama: `http://127.0.0.1:11434/v1/chat/completions`, kein Schlüssel, kein Preis). LM Studio,
               llama.cpp, vLLM u. a. sprechen dasselbe Format und laufen über denselben Anbieter mit eigener `url`.
- `anthropic`  Messages API (`POST /v1/messages`, Header `x-api-key` und `anthropic-version`, Felder `system`,
               `messages`, `max_tokens`; Antwort `content[].text`, Verbrauch `usage.input_tokens`/`output_tokens`).

Geprüft gegen die Anbieter-Dokumentation am 24.10.2026 (OpenAI developers.openai.com, Gemini ai.google.dev,
Anthropic platform.claude.com, Perplexity docs.perplexity.ai, xAI docs.x.ai). Perplexity hat Chat Completions im
September 2026 abgeschaltet, deshalb die Agent API. Gegen echte Schlüssel ist noch nichts gelaufen (siehe TODO.md). Ollama: OpenAI-kompatible Schnittstelle laut
docs.ollama.com/api/openai-compatibility (25.10.2026), gegen eine laufende Installation noch nicht geprüft.

HTTP nur über `http.HttpClient` (Retries, Backoff, Zähler). Der Schlüssel steht nur im Header und nie in URLs oder
Fehlermeldungen; `security.redact` kennt die Schlüsselformate.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .errors import ApiError, ToolError
from .http import HttpClient
from .storage import read_versioned, write_json

log = logging.getLogger("arr.ai")

# Tokens je Anfrage für die Ausgabe (bei Reasoning-Modellen zählen die Denk-Tokens mit). Großzügig, damit kein
# Stimmungs-Stapel abgeschnitten wird; berechnet wird nur, was das Modell tatsächlich erzeugt.
MAX_OUTPUT_TOKENS = 80000



@dataclass(frozen=True)
class ModelInfo:
    """Ein unterstütztes Modell eines Anbieters mit Listenpreis (US-Dollar je Million Tokens) und kurzer Einordnung."""

    ident: str              # Modellname, wie er in `ai.providers[].model` steht
    input_per_million: float
    output_per_million: float
    note: str               # Einordnung für die Auswahl, z. B. „günstig, Standard“


# Unterstützte Modelle je Anbieter mit Listenpreisen, Stand 24.10.2026, aus Anbieterseiten (xAI, Google, Perplexity-Changelog)
# und Preisübersichten (OpenAI, Anthropic; dort ohne offizielle Preisseite in den Quellen). Das erste Modell je Anbieter
# ist die Vorgabe (`config.AI_DEFAULT_MODELS`). Jedes Modell, das denselben Endpunkt spricht, funktioniert auch ohne
# Eintrag hier; dann fehlt nur der Preis. Preise in config.json (`priceInputPerMillion`, `priceOutputPerMillion`) haben
# Vorrang. Cache-Rabatte, Batch-Preise und Langkontext-Aufschläge bleiben unberücksichtigt; Gemini 3.8 Flash ist ein
# Einführungspreis bis 31.12.2026 (danach 1,50/7,50), OpenAI hat Luna im Oktober 2026 halbiert.
AI_MODELS: dict[str, tuple[ModelInfo, ...]] = {
    "openai": (ModelInfo("gpt-6-luna", 0.10, 0.50, "günstig, Vorgabe; Reasoning-Modell"),
               ModelInfo("gpt-6.1-sol", 2.00, 10.00, "Mittelklasse"),
               ModelInfo("gpt-6-astra", 10.00, 50.00, "Spitzenmodell, teuer"),
               ModelInfo("gpt-5.6-terra", 2.00, 12.00, "Vorgänger-Mittelklasse"),
               ModelInfo("gpt-5.6-luna", 0.20, 1.20, "Vorgänger, günstig")),
    "anthropic": (ModelInfo("claude-sonnet-5-5", 2.00, 10.00, "Mittelklasse, Vorgabe"),
                  ModelInfo("claude-haiku-5-5", 0.10, 0.50, "günstig, schnell (bis 100k Tokens je Anfrage)"),
                  ModelInfo("claude-opus-5-5", 4.00, 20.00, "stark, teurer"),
                  ModelInfo("claude-fable-5-1", 10.00, 50.00, "Spitzenmodell, teuer")),
    "gemini": (ModelInfo("gemini-3.8-flash", 0.75, 3.75, "Vorgabe; Einführungspreis bis 31.12.2026"),
               ModelInfo("gemini-3.5-flash-lite", 0.30, 2.50, "günstig, einfacher"),
               ModelInfo("gemini-3.1-pro", 2.00, 12.00, "stark, teurer")),
    "perplexity": (ModelInfo("openai/gpt-5.6-terra", 2.00, 12.00, "Vorgabe; OpenAI-Modell über Perplexity"),
                   ModelInfo("anthropic/claude-sonnet-5-5", 2.00, 10.00, "Anthropic-Modell über Perplexity"),
                   ModelInfo("perplexity/sonar", 0.25, 2.50, "eigenes Perplexity-Modell, günstig")),
    "xai": (ModelInfo("grok-4.7", 2.00, 6.00, "einziges öffentliches API-Modell, Vorgabe"),),
    # Lokal, kostenlos. Namen aus der Ollama-Bibliothek (ollama.com/library, 25.10.2026); RAM-Angabe ist der Bedarf des Modells
    # in der Standardquantisierung. Empfehlung nach Erfahrung mit strengem JSON und deutschem Text, nicht gemessen.
    "local": (ModelInfo("llama3.1:8b", 0.0, 0.0, "Vorgabe; ab 8 GB RAM, zuverlässiges JSON, Deutsch ordentlich"),
              ModelInfo("gemma3:12b", 0.0, 0.0, "besseres Deutsch, ab 12 GB RAM"),
              ModelInfo("qwen3:14b", 0.0, 0.0, "stärkste Zusammenfassungen, ab 16 GB RAM, langsamer"),
              ModelInfo("mistral-small3.2", 0.0, 0.0, "gute Mitte, ab 16 GB RAM"),
              ModelInfo("llama3.2:3b", 0.0, 0.0, "klein und schnell, knappere Texte; ab 4 GB RAM")),
}
AI_PRICES_DATE = "24.10.2026"


def model_info(provider: str, model: str) -> ModelInfo | None:
    """Katalogeintrag eines Modells oder None, wenn es nicht in `AI_MODELS` steht (funktioniert trotzdem, ohne Preis)."""
    return next((info for info in AI_MODELS.get(provider, ()) if info.ident == model), None)
# Ziel-Name im Verbrauchsbuch für Freitextfragen (ki.py ask, Fragedienst); Analysen laufen unter dem App-Namen
QUESTIONS_TARGET = "Freitextfragen"


@dataclass(frozen=True)
class Price:
    """Preis eines Modells in US-Dollar je Million Tokens; `source` sagt, woher er stammt (config oder Liste)."""

    input_per_million: float
    output_per_million: float
    source: str

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_per_million + output_tokens * self.output_per_million) / 1_000_000


def price_for(provider_cfg: dict | None, provider: str, model: str) -> Price | None:
    """Preis aus der Anbieter-Konfiguration (Vorrang) oder der eingebauten Liste; None, wenn beides fehlt."""
    cfg = provider_cfg or {}
    if cfg.get("priceInputPerMillion") is not None and cfg.get("priceOutputPerMillion") is not None:
        return Price(float(cfg["priceInputPerMillion"]), float(cfg["priceOutputPerMillion"]), "config.json")
    if provider in PROVIDERS and PROVIDERS[provider].local:
        return Price(0.0, 0.0, "lokal, kostenlos")   # auch für Modelle, die nicht im Katalog stehen
    listed = model_info(provider, model)
    return Price(listed.input_per_million, listed.output_per_million, f"Preisliste {AI_PRICES_DATE}") if listed else None


def fmt_usd(value: float | None) -> str:
    """Betrag in Dollar mit vier Nachkommastellen und deutschem Komma; None → „unbekannt“."""
    if value is None:
        return "unbekannt"
    return f"{value:,.4f} $".replace(",", "_").replace(".", ",").replace("_", ".")


@dataclass(frozen=True)
class Provider:
    """Beschreibung eines Anbieters: Name, Endpunkt, Anfrageformat, Art der Authentifizierung."""

    name: str
    url: str
    kind: str       # responses | chat | anthropic
    label: str      # Anzeige in Bericht und Log
    local: bool = False  # läuft auf dem eigenen Rechner: kein Schlüssel nötig, http zu 127.0.0.1 erlaubt, Kosten 0


PROVIDERS: dict[str, Provider] = {
    "openai": Provider("openai", "https://api.openai.com/v1/responses", "responses", "OpenAI"),
    "gemini": Provider("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "chat",
                       "Google Gemini"),
    "anthropic": Provider("anthropic", "https://api.anthropic.com/v1/messages", "anthropic", "Anthropic Claude"),
    "perplexity": Provider("perplexity", "https://api.perplexity.ai/v1/agent", "responses", "Perplexity"),
    "xai": Provider("xai", "https://api.x.ai/v1/responses", "responses", "xAI Grok"),
    "local": Provider("local", "http://127.0.0.1:11434/v1/chat/completions", "chat", "Lokales Modell", local=True),
}
ANTHROPIC_VERSION = "2023-06-01"


class AiBudgetError(ToolError):
    """Das Monats-Token-Limit aus der Konfiguration ist erreicht; es wird keine Anfrage mehr gesendet."""


class AiAnswerError(ApiError):
    """Die Antwort des Anbieters war kein verwertbares JSON, abgeschnitten oder hatte nicht die erwartete Form.
    `usage` trägt den Verbrauch, wenn der Anbieter ihn trotzdem gemeldet hat (abgeschnittene Antworten kosten)."""

    def __init__(self, message: str, usage: "Usage | None" = None):
        super().__init__(message)
        self.usage = usage


@dataclass
class Usage:
    """Verbrauch einer Anfrage in Tokens."""

    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None   # geschätzte Kosten in Dollar; None, wenn kein Preis bekannt ist

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


USAGE_SCHEMA = 2  # 2: costUsd, unpricedRequests und byTarget (je Kasse/App); Dateien der Version 1 werden ergänzt


def _usage_entry() -> dict:
    return {"requests": 0, "inputTokens": 0, "outputTokens": 0, "costUsd": 0.0, "unpricedRequests": 0}


def _add_usage(entry: dict, usage: Usage) -> None:
    """Zählt eine Anfrage auf einen Eintrag (Monat, Modell oder Ziel); fehlende Felder alter Dateien werden ergänzt."""
    for key, value in _usage_entry().items():
        entry.setdefault(key, value)
    entry["requests"] += 1
    entry["inputTokens"] += usage.input_tokens
    entry["outputTokens"] += usage.output_tokens
    if usage.cost_usd is None:
        entry["unpricedRequests"] += 1
    else:
        entry["costUsd"] = round(entry["costUsd"] + usage.cost_usd, 6)


class UsageLedger:
    """Verbrauch in `data/ai-usage.json`: Anfragen, Tokens und geschätzte Kosten je Monat, Anbieter/Modell und Ziel
    (Kasse bzw. App, oder `QUESTIONS_TARGET`). Dient der Kostenbremse (`monthlyTokenLimit`) und der Anzeige in
    `ki.py usage`, am Ende eines KI-Laufs und im Bericht.

    Kosten werden beim Eintragen mit dem damals gültigen Preis (`Price`) berechnet und als Dollar gespeichert; ohne
    bekannten Preis zählt `unpricedRequests` hoch, die Summe bleibt dann eine Untergrenze. `run` hält zusätzlich die
    Summen des laufenden Prozesses je Ziel (nur im Speicher) für die Ausgabe am Ende eines Laufs."""

    def __init__(self, path: Path, limit: int, clock: Callable[[], datetime] | None = None):
        self.path, self.limit = path, limit
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.doc = read_versioned(path, USAGE_SCHEMA, lambda: {"schemaVersion": USAGE_SCHEMA, "months": {}})
        self.run: dict[str, dict] = {}   # Ziel → Eintrag, nur dieser Prozess

    def month(self) -> str:
        return self.clock().strftime("%Y-%m")

    def month_entry(self, month: str | None = None) -> dict:
        """Eintrag eines Monats (Standard: laufender), leer wenn noch nichts gebucht wurde."""
        return self.doc["months"].get(month or self.month()) or {}

    def used(self) -> int:
        """Bisher verbrauchte Tokens im laufenden Monat (Eingabe plus Ausgabe)."""
        entry = self.month_entry()
        return int(entry.get("inputTokens", 0)) + int(entry.get("outputTokens", 0))

    def month_cost(self) -> float:
        """Geschätzte Kosten des laufenden Monats in Dollar (Untergrenze, wenn `unpricedRequests` > 0)."""
        return float(self.month_entry().get("costUsd", 0.0))

    def run_total(self) -> dict:
        """Summe des laufenden Prozesses über alle Ziele."""
        total = _usage_entry()
        for entry in self.run.values():
            total["requests"] += entry["requests"]
            total["inputTokens"] += entry["inputTokens"]
            total["outputTokens"] += entry["outputTokens"]
            total["costUsd"] = round(total["costUsd"] + entry["costUsd"], 6)
            total["unpricedRequests"] += entry["unpricedRequests"]
        return total

    def check(self) -> None:
        """Wirft `AiBudgetError`, wenn das Monatslimit erreicht ist."""
        if self.used() >= self.limit:
            raise AiBudgetError(f"KI-Monatslimit erreicht: {self.used():,} von {self.limit:,} Tokens im Monat {self.month()}. "
                                "Erhöhen Sie ai.monthlyTokenLimit in config/config.json oder warten Sie auf den nächsten "
                                "Monat.".replace(",", "."))

    def record(self, provider: str, model: str, usage: Usage, dry_run: bool = False, target: str | None = None) -> None:
        """Verbrauch einer Anfrage festhalten (Monat, Modell, Ziel, Laufsumme) und außer im Probelauf sofort schreiben.

        - Parameter target: Kasse/App oder `QUESTIONS_TARGET`; None landet unter „(ohne Ziel)“."""
        self.doc["schemaVersion"] = USAGE_SCHEMA
        months = self.doc["months"]
        entry = months.setdefault(self.month(), {**_usage_entry(), "byModel": {}, "byTarget": {}})
        _add_usage(entry, usage)
        _add_usage(entry.setdefault("byModel", {}).setdefault(f"{provider}/{model}", _usage_entry()), usage)
        name = target or "(ohne Ziel)"
        _add_usage(entry.setdefault("byTarget", {}).setdefault(name, _usage_entry()), usage)
        _add_usage(self.run.setdefault(name, _usage_entry()), usage)
        entry["updatedAt"] = self.clock().strftime("%Y-%m-%dT%H:%M:%SZ")
        if not dry_run:
            write_json(self.path, self.doc)


class AiClient:
    """Sendet Analyseanfragen an den aktiven Anbieter und zählt den Verbrauch.

    `http` ist öffentlich, damit `Syncer.count_requests` die HTTP-Zähler je Ziel abgreifen kann (wie bei Apple/Google)."""

    def __init__(self, http: HttpClient, provider_name: str, model: str, api_key: str, ledger: UsageLedger,
                 dry_run: bool = False, price: Price | None = None, url: str | None = None,
                 label: str | None = None):
        if provider_name not in PROVIDERS:
            raise ApiError(f"Unbekannter KI-Anbieter: {provider_name}")
        self.http, self.provider, self.model = http, PROVIDERS[provider_name], model
        self.label = label or self.provider.label  # Anzeigename; beim lokalen Anbieter frei wählbar (z. B. „LM Studio“)
        self.url = url or self.provider.url  # abweichende Adresse nur beim lokalen Anbieter (config: ai.providers[].url)
        self._key, self.ledger, self.dry_run = api_key, ledger, dry_run
        self.price = price             # None: Kosten bleiben „unbekannt“
        self.target: str | None = None  # aktuelles Ziel (Kasse/App) für das Verbrauchsbuch; setzt der Aufrufer
        self.requests = 0
        self.last_usage = Usage()

    # ---- Anfrage ----
    def complete(self, system: str, user: str, max_tokens: int = MAX_OUTPUT_TOKENS) -> str:
        """Eine Anfrage: Systemanweisung plus Nutzertext, Antwort als Text. Prüft vorher das Monatslimit."""
        self.ledger.check()
        kind = self.provider.kind
        if kind == "anthropic":
            headers = {"x-api-key": self._key, "anthropic-version": ANTHROPIC_VERSION}
            body = {"model": self.model, "max_tokens": max_tokens, "system": system,
                    "messages": [{"role": "user", "content": user}]}
        elif kind == "chat":
            headers = {"Authorization": f"Bearer {self._key}"} if self._key else {}  # lokale Server brauchen keinen Schlüssel
            body = {"model": self.model, "messages": [{"role": "system", "content": system},
                                                      {"role": "user", "content": user}],
                    "max_tokens": max_tokens}
        else:
            headers = {"Authorization": f"Bearer {self._key}"}
            body = {"model": self.model, "instructions": system, "input": user, "max_output_tokens": max_tokens}
        data = self.http.request_json("POST", self.url, headers=headers, json_body=body)
        try:
            text, usage = parse_answer(kind, data)
        except AiAnswerError as exc:
            if exc.usage is not None:  # abgeschnittene Antwort: der Anbieter berechnet sie trotzdem
                self._book(exc.usage)
            raise
        self._book(usage)
        return text

    def _book(self, usage: Usage) -> None:
        """Kosten schätzen und die Anfrage im Verbrauchsbuch unter dem aktuellen Ziel verbuchen."""
        if self.price is not None:
            usage.cost_usd = self.price.cost(usage.input_tokens, usage.output_tokens)
        self.requests += 1
        self.last_usage = usage
        self.ledger.record(self.provider.name, self.model, usage, self.dry_run, self.target)
        log.debug("KI-Anfrage %s/%s: %d Tokens rein, %d raus, %s", self.provider.name, self.model,
                  usage.input_tokens, usage.output_tokens, fmt_usd(usage.cost_usd))

    def complete_json(self, system: str, user: str, max_tokens: int = MAX_OUTPUT_TOKENS) -> Any:
        """Wie `complete`, erwartet aber JSON (auch in ```-Zäunen) und liefert das geparste Objekt."""
        text = self.complete(system, user, max_tokens)
        return extract_json(text)


# ---- Antworten lesen ----
def parse_answer(kind: str, data: Any) -> tuple[str, Usage]:
    """Text und Verbrauch aus der Antwort je Format; unerwartete Formen → `AiAnswerError`."""
    if not isinstance(data, dict):
        raise AiAnswerError("KI-Antwort ist kein JSON-Objekt.")
    usage_raw = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    try:
        if kind == "anthropic":
            text = "".join(part.get("text", "") for part in data.get("content", []) if part.get("type") == "text")
            usage = Usage(int(usage_raw.get("input_tokens", 0)), int(usage_raw.get("output_tokens", 0)))
            truncated = data.get("stop_reason") == "max_tokens"
        elif kind == "chat":
            text = data["choices"][0]["message"]["content"] or ""
            usage = Usage(int(usage_raw.get("prompt_tokens", 0)), int(usage_raw.get("completion_tokens", 0)))
            truncated = data["choices"][0].get("finish_reason") == "length"
        else:
            parts = []
            for item in data.get("output", []):
                if item.get("type") == "message":
                    parts += [part.get("text", "") for part in item.get("content", []) if part.get("type") == "output_text"]
            text = "".join(parts)
            usage = Usage(int(usage_raw.get("input_tokens", 0)), int(usage_raw.get("output_tokens", 0)))
            details = data.get("incomplete_details") if isinstance(data.get("incomplete_details"), dict) else {}
            truncated = data.get("status") == "incomplete" and details.get("reason", "max_output_tokens") == "max_output_tokens"
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AiAnswerError(f"KI-Antwort hat nicht die erwartete Form ({type(exc).__name__}).") from exc
    if truncated:
        raise AiAnswerError(f"KI-Antwort wurde abgeschnitten (Ausgabelimit {MAX_OUTPUT_TOKENS:,} Tokens erreicht, "
                            f"{usage.output_tokens:,} Tokens erzeugt). Weniger Rezensionen je Anfrage "
                            "(ai.maxReviewsPerRequest) oder ein anderes Modell wählen.".replace(",", "."), usage)
    if not text.strip():
        raise AiAnswerError("KI-Antwort enthält keinen Text.", usage)
    return text, usage


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


_BAD_ESCAPE = re.compile(r'\\(?!["\\/bfnrtu])')   # Backslash vor einem Zeichen, das JSON nicht als Escape kennt
_TRAILING_COMMA = re.compile(r",\s*([}\]])")


def _loads_lenient(candidate: str) -> Any:
    """`json.loads` mit zwei Nachsichten, die Sprachmodelle oft brauchen: rohe Zeilenumbrüche oder Tabulatoren in
    Strings (`strict=False`) und, als letzte Stufe, ungültige Backslash-Folgen sowie Kommas vor `}`/`]`."""
    try:
        return json.loads(candidate)
    except ValueError:
        pass
    try:
        return json.loads(candidate, strict=False)
    except ValueError:
        pass
    return json.loads(_TRAILING_COMMA.sub(r"\1", _BAD_ESCAPE.sub(r"\\\\", candidate)), strict=False)


def extract_json(text: str) -> Any:
    """JSON aus einer Modellantwort: direkt, aus einem ```-Zaun oder vom ersten `{`/`[` bis zum passenden Ende.
    Steuerzeichen in Strings, ungültige Escapes und überzählige Kommas werden toleriert (`_loads_lenient`)."""
    candidates = [text.strip()] + [match.strip() for match in _FENCE.findall(text)]
    start = min((index for index in (text.find("{"), text.find("[")) if index >= 0), default=-1)
    if start >= 0:
        end = max(text.rfind("}"), text.rfind("]"))
        if end > start:
            candidates.append(text[start:end + 1])
    for candidate in candidates:
        try:
            return _loads_lenient(candidate)
        except ValueError:
            continue
    # Die ganze Antwort ins Debug-Log (nur Datei unter data/, ohne Schlüssel), sonst lässt sich die Ursache nicht finden
    log.debug("KI-Antwort nicht lesbar (%d Zeichen): %r", len(text), text)
    raise AiAnswerError(f"KI-Antwort ist kein gültiges JSON ({len(text)} Zeichen; die ganze Antwort steht im Debug-Log unter data/logs).")
