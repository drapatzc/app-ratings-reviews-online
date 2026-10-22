"""Synchronisation: Abruf, Duplikaterkennung, Änderungshistorie, Versionen, Bewertungs-Momentaufnahmen, Zustand."""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .apple import AppleClient
from .apple_analytics import (CRASH_REPORT, SESSION_REPORT, AppleAnalytics, aggregate_crashes, aggregate_sessions,
                              replace_dates)
from .auth import GOOGLE_REPORTING_SCOPE, AppleTokenProvider, GoogleTokenProvider
from .config import Config, parse_date
from .errors import ConfigError, StorageError, ToolError
from .google import API_WINDOW_DAYS, GoogleClient, normalize_csv_row, read_console_csv
from .http import HttpClient, Transport
from .models import SCHEMA_VERSION, changed_fields, content_hash, content_state, snapshot, utc_now, validate_review
from .security import read_secret, redact
from .storage import read_versioned, run_lock, write_json
from .ui import fmt_seconds

log = logging.getLogger("arr.sync")
MAX_HISTORY_RUNS = 500


@dataclass
class Options:
    """Ausgewählte Ziele und Laufoptionen (aus CLI)."""

    customer: str | None = None
    app: str | None = None
    platform: str = "all"
    date_from: str | None = None
    date_to: str | None = None
    incremental: bool | None = None
    full_sync: bool = False
    dry_run: bool = False
    force: bool = False


@dataclass
class Result:
    """Ergebnis für ein Ziel (Kunde/App/Plattform)."""

    customer: str
    app: str
    platform: str
    app_name: str = ""
    status: str = "ok"  # ok | partial | failed | skipped | dry_run
    mode: str = ""
    api_requests: int = 0
    responses: int = 0
    ok_responses: int = 0
    retries: int = 0
    network_errors: int = 0
    bytes_in: int = 0
    duration: float = 0.0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    total: int = 0
    quality_issues: int = 0
    errors: list[str] = field(default_factory=list)
    last_successful_sync: str | None = None


# ----------------------------------------------------------------------------------------------------------
# Pfade und Zustand
# ----------------------------------------------------------------------------------------------------------

def target_dir(data_dir: Path, customer: str, app: str, platform: str) -> Path:
    """Ablageordner einer App je Plattform."""
    return data_dir / "customers" / customer / "apps" / app / platform


def empty_state() -> dict:
    return {"schemaVersion": 1, "customers": {}}


def get_target_state(state: dict, customer: str, app: str, platform: str, create: bool = False) -> dict | None:
    """Liefert den Zustandseintrag eines Ziels (optional neu angelegt)."""
    node = state["customers"]
    for key in (customer,):
        node = node.setdefault(key, {"apps": {}}) if create else node.get(key)
        if node is None:
            return None
    apps = node.setdefault("apps", {})
    app_node = apps.setdefault(app, {}) if create else apps.get(app)
    if app_node is None:
        return None
    if create:
        return app_node.setdefault(platform, {
            "lastSuccessfulSync": None, "lastFullSync": None, "lastAttempt": None, "lastError": None,
            "reviewCount": 0, "status": "never_synced", "lastApiRequests": 0, "dataGaps": []})
    return app_node.get(platform)


# ----------------------------------------------------------------------------------------------------------
# Kernlogik: Zusammenführen
# ----------------------------------------------------------------------------------------------------------

def merge_reviews(existing: dict[str, dict], incoming, history: list[dict], now: str) -> dict[str, int]:
    """Führt `incoming` in `existing` (Schlüssel = Rezensions-ID) zusammen. Idempotent.

    Neue werden ergänzt, geänderte ersetzt (alter Zustand → `history`), identische nur als gesehen markiert.
    """
    history_ids = {entry["changeId"] for entry in history}
    stats = {"new": 0, "updated": 0, "unchanged": 0, "invalid": 0}
    for review in incoming:
        key = review["id"]
        if validate_review(review):
            stats["invalid"] += 1
        old = existing.get(key)
        if old is None:
            review["firstSeenAt"] = review["lastSeenAt"] = now
            existing[key] = review
            stats["new"] += 1
            continue
        review["createdAt"] = min(filter(None, (old.get("createdAt"), review.get("createdAt"))), default=None)
        old_hash, new_hash = content_hash(old), content_hash(review)
        old["lastSeenAt"] = now
        if old_hash == new_hash:
            old["createdAt"] = review["createdAt"]
            stats["unchanged"] += 1
            continue
        change_id = hashlib.sha256(f"{key}|{old_hash}|{new_hash}".encode()).hexdigest()[:32]
        if change_id not in history_ids:
            history.append({"changeId": change_id, "id": key, "reviewId": old["reviewId"], "detectedAt": now,
                            "changedFields": changed_fields(old, review),
                            "previous": snapshot(old), "new": snapshot(review)})
            history_ids.add(change_id)
        review["firstSeenAt"], review["lastSeenAt"] = old.get("firstSeenAt") or now, now
        existing[key] = review
        stats["updated"] += 1
    return stats


