"""Synchronisation: Ziele, Frische, Zeitfenster, Rezensionsabruf, Schreiben, Zustand und Laufprotokoll.

Der Rezensionsabruf steht in `sync_reviews`. Alle weiteren Abrufarten (Stabilität, Store-Kennzahlen, Testbetrieb,
KI-Analyse)
beschreiben sich als `Dataset` und laufen über den gemeinsamen Rahmen `sync_dataset`: Frische, Laden, Zähler,
Probelauf, Schreiben und Zustand sind dort einmal implementiert; die Module liefern nur den eigentlichen Abruf.
Zusammenführen steht in `merge.py`, der CSV-Import in `csv_import.py`; `Syncer` behält die bisherigen Einstiege
`run_stability` und `import_google_csv`.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from .apple import AppleClient
from .auth import GOOGLE_REPORTING_SCOPE, AppleTokenProvider, GoogleTokenProvider
from .config import Config, parse_date
from .config import competitors as config_competitors
from .errors import ConfigError, StorageError, ToolError
from .google import API_WINDOW_DAYS, GoogleClient
from .http import HttpClient, Transport
from .merge import build_versions, derived_distribution, merge_reviews, update_ratings_history  # noqa: F401
from .models import SCHEMA_VERSION, iso_z, parse_iso
from .releases import apply_release_dates
from .security import read_secret, redact
from .storage import read_versioned, run_lock, write_json
from .ui import fmt_seconds

log = logging.getLogger("arr.sync")
MAX_HISTORY_RUNS = 500
DEFAULT_WORDING = "{new} neu · {updated} geändert · {total} gesamt"


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
    label: str = ""  # Anzeige der Abrufart ("Stabilität", "TestFlight"); leer = Rezensionen (Plattformname)
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
    changed: bool = False  # Dokument verändert, ohne dass `new`/`updated` es zeigen (z. B. ersetzte Testspuren)
    quality_issues: int = 0
    errors: list[str] = field(default_factory=list)
    last_successful_sync: str | None = None
    wording: str = DEFAULT_WORDING  # Logzeile; Abrufarten mit anderen Einheiten setzen eine eigene
    competitor: bool = False  # Ziel ist eine Wettbewerber-App (customers[].competitors), nicht eine eigene


@dataclass(frozen=True)
class Dataset:
    """Eine Abrufart neben den Rezensionen. Der Ablauf steht in `Syncer.sync_dataset`, hier nur das Spezifische.

    `fetch(syncer, client, store_id, doc, result, app, now)` verändert `doc` und zählt in `result` (`new`,
    `updated`, `changed`); was bis zu einem Fehler eingetragen wurde, wird gespeichert (Status `partial`).
    """

    mode: str            # `Result.mode`, z. B. "stability"
    label: str           # Anzeige in Logzeile und Zusammenfassung
    platform: str        # "apple" oder "google"
    state_key: str       # Schlüssel in state.json, z. B. "apple-stability"
    file_name: str       # Datei im Plattformordner der App
    new_doc: Callable[[str], dict]   # store_id → leeres Dokument
    fetch: Callable[..., None]
    total: Callable[[dict], int]     # gespeicherte Zeilen für `Result.total` und `reviewCount` im Zustand
    limitations: tuple[str, ...]
    wording: str = DEFAULT_WORDING
    # Eigener Client statt des Store-Clients (KI-Analyse): `client(syncer, customer)`; muss `.http` besitzen
    client: Callable[["Syncer", dict], Any] | None = None
    # Zielmenge: "apps" (eigene Apps, Standard) oder "competitors" (Wettbewerber-Apps des Kunden, nur Apple)
    targets: str = "apps"


# ----------------------------------------------------------------------------------------------------------
# Pfade und Zustand
# ----------------------------------------------------------------------------------------------------------

def target_dir(data_dir: Path, customer: str, app: str, platform: str, competitor: bool = False) -> Path:
    """Ablageordner einer App je Plattform; Wettbewerber liegen getrennt unter `competitors/`, nie unter `apps/`."""
    return data_dir / "customers" / customer / ("competitors" if competitor else "apps") / app / platform


def competitor_app(entry: dict) -> dict:
    """Wettbewerber-Eintrag der Konfiguration als App-Dict für `targets`: Marker `competitor`, Plattform nur Apple;
    die Plattformkonfiguration ist `entry["apple"]` (appId, countries)."""
    return {**entry, "competitor": True, "platforms": {"apple": dict(entry.get("apple") or {})}}


def empty_state() -> dict:
    return {"schemaVersion": 1, "customers": {}}


def get_target_state(state: dict, customer: str, app: str, platform: str, create: bool = False,
                     competitor: bool = False) -> dict | None:
    """Liefert den Zustandseintrag eines Ziels (`platform` ist auch der Schlüssel anderer Abrufarten, z. B.
    `apple-stability`); mit `create` wird er samt Elternknoten angelegt. Wettbewerber stehen unter `competitors`."""
    customers = state["customers"]
    group = "competitors" if competitor else "apps"
    if not create:
        return ((customers.get(customer) or {}).get(group, {}).get(app) or {}).get(platform)
    apps = customers.setdefault(customer, {"apps": {}}).setdefault(group, {})
    return apps.setdefault(app, {}).setdefault(platform, {
        "lastSuccessfulSync": None, "lastFullSync": None, "lastAttempt": None, "lastError": None,
        "reviewCount": 0, "status": "never_synced", "lastApiRequests": 0, "dataGaps": []})


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
        self.cache: dict = {}  # gilt nur für diesen Lauf (z. B. ONGOING-Analytics-Anfrage je App)
        self._failed: dict[tuple, Exception] = {}
        self.last_duration = 0.0
        self.progress: Callable[[str, int, int], None] = lambda label, done, total: None

    # ---- Zielauswahl ----
    def targets(self, include_disabled: bool = False, customer: str | None = None, app: str | None = None,
                platform: str | None = None, competitors: bool = False) -> list[tuple[dict, dict, str, dict]]:
        """Liste aus (Kunde, App, Plattform, Plattformkonfiguration) gemäß Konfiguration und Filtern.

        Ohne Argumente gelten die Filter aus den Optionen; die Optionen selbst werden nie verändert. Mit `competitors`
        kommen statt der eigenen Apps die Wettbewerber des Kunden (`competitor_app`), nur Apple."""
        customer, app = customer or self.opt.customer, app or self.opt.app
        platform = platform or self.opt.platform
        found = []
        for cust in self.cfg.customers:
            if customer and cust["id"] != customer:
                continue
            if not include_disabled and not cust.get("enabled", True):
                continue
            items = [competitor_app(entry) for entry in config_competitors(cust)] if competitors else cust["apps"]
            for item in items:
                if app and item["id"] != app:
                    continue
                if not include_disabled and not item.get("enabled", True):
                    continue
                for pname, pcfg in item["platforms"].items():
                    if platform != "all" and pname != platform:
                        continue
                    if not include_disabled and not pcfg.get("enabled", True):
                        continue
                    found.append((cust, item, pname, pcfg))
        return found

    def _run_targets(self, heading: str, targets: list[tuple[dict, dict, str, dict]],
                     sync_one: Callable[[dict, dict, dict, str, dict], Result],
                     after: Callable[[list[Result]], None] | None = None) -> list[Result]:
        """Gemeinsamer Lauf: Sperre, Zustand lesen, je Ziel `sync_one` mit Zeitmessung und Logzeile, Zustand
        schreiben. Fehler eines Ziels stoppen die anderen nicht. `after` läuft noch innerhalb der Sperre."""
        data_dir, began = self.cfg.data_dir, time.monotonic()
        results: list[Result] = []
        log.info("▶ %s", heading)
        with run_lock(data_dir / ".lock"):
            state = read_versioned(data_dir / "state.json", 1, empty_state)
            for customer, app, platform, pcfg in targets:
                started = time.monotonic()
                result = sync_one(state, customer, app, platform, pcfg)
                result.duration = round(time.monotonic() - started, 2)
                result.app_name = app["name"]
                self._log_line(result)
                results.append(result)
                if not self.opt.dry_run:
                    write_json(data_dir / "state.json", state)
            if after and not self.opt.dry_run:
                after(results)
        self.last_duration = time.monotonic() - began
        self._log_skipped(results)
        return results

    def run(self) -> list[Result]:
        """Rezensionen aller ausgewählten Ziele abrufen; der Lauf wird in sync-history.json protokolliert."""
        targets = self.targets()
        if not targets:
            raise ConfigError("Keine passenden aktivierten Kunden/Apps/Plattformen gefunden.")
        started = self.clock()
        return self._run_targets("Abruf der Rezensionen", targets, self.sync_reviews,
                                 lambda results: self._append_history(started, results))

    def run_datasets(self, datasets: list[Dataset], heading: str) -> list[Result]:
        """Abrufarten neben den Rezensionen (je Plattform und Zielmenge höchstens eine) über alle ausgewählten Ziele.
        Ziele anderer Plattformen werden still übergangen; ohne passendes Ziel gibt es einen Konfigurationsfehler."""
        by_key = {(dataset.targets, dataset.platform): dataset for dataset in datasets}
        targets = []
        for group in dict.fromkeys(dataset.targets for dataset in datasets):
            targets += [target for target in self.targets(competitors=group == "competitors")
                        if (group, target[2]) in by_key]
        if not targets:
            names = " / ".join(dataset.label for dataset in datasets)
            raise ConfigError(f"Keine aktivierte App für den Abruf ausgewählt: {names}.")

        def sync_one(state: dict, customer: dict, app: dict, platform: str, pcfg: dict) -> Result:
            group = "competitors" if app.get("competitor") else "apps"
            return self.sync_dataset(by_key[(group, platform)], state, customer, app, pcfg)
        return self._run_targets(heading, targets, sync_one)

    def _append_history(self, started: datetime, results: list[Result]) -> None:
        path = self.cfg.data_dir / "sync-history.json"
        history = read_versioned(path, 1, lambda: {"schemaVersion": 1, "runs": []})
        finished = self.clock()
        history["runs"].append({
            "startedAt": iso_z(started), "finishedAt": iso_z(finished),
            "durationSeconds": round((finished - started).total_seconds(), 1),
            "options": {"customer": self.opt.customer, "app": self.opt.app, "platform": self.opt.platform,
                        "from": self.opt.date_from, "to": self.opt.date_to, "fullSync": self.opt.full_sync},
            "results": [{"customer": res.customer, "app": res.app, "platform": res.platform, "status": res.status,
                         "mode": res.mode, "apiRequests": res.api_requests, "responses": res.responses,
                         "retries": res.retries, "durationSeconds": res.duration, "new": res.new, "updated": res.updated,
                         "unchanged": res.unchanged, "total": res.total, "errors": res.errors,
                         "lastSuccessfulSync": res.last_successful_sync} for res in results]})
        history["runs"] = history["runs"][-MAX_HISTORY_RUNS:]
        write_json(path, history)

    # ---- Clients ----
    def public_http(self) -> HttpClient:
        """HTTP-Client ohne Zugangsdaten für öffentliche Endpunkte (Wettbewerber: RSS-Feed, iTunes Lookup)."""
        return HttpClient(self.cfg.settings["requestTimeoutSeconds"], self.cfg.settings["maxRetries"], self.transport,
                          self.sleep)

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

    # ---- Gemeinsame Schritte aller Abrufarten ----
    def _fresh(self, tstate: dict, now: datetime, bypass: bool = False) -> bool:
        """True, wenn der letzte erfolgreiche Lauf jünger als `minRefreshMinutes` ist: dann keine API-Aufrufe.
        `--force` und `--full-sync` (und `bypass`, etwa ein expliziter Zeitraum) setzen die Frist außer Kraft."""
        last_ok = tstate["lastSuccessfulSync"]
        if bypass or self.opt.force or self.opt.full_sync or not last_ok or tstate["status"] != "ok":
            return False
        return now - parse_iso(last_ok) < timedelta(minutes=self.cfg.settings["minRefreshMinutes"])

    def _skipped(self, result: Result, tstate: dict) -> Result:
        result.status, result.total = "skipped", tstate["reviewCount"]
        result.last_successful_sync = tstate["lastSuccessfulSync"]
        log.debug("Übersprungen: Wartefrist %s Minuten", self.cfg.settings["minRefreshMinutes"])
        return result

    def _dry_run(self, result: Result, error: Exception | None) -> Result:
        """Probelauf: nichts wird geschrieben, der Zustand bleibt unverändert."""
        result.status = "dry_run" if error is None else "failed"
        if error:
            result.errors.append(redact(error))
        return result

    def _fail(self, result: Result, tstate: dict, now: str, exc: Exception, note: str) -> Result:
        result.status = "failed"
        result.errors.append(redact(exc))
        tstate["lastAttempt"], tstate["status"], tstate["lastError"] = now, "failed", redact(exc)
        result.last_successful_sync = tstate["lastSuccessfulSync"]
        log.error("%s: %s", note, redact(exc))
        return result

    def _finish(self, result: Result, tstate: dict, now: str, error: Exception | None, saved: bool) -> None:
        """Status und Zustand nach dem Abruf: `ok`, `partial` (Fehler, aber Gespeichertes) oder `failed`."""
        tstate["lastAttempt"], tstate["reviewCount"] = now, result.total
        tstate["lastApiRequests"] = result.api_requests
        if error is None:
            result.status = "ok"
            tstate.update(status="ok", lastError=None, lastSuccessfulSync=now)
        else:
            result.errors.append(redact(error))
            result.status = "partial" if saved else "failed"
            tstate["status"], tstate["lastError"] = result.status, redact(error)
        result.last_successful_sync = tstate["lastSuccessfulSync"]

    def sync_dataset(self, dataset: Dataset, state: dict, customer: dict, app: dict, pcfg: dict) -> Result:
        """Ein Ziel einer Abrufart: Frische, Datei laden, `ds.fetch`, Zähler, Probelauf, Schreiben, Zustand."""
        cid, aid, rival = customer["id"], app["id"], bool(app.get("competitor"))
        store_id = str(pcfg["appId"] if dataset.platform == "apple" else pcfg["packageName"])
        result = Result(cid, aid, dataset.platform, mode=dataset.mode, label=dataset.label, wording=dataset.wording,
                        competitor=rival)
        tstate = get_target_state(state, cid, aid, dataset.state_key, create=True, competitor=rival)
        now_dt = self.clock()
        now = iso_z(now_dt)
        if self._fresh(tstate, now_dt):
            return self._skipped(result, tstate)
        path = target_dir(self.cfg.data_dir, cid, aid, dataset.platform, competitor=rival) / dataset.file_name
        try:
            doc = read_versioned(path, SCHEMA_VERSION, lambda: dataset.new_doc(store_id))
        except StorageError as exc:
            return self._fail(result, tstate, now, exc, "Datei beschädigt – nichts überschrieben")
        error: Exception | None = None
        client = before = None
        try:
            client = dataset.client(self, customer) if dataset.client else self._client(customer, dataset.platform)
            before = client.http.snapshot()
            dataset.fetch(self, client, store_id, doc, result, app, now)
        except ToolError as exc:
            error = exc
        finally:
            self.count_requests(result, client, before)
        result.total = dataset.total(doc)
        if self.opt.dry_run:
            return self._dry_run(result, error)
        saved = bool(result.new or result.updated or result.changed)
        if saved:
            doc["limitations"] = list(dataset.limitations)
            write_json(path, doc)
        self._finish(result, tstate, now, error, saved)
        return result

    # ---- Rezensionen ----
    def sync_reviews(self, state: dict, customer: dict, app: dict, platform: str, pcfg: dict) -> Result:
        """Synchronisiert die Rezensionen einer App auf einer Plattform und aktualisiert Dateien und Zustand."""
        cid, aid = customer["id"], app["id"]
        result = Result(cid, aid, platform)
        store_id = str(pcfg.get("appId") if platform == "apple" else pcfg.get("packageName"))
        log.debug("Customer: %s | App: %s | Platform: %s", customer["name"], app["name"], platform)
        tstate = get_target_state(state, cid, aid, platform, create=True)
        now_dt = self.clock()
        now = iso_z(now_dt)
        directory = target_dir(self.cfg.data_dir, cid, aid, platform)
        explicit_range = bool(self.opt.date_from or self.opt.date_to)
        settings = self.cfg.settings
        last_ok = tstate["lastSuccessfulSync"]
        if self._fresh(tstate, now_dt, bypass=explicit_range):
            result.mode = "fresh"
            return self._skipped(result, tstate)

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

        existing = {review["id"]: review for review in reviews_doc["reviews"]}
        log.debug("Existing reviews: %d", len(existing))

        # Modus und Zeitfenster bestimmen
        since, until = self._window(tstate, explicit_range, now_dt, settings)
        full = since is None or self.opt.full_sync
        result.mode = "range" if explicit_range else ("full" if full else "incremental")

        stats = {"new": 0, "updated": 0, "unchanged": 0, "invalid": 0}
        store_versions: list[dict] = []
        summaries: list[dict] = []
        error: Exception | None = None
        client = before = None
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
                    if not _language_filtered(review, pcfg):
                        fetched.append(review)
            except ToolError as exc:  # mitten im Abruf: bisher Geholtes trotzdem sichern
                error = exc
            stats.update(merge_reviews(existing, fetched, history_doc["changes"], now))
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
            self.count_requests(result, client, before)

        result.new, result.updated, result.unchanged = stats["new"], stats["updated"], stats["unchanged"]
        result.quality_issues = stats["invalid"]
        result.total = len(existing)
        if stats["invalid"]:
            log.warning("Datenqualität: %d Rezensionen mit Auffälligkeiten", stats["invalid"])
        if self.opt.dry_run:
            return self._dry_run(result, error)

        saved = bool(stats["new"] or stats["updated"])
        try:
            if saved:
                reviews_doc["reviews"] = sorted(existing.values(), key=lambda review: (review.get("createdAt") or "", review["id"]),
                                                reverse=True)
                write_json(reviews_path, reviews_doc)
                write_json(directory / "review-history.json", history_doc)
            versions = build_versions(platform, store_id, existing, store_versions, versions_doc, now)
            # build_versions übernimmt die alten Einträge als dieselben Objekte; daher den Rückgabewert mitprüfen
            released = apply_release_dates(versions, summaries, now)
            if released or versions["versions"] != versions_doc["versions"]:
                write_json(directory / "versions.json", versions)
            if update_ratings_history(ratings_doc, existing, summaries, now):
                write_json(directory / "ratings-history.json", ratings_doc)
        except (StorageError, OSError) as exc:
            error = error or StorageError(f"Schreiben fehlgeschlagen: {exc}")

        if error is None and explicit_range:
            # Expliziter Zeitraum ist kein vollständiger Stand: lastSuccessfulSync und Status bleiben stehen.
            tstate.update(lastAttempt=now, reviewCount=result.total, lastApiRequests=result.api_requests, lastError=None)
            if tstate["status"] == "never_synced":
                tstate["status"] = "partial"
            result.status, result.last_successful_sync = "ok", tstate["lastSuccessfulSync"]
            return result
        if error is None:
            self._record_gap(tstate, platform, last_ok, now)
            if full or platform == "google":
                tstate["lastFullSync"] = now
        self._finish(result, tstate, now, error, saved)  # lastSuccessfulSync = Startzeit, erst nach vollem Erfolg
        return result

    # ---- Hilfen ----
    def _window(self, tstate: dict, explicit: bool, now: datetime, settings: dict):
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
            full_due = bool(interval) and now - parse_iso(tstate["lastFullSync"]) > timedelta(days=interval)
        if self.opt.full_sync or not last_ok or not incremental or full_due:
            if full_due and not self.opt.full_sync:
                log.info("Periodische vollständige Synchronisation fällig")
            return floor, until
        since = iso_z(parse_iso(last_ok) - timedelta(days=settings["overlapDays"]))
        return max(since, floor) if floor else since, until

    def _record_gap(self, tstate: dict, platform: str, previous: str | None, now: str) -> None:
        """Google liefert nur 7 Tage: ein größerer Abstand zwischen zwei Läufen kann Rezensionen kosten."""
        if platform == "google" and previous and parse_iso(now) - parse_iso(previous) > timedelta(days=API_WINDOW_DAYS):
            tstate.setdefault("dataGaps", []).append({"from": previous, "to": now})
            log.warning("Abstand seit letztem Lauf > %d Tage: Rezensionen dazwischen können fehlen", API_WINDOW_DAYS)

    def _log_skipped(self, results: list[Result]) -> None:
        """Eine Sammelzeile statt einer Zeile je übersprungener App."""
        skipped = [res for res in results if res.status == "skipped"]
        if skipped:
            names = ", ".join(res.app_name or res.app for res in skipped[:4]) + (" …" if len(skipped) > 4 else "")
            log.info("↷ %d übersprungen (vor weniger als %s Min abgerufen; erzwingen mit --force): %s",
                     len(skipped), self.cfg.settings["minRefreshMinutes"], names)

    def _log_line(self, res: Result) -> None:
        """Eine Zeile je Ziel: Symbol, App, Abrufart, Ergebnis, Anfragen, Dauer."""
        symbol = {"ok": "✔", "skipped": "↷", "dry_run": "◌", "partial": "◐", "failed": "✖"}.get(res.status, "•")
        if res.status == "skipped":
            detail = "übersprungen (Wartefrist, 0 Anfragen)"
        else:
            detail = (res.wording.format(new=res.new, updated=res.updated, total=res.total)
                      + f" · {res.api_requests} Anfragen · {fmt_seconds(res.duration)}")
        line = f"{symbol} {res.app_name or res.app} · {res.label or res.platform.capitalize()}: {detail}"
        if res.status == "skipped":
            log.debug(line)  # zusammengefasst in _log_skipped
        else:
            (log.error if res.status in ("failed", "partial") else log.info)(line)
        for message in res.errors:
            log.error("   ↳ %s", message)

    # ---- Stufe 2 und CSV-Import: eigene Module, hier nur die bisherigen Einstiege ----
    def run_stability(self) -> list[Result]:
        """Ruft Absturz- und Sitzungsdaten für alle ausgewählten Apple-Apps ab (siehe `stability_sync`)."""
        from .stability_sync import run_stability  # spät importiert: stability_sync importiert dieses Modul
        return run_stability(self)

    def import_google_csv(self, customer_id: str, app_id: str, paths: list[Path]) -> Result:
        """Importiert Play-Console-CSV-Exporte in die Google-Daten einer App (siehe `csv_import`)."""
        from .csv_import import import_google_csv  # spät importiert, wie oben
        return import_google_csv(self, customer_id, app_id, paths)

    def count_requests(self, result: Result, client, before: dict | None) -> None:
        """Überträgt die HTTP-Zähler seit `before` (Momentaufnahme von `client.http`) in `result`."""
        if client is None or before is None:
            return
        after = client.http.snapshot()
        result.api_requests = after["requests"] - before["requests"]
        result.responses = after["responses"] - before["responses"]
        result.ok_responses = after["ok"] - before["ok"]
        result.retries = after["retries"] - before["retries"]
        result.network_errors = after["networkErrors"] - before["networkErrors"]
        result.bytes_in = after["bytesIn"] - before["bytesIn"]


def _language_filtered(review: dict, pcfg: dict) -> bool:
    """Clientseitiger Filter für konfigurierte Sprachen (nur wenn die Sprache bekannt ist)."""
    languages = pcfg.get("languages") or []
    if not languages or not review.get("language"):
        return False
    return review["language"].split("_")[0].split("-")[0].lower() not in {lang.lower() for lang in languages}
