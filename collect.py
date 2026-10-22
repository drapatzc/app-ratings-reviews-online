#!/usr/bin/env python3
"""collect.py – ruft Bewertungen/Rezensionen aus App Store Connect und Google Play ab und speichert sie als JSON."""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.config import load_config  # noqa: E402
from src.errors import ToolError  # noqa: E402
from src.security import redact  # noqa: E402
from src.ui import COLOR, ago, fmt_int, fmt_seconds, heading, paint, progress_printer, status_badge, table  # noqa: E402

COLOR_DIM = COLOR
from src.storage import read_json, read_versioned, write_json  # noqa: E402
from src.sync import Options, Syncer, empty_state, get_target_state  # noqa: E402
from src.testing_sync import run_testing  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Bewertungen und Rezensionen abrufen und als JSON speichern.")
    p.add_argument("--config", default=str(ROOT / "config" / "config.json"), help="Pfad zur config.json")
    p.add_argument("--customer", help="nur diesen Kunden (id) verarbeiten")
    p.add_argument("--app", help="nur diese App (id) verarbeiten")
    p.add_argument("--platform", choices=["apple", "google", "all"], default="all")
    p.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD", help="Startdatum (Erstellungsdatum der Rezension)")
    p.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD", help="Enddatum")
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--incremental", action="store_true", default=None, help="inkrementell abrufen")
    mode.add_argument("--full-sync", action="store_true", help="vollständig abrufen (löscht nichts)")
    p.add_argument("--force", action="store_true", help="Aktualisierungsfrist (minRefreshMinutes) ignorieren")
    p.add_argument("--dry-run", action="store_true", help="abrufen, aber nichts speichern")
    p.add_argument("--status", action="store_true", help="Zustand anzeigen (ohne API-Zugriff)")
    p.add_argument("--list-apps", action="store_true", help="konfigurierte Apps anzeigen (ohne API-Zugriff)")
    p.add_argument("--import-google-csv", nargs="+", metavar="DATEI",
                   help="Play-Console-Export(e) importieren (benötigt --customer und --app)")
    p.add_argument("--dataset", choices=["reviews", "stability", "testing", "all"], default="reviews",
                   help="reviews (Standard), stability (Abstürze/Sitzungen, nur Apple), testing (Testdaten: Apple TestFlight, Google Testspuren) oder all")
    p.add_argument("--once-per-day", action="store_true",
                   help="höchstens ein erfolgreicher Lauf pro Kalendertag (UTC); für CI/cron. Fehlgeschlagene Läufe dürfen wiederholt werden")
    p.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="überschreibt settings.logLevel")
    return p


