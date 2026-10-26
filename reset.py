#!/usr/bin/env python3
"""reset.py – gespeicherte Daten löschen und neu anfangen (mit automatischem Backup und Rückfrage).

Gelöscht werden nur Daten (data/customers, state.json, sync-history.json) und der Bericht. Konfiguration, Schlüssel
und Programmcode bleiben immer unangetastet. Mit --customer/--app wird nur dieser Teil gelöscht.
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tarfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.config import load_config  # noqa: E402
from src.errors import ToolError  # noqa: E402
from src.storage import read_versioned, run_lock, write_json  # noqa: E402

CONFIRM_WORD = "LOESCHEN"


def size_of(path: Path) -> int:
    """Gesamtgröße einer Datei oder eines Ordners in Bytes."""
    if path.is_file():
        return path.stat().st_size
    return sum(file.stat().st_size for file in path.rglob("*") if file.is_file())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daten löschen und neu anfangen.")
    parser.add_argument("--config", default=str(ROOT / "config" / "config.json"))
    parser.add_argument("--customer", help="nur diesen Kunden löschen")
    parser.add_argument("--app", help="nur diese App löschen (mit --customer, sonst bei allen Kunden)")
    parser.add_argument("--no-backup", action="store_true", help="kein Backup vor dem Löschen (nicht empfohlen)")
    parser.add_argument("--keep-report", action="store_true", help="reports/index.html nicht löschen")
    parser.add_argument("--dry-run", action="store_true", help="nur anzeigen, nichts löschen")
    parser.add_argument("--yes", action="store_true", help="ohne Rückfrage (für Skripte)")
    args = parser.parse_args(argv)
    try:
        cfg_path = Path(args.config).expanduser()
        cfg = load_config(cfg_path)
        data_dir, report_dir = cfg.data_dir, cfg.report_dir
    except ToolError:
        data_dir, report_dir = ROOT / "data", ROOT / "reports"
    customers_dir = data_dir / "customers"
    partial = bool(args.customer or args.app)

    # --- Was würde gelöscht? ---
    targets: list[Path] = []
    if partial:
        for cdir in sorted(customers_dir.iterdir()) if customers_dir.is_dir() else []:
            if args.customer and cdir.name != args.customer:
                continue
            if args.app:
                for group in ("apps", "competitors"):  # Wettbewerber liegen getrennt unter competitors/
                    adir = cdir / group / args.app
                    if adir.exists():
                        targets.append(adir)
            else:
                targets.append(cdir)
    else:
        candidates = (customers_dir, data_dir / "state.json", data_dir / "sync-history.json", data_dir / "last-daily.json",
                      data_dir / "ai-questions.json", data_dir / "ai-usage.json", data_dir / "ai-themes.json")
        targets = [target for target in candidates if target.exists()]
        if not args.keep_report and (report_dir / "index.html").exists():
            targets.append(report_dir / "index.html")
    if not targets:
        print("Nichts zu löschen – es sind keine passenden Daten vorhanden.")
        return 0
    print("Folgendes wird gelöscht:" if not args.dry_run else "Trockenlauf – folgendes würde gelöscht:")
    for target in targets:
        print(f"  - {target}  ({size_of(target) / 1024:.0f} KB)")
    if partial:
        print("  - zugehörige Einträge in data/state.json")
    print("Konfiguration, Schlüssel und Programm bleiben unberührt.")
    if args.dry_run:
        return 0

    # --- Rückfrage ---
    if not args.yes:
        print(f"\nZur Bestätigung bitte {CONFIRM_WORD} eingeben (alles andere bricht ab).")
        try:
            answer = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            answer = ""
        if answer != CONFIRM_WORD:
            print("Abgebrochen. Es wurde nichts gelöscht.")
            return 1

    try:
        with run_lock(data_dir / ".lock"):
            # --- Backup ---
            if not args.no_backup:
                backup_dir = ROOT / "backups"
                backup_dir.mkdir(exist_ok=True)
                backup = backup_dir / f"backup-{datetime.now():%Y-%m-%d-%H%M%S}.tgz"
                with tarfile.open(backup, "w:gz") as tar:
                    for target in targets + [data_dir / "state.json"]:
                        if target.exists():
                            inside = data_dir.parent in target.parents
                            tar.add(target, arcname=str(target.relative_to(data_dir.parent)) if inside else target.name)
                backup.chmod(0o600)
                print(f"Backup erstellt: {backup}")
            # --- Löschen ---
            for target in targets:
                shutil.rmtree(target) if target.is_dir() else target.unlink()
            if partial:
                state_path = data_dir / "state.json"
                if state_path.exists():
                    state = read_versioned(state_path, 1, lambda: {"schemaVersion": 1, "customers": {}})
                    for cid in list(state["customers"]):
                        if args.customer and cid != args.customer:
                            continue
                        if args.app:
                            for group in ("apps", "competitors"):
                                state["customers"][cid].get(group, {}).pop(args.app, None)
                        else:
                            state["customers"].pop(cid)
                    write_json(state_path, state)
    except ToolError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    print("Gelöscht. Neu anfangen mit: ./ratings.sh all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
