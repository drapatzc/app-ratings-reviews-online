"""Lokaler Fragedienst: Freitextfragen aus dem geöffneten Bericht heraus (nur 127.0.0.1, nur solange er läuft).

Der Bericht ist eine statische Datei ohne Netzaufrufe. Damit man Fragen an die KI direkt dort stellen kann, läuft auf
Wunsch dieser kleine Dienst (`./ratings.sh ai-serve`, Menü „KI-Analyse“). Er bindet ausschließlich an 127.0.0.1,
nimmt `POST /ask` mit `{question, customer, app, platform, selection}` entgegen, ruft dieselbe Funktion wie die Kommandozeile
(`ai_ask.ask`), speichert die Antwort in `data/ai-questions.json` und liefert sie als JSON zurück. `GET /status` sagt
dem Bericht, dass der Dienst da ist. Entscheidung des Nutzers (24.10.2026): bewusste Ausnahme von „kein Server“ und
„keine Nachlade-Requests“, nur lokal.

Schutz: Beim Start entsteht ein Zufalls-Token in `data/ai-service.json` (Rechte 0600, mit Port und PID); `report.py`
bettet Port und Token nur in einen Bericht ein, der erzeugt wird, während der Dienst läuft, und erweitert dessen CSP um
`connect-src http://127.0.0.1:<port>`. Jede Anfrage braucht den Header `X-Ai-Token`; erlaubte Origins sind nur `null`
(Datei im Browser), `http://127.0.0.1` und `http://localhost`. Nur ein Thread, Fragen laufen nacheinander. Budget,
Belegprüfung und Feature-Schalter (`ai.features.questions`) greifen wie bei der Kommandozeile. Beim Beenden wird die
Token-Datei gelöscht.
"""
from __future__ import annotations

import json
import logging
import os
import secrets
import signal
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

from .ai_analysis import make_client
from .ai_ask import MAX_QUESTION_LEN, ask, delete_question
from .ai_providers import AiClient
from .config import Config
from .errors import ConfigError, ToolError
from .models import utc_now
from .security import redact
from .storage import read_versioned, write_json

log = logging.getLogger("arr.ai")

SERVICE_FILE = "ai-service.json"
HOST = "127.0.0.1"
MAX_BODY = 256_000  # Bytes je Anfrage; der Bericht schickt die IDs der gefilterten Rezensionen mit (bis 3000)
ALLOWED_ORIGINS = ("null", f"http://{HOST}", "http://localhost")
TOKEN_HEADER = "X-Ai-Token"
PLATFORMS = ("apple", "google", "all")


def service_path(data_dir: Path) -> Path:
    return data_dir / SERVICE_FILE


def running_service(data_dir: Path) -> dict | None:
    """Port und Token des laufenden Dienstes oder None (Datei fehlt oder der Prozess lebt nicht mehr)."""
    path = service_path(data_dir)
    if not path.is_file():
        return None
    try:
        info = read_versioned(path, 1, lambda: None)
    except ToolError:
        return None
    if not info or not isinstance(info.get("port"), int) or not info.get("token"):
        return None
    try:
        os.kill(int(info.get("pid", 0)), 0)
    except (OSError, ValueError):
        return None
    return {"port": info["port"], "token": info["token"]}


class AskServer(HTTPServer):
    """HTTP-Server mit Konfiguration, Client und Token; verarbeitet eine Anfrage nach der anderen."""

    allow_reuse_address = True

    def __init__(self, cfg: Config, port: int, transport=None, client: AiClient | None = None):
        if not cfg.ai["features"].get("questions"):
            raise ConfigError("Freitextfragen sind ausgeschaltet. In config/config.json ai.features.questions auf true setzen.")
        super().__init__((HOST, port), AskHandler)
        self.cfg, self.transport = cfg, transport
        self.client = client or make_client(cfg, transport)
        self.token = secrets.token_urlsafe(32)
        self.questions_answered = 0
        write_json(service_path(cfg.data_dir), {"schemaVersion": 1, "port": self.server_port, "token": self.token,
                                                "pid": os.getpid(), "startedAt": utc_now(),
                                                "provider": self.client.provider.name, "model": self.client.model})

    def shutdown_file(self) -> None:
        """Token-Datei entfernen (beim Beenden), damit kein alter Bericht einen toten Dienst anspricht."""
        try:
            service_path(self.cfg.data_dir).unlink()
        except OSError:
            pass