def build_versions(platform: str, store_app_id: str, reviews: dict[str, dict], store_versions: list[dict],
                   previous: dict, now: str) -> dict:
    """Erzeugt versions.json: Versionen aus Store-Metadaten und aus Rezensionen, mit zugehörigen Rezensions-IDs."""
    entries: dict[tuple, dict] = {}
    for item in previous.get("versions", []):
        entries[(item["version"], item.get("build"))] = item
    for item in store_versions:
        key = (item["version"], item.get("build"))
        entry = entries.setdefault(key, {**item, "platform": platform, "firstSeenAt": now,
                                         "source": "store-api", "reviewIds": []})
        for name in ("releasedAt", "createdAt", "state", "storePlatform"):
            if item.get(name) is not None:
                entry[name] = item[name]
    ids: dict[tuple, list[str]] = {}
    for review in reviews.values():
        if review.get("appVersion") or review.get("buildNumber"):
            ids.setdefault((review.get("appVersion"), review.get("buildNumber")), []).append(review["id"])
    for key, rids in ids.items():
        entries.setdefault(key, {"version": key[0], "build": key[1], "platform": platform, "releasedAt": None,
                                 "firstSeenAt": now, "source": "reviews", "reviewIds": []})
    for key, entry in entries.items():
        entry["reviewIds"] = sorted(ids.get(key, []))
    ordered = sorted(entries.values(), key=lambda e: (str(e["version"]), str(e.get("build"))))
    return {"schemaVersion": SCHEMA_VERSION, "platform": platform, "storeAppId": store_app_id, "versions": ordered}


def derived_distribution(reviews: dict[str, dict]) -> dict:
    """Sterneverteilung aus gesammelten Rezensionen (KEINE offizielle Store-Gesamtbewertung)."""
    counts = {str(i): 0 for i in range(1, 6)}
    for review in reviews.values():
        if str(review.get("rating")) in counts:
            counts[str(review["rating"])] += 1
    total = sum(counts.values())
    average = round(sum(int(k) * v for k, v in counts.items()) / total, 3) if total else None
    return {"total": total, "average": average, "distribution": counts}


def update_ratings_history(history: dict, reviews: dict[str, dict], store_summaries: list[dict], now: str) -> bool:
    """Hängt Momentaufnahmen nur bei geänderten Werten an. Gibt True zurück, wenn etwas hinzukam."""
    snaps = history.setdefault("snapshots", [])
    changed = False

    def last(origin: str, country: str | None) -> dict | None:
        return next((s for s in reversed(snaps) if s["origin"] == origin and s.get("country") == country), None)

    derived = derived_distribution(reviews)
    prev = last("derived-from-collected-reviews", None)
    if derived["total"] and (prev is None or (prev["total"], prev["distribution"]) != (derived["total"],
                                                                                     derived["distribution"])):
        snaps.append({"capturedAt": now, "origin": "derived-from-collected-reviews", "source": "reviews.json",
                      "country": None, "appVersion": None, **derived})
        changed = True
    for summary in store_summaries:
        prev = last("store-official", summary["country"])
        values = (summary["averageRating"], summary["ratingCount"])
        if prev is None or (prev["average"], prev["total"]) != values:
            snaps.append({"capturedAt": now, "origin": "store-official", "source": "itunes-lookup",
                          "country": summary["country"], "appVersion": summary.get("currentVersion"),
                          "total": summary["ratingCount"], "average": summary["averageRating"],
                          "distribution": summary.get("distribution"),
                          "currentVersion": {"average": summary.get("averageRatingCurrentVersion"),
                                             "total": summary.get("ratingCountCurrentVersion")}})
            changed = True
    return changed


