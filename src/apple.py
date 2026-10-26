"""Apple App Store Connect API: Kundenrezensionen, App-Store-Versionen, öffentliche Bewertungsübersicht.

Dokumentierte Endpunkte (Stand der Implementierung):
- GET /v1/apps/{id}/customerReviews          (limit max. 200, sort, filter[rating|territory], include=response)
- GET /v1/apps/{id}/appStoreVersions         (Versionen; nur Metadaten)
- GET https://itunes.apple.com/lookup        (iTunes Search API, öffentlich, ohne Authentifizierung; Feld
                                              currentVersionReleaseDate am 22.10.2026 live geprüft)
Es gibt KEINEN serverseitigen Datumsfilter; wir sortieren absteigend nach createdDate und brechen ab.
"""
from __future__ import annotations

import logging
from typing import Iterator
from urllib.parse import urlparse

from .auth import AppleTokenProvider, authorized_json
from .errors import ApiError
from .http import HttpClient
from .models import new_review, to_utc_iso

log = logging.getLogger("arr.apple")

API_HOST = "api.appstoreconnect.apple.com"
BASE = f"https://{API_HOST}"
LOOKUP_URL = "https://itunes.apple.com/lookup"
PAGE_SIZE = 200


class AppleClient:
    """Kapselt Authentifizierung, Pagination und Normalisierung für Apple."""

    def __init__(self, http: HttpClient, tokens: AppleTokenProvider):
        self.http, self.tokens = http, tokens

    def get(self, url: str, params: dict | None = None) -> dict:
        """GET gegen die App Store Connect API; nur der eigene Host, Token wird nach 401 einmal erneuert."""
        if urlparse(url).hostname != API_HOST:
            raise ApiError("Pagination-Link zeigt auf einen fremden Host und wird nicht verwendet.")
        return authorized_json(self.http, self.tokens, "GET", url, params)

    def pages(self, url: str, params: dict | None = None) -> Iterator[dict]:
        """Liefert die Antwortseiten und folgt `links.next`; `params` gelten nur für die erste Seite."""
        while url:
            body = self.get(url, params)
            params = None
            yield body
            url = (body.get("links") or {}).get("next")

    def fetch_reviews(self, customer_id: str, app_id: str, store_app_id: str, since: str | None = None,
                      until: str | None = None, countries: list[str] | None = None) -> Iterator[dict]:
        """Liefert normalisierte Rezensionen, neueste zuerst. Stoppt nach der Seite, die `since` unterschreitet."""
        params = {"limit": PAGE_SIZE, "sort": "-createdDate", "include": "response"}
        if countries:
            params["filter[territory]"] = ",".join(countries)
        for body in self.pages(f"{BASE}/v1/apps/{store_app_id}/customerReviews", params):
            included = {(i.get("type"), i.get("id")): i for i in body.get("included", []) if isinstance(i, dict)}
            reached_since = False
            for item in body.get("data", []):
                review = normalize_review(customer_id, app_id, store_app_id, item, included)
                if review is None:
                    continue
                created = review["createdAt"]
                if since and created and created < since:
                    reached_since = True
                    continue
                if until and created and created > until:
                    continue
                yield review
            if reached_since:
                break

    def fetch_versions(self, store_app_id: str) -> list[dict]:
        """Liest App-Store-Versionen. Apple liefert hier createdDate, nicht das Veröffentlichungsdatum."""
        versions = []
        for body in self.pages(f"{BASE}/v1/apps/{store_app_id}/appStoreVersions", {"limit": PAGE_SIZE}):
            for item in body.get("data", []):
                attrs = item.get("attributes") or {}
                if attrs.get("versionString"):
                    versions.append({"version": attrs["versionString"], "build": None,
                                     "releasedAt": None, "createdAt": to_utc_iso(attrs.get("createdDate")),
                                     "state": attrs.get("appStoreState"), "storePlatform": attrs.get("platform")})
        return versions

    def fetch_rating_summary(self, store_app_id: str, country: str) -> dict | None:
        """Öffentliche Gesamtbewertung je Land (iTunes Lookup). Keine Sterne-Verteilung verfügbar."""
        body = self.http.request_json("GET", LOOKUP_URL, params={"id": store_app_id, "country": country.lower()})
        results = body.get("results") or []
        if not results:
            return None
        item = results[0]
        return {"country": country.upper(), "averageRating": item.get("averageUserRating"),
                "ratingCount": item.get("userRatingCount"), "distribution": None,
                "currentVersion": item.get("version"),
                "currentVersionReleasedAt": to_utc_iso(item.get("currentVersionReleaseDate")),
                "averageRatingCurrentVersion": item.get("averageUserRatingForCurrentVersion"),
                "ratingCountCurrentVersion": item.get("userRatingCountForCurrentVersion")}


def normalize_review(customer_id: str, app_id: str, store_app_id: str, item: dict, included: dict) -> dict | None:
    """Wandelt ein customerReviews-Objekt in das einheitliche Modell um (ohne reviewerNickname)."""
    review_id = item.get("id")
    attrs = item.get("attributes") or {}
    if not review_id:
        return None
    reply = None
    ref = (((item.get("relationships") or {}).get("response") or {}).get("data")) or None
    if ref and (ref.get("type"), ref.get("id")) in included:
        r_attrs = included[(ref["type"], ref["id"])].get("attributes") or {}
        reply = {"text": r_attrs.get("responseBody"), "repliedAt": to_utc_iso(r_attrs.get("lastModifiedDate")),
                 "state": r_attrs.get("state")}
    raw = {"id": review_id, "attributes": {k: value for k, value in attrs.items() if k != "reviewerNickname"}}
    if reply:
        raw["response"] = reply
    return new_review(
        customer_id, app_id, "apple", store_app_id, review_id,
        rating=attrs.get("rating"), title=attrs.get("title"), text=attrs.get("body"),
        country=attrs.get("territory"), createdAt=to_utc_iso(attrs.get("createdDate")),
        developerReply=reply, raw=raw)
