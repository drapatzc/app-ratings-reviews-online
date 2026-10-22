"""Authentifizierung: Apple-JWT (ES256) und Google-OAuth2 per Service Account (RS256 JWT-Bearer)."""
from __future__ import annotations

import base64
import json
import time
from typing import Callable

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from .errors import ApiError, AuthError, ConfigError
from .http import HttpClient

APPLE_TOKEN_LIFETIME = 15 * 60  # Sekunden; Apple erlaubt maximal 20 Minuten
GOOGLE_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
GOOGLE_REPORTING_SCOPE = "https://www.googleapis.com/auth/playdeveloperreporting"
GOOGLE_DEFAULT_TOKEN_URI = "https://oauth2.googleapis.com/token"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _load_key(pem: str, label: str):
    try:
        return serialization.load_pem_private_key(pem.encode(), password=None)
    except (ValueError, TypeError) as exc:
        raise ConfigError(f"{label}: Privater Schlüssel ist kein gültiges PEM (ohne Passwort).") from exc


class AppleTokenProvider:
    """Erzeugt und cached JWTs für die App Store Connect API."""

    def __init__(self, issuer_id: str, key_id: str, private_key_pem: str, clock: Callable[[], float] = time.time):
        self.issuer_id, self.key_id, self.clock = issuer_id, key_id, clock
        key = _load_key(private_key_pem, "Apple-Schlüssel")
        if not isinstance(key, ec.EllipticCurvePrivateKey):
            raise ConfigError("Apple-Schlüssel: erwartet wird ein EC-Schlüssel (.p8, ES256).")
        self._key = key
        self._token: str | None = None
        self._expires = 0.0

    def token(self) -> str:
        """Liefert ein gültiges Token; erneuert es 60 s vor Ablauf."""
        now = self.clock()
        if self._token is None or now >= self._expires - 60:
            self._expires = now + APPLE_TOKEN_LIFETIME
            header = {"alg": "ES256", "kid": self.key_id, "typ": "JWT"}
            claims = {"iss": self.issuer_id, "iat": int(now), "exp": int(self._expires),
                      "aud": "appstoreconnect-v1"}
            signing = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(claims).encode())}"
            r, s = decode_dss_signature(self._key.sign(signing.encode(), ec.ECDSA(hashes.SHA256())))
            self._token = f"{signing}.{_b64(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
        return self._token

    def invalidate(self) -> None:
        """Verwirft das Token (z. B. nach HTTP 401), sodass ein neues erzeugt wird."""
        self._token = None


class GoogleTokenProvider:
    """Holt und cached OAuth2-Access-Tokens für ein Service-Account."""

    def __init__(self, service_account_json: str, http: HttpClient, clock: Callable[[], float] = time.time,
                 scope: str = GOOGLE_SCOPE):
        try:
            info = json.loads(service_account_json)
            self.email = info["client_email"]
            self._key = _load_key(info["private_key"], "Google-Schlüssel")
        except (ValueError, KeyError) as exc:
            raise ConfigError("Google Service Account: JSON ungültig (client_email/private_key fehlen).") from exc
        self.token_uri = info.get("token_uri") or GOOGLE_DEFAULT_TOKEN_URI
        self.http, self.clock, self.scope = http, clock, scope
        self._token: str | None = None
        self._expires = 0.0

    def token(self) -> str:
        """Liefert einen gültigen Access-Token (Wiederverwendung bis 60 s vor Ablauf)."""
        now = self.clock()
        if self._token and now < self._expires - 60:
            return self._token
        claims = {"iss": self.email, "scope": self.scope, "aud": self.token_uri,
                  "iat": int(now), "exp": int(now) + 3600}
        signing = f"{_b64(json.dumps({'alg': 'RS256', 'typ': 'JWT'}).encode())}.{_b64(json.dumps(claims).encode())}"
        signature = self._key.sign(signing.encode(), padding.PKCS1v15(), hashes.SHA256())
        try:
            response = self.http.request_json(
                "POST", self.token_uri,
                form={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                      "assertion": f"{signing}.{_b64(signature)}"})
        except ApiError as exc:
            if exc.status in (400, 401):
                raise AuthError("Google lehnte das Service Account ab (HTTP %s). JSON und Berechtigungen prüfen."
                                % exc.status) from exc
            raise
        token = response.get("access_token")
        if not token:
            raise AuthError("Google lieferte keinen Access-Token.")
        self._token = token
        self._expires = now + int(response.get("expires_in", 3600))
        return token

    def invalidate(self) -> None:
        """Verwirft den Access-Token (z. B. nach HTTP 401), sodass beim nächsten Aufruf ein neuer geholt wird."""
        self._token = None
