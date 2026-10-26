#!/usr/bin/env python3
"""notify.py – meldet nach dem Tageslauf neue 1–2-★-Rezensionen, Ampelwechsel und Absturzsprünge (E-Mail, Slack, Webhook)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.config import load_config  # noqa: E402
from src.errors import ToolError  # noqa: E402
from src.logsetup import setup_logging  # noqa: E402
from src.notify import run_notify  # noqa: E402
from src.security import redact  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benachrichtigung nach dem Tageslauf: liest nur den Datenbestand, keine Store-API.")
    parser.add_argument("--config", default=str(ROOT / "config" / "config.json"), help="Pfad zur config.json")
    parser.add_argument("--dry-run", action="store_true", help="Nachricht anzeigen, nichts senden, Zustand nicht ändern")
    parser.add_argument("--test", action="store_true", help="Testnachricht an alle freigeschalteten Kanäle (prüft die Zugänge)")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="überschreibt settings.logLevel")
    return parser


def main(argv: list[str] | None = None, transport=None, smtp_factory=None, clock=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(Path(args.config).expanduser(), {"logLevel": args.log_level})
        setup_logging(cfg.settings["logLevel"], cfg.data_dir, "notify")
        return run_notify(cfg, dry_run=args.dry_run, test=args.test, transport=transport, smtp_factory=smtp_factory,
                          clock=clock)
    except ToolError as exc:
        print(f"[ERROR] {redact(exc)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
