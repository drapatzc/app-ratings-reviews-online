"""Google Play Developer API (androidpublisher v3): reviews.list und Import von Play-Console-CSV-Exporten.

Wichtige Einschränkungen (laut Google-Dokumentation):
- reviews.list liefert nur Rezensionen, die in den letzten 7 Tagen erstellt oder geändert wurden.
- Nur Rezensionen MIT Text; reine Sternebewertungen sind nicht enthalten.
- Es gibt kein Erstellungsdatum, nur `lastModified` des Nutzerkommentars.
- Kontingent: 200 GET-Anfragen pro Stunde und App.
"""
from __future__ import annotations

import csv
import io
import logging
import re
from pathlib import Path
from typing import Iterator
from urllib.parse import parse_qs, quote, urlparse

from .auth import GoogleTokenProvider
from .errors import AuthError, ToolError
from .http import HttpClient
from .models import new_review, to_utc_iso

log = logging.getLogger("arr.google")

BASE = "https://androidpublisher.googleapis.com/androidpublisher/v3/applications"
PAGE_SIZE = 100
API_WINDOW_DAYS = 7


class GoogleClient:
    """Kapselt Authentifizierung, Pagination und Normalisierung für Google Play."""

    def __init__(self, http: HttpClient, tokens: GoogleTokenProvider):
        self.http, self.tokens = http, tokens

    def fetch_reviews(self, customer_id: str, app_id: str, package_name: str) -> Iterator[dict]:
        """Liefert normalisierte Rezensionen der letzten 7 Tage (alles, was die API hergibt)."""
        url = f"{BASE}/{quote(package_name, safe='.')}/reviews"
        params: dict | None = {"maxResults": PAGE_SIZE}
        while True:
            body = self._get(url, params)
            for item in body.get("reviews", []):
                review = normalize_review(customer_id, app_id, package_name, item)
                if review:
                    yield review
            token = (body.get("tokenPagination") or {}).get("nextPageToken")
            if not token:
                break
            params = {"maxResults": PAGE_SIZE, "token": token}

    def _get(self, url: str, params: dict | None) -> dict:
        for attempt in (0, 1):
            try:
                return self.http.request_json("GET", url, {"Authorization": f"Bearer {self.tokens.token()}"}, params)
            except AuthError:
                if attempt:
                    raise
                self.tokens.invalidate()  # einmal mit frischem Token wiederholen
        raise AuthError("Authentifizierung fehlgeschlagen.")  # pragma: no cover


def split_title_text(text: str | None) -> tuple[str | None, str | None]:
    """Google liefert Titel und Text als `Titel<TAB>Text`. Ohne Tab gibt es keinen Titel."""
    if text is None:
        return None, None
    if "\t" in text:
        title, _, body = text.partition("\t")
        return (title.strip() or None), (body.strip() or None)
    return None, text.strip() or None


def _comment_time(comment: dict) -> str | None:
    stamp = comment.get("lastModified") or {}
    seconds = stamp.get("seconds")
    return to_utc_iso(int(seconds)) if seconds not in (None, "") else None


def normalize_review(customer_id: str, app_id: str, package_name: str, item: dict) -> dict | None:
    """Wandelt ein Review-Objekt in das Modell um. authorName wird nicht gespeichert (Datenminimierung)."""
    review_id = item.get("reviewId")
    comments = item.get("comments") or []
    user = next((c["userComment"] for c in comments if isinstance(c, dict) and "userComment" in c), None)
    dev = next((c["developerComment"] for c in comments if isinstance(c, dict) and "developerComment" in c), None)
    if not review_id or user is None:
        return None
    title, text = split_title_text(user.get("text"))
    meta = user.get("deviceMetadata") or {}
    device = user.get("device") or meta.get("productName")
    os_level = user.get("androidOsVersion")
    reply = None
    if dev:
        reply = {"text": dev.get("text"), "repliedAt": _comment_time(dev), "state": None}
    modified = _comment_time(user)
    raw_user = {k: v for k, v in user.items() if k != "text"}
    return new_review(
        customer_id, app_id, "google", package_name, review_id,
        rating=user.get("starRating"), title=title, text=text, language=user.get("reviewerLanguage"),
        appVersion=user.get("appVersionName"),
        buildNumber=str(user["appVersionCode"]) if user.get("appVersionCode") is not None else None,
        operatingSystem="Android", osVersion=str(os_level) if os_level is not None else None,
        device=device, createdAt=modified, updatedAt=modified, developerReply=reply,
        raw={"reviewId": review_id, "userComment": raw_user,
             **({"developerComment": {k: v for k, v in dev.items() if k != "text"}} if dev else {})})


_REVIEW_ID_RE = re.compile(r"(?:reviewId|reviewid)=([^&\s]+)")


def read_console_csv(path: Path) -> list[dict]:
    """Liest einen Play-Console-Export (reviews_<package>_<YYYYMM>.csv, meist UTF-16) als Zeilen-Dictionaries."""
    data = path.read_bytes()
    for encoding in ("utf-16", "utf-8-sig", "latin-1"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeError:
            continue
    else:  # pragma: no cover
        raise ToolError(f"CSV nicht lesbar: {path}")
    return list(csv.DictReader(io.StringIO(text)))


def normalize_csv_row(customer_id: str, app_id: str, package_name: str, row: dict) -> dict | None:
    """Wandelt eine Zeile des Play-Console-Exports um. Die Review-ID steht nur im Review-Link."""
    link = (row.get("Review Link") or "").strip()
    review_id = parse_qs(urlparse(link).query).get("reviewId", [None])[0]
    if not review_id:
        match = _REVIEW_ID_RE.search(link)
        review_id = match.group(1) if match else None
    if not review_id:
        return None
    if (row.get("Package Name") or package_name) != package_name:
        return None
    title, text = (row.get("Review Title") or None), (row.get("Review Text") or None)
    rating = row.get("Star Rating")
    reply_text = row.get("Developer Reply Text") or None
    reply = None
    if reply_text:
        reply = {"text": reply_text, "repliedAt": to_utc_iso(row.get("Developer Reply Millis Since Epoch")),
                 "state": None}
    code = row.get("App Version Code")
    return new_review(
        customer_id, app_id, "google", package_name, review_id,
        rating=int(rating) if rating and rating.isdigit() else None, title=title, text=text,
        language=row.get("Reviewer Language") or None, appVersion=row.get("App Version Name") or None,
        buildNumber=code or None, operatingSystem="Android", osVersion=None, device=row.get("Device") or None,
        createdAt=to_utc_iso(row.get("Review Submit Millis Since Epoch")),
        updatedAt=to_utc_iso(row.get("Review Last Update Millis Since Epoch")),
        developerReply=reply, raw={"source": "play-console-csv", "reviewId": review_id})