def setup_logging(level: str) -> None:
    class Fmt(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            msg = redact(record.getMessage())
            if record.levelno >= logging.ERROR:
                return paint(f"  {msg}", "31")
            if record.levelno >= logging.WARNING:
                return paint(f"  ⚠ {msg}", "33")
            if record.levelno == logging.DEBUG:
                return paint(f"    {msg}", "2")
            return paint(msg, "1", "35") if msg[:1] in ("▶", "■") else "  " + msg
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(Fmt())
    root = logging.getLogger("arr")
    root.handlers[:] = [handler]
    root.setLevel(level.upper())


def main(argv: list[str] | None = None, transport=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(Path(args.config).expanduser(),
                          {"incrementalSync": True if args.incremental else None,
                           "logLevel": args.log_level})
        setup_logging(cfg.settings["logLevel"])
        opts = Options(customer=args.customer, app=args.app, platform=args.platform, date_from=args.date_from,
                       date_to=args.date_to, incremental=True if args.incremental else (False if args.full_sync else None),
                       full_sync=args.full_sync, dry_run=args.dry_run, force=args.force)
        syncer = Syncer(cfg, opts, transport=transport)
        syncer.progress = progress_printer
        if args.list_apps:
            return list_apps(syncer)
        if args.status:
            return show_status(cfg, syncer)
        if args.import_google_csv:
            if not (args.customer and args.app):
                print("[ERROR] --import-google-csv benötigt --customer und --app", file=sys.stderr)
                return 2
            r = syncer.import_google_csv(args.customer, args.app, [Path(f).expanduser() for f in args.import_google_csv])
            logging.getLogger("arr").info("Import: neu %d, aktualisiert %d, unverändert %d, gesamt %d",
                                          r.new, r.updated, r.unchanged, r.total)
            return 0
        marker = cfg.data_dir / "last-daily.json"
        today = datetime.now(timezone.utc).date().isoformat()
        guard = args.once_per_day and not args.dry_run
        if guard and (read_json(marker, {}) or {}).get("date") == today:
            logging.getLogger("arr").info("Heute (%s, UTC) bereits erfolgreich gelaufen – übersprungen (--once-per-day).", today)
            return 0
        results, total = [], 0.0
        if args.dataset in ("reviews", "all"):
            results += syncer.run()
            total += syncer.last_duration
        if args.dataset in ("stability", "all"):
            results += syncer.run_stability()
            total += syncer.last_duration
        if args.dataset in ("testing", "all"):
            results += run_testing(syncer)
            total += syncer.last_duration
        print_summary(results, total)
        code = 1 if any(r.status in ("failed", "partial") for r in results) else 0
        if guard and code == 0:  # Marker nur nach vollständigem Erfolg: ein Fehlschlag darf am selben Tag wiederholt werden
            write_json(marker, {"schemaVersion": 1, "date": today, "dataset": args.dataset,
                                "finishedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
        return code
    except ToolError as exc:
        print(f"[ERROR] {redact(exc)}", file=sys.stderr)
        return 2


def print_summary(results, total_seconds: float) -> None:
    """Statistik am Ende: Dauer, Requests und Responses je App und Anbieter sowie gesamt."""
    names = {"apple": "Apple", "google": "Google"}
    badge = {"ok": "ok", "skipped": "übersprungen", "dry_run": "Probelauf", "partial": "teilweise", "failed": "Fehler"}

    def row(label, plat, kind, status, rs, seconds=None):
        return [label, plat, kind, status, fmt_seconds(sum(r.duration for r in rs) if seconds is None else seconds),
                fmt_int(sum(r.api_requests for r in rs)), fmt_int(sum(r.responses for r in rs)),
                fmt_int(sum(r.ok_responses for r in rs)), fmt_int(sum(r.retries for r in rs)),
                fmt_int(sum(r.new for r in rs)), fmt_int(sum(r.updated for r in rs)), fmt_int(sum(r.total for r in rs))]

    rows = []
    for r in results:
        st = paint("✔ " + badge.get(r.status, r.status), "32") if r.status in ("ok", "dry_run") else (
            paint("↷ " + badge[r.status], "33") if r.status == "skipped" else paint("✖ " + badge.get(r.status, r.status), "1", "31"))
        rows.append(row(r.app_name or r.app, names[r.platform], {"stability": "Stabilität", "testflight": "TestFlight", "testing": "Testspuren"}.get(r.mode, "Rezensionen"), st, [r]))
    platforms = [p for p in ("apple", "google") if any(r.platform == p for r in results)]
    if len(platforms) > 1:
        for platform in platforms:
            rows.append([paint(c, "1") for c in row(f"Summe {names[platform]}", "", "", "", [r for r in results if r.platform == platform])])
    rows.append([paint(c, "1", "35") for c in row("GESAMT", "", "", "", results, total_seconds)])
    print(heading("Zusammenfassung"))
    print(table(["App", "Anbieter", "Daten", "Status", "Dauer", "Requests", "Responses", "OK", "Retries", "Neu", "Änd.", "Gesamt"],
                rows, ["left", "left", "left", "left"] + ["right"] * 8))
    failed = [r for r in results if r.status in ("failed", "partial")]
    skipped = [r for r in results if r.status == "skipped"]
    kb = sum(r.bytes_in for r in results) / 1024
    size = f"{kb:.0f} KB" if kb < 1024 else f"{kb / 1024:.1f} MB".replace(".", ",")
    print(f"\nLaufzeit {fmt_seconds(total_seconds)} · {len(results)} {'Ziel' if len(results) == 1 else 'Ziele'} · "
          + (paint(f"{len(failed)} mit Fehler", "1", "31") if failed else paint("0 mit Fehler", "32"))
          + f" · {len(skipped)} übersprungen · {size} empfangen · {sum(r.network_errors for r in results)} Netzwerkfehler")
    print(paint("Requests = gesendete HTTP-Anfragen inkl. Wiederholungen · Responses = erhaltene Antworten · OK = Status 2xx · "
                "Neu/Gesamt bei Stabilität = Datenzeilen", "2" if COLOR_DIM else ""))
    for r in failed:
        print(paint(f"  ✖ {r.app_name or r.app} / {names[r.platform]}: {r.errors[0] if r.errors else ''}", "31"))


def list_apps(syncer: Syncer) -> int:
    """Gibt alle konfigurierten Ziele als Tabelle aus, inklusive deaktivierter."""
    for customer in syncer.cfg.customers:
        off = "" if customer.get("enabled", True) else paint("  (Kunde deaktiviert)", "33")
        print(heading(f"{customer['name']}  [{customer['id']}]") + off)
        rows = []
        for app in customer["apps"]:
            def cell(platform: str) -> str:
                cfg = app["platforms"].get(platform)
                if not cfg:
                    return "–"
                store_id = cfg.get("appId") or cfg.get("packageName") or ""
                return paint(f"✔ {store_id}", "32") if cfg.get("enabled", True) else paint(f"○ aus ({store_id})", "33")
            active = app.get("enabled", True) and customer.get("enabled", True)
            rows.append([app["id"], app["name"], cell("apple"), cell("google"),
                         paint("✔ aktiv", "32") if active else paint("○ deaktiviert", "33")])
        print(table(["App-ID", "Name", "Apple (App-ID)", "Google (Package)", "Status"], rows))
    return 0


def show_status(cfg, syncer: Syncer) -> int:
    """Zeigt den gespeicherten Synchronisationszustand als Tabelle – ohne Netzwerkzugriff."""
    state = read_versioned(cfg.data_dir / "state.json", 1, empty_state)
    by_customer: dict[str, list] = {}
    for customer, app, platform, _ in syncer.targets(include_disabled=True):
        by_customer.setdefault(customer["name"], []).append((customer, app, platform))
    totals = {"ok": 0, "problem": 0, "never": 0, "reviews": 0}
    for name, targets in by_customer.items():
        print(heading(name))
        rows = []
        for customer, app, platform in targets:
            s = get_target_state(state, customer["id"], app["id"], platform) or {}
            stab = get_target_state(state, customer["id"], app["id"], "apple-stability") if platform == "apple" else None
            status = s.get("status", "never_synced")
            totals["reviews"] += s.get("reviewCount", 0)
            totals["ok" if status == "ok" else "never" if status == "never_synced" else "problem"] += 1
            stab_cell = "–" if platform != "apple" else (
                (f"{status_badge(stab['status'])} {stab.get('reviewCount', 0)} Zeilen" if stab.get("reviewCount") else f"{status_badge(stab['status'])} (keine Daten)") if stab else paint("○ nie abgerufen"))
            error = s.get("lastError") or (stab or {}).get("lastError")
            rows.append([app["name"], platform.capitalize(), status_badge(status), str(s.get("reviewCount", 0)),
                         ago(s.get("lastSuccessfulSync")), stab_cell, paint(error[:60], "31") if error else ""])
        print(table(["App", "Plattform", "Rezensionen-Status", "Anzahl", "Letzter Erfolg", "Stabilität", "Fehler"], rows,
                    ["left", "left", "left", "right", "left", "left", "left"]))
    print(f"\n{paint('Gesamt:', '1')} {totals['reviews']} Rezensionen · {paint(str(totals['ok']) + ' ok', '32')} · "
          f"{paint(str(totals['problem']) + ' mit Problem', '31') if totals['problem'] else '0 mit Problem'} · "
          f"{totals['never']} nie abgerufen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
