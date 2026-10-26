"""HTTP-Client auf Basis der Standardbibliothek: Retries, Backoff, Retry-After, Zählung der Aufrufe.

Nur HTTPS. Einzige Ausnahme (25.10.2026, lokale KI über Ollama): unverschlüsseltes http zu 127.0.0.1, localhost oder ::1,
weil die Daten dort den Rechner nicht verlassen (`is_local_url`)."""
from __future__ import annotations

import json
import logging
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from typing import Any, Callable

from .errors import ApiError, AuthError
from .security import redact

log = logging.getLogger("arr.http")

# Transport: (method, url, headers, body, timeout) -> (status, headers, body_bytes). Ersetzbar für Tests.
Transport = Callable[[str, str, dict, bytes | None, float], tuple[int, dict, bytes]]


LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


def is_local_url(url: str) -> bool:
    """True für http(s)-Adressen, deren Host der eigene Rechner ist (127.0.0.1, localhost, ::1)."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and (parts.hostname or "") in LOCAL_HOSTS


def is_allowed_url(url: str) -> bool:
    """https überall; http nur zum eigenen Rechner."""
    return url.startswith("https://") or (url.startswith("http://") and is_local_url(url))


class _NoAuthRedirect(urllib.request.HTTPRedirectHandler):
    """Folgt Weiterleitungen nur ohne Authorization-Header und nur auf https. Sonst bleibt die 3xx-Antwort stehen.

    urllib würde den Header sonst an das neue Ziel mitschicken, auch an einen fremden Host oder per http."""

    def redirect_request(self, req, handle, code, msg, headers, newurl):
        if req.has_header("Authorization") or not newurl.startswith("https://"):
            return None
        return super().redirect_request(req, handle, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_NoAuthRedirect)


def default_transport(method: str, url: str, headers: dict, body: bytes | None, timeout: float):
    """Echter HTTPS-Transport mit Zertifikatsprüfung (Standard-SSL-Kontext), ohne Weiterleitung mit Token."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with _OPENER.open(request, timeout=timeout) as response:  # noqa: S310 - nur https-URLs
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read() or b""
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ConnectionError(str(getattr(exc, "reason", exc))) from exc


class HttpClient:
    """Führt JSON-Anfragen mit Wiederholungen aus und zählt die tatsächlichen API-Aufrufe."""

    def __init__(self, timeout: float = 30, max_retries: int = 3, transport: Transport | None = None,
                 sleep: Callable[[float], None] | None = None):
        self.timeout = timeout
        self.max_retries = max_retries
        self.transport = transport or default_transport
        self.sleep = sleep or (lambda seconds: time.sleep(seconds))
        self.request_count = 0
        self.response_count = 0
        self.status_counts: dict[int, int] = {}
        self.retries = 0
        self.network_errors = 0
        self.bytes_in = 0

    def request_json(self, method: str, url: str, headers: dict | None = None, params: dict | None = None,
                     form: dict | None = None, as_bytes: bool = False, json_body: dict | None = None) -> Any:
        """Sendet eine Anfrage und liefert das geparste JSON (oder mit as_bytes die rohen Bytes). 401/403 → AuthError, 429/5xx → Retry."""
        if not is_allowed_url(url):
            raise ApiError("Nur HTTPS-URLs sind erlaubt (http nur zu 127.0.0.1 oder localhost).")
        if params:
            url = f"{url}{'&' if '?' in url else '?'}{urllib.parse.urlencode(params, safe='[],')}"
        hdrs = {"Accept": "application/json", "User-Agent": "app-ratings-reviews/1.0", **(headers or {})}
        body = None
        if form is not None:
            body = urllib.parse.urlencode(form).encode()
            hdrs["Content-Type"] = "application/x-www-form-urlencoded"
        elif json_body is not None:
            body = json.dumps(json_body).encode()
            hdrs["Content-Type"] = "application/json"
        attempt = 0
        while True:
            self.request_count += 1
            try:
                status, resp_headers, raw = self.transport(method, url, hdrs, body, self.timeout)
            except ConnectionError as exc:
                self.network_errors += 1
                if attempt >= self.max_retries:
                    raise ApiError(f"Netzwerkfehler: {redact(exc)}") from exc
                self._wait(attempt, None)
                attempt += 1
                continue
            self.response_count += 1
            self.bytes_in += len(raw)
            self.status_counts[status] = self.status_counts.get(status, 0) + 1
            if 200 <= status < 300:
                if as_bytes:
                    return raw
                try:
                    return json.loads(raw.decode("utf-8")) if raw else {}
                except (ValueError, UnicodeDecodeError) as exc:
                    raise ApiError("Ungültige JSON-Antwort der API.", status) from exc
            if 300 <= status < 400:
                raise ApiError(f"Weiterleitung (HTTP {status}) nicht erlaubt, Ziel: "
                               f"{redact(resp_headers.get('Location') or resp_headers.get('location') or '?')}", status)
            if status in (401, 403):
                raise AuthError(f"Zugriff verweigert (HTTP {status}). Zugangsdaten oder Berechtigungen prüfen.")
            if status == 429 or status >= 500:
                if attempt >= self.max_retries:
                    raise ApiError(f"API nicht verfügbar oder Limit erreicht (HTTP {status}) nach "
                                   f"{attempt + 1} Versuchen.", status)
                self._wait(attempt, resp_headers.get("Retry-After") or resp_headers.get("retry-after"))
                attempt += 1
                continue
            raise ApiError(f"Unerwartete API-Antwort (HTTP {status}): {redact(raw[:200].decode('utf-8', 'replace'))}",
                           status)

    def _wait(self, attempt: int, retry_after: str | None) -> None:
        """Wartet gemäß Retry-After oder exponentiell mit Zufallsanteil."""
        delay = None
        if retry_after:
            try:
                delay = float(retry_after)
            except ValueError:
                try:
                    delay = max(0.0, parsedate_to_datetime(retry_after).timestamp() - time.time())
                except (TypeError, ValueError):
                    delay = None
        if delay is None:
            delay = min(60.0, 2 ** attempt) + random.uniform(0, 1)
        self.retries += 1
        log.warning("Wiederholung in %.1f s (Versuch %d)", delay, attempt + 1)
        self.sleep(min(delay, 300.0))

    def snapshot(self) -> dict:
        """Aktuelle Zählerstände (für Differenzen pro Ziel)."""
        return {"requests": self.request_count, "responses": self.response_count, "retries": self.retries,
                "networkErrors": self.network_errors, "bytesIn": self.bytes_in,
                "ok": sum(count for code, count in self.status_counts.items() if 200 <= code < 300)}
