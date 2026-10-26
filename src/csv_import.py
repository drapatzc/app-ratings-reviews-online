"""Import von Play-Console-CSV-Exporten (offizielle Bestandsdaten Google) in `reviews.json` einer App."""
from __future__ import annotations

from pathlib import Path

from .errors import ConfigError
from .google import normalize_csv_row, read_console_csv
from .merge import merge_reviews
from .models import SCHEMA_VERSION, iso_z
from .storage import read_versioned, run_lock, write_json
from .sync import Result, Syncer, empty_state, get_target_state, target_dir


def import_google_csv(syncer: Syncer, customer_id: str, app_id: str, paths: list[Path]) -> Result:
    """Importiert Play-Console-CSV-Exporte (offizielle Bestandsdaten) in die Google-Daten einer App."""
    targets = syncer.targets(customer=customer_id, app=app_id, platform="google")
    if not targets:
        raise ConfigError("Kunde/App mit aktivierter Google-Plattform nicht gefunden.")
    customer, app, _platform, pcfg = targets[0]
    cid, aid, package = customer["id"], app["id"], pcfg["packageName"]
    directory = target_dir(syncer.cfg.data_dir, cid, aid, "google")
    now = iso_z(syncer.clock())
    result = Result(cid, aid, "google", mode="csv-import")
    with run_lock(syncer.cfg.data_dir / ".lock"):
        doc = read_versioned(directory / "reviews.json", SCHEMA_VERSION, lambda: {
            "schemaVersion": SCHEMA_VERSION, "customerId": cid, "appId": aid, "platform": "google",
            "storeAppId": package, "reviews": []})
        history = read_versioned(directory / "review-history.json", SCHEMA_VERSION,
                                 lambda: {"schemaVersion": SCHEMA_VERSION, "changes": []})
        existing = {review["id"]: review for review in doc["reviews"]}
        rows = [normalize_csv_row(cid, aid, package, row) for path in paths for row in read_console_csv(path)]
        stats = merge_reviews(existing, [review for review in rows if review], history["changes"], now)
        result.new, result.updated, result.unchanged, result.total = (
            stats["new"], stats["updated"], stats["unchanged"], len(existing))
        if not syncer.opt.dry_run:
            doc["reviews"] = sorted(existing.values(), key=lambda review: (review.get("createdAt") or "", review["id"]),
                                    reverse=True)
            write_json(directory / "reviews.json", doc)
            write_json(directory / "review-history.json", history)
            state = read_versioned(syncer.cfg.data_dir / "state.json", 1, empty_state)
            get_target_state(state, cid, aid, "google", create=True)["reviewCount"] = len(existing)
            write_json(syncer.cfg.data_dir / "state.json", state)
    return result
