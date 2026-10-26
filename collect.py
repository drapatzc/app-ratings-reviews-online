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

from src.ai_analysis import run_ai  # noqa: E402
from src.apple_store_metrics import run_store_metrics  # noqa: E402
from src.backup import backup_data  # noqa: E402
from src.competitors import run_competitors  # noqa: E402
from src.config import active_ai_provider, competitors, load_config  # noqa: E402
from src.errors import ToolError  # noqa: E402
from src.logsetup import setup_logging  # noqa: E402
from src.models import utc_now  # noqa: E402
from src.reporting import load_topics  # noqa: E402
from src.security import redact  # noqa: E402
from src.storage import read_json, read_versioned, write_json  # noqa: E402
from src.sync import Options, Syncer, empty_state, get_target_state  # noqa: E402
from src.testing_sync import run_testing  # noqa: E402
from src.ui import COLOR, ago, fmt_int, fmt_seconds, heading, paint, progress_printer, status_badge, table  # noqa: E402

log = logging.getLogger("arr")
PLATFORM_NAMES = {"apple": "Apple", "google": "Google"}
# Status in der Zusammenfassung: Symbol, Text, Farbcodes
STATUS_CELL = {"ok": ("✔", "ok", ("32",)), "dry_run": ("✔", "Probelauf", ("32",)),
               "skipped": ("↷", "übersprungen", ("33",)), "partial": ("✖", "teilweise", ("1", "31")),
               "failed": ("✖", "Fehler", ("1", "31"))}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bewertungen und Rezensionen abrufen und als JSON speichern.")
    parser.add_argument("--config", default=str(ROOT / "config" / "config.json"), help="Pfad zur config.json")
    parser.add_argument("--customer", help="nur diesen Kunden (id) verarbeiten")
    parser.add_argument("--app", help="nur diese App (id) verarbeiten")
    parser.add_argument("--platform", choices=["apple", "google", "all"], default="all")
    parser.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD", help="Startdatum (Erstellungsdatum der Rezension)")
    parser.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD", help="Enddatum")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--incremental", action="store_true", default=None, help="inkrementell abrufen")
    mode.add_argument("--full-sync", action="store_true", help="vollständig abrufen (löscht nichts)")
    parser.add_argument("--force", action="store_true", help="Aktualisierungsfrist (minRefreshMinutes) ignorieren")
    parser.add_argument("--dry-run", action="store_true", help="abrufen, aber nichts speichern")
    parser.add_argument("--no-backup", action="store_true", help="keine Sicherungskopie von data/ vor dem Lauf (nicht empfohlen)")
    parser.add_argument("--status", action="store_true", help="Zustand anzeigen (ohne API-Zugriff)")
    parser.add_argument("--list-apps", action="store_true", help="konfigurierte Apps anzeigen (ohne API-Zugriff)")
    parser.add_argument("--import-google-csv", nargs="+", metavar="DATEI",
                   help="Play-Console-Export(e) importieren (benötigt --customer und --app)")
    parser.add_argument("--dataset", choices=["reviews", "stability", "store", "testing", "competitors", "ai", "all"],
                   default="reviews",
                   help="reviews (Standard), stability (Abstürze/Sitzungen, nur Apple), store (Downloads, Installationen, Store-Aufrufe, nur Apple), testing (Testdaten: Apple TestFlight, Google Testspuren), competitors (Wettbewerber-Apps, NUR APPLE, aus dem öffentlichen Apple-Feed, braucht customers[].competitors), ai (KI-Analyse der gespeicherten Rezensionen, braucht einen freigeschalteten Anbieter) oder all (competitors nur mit Einträgen, ai nur, wenn ein Anbieter aktiv ist)")
    parser.add_argument("--once-per-day", action="store_true",
                   help="höchstens ein erfolgreicher Lauf pro Kalendertag (UTC); für CI/cron. Fehlgeschlagene Läufe dürfen wiederholt werden")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="überschreibt settings.logLevel")
    return parser