# ----------------------------------------------------------------------------------------------------------
# Orchestrierung
# ----------------------------------------------------------------------------------------------------------

class Syncer:
    """Führt einen Abruflauf über alle ausgewählten Ziele aus."""

    def __init__(self, config: Config, options: Options, transport: Transport | None = None,
                 clock: Callable[[], datetime] | None = None, sleep: Callable[[float], None] | None = None):
        self.cfg, self.opt, self.transport, self.sleep = config, options, transport, sleep
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._clients: dict[tuple, Any] = {}
        self._failed: dict[tuple, Exception] = {}
        self.last_duration = 0.0
        self.progress: Callable[[str, int, int], None] = lambda label, done, total: None

    # ---- Zielauswahl ----
    def targets(self, include_disabled: bool = False) -> list[tuple[dict, dict, str, dict]]:
        """Liste aus (Kunde, App, Plattform, Plattformkonfiguration) gemäß Konfiguration und Filtern."""
        found = []
        for customer in self.cfg.customers:
            if self.opt.customer and customer["id"] != self.opt.customer:
                continue
            if not include_disabled and not customer.get("enabled", True):
                continue
            for app in customer["apps"]:
                if self.opt.app and app["id"] != self.opt.app:
                    continue
                if not include_disabled and not app.get("enabled", True):
                    continue
                for platform, pcfg in app["platforms"].items():
                    if self.opt.platform != "all" and platform != self.opt.platform:
                        continue
                    if not include_disabled and not pcfg.get("enabled", True):
                        continue
                    found.append((customer, app, platform, pcfg))
        return found

    def run(self) -> list[Result]:
        """Verarbeitet alle Ziele. Fehler eines Ziels stoppen die anderen nicht."""
        data_dir = self.cfg.data_dir
        started = self.clock()
        t0 = time.monotonic()
        results: list[Result] = []
        targets = self.targets()
        if not targets:
            raise ConfigError("Keine passenden aktivierten Kunden/Apps/Plattformen gefunden.")
        log.info("▶ Abruf der Rezensionen")
        with run_lock(data_dir / ".lock"):
            state = read_versioned(data_dir / "state.json", 1, empty_state)
            for customer, app, platform, pcfg in targets:
                result = self.sync_target(state, customer, app, platform, pcfg)
                results.append(result)
                if not self.opt.dry_run:
                    write_json(data_dir / "state.json", state)
            if not self.opt.dry_run:
                self._append_history(data_dir, started, results)
        self.last_duration = time.monotonic() - t0
        self._log_skipped(results)
        return results

    def _append_history(self, data_dir: Path, started: datetime, results: list[Result]) -> None:
        path = data_dir / "sync-history.json"
        history = read_versioned(path, 1, lambda: {"schemaVersion": 1, "runs": []})
        finished = self.clock()
        history["runs"].append({
            "startedAt": started.strftime("%Y-%m-%dT%H:%M:%SZ"), "finishedAt": finished.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "durationSeconds": round((finished - started).total_seconds(), 1),
            "options": {"customer": self.opt.customer, "app": self.opt.app, "platform": self.opt.platform,
                        "from": self.opt.date_from, "to": self.opt.date_to, "fullSync": self.opt.full_sync},
            "results": [{"customer": r.customer, "app": r.app, "platform": r.platform, "status": r.status,
                         "mode": r.mode, "apiRequests": r.api_requests, "responses": r.responses,
                         "retries": r.retries, "durationSeconds": r.duration, "new": r.new, "updated": r.updated,
                         "unchanged": r.unchanged, "total": r.total, "errors": r.errors,
                         "lastSuccessfulSync": r.last_successful_sync} for r in results]})
        history["runs"] = history["runs"][-MAX_HISTORY_RUNS:]
        write_json(path, history)

    # ---- Clients ----
    def _client(self, customer: dict, platform: str):
        key = (customer["id"], platform)
        if key in self._failed:
            raise self._failed[key]
        if key not in self._clients:
            try:
                http = HttpClient(self.cfg.settings["requestTimeoutSeconds"], self.cfg.settings["maxRetries"],
                                  self.transport, self.sleep)
                creds = (customer.get("credentials") or {}).get(platform) or {}
                if platform == "apple":
                    pem = read_secret(creds.get("privateKeyEnvironmentVariable"), creds.get("privateKeyFile"),
                                      f"Kunde {customer['id']} Apple")
                    tokens = AppleTokenProvider(creds["issuerId"], creds["keyId"], pem)
                    self._clients[key] = AppleClient(http, tokens)
                else:
                    raw = read_secret(creds.get("serviceAccountEnvironmentVariable"), creds.get("serviceAccountFile"),
                                      f"Kunde {customer['id']} Google")
                    if not raw.startswith("{"):
                        raise ConfigError("Google Service Account: Inhalt ist kein JSON.")
                    self._clients[key] = GoogleClient(http, GoogleTokenProvider(raw, http))
                    self._clients[key].reporting_tokens = GoogleTokenProvider(raw, http, scope=GOOGLE_REPORTING_SCOPE)
            except ToolError as exc:
                self._failed[key] = exc
                raise
        return self._clients[key]

    # ---- Ein Ziel ----
    def sync_target(self, state: dict, customer: dict, app: dict, platform: str, pcfg: dict) -> Result:
        """Synchronisiert eine App auf einer Plattform (mit Zeitmessung)."""
        started = time.monotonic()
        result = self._sync_target(state, customer, app, platform, pcfg)
        result.duration = round(time.monotonic() - started, 2)
        self._log_line(app["name"], platform.capitalize(), result)
        return result

    def _sync_target(self, state: dict, customer: dict, app: dict, platform: str, pcfg: dict) -> Result:
        """Synchronisiert eine App auf einer Plattform und aktualisiert Dateien und Zustand."""
        cid, aid = customer["id"], app["id"]
        result = Result(cid, aid, platform)
        store_id = str(pcfg.get("appId") if platform == "apple" else pcfg.get("packageName"))
        log.debug("Customer: %s | App: %s | Platform: %s", customer["name"], app["name"], platform)
        tstate = get_target_state(state, cid, aid, platform, create=True)
        now_dt = self.clock()
        now = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        directory = target_dir(self.cfg.data_dir, cid, aid, platform)
        explicit_range = bool(self.opt.date_from or self.opt.date_to)
        settings = self.cfg.settings

        # Frische-Prüfung: keine API-Aufrufe, wenn der lokale Zustand aktuell genug ist.
        last_ok = tstate["lastSuccessfulSync"]
        if (not (self.opt.force or self.opt.full_sync or explicit_range) and last_ok
                and tstate["status"] == "ok"
                and now_dt - _parse(last_ok) < timedelta(minutes=settings["minRefreshMinutes"])):
            result.status, result.mode, result.total = "skipped", "fresh", tstate["reviewCount"]
            result.last_successful_sync = last_ok
            log.debug("Übersprungen: Wartefrist %s Minuten", settings["minRefreshMinutes"])
            return result

        try:
            reviews_path = directory / "reviews.json"
            reviews_doc = read_versioned(reviews_path, SCHEMA_VERSION, lambda: {
                "schemaVersion": SCHEMA_VERSION, "customerId": cid, "appId": aid, "platform": platform,
                "storeAppId": store_id, "reviews": []})
            history_doc = read_versioned(directory / "review-history.json", SCHEMA_VERSION, lambda: {
                "schemaVersion": SCHEMA_VERSION, "changes": []})
            versions_doc = read_versioned(directory / "versions.json", SCHEMA_VERSION, lambda: {
                "schemaVersion": SCHEMA_VERSION, "versions": []})
            ratings_doc = read_versioned(directory / "ratings-history.json", SCHEMA_VERSION, lambda: {
                "schemaVersion": SCHEMA_VERSION, "platform": platform, "storeAppId": store_id, "snapshots": []})
        except StorageError as exc:
            return self._fail(result, tstate, now, exc, "Datei beschädigt – nichts überschrieben")

        existing = {r["id"]: r for r in reviews_doc["reviews"]}
        index_size = len(existing)
        log.debug("Existing reviews: %d", index_size)

        # Modus und Zeitfenster bestimmen
        since, until = self._window(tstate, platform, explicit_range, now_dt, settings)
        full = since is None or self.opt.full_sync
        result.mode = "range" if explicit_range else ("full" if full else "incremental")

        stats = {"new": 0, "updated": 0, "unchanged": 0, "invalid": 0}
        store_versions: list[dict] = []
        summaries: list[dict] = []
        error: Exception | None = None
        client = None
        before = None
        try:
            client = self._client(customer, platform)
            before = client.http.snapshot()
            if platform == "apple":
                iterator = client.fetch_reviews(cid, aid, store_id, since, until, pcfg.get("countries") or None)
            else:
                iterator = client.fetch_reviews(cid, aid, store_id)
            fetched = []
            try:
                for review in iterator:
                    if _language_filtered(review, pcfg):
                        continue
                    fetched.append(review)
            except ToolError as exc:  # mitten im Abruf: bisher Geholtes trotzdem sichern
                error = exc
            part = merge_reviews(existing, fetched, history_doc["changes"], now)
            stats.update(part)
            if error is None and platform == "apple":
                try:
                    if settings["fetchAppleVersions"] and (full or not versions_doc["versions"]):
                        store_versions = client.fetch_versions(store_id)
                    for country in pcfg.get("ratingCountries") or []:
                        summary = client.fetch_rating_summary(store_id, country)
                        if summary:
                            summaries.append(summary)
                except ToolError as exc:  # Nebenabrufe dürfen den Hauptabruf nicht entwerten
                    result.errors.append(f"Nebenabruf (Versionen/Bewertungsübersicht): {redact(exc)}")
        except ToolError as exc:
            error = error or exc
        finally:
            if client is not None and before is not None:
                after = client.http.snapshot()
                result.api_requests = after["requests"] - before["requests"]
                result.responses = after["responses"] - before["responses"]
                result.ok_responses = after["ok"] - before["ok"]
                result.retries = after["retries"] - before["retries"]
                result.network_errors = after["networkErrors"] - before["networkErrors"]
                result.bytes_in = after["bytesIn"] - before["bytesIn"]

        result.new, result.updated, result.unchanged = stats["new"], stats["updated"], stats["unchanged"]
        result.quality_issues = stats["invalid"]
        result.total = len(existing)
        if stats["invalid"]:
            log.warning("Datenqualität: %d Rezensionen mit Auffälligkeiten", stats["invalid"])

        if self.opt.dry_run:
            result.status = "dry_run" if error is None else "failed"
            if error:
                result.errors.append(redact(error))
            self._log_result(result)
            return result

        try:
            changed = stats["new"] or stats["updated"]
            if changed:
                reviews_doc["reviews"] = sorted(existing.values(), key=lambda r: (r.get("createdAt") or "", r["id"]),
                                                reverse=True)
                write_json(reviews_path, reviews_doc)
                write_json(directory / "review-history.json", history_doc)
            versions = build_versions(platform, store_id, existing, store_versions, versions_doc, now)
            if versions["versions"] != versions_doc["versions"]:
                write_json(directory / "versions.json", versions)
            if update_ratings_history(ratings_doc, existing, summaries, now):
                write_json(directory / "ratings-history.json", ratings_doc)
        except (StorageError, OSError) as exc:
            error = error or StorageError(f"Schreiben fehlgeschlagen: {exc}")

        tstate["lastAttempt"] = now
        tstate["reviewCount"] = len(existing)
        tstate["lastApiRequests"] = result.api_requests
        if error is not None:
            result.errors.append(redact(error))
            result.status = "partial" if (stats["new"] or stats["updated"]) else "failed"
            tstate["status"], tstate["lastError"] = result.status, redact(error)
        else:
            result.status = "ok"
            tstate["lastError"] = None
            if explicit_range:
                tstate.setdefault("status", "ok")
                if tstate["status"] == "never_synced":
                    tstate["status"] = "partial"
            else:
                self._record_gap(tstate, platform, last_ok, now)
                tstate["status"] = "ok"
                tstate["lastSuccessfulSync"] = now  # Startzeit des Laufs, erst nach vollständigem Erfolg
                if full and platform == "apple":
                    tstate["lastFullSync"] = now
                elif platform == "google":
                    tstate["lastFullSync"] = now
        result.last_successful_sync = tstate["lastSuccessfulSync"]
        self._log_result(result)
        return result

    # ---- Hilfen ----
    def _window(self, tstate: dict, platform: str, explicit: bool, now: datetime, settings: dict):
        """Bestimmt (since, until) als UTC-ISO-Strings; since=None bedeutet: alles abrufen."""
        start_default = parse_date(settings.get("defaultStartDate"), "defaultStartDate")
        end_default = parse_date(settings.get("defaultEndDate"), "defaultEndDate")
        d_from = parse_date(self.opt.date_from, "--from") or start_default
        d_to = parse_date(self.opt.date_to, "--to") or end_default
        until = f"{d_to.isoformat()}T23:59:59Z" if d_to else None
        floor = f"{d_from.isoformat()}T00:00:00Z" if d_from else None
        if explicit:
            return floor, until
        last_ok = tstate["lastSuccessfulSync"]
        incremental = settings["incrementalSync"] if self.opt.incremental is None else self.opt.incremental
        full_due = False
        if tstate.get("lastFullSync"):
            interval = settings["fullSyncIntervalDays"]
            full_due = bool(interval) and now - _parse(tstate["lastFullSync"]) > timedelta(days=interval)
        if self.opt.full_sync or not last_ok or not incremental or full_due:
            if full_due and not self.opt.full_sync:
                log.info("Periodische vollständige Synchronisation fällig")
            return floor, until
        since = (_parse(last_ok) - timedelta(days=settings["overlapDays"])).strftime("%Y-%m-%dT%H:%M:%SZ")
        return max(since, floor) if floor else since, until

    def _record_gap(self, tstate: dict, platform: str, previous: str | None, now: str) -> None:
        """Google liefert nur 7 Tage: ein größerer Abstand zwischen zwei Läufen kann Rezensionen kosten."""
        if platform == "google" and previous and _parse(now) - _parse(previous) > timedelta(days=API_WINDOW_DAYS):
            tstate.setdefault("dataGaps", []).append({"from": previous, "to": now})
            log.warning("Abstand seit letztem Lauf > %d Tage: Rezensionen dazwischen können fehlen", API_WINDOW_DAYS)

    def _fail(self, result: Result, tstate: dict, now: str, exc: Exception, note: str) -> Result:
        result.status = "failed"
        result.errors.append(redact(exc))
        tstate["lastAttempt"], tstate["status"], tstate["lastError"] = now, "failed", redact(exc)
        result.last_successful_sync = tstate["lastSuccessfulSync"]
        log.error("%s: %s", note, redact(exc))
        return result

    def _log_skipped(self, results: list[Result]) -> None:
        """Eine Sammelzeile statt einer Zeile je übersprungener App."""
        skipped = [r for r in results if r.status == "skipped"]
        if skipped:
            names = ", ".join(r.app_name or r.app for r in skipped[:4]) + (" …" if len(skipped) > 4 else "")
            log.info("↷ %d übersprungen (vor weniger als %s Min abgerufen; erzwingen mit --force): %s",
                     len(skipped), self.cfg.settings["minRefreshMinutes"], names)

    def _log_result(self, r: Result) -> None:
        """Ausführliche Zahlen nur auf DEBUG; die Ein-Zeilen-Zusammenfassung folgt in _log_line."""
        log.debug("API requests: %d | new %d | updated %d | unchanged %d | total %d", r.api_requests, r.new, r.updated,
                  r.unchanged, r.total)

    def _log_line(self, app_name: str, platform: str, r: Result, extra: str = "") -> None:
        """Eine Zeile je Ziel: Symbol, App, Plattform, Ergebnis, Anfragen, Dauer."""
        symbol = {"ok": "✔", "skipped": "↷", "dry_run": "◌", "partial": "◐", "failed": "✖"}.get(r.status, "•")
        if r.status == "skipped":
            detail = "übersprungen (Wartefrist, 0 Anfragen)"
        elif platform == "Stabilität":
            detail = (f"{r.unchanged} neue Tagesberichte · {r.total} Zeilen gesamt · {r.api_requests} Anfragen · "
                      f"{fmt_seconds(r.duration)}")
        else:
            detail = (f"{r.new} neu · {r.updated} geändert · {r.total} gesamt · {r.api_requests} Anfragen · "
                      f"{fmt_seconds(r.duration)}")
        r.app_name = app_name
        line = f"{symbol} {app_name} · {platform}: {detail}{extra}"
        if r.status == "skipped":
            log.debug(line)  # zusammengefasst in _log_skipped
        else:
            (log.error if r.status in ("failed", "partial") else log.info)(line)
        for message in r.errors:
            log.error("   ↳ %s", message)

    # ---- Stufe 2: Stabilität (Apple Analytics) ----
    def run_stability(self) -> list[Result]:
        """Ruft Absturz- und Sitzungsdaten für alle ausgewählten Apple-Apps ab."""
        self.opt.platform = "apple" if self.opt.platform in ("all", "apple") else self.opt.platform
        targets = [t for t in self.targets() if t[2] == "apple"]
        if not targets:
            raise ConfigError("Keine aktivierte Apple-App für den Stabilitätsabruf ausgewählt.")
        data_dir, results, t0 = self.cfg.data_dir, [], time.monotonic()
        log.info("▶ Abruf der Stabilitätsdaten (Apple Analytics)")
        with run_lock(data_dir / ".lock"):
            state = read_versioned(data_dir / "state.json", 1, empty_state)
            for customer, app, platform, pcfg in targets:
                started = time.monotonic()
                result = self._sync_stability(state, customer, app, pcfg)
                result.duration = round(time.monotonic() - started, 2)
                self._log_line(app["name"], "Stabilität", result)
                results.append(result)
                if not self.opt.dry_run:
                    write_json(data_dir / "state.json", state)
        self.last_duration = time.monotonic() - t0
        self._log_skipped(results)
        return results

    def _sync_stability(self, state: dict, customer: dict, app: dict, pcfg: dict) -> Result:
        cid, aid, store_id = customer["id"], app["id"], str(pcfg["appId"])
        result = Result(cid, aid, "apple", mode="stability")
        tstate = get_target_state(state, cid, aid, "apple-stability", create=True)
        now_dt = self.clock()
        now = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        last_ok = tstate["lastSuccessfulSync"]
        if (not (self.opt.force or self.opt.full_sync) and last_ok and tstate["status"] == "ok"
                and now_dt - _parse(last_ok) < timedelta(minutes=self.cfg.settings["minRefreshMinutes"])):
            result.status, result.total = "skipped", tstate["reviewCount"]
            return result
        path = target_dir(self.cfg.data_dir, cid, aid, "apple") / "stability-metrics.json"
        try:
            doc = read_versioned(path, SCHEMA_VERSION, lambda: {
                "schemaVersion": SCHEMA_VERSION, "platform": "apple", "storeAppId": store_id,
                "source": "App Store Connect API – Analytics Reports", "reports": [CRASH_REPORT, SESSION_REPORT],
                "instances": [], "crashes": [], "sessions": []})
        except StorageError as exc:
            return self._fail(result, tstate, now, exc, "Datei beschädigt – nichts überschrieben")
        known = set() if self.opt.full_sync else set(doc["instances"])
        new_instances = 0
        error: Exception | None = None
        client = None
        before = None
        try:
            client = self._client(customer, "apple")
            before = client.http.snapshot()
            analytics = AppleAnalytics(client)
            ids = analytics.report_ids(store_id)
            todo = []
            for name, section, aggregate in ((CRASH_REPORT, "crashes", aggregate_crashes),
                                             (SESSION_REPORT, "sessions", aggregate_sessions)):
                todo += [(inst, section, aggregate) for inst in analytics.instances(ids[name]) if inst["id"] not in known]
            if todo:
                for done, (inst, section, aggregate) in enumerate(todo):
                    self.progress(f"{app['name']} · Stabilität", done, len(todo))
                    rows = aggregate(list(analytics.instance_rows(inst["id"])))
                    doc[section] = replace_dates(doc[section], rows)
                    doc["instances"].append(inst["id"])
                    known.add(inst["id"])
                    new_instances += 1
                    result.new += len(rows)
                self.progress("", 0, 0)  # Fortschrittszeile entfernen
        except ToolError as exc:
            error = exc
        finally:
            if client is not None and before is not None:
                after = client.http.snapshot()
                result.api_requests = after["requests"] - before["requests"]
                result.responses = after["responses"] - before["responses"]
                result.ok_responses = after["ok"] - before["ok"]
                result.retries = after["retries"] - before["retries"]
                result.network_errors = after["networkErrors"] - before["networkErrors"]
                result.bytes_in = after["bytesIn"] - before["bytesIn"]
        result.total = len(doc["crashes"]) + len(doc["sessions"])
        result.unchanged = new_instances
        log.debug("Neue Berichtsinstanzen: %d | gespeicherte Zeilen: %d", new_instances, result.total)
        if self.opt.dry_run:
            result.status = "dry_run" if error is None else "failed"
            if error:
                result.errors.append(redact(error))
            return result
        if new_instances:
            doc["limitations"] = ["Apple blendet Zeilen mit sehr wenigen Geräten aus (Datenschutz); Summen können "
                                  "daher zu niedrig sein.", "Daten ab Einrichtung der Berichtsanfrage; kein Rückblick."]
            write_json(path, doc)
        tstate["lastAttempt"], tstate["reviewCount"] = now, result.total
        if error is None:
            tstate.update(status="ok", lastError=None, lastSuccessfulSync=now)
            result.status = "ok"
        else:
            result.errors.append(redact(error))
            result.status = "partial" if new_instances else "failed"
            tstate["status"], tstate["lastError"] = result.status, redact(error)
        result.last_successful_sync = tstate["lastSuccessfulSync"]
        return result

    # ---- Import ----
    def import_google_csv(self, customer_id: str, app_id: str, paths: list[Path]) -> Result:
        """Importiert Play-Console-CSV-Exporte (offizielle Bestandsdaten) in die Google-Daten einer App."""
        self.opt.customer, self.opt.app, self.opt.platform = customer_id, app_id, "google"
        targets = self.targets()
        if not targets:
            raise ConfigError("Kunde/App mit aktivierter Google-Plattform nicht gefunden.")
        customer, app, platform, pcfg = targets[0]
        package = pcfg["packageName"]
        directory = target_dir(self.cfg.data_dir, customer["id"], app["id"], "google")
        now = self.clock().strftime("%Y-%m-%dT%H:%M:%SZ")
        result = Result(customer["id"], app["id"], "google", mode="csv-import")
        with run_lock(self.cfg.data_dir / ".lock"):
            doc = read_versioned(directory / "reviews.json", SCHEMA_VERSION, lambda: {
                "schemaVersion": SCHEMA_VERSION, "customerId": customer["id"], "appId": app["id"],
                "platform": "google", "storeAppId": package, "reviews": []})
            history = read_versioned(directory / "review-history.json", SCHEMA_VERSION,
                                     lambda: {"schemaVersion": SCHEMA_VERSION, "changes": []})
            existing = {r["id"]: r for r in doc["reviews"]}
            rows = [normalize_csv_row(customer["id"], app["id"], package, row)
                    for path in paths for row in read_console_csv(path)]
            stats = merge_reviews(existing, [r for r in rows if r], history["changes"], now)
            result.new, result.updated, result.unchanged, result.total = (
                stats["new"], stats["updated"], stats["unchanged"], len(existing))
            if not self.opt.dry_run:
                doc["reviews"] = sorted(existing.values(), key=lambda r: (r.get("createdAt") or "", r["id"]),
                                        reverse=True)
                write_json(directory / "reviews.json", doc)
                write_json(directory / "review-history.json", history)
                state = read_versioned(self.cfg.data_dir / "state.json", 1, empty_state)
                get_target_state(state, customer["id"], app["id"], "google", create=True)["reviewCount"] = len(existing)
                write_json(self.cfg.data_dir / "state.json", state)
        return result


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _language_filtered(review: dict, pcfg: dict) -> bool:
    """Clientseitiger Filter für konfigurierte Sprachen (nur wenn die Sprache bekannt ist)."""
    languages = pcfg.get("languages") or []
    if not languages or not review.get("language"):
        return False
    return review["language"].split("_")[0].split("-")[0].lower() not in {l.lower() for l in languages}
