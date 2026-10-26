#!/usr/bin/env python3
"""report.py – erzeugt aus den gespeicherten JSON-Daten einen eigenständigen HTML-Bericht (ohne API-Zugriff)."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.config import DEFAULT_SETTINGS, Config, load_config  # noqa: E402
from src.errors import ToolError  # noqa: E402
from src.markdown import write_markdown  # noqa: E402
from src.reporting import PAGES, build_dataset, render_html, render_page  # noqa: E402
from src.security import redact  # noqa: E402
from src.storage import write_text  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="HTML-Bericht aus gespeicherten Daten erzeugen.")
    parser.add_argument("--config", default=str(ROOT / "config" / "config.json"))
    parser.add_argument("--data-dir", help="Datenverzeichnis (überschreibt settings.outputDirectory)")
    parser.add_argument("--output", help="Ausgabedatei (Standard: <reportDirectory>/index.html)")
    parser.add_argument("--customer", help="nur diesen Kunden (id) im Bericht")
    parser.add_argument("--app", help="nur diese App (id) im Bericht")
    parser.add_argument("--platform", choices=["apple", "google", "all"], default="all")
    parser.add_argument("--no-markdown", action="store_true", help="keine Markdown-Zusammenfassungen erzeugen")
    parser.add_argument("--days", type=int, default=14, help="Zeitraum der Markdown-Dateien in Tagen (Standard 14)")
    parser.add_argument("--until", metavar="YYYY-MM-DD", help="Ende des Markdown-Zeitraums (Standard: Datenstand)")
    parser.add_argument("--zip", action="store_true", help="Markdown-Dateien zusätzlich als ZIP zum Versenden packen")
    args = parser.parse_args(argv)
    try:
        # Der Bericht braucht nur Namen und Pfade; eine unvollständige Konfiguration (etwa ohne Zugänge) reicht.
        cfg_path = Path(args.config).expanduser()
        cfg = (load_config(cfg_path, strict=False) if cfg_path.is_file()
               else Config(settings=dict(DEFAULT_SETTINGS), customers=[], base_dir=ROOT))
        data_dir = Path(args.data_dir).expanduser() if args.data_dir else cfg.data_dir
        output = Path(args.output).expanduser() if args.output else cfg.report_dir / "index.html"
        dataset = build_dataset(data_dir, cfg.raw, args.customer, args.app, args.platform,
                                cfg.base_dir / "config" / "themen.json", cfg.base_dir / "config" / "fragen.json")
        year = date.today().year
        html = render_html(dataset, ROOT / "templates" / "report.html", year)
        write_text(output, html)  # atomar: ein Browser oder Webserver sieht nie eine halbe Datei
        for name in PAGES:  # Hilfe, Impressum, Datenschutz neben dem Bericht
            write_text(output.parent / f"{name}.html", render_page(name, ROOT / "templates", year))
        print(f"[INFO] Bericht erzeugt: {output} ({len(dataset['reviews'])} Rezensionen, {len(dataset['apps'])} App/Plattform-Einträge)")
        if not args.no_markdown:
            files = write_markdown(dataset, output.parent / "markdown", args.days, args.until, args.zip)
            print(f"[INFO] Markdown: {len([file for file in files if file.suffix == '.md'])} Dateien in {output.parent / 'markdown'}"
                  + (f" · ZIP: {files[-1]}" if args.zip else ""))
        return 0
    except (ToolError, ValueError, OSError) as exc:
        print(f"[ERROR] {redact(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
