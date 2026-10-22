"""Abruf der Testdaten: Apple TestFlight (Builds, Nutzung, Absturzmeldungen) und Google Play (Testspuren, Absturzraten)."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from .apple_testflight import fetch_builds, fetch_crashes, fetch_usage, merge_by_id
from .google_testing import fetch_crash_rates, fetch_tracks
from .errors import ConfigError, StorageError, ToolError
from .models import SCHEMA_VERSION
from .security import redact
from .storage import read_versioned, run_lock, write_json
from .sync import Result, Syncer, empty_state, get_target_state, target_dir, _parse

log = logging.getLogger("arr.testflight")
STATE_KEY = "apple-testflight"
GOOGLE_KEY = "google-testing"


def run_testing(syncer: Syncer) -> list[Result]:
    """Ruft die Testdaten aller ausgewählten Apps ab. Fehler einer App stoppen die anderen nicht."""
    targets = syncer.targets()
    if not targets:
        raise ConfigError("Keine aktivierte App für den Testdaten-Abruf ausgewählt.")
    data_dir, results, t0 = syncer.cfg.data_dir, [], time.monotonic()
    log.info("▶ Abruf der Testdaten (TestFlight, Google Play Testspuren)")
    with run_lock(data_dir / ".lock"):
        state = read_versioned(data_dir / "state.json", 1, empty_state)
        for customer, app, platform, pcfg in targets:
            started = time.monotonic()
            sync = _sync_apple if platform == "apple" else _sync_google
            result = sync(syncer, state, customer, app, pcfg)
            result.duration = round(time.monotonic() - started, 2)
            result.app_name = app["name"]
            syncer._log_line(app["name"], "TestFlight" if platform == "apple" else "Testspuren", result)
            results.append(result)
            if not syncer.opt.dry_run:
                write_json(data_dir / "state.json", state)
    syncer.last_duration = time.monotonic() - t0
    syncer._log_skipped(results)
    return results


def _sync_apple(syncer: Syncer, state: dict, customer: dict, app: dict, pcfg: dict) -> Result:
    cid, aid, store_id = customer["id"], app["id"], str(pcfg["appId"])
    result = Result(cid, aid, "apple", mode="testflight")
    tstate = get_target_state(state, cid, aid, STATE_KEY, create=True)
    now_dt = syncer.clock()
    now = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    last_ok = tstate["lastSuccessfulSync"]
    if (not (syncer.opt.force or syncer.opt.full_sync) and last_ok and tstate["status"] == "ok"
            and now_dt - _parse(last_ok) < timedelta(minutes=syncer.cfg.settings["minRefreshMinutes"])):
        result.status, result.total = "skipped", tstate["reviewCount"]
        return result
    path = target_dir(syncer.cfg.data_dir, cid, aid, "apple") / "testflight.json"
    try:
        doc = read_versioned(path, SCHEMA_VERSION, lambda: {
            "schemaVersion": SCHEMA_VERSION, "platform": "apple", "storeAppId": store_id,
            "source": "App Store Connect API – TestFlight", "builds": [], "crashes": []})
    except StorageError as exc:
        return syncer._fail(result, tstate, now, exc, "Datei beschädigt – nichts überschrieben")
    error: Exception | None = None
    client = before = None
    changed = False
    try:
        client = syncer._client(customer, "apple")
        before = client.http.snapshot()
        result.new += merge_by_id(doc["builds"], fetch_builds(client, store_id))
        for build in doc["builds"]:
            # Abgelaufene Builds ändern sich nicht mehr: Nutzung nur einmal holen.
            if build.get("expired") and build.get("usage"):
                continue
            usage = fetch_usage(client, build["id"])
            if usage and usage != {k: v for k, v in (build.get("usage") or {}).items() if k != "capturedAt"}:
                build["usage"] = {**usage, "capturedAt": now}
                changed = True
        result.new += merge_by_id(doc["crashes"], fetch_crashes(client, store_id))
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
    result.total = len(doc["builds"])
    if syncer.opt.dry_run:
        result.status = "dry_run" if error is None else "failed"
        if error:
            result.errors.append(redact(error))
        return result
    if result.new or changed:
        doc["limitations"] = [
            "Nutzungszahlen je Build (Installationen, Sitzungen, Abstürze) gelten für den von Apple gemeldeten Zeitraum "
            "(rund ein Jahr), nicht je Tag.", "Betriebssystem und Gerät gibt es nur bei einzelnen Absturzmeldungen von Testern."]
        write_json(path, doc)
    tstate["lastAttempt"], tstate["reviewCount"] = now, result.total
    if error is None:
        tstate.update(status="ok", lastError=None, lastSuccessfulSync=now)
        result.status = "ok"
    else:
        result.errors.append(redact(error))
        result.status = "partial" if result.new else "failed"
        tstate["status"], tstate["lastError"] = result.status, redact(error)
    result.last_successful_sync = tstate["lastSuccessfulSync"]
    return result


def _sync_google(syncer: Syncer, state: dict, customer: dict, app: dict, pcfg: dict) -> Result:
    """Testspuren (ersetzt den Stand) und Absturzraten je Versionscode (Zusammenführen über Datum und Versionscode)."""
    cid, aid, package = customer["id"], app["id"], str(pcfg["packageName"])
    result = Result(cid, aid, "google", mode="testing")
    tstate = get_target_state(state, cid, aid, GOOGLE_KEY, create=True)
    now_dt = syncer.clock()
    now = now_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    last_ok = tstate["lastSuccessfulSync"]
    if (not (syncer.opt.force or syncer.opt.full_sync) and last_ok and tstate["status"] == "ok"
            and now_dt - _parse(last_ok) < timedelta(minutes=syncer.cfg.settings["minRefreshMinutes"])):
        result.status, result.total = "skipped", tstate["reviewCount"]
        return result
    path = target_dir(syncer.cfg.data_dir, cid, aid, "google") / "google-testing.json"
    try:
        doc = read_versioned(path, SCHEMA_VERSION, lambda: {
            "schemaVersion": SCHEMA_VERSION, "platform": "google", "packageName": package,
            "source": "Google Play – Testspuren und Play Developer Reporting API (nicht live geprüft)",
            "tracks": [], "crashRates": []})
    except StorageError as exc:
        return syncer._fail(result, tstate, now, exc, "Datei beschädigt – nichts überschrieben")
    error: Exception | None = None
    client = before = None
    changed = False
    try:
        client = syncer._client(customer, "google")
        before = client.http.snapshot()
        tracks = fetch_tracks(client, package)
        if tracks and tracks != doc["tracks"]:
            doc["tracks"], doc["tracksCapturedAt"], changed = tracks, now, True
        rows = fetch_crash_rates(client, package, now_dt.date())
        known = {r["id"]: r for r in doc["crashRates"]}
        for row in rows:  # Google korrigiert die letzten Tage nachträglich: neuer Wert ersetzt den alten
            if known.get(row["id"]) != row:
                result.new += 1 if row["id"] not in known else 0
                result.updated += 1 if row["id"] in known else 0
                known[row["id"]] = row
        doc["crashRates"] = sorted(known.values(), key=lambda r: (r["date"], r["versionCode"]))
        changed = changed or bool(result.new or result.updated)
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
    result.total = len(doc["crashRates"])
    if syncer.opt.dry_run:
        result.status = "dry_run" if error is None else "failed"
        if error:
            result.errors.append(redact(error))
        return result
    if changed:
        doc["limitations"] = [
            "Nicht gegen die echte Google-API geprüft. Die Absturzraten stammen von Google, sind Anteile der Nutzer und "
            "nicht mit Apple vergleichbar.", "Die Reporting-API trennt nicht nach Test und Produktion; die Zuordnung "
            "zur Spur erfolgt über den Versionscode.", "Die jüngsten ein bis drei Tage fehlen (Verzögerung bei Google)."]
        write_json(path, doc)
    tstate["lastAttempt"], tstate["reviewCount"] = now, result.total
    if error is None:
        tstate.update(status="ok", lastError=None, lastSuccessfulSync=now)
        result.status = "ok"
    else:
        result.errors.append(redact(error))
        result.status = "partial" if changed else "failed"
        tstate["status"], tstate["lastError"] = result.status, redact(error)
    result.last_successful_sync = tstate["lastSuccessfulSync"]
    return result
