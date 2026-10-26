#!/usr/bin/env python3
"""demo.py – erzeugt erfundene Testdaten für den Debug-Modus (kurzmenudebug.sh), ohne Netz und ohne die echten Daten.

Schreibt nach data-debug/ und config/config.debug.json (Logik in src/demo_data.py). Danach arbeiten
`collect.py --status --config config/config.debug.json` und `report.py --config config/config.debug.json` wie gewohnt.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.demo_data import CATEGORIES, DEBUG_CONFIG, DEFAULT_MONTHS, DEFAULT_VOLUME, PERIODS, VOLUMES  # noqa: E402
from src.demo_data import DemoOptions, generate, parse_range  # noqa: E402
from src.errors import ToolError  # noqa: E402
from src.security import redact  # noqa: E402
from src.ui import fmt_int, fmt_seconds, heading, table  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Erfundene Testdaten für den Debug-Modus erzeugen (kein Netz).")
    parser.add_argument("--config", default=str(ROOT / DEBUG_CONFIG),
                        help="Ziel der Debug-Konfiguration (Standard config/config.debug.json); wird überschrieben")
    parser.add_argument("--source-config", default=str(ROOT / "config" / "config.json"),
                        help="echte Konfiguration, aus der nur der KI-Block übernommen wird (Standard config/config.json)")
    parser.add_argument("--categories", default="all",
                        help="Kategorien, durch Komma getrennt, oder all (Standard). Liste: --list-categories")
    parser.add_argument("--volume", choices=list(VOLUMES), default=DEFAULT_VOLUME,
                        help="Umfang: Vorgabe für Rezensionen je App und Dichte der Kennzahlen")
    parser.add_argument("--months", type=int, default=DEFAULT_MONTHS,
                        help=f"Zeitraum in Monaten (Standard {DEFAULT_MONTHS}; im Menü wählbar: {', '.join(map(str, PERIODS))})")
    parser.add_argument("--reviews", metavar="MIN-MAX",
                        help="Bereich der Rezensionen je App, einmal für alle Apps (Standard aus --volume), z. B. 20-120")
    parser.add_argument("--apps", type=int, metavar="N",
                        help="höchstens N Apps je Kategorie (die ersten N; Standard: alle, Krankenkassen haben 30)")
    parser.add_argument("--seed", type=int, help="Startwert des Zufalls (Standard: aus der Wahl abgeleitet, reproduzierbar)")
    parser.add_argument("--list-categories", action="store_true", help="verfügbare Kategorien anzeigen und beenden")
    return parser


def list_categories() -> int:
    rows = [[key, category.label, str(len(category.apps)),
             ", ".join(sorted({platform for app in category.apps for platform in app.platforms}))]
            for key, category in CATEGORIES.items()]
    print(heading("Kategorien der Testdaten"))
    print(table(["Schlüssel", "Kategorie", "Apps", "Plattformen"], rows, ["left", "left", "right", "left"]))
    print("\nUmfang (--volume): " + " · ".join(f"{key} = {vol.reviews[0]}-{vol.reviews[1]} Rezensionen je App"
                                                for key, vol in VOLUMES.items()))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list_categories:
        return list_categories()
    try:
        categories = tuple(CATEGORIES) if args.categories.strip() == "all" else tuple(
            part.strip() for part in args.categories.split(",") if part.strip())
        opts = DemoOptions(categories=categories, volume=args.volume, months=args.months,
                           reviews=parse_range(args.reviews) if args.reviews else None, seed=args.seed, apps=args.apps)
        started = time.monotonic()
        print(f"▶ Testdaten erzeugen: {', '.join(categories)} · Umfang {opts.volume} · {opts.months} Monate · "
              f"{opts.review_range()[0]}-{opts.review_range()[1]} Rezensionen je App"
              + (f" · höchstens {opts.apps} Apps je Kategorie" if opts.apps else ""), flush=True)
        counts = generate(opts, ROOT, Path(args.config).expanduser(), Path(args.source_config).expanduser())
        print(heading("Zusammenfassung"))
        print(table(["Apps", "Ziele", "Rezensionen", "Stabilität (Zeilen)", "Store (Zeilen)", "Dauer"],
                    [[fmt_int(counts["apps"]), fmt_int(counts["targets"]), fmt_int(counts["reviews"]),
                      fmt_int(counts["stability"]), fmt_int(counts["store"]), fmt_seconds(time.monotonic() - started)]],
                    ["right"] * 6))
        print(f"\nDaten: {counts['dataDir']}\nKonfiguration: {counts['config']}\nStartwert (--seed): {counts['seed']}")
        print("Alle Werte sind erfunden. Echte Daten unter data/ wurden nicht angefasst.")
        return 0
    except ToolError as exc:
        print(f"[ERROR] {redact(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