def main(argv: list[str] | None = None, transport=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(Path(args.config).expanduser(),
                          {"incrementalSync": True if args.incremental else None,
                           "logLevel": args.log_level})
        setup_logging(cfg.settings["logLevel"], cfg.data_dir, "collect")
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
            safety_backup(cfg, args)
            res = syncer.import_google_csv(args.customer, args.app, [Path(file).expanduser() for file in args.import_google_csv])
            log.info("Import: neu %d, aktualisiert %d, unverändert %d, gesamt %d", res.new, res.updated, res.unchanged, res.total)
            return 0
        marker = cfg.data_dir / "last-daily.json"
        today = datetime.now(timezone.utc).date().isoformat()
        guard = args.once_per_day and not args.dry_run
        if guard and (read_json(marker, {}) or {}).get("date") == today:
            log.info("Heute (%s, UTC) bereits erfolgreich gelaufen – übersprungen (--once-per-day).", today)
            return 0
        safety_backup(cfg, args)
        results, total = [], 0.0
        if args.dataset in ("reviews", "all"):
            results += syncer.run()
            total += syncer.last_duration
        if args.dataset in ("stability", "all"):
            results += syncer.run_stability()
            total += syncer.last_duration
        if args.dataset in ("store", "all"):
            results += run_store_metrics(syncer)
            total += syncer.last_duration
        if args.dataset in ("testing", "all"):
            results += run_testing(syncer)
            total += syncer.last_duration
        if args.dataset in ("competitors", "all"):
            results += run_competitors(syncer, required=args.dataset == "competitors")
            total += syncer.last_duration
        if args.dataset == "ai" or (args.dataset == "all" and active_ai_provider(cfg.ai)[0]):
            results += run_ai(syncer, load_topics(cfg.base_dir / "config" / "themen.json")["topics"])
            total += syncer.last_duration
        elif args.dataset == "all":
            log.info("KI-Analyse übersprungen: kein Anbieter freigeschaltet (ai.providers in config/config.json).")
        print_summary(results, total)
        code = 1 if any(res.status in ("failed", "partial") for res in results) else 0
        if guard and code == 0:  # Marker nur nach vollständigem Erfolg: ein Fehlschlag darf am selben Tag wiederholt werden
            write_json(marker, {"schemaVersion": 1, "date": today, "dataset": args.dataset, "finishedAt": utc_now()})
        return code
    except ToolError as exc:
        print(f"[ERROR] {redact(exc)}", file=sys.stderr)
        return 2


def safety_backup(cfg, args) -> None:
    """Legt vor einem Lauf, der Daten ändert, ein ZIP von data/ unter settings.backupDirectory an (src/backup.py).

    Kein Probelauf, keine Sicherung mit --no-backup. Schlägt das Sichern fehl (Platte voll, keine Rechte), bricht der Lauf ab, damit
    nie ohne Sicherung geändert wird; --no-backup umgeht das bewusst.
    - Throws: ToolError, wenn das ZIP nicht geschrieben werden konnte.
    """
    if args.dry_run or args.no_backup:
        return
    try:
        backup_data(cfg.data_dir, cfg.backup_dir, int(cfg.settings["backupKeep"]))
    except OSError as exc:
        raise ToolError(f"Sicherung von {cfg.data_dir} nach {cfg.backup_dir} fehlgeschlagen ({exc.strerror or exc}); der Lauf wurde "
                        "nicht gestartet. Platz und Rechte prüfen oder mit --no-backup ohne Sicherung laufen lassen.") from exc


def print_summary(results, total_seconds: float) -> None:
    """Statistik am Ende: Dauer, Requests und Responses je App und Anbieter sowie gesamt."""

    def row(label, plat, kind, status, items, seconds=None):
        return [label, plat, kind, status, fmt_seconds(sum(res.duration for res in items) if seconds is None else seconds),
                fmt_int(sum(res.api_requests for res in items)), fmt_int(sum(res.responses for res in items)),
                fmt_int(sum(res.ok_responses for res in items)), fmt_int(sum(res.retries for res in items)),
                fmt_int(sum(res.new for res in items)), fmt_int(sum(res.updated for res in items)),
                fmt_int(sum(res.total for res in items))]

    rows = []
    for res in results:
        symbol, text, codes = STATUS_CELL.get(res.status, ("•", res.status, ()))
        rows.append(row(res.app_name or res.app, PLATFORM_NAMES[res.platform], res.label or "Rezensionen",
                        paint(f"{symbol} {text}", *codes), [res]))
    platforms = [pname for pname in PLATFORM_NAMES if any(res.platform == pname for res in results)]
    if len(platforms) > 1:
        for platform in platforms:
            rows.append([paint(cell, "1") for cell in row(f"Summe {PLATFORM_NAMES[platform]}", "", "", "",
                                                    [res for res in results if res.platform == platform])])
    rows.append([paint(cell, "1", "35") for cell in row("GESAMT", "", "", "", results, total_seconds)])
    print(heading("Zusammenfassung"))
    print(table(["App", "Anbieter", "Daten", "Status", "Dauer", "Requests", "Responses", "OK", "Retries", "Neu", "Änd.", "Gesamt"],
                rows, ["left", "left", "left", "left"] + ["right"] * 8))
    failed = [res for res in results if res.status in ("failed", "partial")]
    skipped = [res for res in results if res.status == "skipped"]
    kilobytes = sum(res.bytes_in for res in results) / 1024
    size = f"{kilobytes:.0f} KB" if kilobytes < 1024 else f"{kilobytes / 1024:.1f} MB".replace(".", ",")
    print(f"\nLaufzeit {fmt_seconds(total_seconds)} · {len(results)} {'Ziel' if len(results) == 1 else 'Ziele'} · "
          + (paint(f"{len(failed)} mit Fehler", "1", "31") if failed else paint("0 mit Fehler", "32"))
          + f" · {len(skipped)} übersprungen · {size} empfangen · {sum(res.network_errors for res in results)} Netzwerkfehler")
    print(paint("Requests = gesendete HTTP-Anfragen inkl. Wiederholungen · Responses = erhaltene Antworten · OK = Status 2xx · "
                "Stabilität und Store-Kennzahlen: Neu = neue Tagesberichte, Gesamt = gespeicherte Zeilen · "
                "KI-Analyse: Neu = neue Analysen, Gesamt = analysierte Rezensionen", "2" if COLOR else ""))
    for res in failed:
        first_error = res.errors[0] if res.errors else ""
        print(paint(f"  ✖ {res.app_name or res.app} / {PLATFORM_NAMES[res.platform]}: {first_error}", "31"))


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
        rivals = competitors(customer)
        if rivals:
            print(paint("  Wettbewerber (nur Apple, öffentlicher Apple-Feed, ohne Zugang):", "1"))
            rows = [[entry.get("id", "?"), entry.get("name", "?"), str((entry.get("apple") or {}).get("appId", "?")),
                     ", ".join((entry.get("apple") or {}).get("countries") or []),
                     paint("✔ aktiv", "32") if entry.get("enabled", True) and customer.get("enabled", True)
                     else paint("○ deaktiviert", "33")]
                    for entry in rivals]
            print(table(["ID", "Name", "Apple (App-ID)", "Länder", "Status"], rows))
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
            tstate = get_target_state(state, customer["id"], app["id"], platform) or {}
            stab = get_target_state(state, customer["id"], app["id"], "apple-stability") if platform == "apple" else None
            ai_state = get_target_state(state, customer["id"], app["id"], f"{platform}-ai")
            status = tstate.get("status", "never_synced")
            totals["reviews"] += tstate.get("reviewCount", 0)
            totals["ok" if status == "ok" else "never" if status == "never_synced" else "problem"] += 1
            stab_cell = "–" if platform != "apple" else (
                (f"{status_badge(stab['status'])} {stab.get('reviewCount', 0)} Zeilen" if stab.get("reviewCount") else f"{status_badge(stab['status'])} (keine Daten)") if stab else paint("○ nie abgerufen"))
            ai_cell = (f"{status_badge(ai_state['status'])} {ai_state.get('reviewCount', 0)} analysiert" if ai_state
                       else paint("○ keine", "2"))
            error = tstate.get("lastError") or (stab or {}).get("lastError") or (ai_state or {}).get("lastError")
            rows.append([app["name"], platform.capitalize(), status_badge(status), str(tstate.get("reviewCount", 0)),
                         ago(tstate.get("lastSuccessfulSync")), stab_cell, ai_cell, paint(error[:60], "31") if error else ""])
        print(table(["App", "Plattform", "Rezensionen-Status", "Anzahl", "Letzter Erfolg", "Stabilität", "KI", "Fehler"], rows,
                    ["left", "left", "left", "right", "left", "left", "left", "left"]))
    print(f"\n{paint('Gesamt:', '1')} {totals['reviews']} Rezensionen · {paint(str(totals['ok']) + ' ok', '32')} · "
          f"{paint(str(totals['problem']) + ' mit Problem', '31') if totals['problem'] else '0 mit Problem'} · "
          f"{totals['never']} nie abgerufen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
