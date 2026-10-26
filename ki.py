#!/usr/bin/env python3
"""ki.py – KI-Werkzeuge neben dem Abruf: Frage an die Rezensionen stellen, Themenvorschläge übernehmen, Verbrauch zeigen.

Die eigentliche Analyse läuft über `collect.py --dataset ai` (siehe `src/ai_analysis.py`). Dieses Skript ist ein
dünner Einstieg für `src/ai_ask.py` und `src/ai_themes.py`; die Logik liegt dort.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.ai_ask import ask, clear_questions, delete_question, load_questions  # noqa: E402
from src.ai_providers import AI_MODELS, AI_PRICES_DATE, PROVIDERS, UsageLedger, fmt_usd, price_for  # noqa: E402
from src.ai_service import serve  # noqa: E402
from src.ai_themes import accept, ignore, suggestions  # noqa: E402
from src.config import active_ai_provider, load_config  # noqa: E402
from src.errors import ConfigError, ToolError  # noqa: E402
from src.logsetup import setup_logging  # noqa: E402
from src.security import redact  # noqa: E402
from src.ui import fmt_int, heading, paint, table  # noqa: E402

CONFIDENCE_TEXT = {"sicher": "sichere Aussage", "hinweis": "Hinweis: wenig Belege", "unklar": "unklar, Rezensionen geben es nicht her"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="KI-Werkzeuge: Fragen, Themenvorschläge, Verbrauch.")
    parser.add_argument("--config", default=str(ROOT / "config" / "config.json"), help="Pfad zur config.json")
    sub = parser.add_subparsers(dest="command", required=True)
    ask_cmd = sub.add_parser("ask", help="Frage an die gespeicherten Rezensionen stellen (kostet eine Anfrage)")
    ask_cmd.add_argument("question", help="die Frage, in Anführungszeichen")
    ask_cmd.add_argument("--customer", help="nur dieser Kunde (id)")
    ask_cmd.add_argument("--app", action="append", help="nur diese App (id); mehrfach möglich für mehrere Apps")
    ask_cmd.add_argument("--platform", choices=["apple", "google", "all"], default="all")
    ask_cmd.add_argument("--from", dest="date_from", metavar="YYYY-MM-DD", help="nur Rezensionen ab diesem Tag")
    ask_cmd.add_argument("--to", dest="date_to", metavar="YYYY-MM-DD", help="nur Rezensionen bis zu diesem Tag")
    ask_cmd.add_argument("--stars-min", type=int, choices=range(1, 6), metavar="1-5", help="nur Rezensionen ab so vielen Sternen")
    ask_cmd.add_argument("--stars-max", type=int, choices=range(1, 6), metavar="1-5", help="nur Rezensionen bis so viele Sterne")
    ask_cmd.add_argument("--no-save", action="store_true", help="Antwort nicht in data/ai-questions.json ablegen")
    questions = sub.add_parser("questions", help="gespeicherte Fragen und Antworten anzeigen oder löschen (ohne Netzwerk)")
    questions.add_argument("--delete", type=int, metavar="NR", help="Frage mit dieser Nummer (aus der Liste) löschen")
    questions.add_argument("--clear", action="store_true", help="alle gespeicherten Fragen löschen")
    themes = sub.add_parser("themes", help="Themenvorschläge der KI anzeigen oder übernehmen (ohne Netzwerk)")
    themes.add_argument("--accept", type=int, metavar="NR", help="Vorschlag mit dieser Nummer nach config/themen.json übernehmen")
    themes.add_argument("--bereich", choices=["app", "anbieter"], help="Bereich des neuen Themas (optional)")
    themes.add_argument("--ignore", type=int, metavar="NR", help="Vorschlag mit dieser Nummer dauerhaft ablehnen")
    sub.add_parser("usage", help="Verbrauch und Kosten je Monat und je Kasse/App, aktiver Anbieter (ohne Netzwerk)")
    sub.add_parser("models", help="unterstützte Modelle je Anbieter mit Listenpreisen anzeigen (ohne Netzwerk)")
    srv = sub.add_parser("serve", help="lokalen Fragedienst für den Bericht starten (nur 127.0.0.1, Strg+C beendet)")
    srv.add_argument("--port", type=int, help="Port (Standard ai.servicePort, 0 = freier Port)")
    srv.add_argument("--report", action="store_true", help="nach dem Start den Bericht neu erzeugen (mit --customer/--app/--platform)")
    srv.add_argument("--open", action="store_true", help="mit --report: den Bericht danach im Browser öffnen")
    srv.add_argument("--customer", help="nur dieser Kunde (id) im Bericht")
    srv.add_argument("--app", help="nur diese App (id) im Bericht")
    srv.add_argument("--platform", choices=["apple", "google", "all"], default="all")
    return parser


def show_answer(entry: dict) -> None:
    print(heading("Antwort"))
    print(entry["answer"] or paint("(keine Antwort)", "33"))
    scope = (entry.get("scope") or {}).get("label")
    print(paint(f"\n{CONFIDENCE_TEXT.get(entry['confidence'], entry['confidence'])} · {entry['reviewCount']} von "
                f"{entry.get('availableCount', entry['reviewCount'])} Rezensionen gelesen" + (f" · Auswahl: {scope}" if scope else "") + " · "
                f"{entry['provider']}/{entry['model']} · {fmt_int(entry['inputTokens'] + entry['outputTokens'])} Tokens", "2"))
    if entry["quotes"]:
        print(heading("Belege"))
        for quote in entry["quotes"]:
            print(f"  „{quote['text']}“ · {quote.get('appName')} · {quote.get('rating')} ★ · {(quote.get('createdAt') or '')[:10]}")


def main(argv: list[str] | None = None, transport=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(Path(args.config).expanduser(), strict=args.command == "ask")
        setup_logging("WARNING", cfg.data_dir, "ki")  # Terminal nur Warnungen, Datei alles (Anfragen, Antwortfehler)
        if args.command == "ask":
            apps = args.app or []
            # Eine App: wie bisher über --app (Ordnerauswahl); mehrere: Kunde aus der Konfiguration, Apps über die Auswahl
            only_app = apps[0] if len(apps) == 1 else None
            selected_apps = []
            if len(apps) > 1:
                for customer in cfg.customers:
                    if args.customer and customer["id"] != args.customer:
                        continue
                    selected_apps += [f"{customer['id']}/{app['id']}" for app in customer.get("apps", []) if app["id"] in apps]
                if not selected_apps:
                    raise ConfigError(f"Keine der Apps {', '.join(apps)} steht in der Konfiguration.")
            selection = {"apps": selected_apps, "from": args.date_from, "to": args.date_to, "ratingMin": args.stars_min,
                         "ratingMax": args.stars_max, "label": " · ".join(part for part in [
                             ", ".join(apps) if len(apps) > 1 else None, f"ab {args.date_from}" if args.date_from else None,
                             f"bis {args.date_to}" if args.date_to else None,
                             f"{args.stars_min or 1}–{args.stars_max or 5} ★" if args.stars_min or args.stars_max else None] if part) or None}
            entry = ask(cfg, args.question, args.customer, only_app, args.platform, transport, save=not args.no_save, selection=selection)
            show_answer(entry)
            return 0
        if args.command == "questions":
            questions = load_questions(cfg.data_dir)["questions"]
            if args.clear:
                print(f"{clear_questions(cfg.data_dir)} Fragen gelöscht.")
                return 0
            if args.delete:
                if not 1 <= args.delete <= len(questions):
                    print(f"[ERROR] Es gibt keine Frage Nr. {args.delete} (vorhanden: {len(questions)}).", file=sys.stderr)
                    return 2
                entry = questions[args.delete - 1]
                delete_question(cfg.data_dir, entry["askedAt"], entry["question"])
                print(f"Gelöscht: Nr. {args.delete} „{entry['question']}“.")
                return 0
            if not questions:
                print("Noch keine Fragen gestellt (./ratings.sh ask \"…\").")
                return 0
            for number, entry in enumerate(questions, 1):  # älteste zuerst, Nummer für --delete
                print(f"\n{paint(str(number).rjust(3), '1', '36')}  {paint(entry['askedAt'][:16].replace('T', ' '), '2')}  {paint(entry['question'], '1')}")
                print(f"      {entry['answer']}  {paint('(' + CONFIDENCE_TEXT.get(entry['confidence'], entry['confidence']) + ')', '2')}")
            print(paint(f"\n{len(questions)} Fragen gespeichert (höchstens 100, die ältesten fallen weg). Löschen: ./ratings.sh ai-questions --delete NR, alle: --clear", "2"))
            return 0
        if args.command == "themes":
            return themes_command(cfg, args)
        if args.command == "models":
            return models_command(cfg)
        if args.command == "serve":
            return serve_command(cfg, args, transport)
        return usage_command(cfg)
    except ToolError as exc:
        print(f"[ERROR] {redact(exc)}", file=sys.stderr)
        return 2


def themes_command(cfg, args) -> int:
    themen = cfg.base_dir / "config" / "themen.json"
    found = suggestions(cfg.data_dir, themen)
    if args.accept or args.ignore:
        number = args.accept or args.ignore
        if not 1 <= number <= len(found):
            print(f"[ERROR] Es gibt keinen Vorschlag Nr. {number} (vorhanden: {len(found)}).", file=sys.stderr)
            return 2
        chosen = found[number - 1]
        if args.accept:
            topic_id = accept(themen, chosen, args.bereich)
            print(f"Übernommen: „{chosen['de']}“ als Thema '{topic_id}' mit {len(chosen['terms'])} Begriffen in {themen}. "
                  "Bericht neu erzeugen, damit das Thema erscheint.")
        else:
            ignore(cfg.data_dir, chosen["de"])
            print(f"Abgelehnt: „{chosen['de']}“ erscheint nicht mehr als Vorschlag.")
        return 0
    if not found:
        print("Keine offenen Themenvorschläge. Erst ./ratings.sh analyze laufen lassen; bekannte und abgelehnte Themen werden ausgeblendet.")
        return 0
    print(heading("Themenvorschläge der KI (nicht in config/themen.json)"))
    print(table(["Nr.", "Thema", "Englisch", "Rezensionen", "Apps", "Suchbegriffe"],
                [[str(index), entry["de"], entry["en"], str(entry["count"]), str(len(entry["apps"])), ", ".join(entry["terms"])]
                 for index, entry in enumerate(found, 1)], ["right", "left", "left", "right", "right", "left"]))
    print(paint("\nÜbernehmen: ./ratings.sh ai-themes --accept NR [--bereich app|anbieter] · Ablehnen: --ignore NR", "2"))
    return 0


def serve_command(cfg, args, transport=None) -> int:
    """Fragedienst im Vordergrund; der Bericht muss danach neu erzeugt werden, damit er Port und Token kennt."""
    port = args.port if args.port is not None else int(cfg.ai["servicePort"])

    def ready(server) -> None:
        print(heading("Fragedienst läuft"))
        print(f"  Adresse: http://127.0.0.1:{server.server_port} (nur dieser Rechner) · Anbieter {server.client.provider.name} / "
              f"{server.client.model}")
        if args.report:
            import report  # spät: nur hier gebraucht
            report_args = ["--config", args.config] + (["--customer", args.customer] if args.customer else []) \
                + (["--app", args.app] if args.app else []) + (["--platform", args.platform] if args.platform != "all" else [])
            if report.main(report_args) != 0:
                print("[ERROR] Bericht konnte nicht erzeugt werden; der Dienst läuft trotzdem.", file=sys.stderr)
            elif args.open:
                import webbrowser
                webbrowser.open((cfg.report_dir / "index.html").resolve().as_uri())
            print("  Der Bericht kennt den Dienst: unter „Fragen an die Daten“ steht jetzt ein Eingabefeld.")
        else:
            print("  Jetzt den Bericht neu erzeugen (./ratings.sh report), dann erscheint unter „Fragen an die Daten“ ein Eingabefeld.")
        print(paint("  Beenden mit Strg+C; danach verschwindet das Eingabefeld beim nächsten Erzeugen des Berichts.", "2"))
    server = serve(cfg, port, transport, on_ready=ready)
    print(f"\nFragedienst beendet · {server.questions_answered} Fragen beantwortet.")
    return 0


def models_command(cfg) -> int:
    """Modellliste je Anbieter mit Preisen; markiert das konfigurierte Modell je Anbieter und den aktiven Anbieter."""
    active, _ = active_ai_provider(cfg.ai)
    configured = {entry.get("name"): entry for entry in cfg.ai["providers"] if isinstance(entry, dict)}
    print(heading(f"Unterstützte KI-Modelle (Listenpreise in US-Dollar je Million Tokens, Stand {AI_PRICES_DATE})"))
    rows = []
    for name, models in AI_MODELS.items():
        chosen = (configured.get(name) or {}).get("model")
        shown = (configured.get(name) or {}).get("label") or PROVIDERS[name].label   # lokaler Anbieter: eigener Name
        for info in models:
            mark = ""
            if chosen == info.ident:
                mark = paint("aktiv", "32") if active and active["name"] == name else "konfiguriert"
            price_in, price_out = (("lokal", "lokal") if PROVIDERS[name].local
                                   else (fmt_usd(info.input_per_million), fmt_usd(info.output_per_million)))
            rows.append([shown, info.ident, price_in, price_out, info.note, mark])
        if chosen and all(info.ident != chosen for info in models):
            note = ("jedes vom lokalen Server angebotene Modell funktioniert (Ollama: `ollama pull NAME`)" if PROVIDERS[name].local
                    else "nicht in der Liste: Preise in config.json eintragen")
            rows.append([shown, chosen, "?", "?", note,
                         paint("aktiv", "32") if active and active["name"] == name else "konfiguriert"])
    print(table(["Anbieter", "Modell (ai.providers[].model)", "rein", "raus", "Einordnung", ""], rows,
                ["left", "left", "right", "right", "left", "left"]))
    print(paint("  Auswahl: in config/config.json beim Anbieter \"model\" setzen; der erste Anbieter mit \"enabled\": true und "
                "gesetztem Schlüssel ist aktiv. Andere Modelle desselben Anbieters funktionieren auch, dann Preise selbst eintragen "
                "(priceInputPerMillion/priceOutputPerMillion). Preise aus Anbieterseiten und Übersichten, ohne Gewähr. "
                "Der Anbieter \"local\" läuft lokal und kostenlos (Ollama, LM Studio, llama.cpp u. a.): Modell laden, Name in \"model\" eintragen, bei anderer Adresse \"url\" setzen (KI.md).", "2"))
    return 0


def usage_command(cfg) -> int:
    provider, notes = active_ai_provider(cfg.ai)
    print(heading("KI-Anbieter"))
    for note in notes or ["ai.providers ist leer – KI ist aus"]:
        print("  " + (paint(note, "32") if note.endswith("Schlüssel)") else note))
    if provider:
        print(f"  Aktiv: {paint(provider['name'] + ' / ' + provider['model'], '1')} · Sprache {cfg.ai['language']} · "
              f"Texte senden: {'ja' if cfg.ai['sendReviewText'] else 'nein'} · Funktionen: "
              + ", ".join(name for name, on in cfg.ai["features"].items() if on))
        price = price_for(provider, provider["name"], provider["model"])
        if price:
            print(f"  Preis: {fmt_usd(price.input_per_million)} rein / {fmt_usd(price.output_per_million)} raus je Million Tokens "
                  f"({price.source})")
        else:
            print(paint("  Preis unbekannt: priceInputPerMillion/priceOutputPerMillion beim Anbieter in config.json eintragen, "
                        "sonst bleiben die Kosten „unbekannt“.", "33"))
    ledger = UsageLedger(cfg.data_dir / "ai-usage.json", int(cfg.ai["monthlyTokenLimit"]))
    months = ledger.doc.get("months", {})
    print(heading("Verbrauch und Kosten je Monat"))
    if not months:
        print("  Noch keine Anfragen.")
    else:
        cost = lambda entry: fmt_usd(entry.get("costUsd", 0.0)) + (" (+?)" if entry.get("unpricedRequests") else "")  # noqa: E731
        rows = [[month, fmt_int(entry["requests"]), fmt_int(entry["inputTokens"]), fmt_int(entry["outputTokens"]),
                 fmt_int(entry["inputTokens"] + entry["outputTokens"]), cost(entry)] for month, entry in sorted(months.items())]
        print(table(["Monat", "Anfragen", "Tokens rein", "Tokens raus", "Gesamt", "Kosten"], rows, ["left"] + ["right"] * 5))
        latest, entry = sorted(months.items())[-1]
        targets = entry.get("byTarget") or {}
        if targets:
            print(heading(f"Kosten je Kasse / App im Monat {latest}"))
            rows = [[name, fmt_int(item["requests"]), fmt_int(item["inputTokens"]), fmt_int(item["outputTokens"]), cost(item)]
                    for name, item in sorted(targets.items(), key=lambda pair: (-pair[1].get("costUsd", 0.0), pair[0]))]
            rows.append(["Gesamt", fmt_int(entry["requests"]), fmt_int(entry["inputTokens"]), fmt_int(entry["outputTokens"]), cost(entry)])
            print(table(["Kasse / App", "Anfragen", "Tokens rein", "Tokens raus", "Kosten"], rows, ["left"] + ["right"] * 4))
        else:
            print(paint("  Aufteilung je Kasse/App gibt es erst für Anfragen ab Schema 2 des Verbrauchsbuchs.", "2"))
    print(f"\n  Monatslimit: {fmt_int(ledger.limit)} Tokens · diesen Monat verbraucht: {fmt_int(ledger.used())} · "
          f"Kosten diesen Monat: {fmt_usd(ledger.month_cost())}")
    print(paint(f"  Kosten sind Schätzungen aus Tokens × Listenpreis (Stand {AI_PRICES_DATE} oder config.json), in US-Dollar, ohne "
                "Cache-Rabatte; „(+?)“ heißt: Anfragen ohne bekannten Preis, Summe ist eine Untergrenze. Maßgeblich ist die "
                "Rechnung des Anbieters.", "2"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
