#!/usr/bin/env python3
"""report.py – erzeugt aus den gespeicherten JSON-Daten einen eigenständigen HTML-Bericht (ohne API-Zugriff)."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.config import DEFAULT_SETTINGS  # noqa: E402
from src.errors import ToolError  # noqa: E402
from src.markdown import write_markdown  # noqa: E402
from src.reporting import PAGES, build_dataset, render_html, render_page  # noqa: E402
from src.security import redact, restrict_permissions  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="HTML-Bericht aus gespeicherten Daten erzeugen.")
    p.add_argument("--config", default=str(ROOT / "config" / "config.json"))
    p.add_argument("--data-dir", help="Datenverzeichnis (überschreibt settings.outputDirectory)")
    p.add_argument("--output", help="Ausgabedatei (Standard: <reportDirectory>/index.html)")
    p.add_argument("--customer", help="nur diesen Kunden (id) im Bericht")
    p.add_argument("--app", help="nur diese App (id) im Bericht")
    p.add_argument("--platform", choices=["apple", "google", "all"], default="all")
    p.add_argument("--no-markdown", action="store_true", help="keine Markdown-Zusammenfassungen erzeugen")
    p.add_argument("--days", type=int, default=14, help="Zeitraum der Markdown-Dateien in Tagen (Standard 14)")
    p.add_argument("--until", metavar="YYYY-MM-DD", help="Ende des Markdown-Zeitraums (Standard: Datenstand)")
    p.add_argument("--zip", action="store_true", help="Markdown-Dateien zusätzlich als ZIP zum Versenden packen")
    args = p.parse_args(argv)
    try:
        config, base = None, ROOT
        cfg_path = Path(args.config).expanduser()
        if cfg_path.is_file():
            config = json.loads(cfg_path.read_text(encoding="utf-8"))
            base = cfg_path.resolve().parent.parent if cfg_path.resolve().parent.name == "config" else cfg_path.resolve().parent
        settings = {**DEFAULT_SETTINGS, **((config or {}).get("settings") or {})}
        resolve = lambda v: Path(v).expanduser() if Path(v).expanduser().is_absolute() else (base / v).resolve()  # noqa: E731
        data_dir = Path(args.data_dir).expanduser() if args.data_dir else resolve(settings["outputDirectory"])
        output = Path(args.output).expanduser() if args.output else resolve(settings["reportDirectory"]) / "index.html"
        dataset = build_dataset(data_dir, config, args.customer, args.app, args.platform)
        year = date.today().year
        html = render_html(dataset, ROOT / "templates" / "report.html", year)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(html, encoding="utf-8")
        restrict_permissions(output)
        for name in PAGES:  # Hilfe, Impressum, Datenschutz neben dem Bericht
            page = output.parent / f"{name}.html"
            page.write_text(render_page(name, ROOT / "templates", year), encoding="utf-8")
            restrict_permissions(page)
        print(f"[INFO] Bericht erzeugt: {output} ({len(dataset['reviews'])} Rezensionen, {len(dataset['apps'])} App/Plattform-Einträge)")
        if not args.no_markdown:
            files = write_markdown(dataset, output.parent / "markdown", args.days, args.until, args.zip)
            print(f"[INFO] Markdown: {len([f for f in files if f.suffix == '.md'])} Dateien in {output.parent / 'markdown'}"
                  + (f" · ZIP: {files[-1]}" if args.zip else ""))
        return 0
    except (ToolError, ValueError, OSError) as exc:
        print(f"[ERROR] {redact(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