class AskHandler(BaseHTTPRequestHandler):
    """Endpunkte `GET /status`, `POST /ask`, `POST /delete`, `OPTIONS` (CORS-Vorabfrage des Browsers)."""

    server: AskServer
    server_version = "app-ratings-reviews-ai/1.0"
    sys_version = ""

    def log_message(self, fmt: str, *args: Any) -> None:  # Zugriffe ins Projekt-Log statt stderr, ohne Token
        log.debug("Fragedienst: " + redact(fmt % args))

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin == "null" or any(origin.startswith(prefix) for prefix in ALLOWED_ORIGINS[1:])

    def _send(self, status: HTTPStatus, body: dict) -> None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self._cors()
        self.end_headers()
        self.wfile.write(raw)

    def _cors(self) -> None:
        origin = self.headers.get("Origin")
        if origin is not None and self._origin_ok():
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Headers", f"Content-Type, {TOKEN_HEADER}")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Cache-Control", "no-store")

    def do_OPTIONS(self) -> None:  # noqa: N802 - Name von http.server vorgegeben
        if not self._origin_ok():
            self._send(HTTPStatus.FORBIDDEN, {"error": "Origin nicht erlaubt."})
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/status":
            self._send(HTTPStatus.NOT_FOUND, {"error": "Unbekannter Pfad."})
            return
        if not self._origin_ok() or self.headers.get(TOKEN_HEADER) != self.server.token:
            self._send(HTTPStatus.FORBIDDEN, {"error": "Token oder Origin nicht erlaubt."})
            return
        client = self.server.client
        self._send(HTTPStatus.OK, {"ok": True, "provider": client.provider.name, "model": client.model,
                                   "answered": self.server.questions_answered,
                                   "usedTokens": client.ledger.used(), "monthlyTokenLimit": client.ledger.limit})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in ("/ask", "/delete"):
            self._send(HTTPStatus.NOT_FOUND, {"error": "Unbekannter Pfad."})
            return
        if not self._origin_ok() or self.headers.get(TOKEN_HEADER) != self.server.token:
            self._send(HTTPStatus.FORBIDDEN, {"error": "Token oder Origin nicht erlaubt."})
            return
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            self._send(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "Content-Type muss application/json sein."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if not 0 < length <= MAX_BODY:
            self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": f"Anfrage fehlt oder ist größer als {MAX_BODY} Bytes."})
            return
        try:
            body = json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._send(HTTPStatus.BAD_REQUEST, {"error": "Anfrage ist kein gültiges JSON."})
            return
        if not isinstance(body, dict):
            self._send(HTTPStatus.BAD_REQUEST, {"error": "Anfrage muss ein JSON-Objekt sein."})
            return
        if self.path == "/delete":  # eine gespeicherte Frage entfernen (Zeitstempel plus Fragetext als Schlüssel)
            removed = delete_question(self.server.cfg.data_dir, str(body.get("askedAt") or ""), str(body.get("question") or "") or None)
            self._send(HTTPStatus.OK if removed else HTTPStatus.NOT_FOUND, {"ok": bool(removed), "removed": removed})
            return
        question = str(body.get("question") or "")[:MAX_QUESTION_LEN + 1]
        customer = _ident(body.get("customer"))
        app = _ident(body.get("app"))
        platform = body.get("platform") if body.get("platform") in PLATFORMS else None
        selection = body.get("selection") if isinstance(body.get("selection"), dict) else None
        try:
            entry = ask(self.server.cfg, question, customer, app, platform, self.server.transport, save=True,
                        client=self.server.client, selection=selection)
        except ToolError as exc:
            self._send(HTTPStatus.BAD_REQUEST, {"error": redact(exc)})
            return
        except Exception as exc:  # noqa: BLE001 - der Dienst darf wegen einer Frage nicht sterben
            log.error("Fragedienst: %s", redact(exc))
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Unerwarteter Fehler, siehe Protokoll."})
            return
        self.server.questions_answered += 1
        self._send(HTTPStatus.OK, {"ok": True, "entry": entry})


def _ident(value: Any) -> str | None:
    """Kunden- oder App-ID aus der Anfrage: nur erlaubte Zeichen, sonst None (alle)."""
    text = str(value or "").strip()
    return text if text and all(char.isalnum() or char in "._-" for char in text) and len(text) <= 100 else None


def serve(cfg: Config, port: int, transport=None, client: AiClient | None = None, on_ready=None) -> AskServer:
    """Startet den Dienst und blockiert bis Strg+C; `on_ready(server)` wird nach dem Binden gerufen (Tests)."""
    server = AskServer(cfg, port, transport, client)

    def stop(signum, frame):  # SIGTERM (z. B. aus dem Menü) wie Strg+C behandeln, damit die Token-Datei verschwindet
        raise KeyboardInterrupt
    try:
        signal.signal(signal.SIGTERM, stop)
    except (ValueError, OSError):
        pass  # nicht im Hauptthread (Tests): dann nur Strg+C
    try:
        if on_ready:
            on_ready(server)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown_file()
        server.server_close()
    return server
