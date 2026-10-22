#!/usr/bin/env python3
"""menu.py – Menü für collect.py und report.py: Parameter wählen statt auswendig kennen."""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ---- Optik: Farben nur auf echten Terminals (nicht bei Pipes, NO_COLOR=1 schaltet ab) ----
COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
ICONS = {"everything": "🚀", "fetch": "⬇️ ", "report": "📊", "open": "🌐", "select": "🎯", "info": "ℹ️ ", "csv": "📥",
         "normal": "🔄", "full": "♻️ ", "force": "⚡", "stab": "🛡️ ", "all": "🚀", "dry": "🧪", "range": "📅",
         "toggle": "🔁", "customer": "🏢", "app": "📱", "platform": "🖥️ ", "clearrange": "🧹", "reset": "↩️ ",
         "reset": "🗑️ ", "markdown": "📝", "docs": "📚", "summ": "🗒️ ", "regen": "🔄", "zip": "📦", "wipeall": "💥", "wipesel": "🧹", "status": "📋", "apps": "🗂️ ", "test": "✅"}
GRADIENT = (63, 99, 135, 171, 207)


def paint(text: str, *codes: str) -> str:
    """Färbt Text mit ANSI-Codes, sofern das Terminal Farben kann."""
    return f"\033[{';'.join(codes)}m{text}\033[0m" if COLOR and codes else text


def gradient(text: str) -> str:
    """Farbverlauf (Indigo → Pink) über den Text."""
    if not COLOR:
        return text
    return "".join(f"\033[1;38;5;{GRADIENT[min(len(GRADIENT) - 1, i * len(GRADIENT) // max(1, len(text)))]}m{ch}"
                   for i, ch in enumerate(text)) + "\033[0m"


# Bildschirm leeren und auf Enter warten nur auf echten Terminals; in Pipes, Logs und Tests bleibt alles erhalten.
TTY_OUT = sys.stdout.isatty()
TTY_IN = sys.stdin.isatty()


def clear_screen() -> None:
    """Leert den Bildschirm samt Scroll-Puffer (nur auf echten Terminals)."""
    if TTY_OUT:
        print("\033[H\033[2J\033[3J", end="", flush=True)


def banner() -> None:
    """Kopfzeile des Programms."""
    width = min(shutil.get_terminal_size((80, 24)).columns, 78)
    print()
    print(gradient("  ╭" + "─" * (width - 6) + "╮"))
    for line, sub in (("APP RATINGS & REVIEWS", True), ("Apple · Google · Stabilität", False)):
        pad = (width - 6 - len(line)) // 2
        body = " " * pad + (gradient(line) if sub else line) + " " * (width - 6 - pad - len(line))
        print(paint("  │", "35") + body + paint("│", "35"))
    print(gradient("  ╰" + "─" * (width - 6) + "╯"))

from src.config import DEFAULT_SETTINGS, load_config  # noqa: E402
from src.ui import ago  # noqa: E402
from src.errors import ToolError  # noqa: E402

CONFIG = ROOT / "config" / "config.json"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


HELP_SHORT = """
HILFE – KURZMENÜ
================
Das Kurzmenü enthält nur die drei wichtigsten Funktionen. Alles Weitere (Auswahl einer App, Zeitraum,
Markdown-Dateien, CSV-Import, Daten löschen) bietet das große Menü: menu.sh bzw. ./ratings.sh menu.

1  Alles abrufen
   Holt Rezensionen, Stabilität (Abstürze, Sitzungen) und Testbetrieb (TestFlight, Google-Testspuren) für alle Apps und erzeugt danach den Bericht
   und die Markdown-Zusammenfassungen neu. Kein ZIP, der Browser öffnet sich nicht.
   Befehl: python collect.py --dataset all, danach python report.py
   Mehrfaches Ausführen ist gefahrlos: Es entstehen keine Duplikate. Wurde eine App vor weniger als
   30 Minuten abgerufen, wird sie übersprungen (Einstellung minRefreshMinutes).

2  Status
   Zeigt je App den letzten erfolgreichen Abruf, die Anzahl der Rezensionen, den Stand der Stabilität
   und Fehler. Braucht kein Internet.
   Befehl: python collect.py --status

3  Bericht anzeigen
   Öffnet reports/index.html im Browser. Fehlt der Bericht, wird er vorher erzeugt.

Dateien:   Daten in data/, Bericht in reports/index.html, Zusammenfassungen in reports/markdown/
Fehler:    Status „Fehler“ oder „teilweise“ → Punkt 2 zeigt die Meldung. Häufige Ursachen: kein Internet,
           Apple-Schlüssel (.p8) fehlt oder wurde widerrufen, config/config.json fehlerhaft.
Beenden:   Q oder Strg+C
"""


HELP_MAIN = """
HILFE – HAUPTMENÜ
=================
Zweck: Alle Befehle von collect.py (Abruf) und report.py (Bericht) ohne Parameter-Wissen bedienen.
Jeder Menüpunkt zeigt vor dem Start den echten Befehl ("$ python collect.py …") – so lernst du die Kommandozeile.
Die Auswahl (Kunde/App/Plattform/Zeitraum) oben gilt für ALLE Abrufe, bis du sie änderst oder das Menü beendest.

Punkte
  1) ALLES AUF EINMAL     collect.py --dataset all [Auswahl], danach report.py und Browser. Holt Rezensionen, Stabilität UND Testbetrieb
                          (Stabilität und TestFlight nur Apple, Google-Testspuren nur Google). Der komplette Standardlauf; mehrfaches Ausführen ist gefahrlos (keine Duplikate).
                          Apps, die in den letzten 30 Minuten liefen, werden übersprungen (Wartefrist) – für Zwang: Abruf-Menü, Punkt 3.
  2) Daten abrufen …      Untermenü: einzelne Abrufarten (nur Rezensionen, nur Stabilität, nur Testbetrieb, vollständig, Probelauf, Zeitraum).
  3) Bericht erzeugen …   Startet report.py: liest NUR die lokalen JSON-Dateien (kein Netzwerk, keine API) und schreibt
                          reports/index.html; öffnet danach den Browser. Die Auswahl oben (Kunde/App/Plattform) gilt auch hier.
  4) Letzten Bericht …    Öffnet reports/index.html ohne Neuerzeugung (zeigt also den alten Stand).
  5) Auswahl ändern …     Untermenü: Kunde, App, Plattform, Zeitraum festlegen (nur im Menü gespeichert, nicht in der Datei).
  6) Status und Übersicht Untermenü: Zustand je App ansehen (ohne Netzwerk), Apps auflisten, Tests starten.
  7) Google-CSV …         Importiert Play-Console-Exporte (historische Google-Rezensionen). Braucht Kunde UND App in der Auswahl.
  8) Markdown-Dateien …   Dokumentation und Zusammenfassungen (14 Tage je App/Plattform) auswählen und im Editor öffnen,
                          neu erzeugen, als ZIP zum Versenden packen.
  9) Daten löschen …      Untermenü mit Backup und Rückfrage (siehe dortige Hilfe).
  Q) Beenden             In jedem Menü: beendet das Programm. 0 = eine Ebene zurück (in Untermenüs).

Duplikate: Jede Rezension hat die ID plattform:storeAppId:reviewId; Stabilitätszeilen sind je Tag/Version/OS/Gerät eindeutig und
bereits geladene Berichtsinstanzen werden nicht erneut geholt. Mehrfaches Lesen erzeugt daher keine doppelten Einträge.
Einzige Falle: App-IDs in config.json NICHT umbenennen – die ID ist der Ordnername unter data/, eine neue ID legt einen neuen Ordner an.

Tasten und Hinweise
  Tasten        Zahl = Auswahl, 0 = zurück, Q = beenden, H = diese Hilfe.
  Abbrechen     Strg+C beendet einen laufenden Abruf; bereits geholte Daten bleiben erhalten.
  Kopfzeile     „Letzter Abruf" = jüngster erfolgreicher Abruf aller Apps, „Bericht" = Alter von reports/index.html.
  Doku          ANLEITUNG.md (Bedienung), README.md (alle Befehle), BETRIEB.md (täglicher Lauf, Server).
                Für Entwickler: TECHNIK.md.
"""

HELP_FETCH = """
HILFE – DATEN ABRUFEN
=====================
Jeder Punkt startet collect.py mit der aktuellen Auswahl (Kunde/App/Plattform/Zeitraum). Am Ende steht eine Statistik:
Dauer, Requests (gesendete HTTP-Anfragen inkl. Wiederholungen), Responses (erhaltene Antworten), OK (2xx), Retries, neu/geändert.

  1) Abrufen (automatisch)   collect.py [Auswahl]            Nur REZENSIONEN. Erster Lauf pro App: alles; danach inkrementell
                             (Apple: neueste Seiten bis "letzter Erfolg − overlapDays"; Google: ohnehin nur die letzten 7 Tage).
                             Apps, die in den letzten minRefreshMinutes (Standard 30) erfolgreich liefen, werden ÜBERSPRUNGEN (0 Anfragen).
  2) Vollständig neu lesen   --full-sync                      Nur REZENSIONEN. Liest alles neu; erkennt nachträgliche Änderungen alter
                             Apple-Rezensionen. Löscht nie etwas. Passiert automatisch alle fullSyncIntervalDays (30).
  3) Wartefrist ignorieren   --force                          Nur REZENSIONEN. Wie 1), aber ohne die 30-Minuten-Sperre.
  4) Stabilität abrufen      --dataset stability              NUR STABILITÄT (Apple Analytics: Abstürze, Sitzungen je Tag/Version/OS/Gerät).
                             Lädt nur neue Berichtsinstanzen; erster Lauf je App ca. 100–150 Anfragen. Ändert nichts bei Apple.
  5) Testbetrieb abrufen     --dataset testing               NUR TESTBETRIEB (Apple TestFlight: Builds, Installationen, Sitzungen, Abstürze;
                             Google Play: Testspuren und Absturzraten je Versionscode, noch nicht live geprüft). Im Bericht unter „Testbetrieb“.
  6) Rezensionen, Stabilität --dataset all                    Alles nacheinander. Das ist der Komplett-Abruf.
     UND Testbetrieb
  7) Probelauf               --dry-run                        Nur REZENSIONEN. Ruft ab, speichert NICHTS, zeigt was neu wäre (kostet echte Anfragen).
  8) Nur einen Zeitraum      --from YYYY-MM-DD --to YYYY-MM-DD   Nur REZENSIONEN. Filtert nach Erstellungsdatum; setzt den Sync-Zustand
                             NICHT weiter. Datum wird abgefragt (Enter = offen).
  9) Bericht danach öffnen   Schaltet um, ob nach einem Abruf automatisch report.py läuft und der Browser öffnet.

Wichtig
  - Punkte 1, 2, 3, 7, 8 holen weder Stabilität noch Testbetrieb. Für alles: Punkt 6 (oder ./ratings.sh all).
  - Stabilität gibt es nur für Apple; Google-Apps werden dabei ignoriert.
  - Ergebnis-Status je Ziel: ok | partial (Teilfehler, bisher Geholtes gesichert) | failed | skipped (Wartefrist) | dry_run.
  - 401/403 = Zugangsdaten/Berechtigung prüfen (Key ID muss zur .p8-Datei passen). 429/5xx = automatische Wiederholung mit Backoff.
  - Fehler einer App stoppen die anderen nicht. Exit-Code 1 bei Fehlern.
  - Dateien: reviews.json, review-history.json, versions.json, ratings-history.json bzw. stability-metrics.json; Zustand in data/state.json.
"""

HELP_SELECT = """
HILFE – AUSWAHL ÄNDERN
======================
Legt fest, WAS die Abrufe verarbeiten. Gilt bis zum Beenden des Menüs (wird nicht in config.json gespeichert).
Entspricht den Optionen --customer, --app, --platform, --from, --to von collect.py.

  Kunde wählen     --customer ID   Beschränkt auf einen Kunden. Setzt die App-Auswahl zurück.
  App wählen       --app ID        Beschränkt auf eine App (IDs stehen in config.json, z. B. scanbox). Gut zum schnellen Testen.
  Plattform wählen --platform apple|google|all
  Zeitraum setzen  --from / --to   Format YYYY-MM-DD, nach Erstellungsdatum der Rezension. Wirkt nur beim Abruf-Punkt
                                   "Nur einen Zeitraum abrufen" im Abruf-Menü.
  Zeitraum löschen Setzt von/bis zurück.
  Alles zurücksetzen  Kunde, App, Zeitraum leer, Plattform alle.

Hinweise
  - Deaktivierte Kunden/Apps/Plattformen ("enabled": false in config.json) werden nie abgerufen, auch wenn ausgewählt.
  - Kunde, App und Plattform gelten auch für den Bericht (report.py --customer/--app/--platform); der Zeitraum nicht.
    Für den Bericht über ALLE Apps: Auswahl zurücksetzen.
  - Für CSV-Import (Hauptmenü 6) müssen Kunde UND App gesetzt sein.
"""

HELP_PICK = """
HILFE – LISTE
=============
Zahl wählen übernimmt den Eintrag. Der erste Eintrag ("Alle …") hebt die Einschränkung auf. 0 geht zurück ohne Änderung.
Die Einträge kommen aus config/config.json (id und Name). Die ID ist der Ordnername unter data/ und sollte nie geändert werden.
"""

HELP_INFO = """
HILFE – STATUS UND ÜBERSICHT
============================
Alles hier läuft OHNE Netzwerk und ändert keine Daten (außer Tests, die nur in temporären Ordnern arbeiten).

  Status je App    collect.py --status
                   Je Kunde/App/Plattform: status (ok/partial/failed/never_synced), Anzahl Rezensionen, letzter Erfolg,
                   letzter Versuch, letzter Fehler. Quelle: data/state.json. Stabilität steht unter "apple-stability".
  Apps anzeigen    collect.py --list-apps
                   Alle konfigurierten Kunden/Apps/Plattformen inkl. deaktivierter ("aus"). Prüft nebenbei die Konfiguration.
  Tests ausführen  python -m pytest tests -q
                   Automatische Tests mit Fake-Servern (keine Zugangsdaten, kein Netzwerk). Sollte immer grün sein; sonst Fehler melden.

Fehlersuche
  - "Zugangsdaten fehlen": privateKeyFile/Umgebungsvariable in config.json prüfen.
  - HTTP 401: Key ID passt nicht zur .p8, falsche Issuer ID oder fehlende Rolle des API-Schlüssels.
  - "Ein anderer collect.py-Lauf ist aktiv": läuft noch ein Prozess; data/.lock zeigt die Sperre.
  - "Beschädigte JSON-Datei": Datei bleibt unberührt; aus Backup wiederherstellen (./ratings.sh backup legt Sicherungen an).
"""

HELP_CSV = """
HILFE – GOOGLE-CSV IMPORT
=========================
Importiert die monatlichen Rezensions-Exporte der Google Play Console (Berichte herunterladen > Rezensionen,
Dateien wie reviews_<package>_YYYYMM.csv, meist UTF-16). Nötig, weil die Google-API nur die letzten 7 Tage liefert.
  - Vorher unter "Auswahl ändern" Kunde UND App wählen (und die Google-Plattform muss in config.json aktiviert sein).
  - Pfade durch Leerzeichen trennen (Platzhalter wie ~/Downloads/reviews_*.csv gehen nur auf der Kommandozeile).
  - Die Review-ID wird aus dem "Review Link" gelesen; Zeilen ohne ID werden übersprungen.
  - Duplikate werden erkannt (Schlüssel platform+package+reviewId), Änderungen kommen in review-history.json.
Befehl: collect.py --import-google-csv DATEI… --customer ID --app ID
"""


HELP_RESET = """
HILFE – DATEN LÖSCHEN UND NEU ANFANGEN
======================================
Löscht gespeicherte Daten (reset.py). Vorher wird IMMER ein Backup in backups/ angelegt (tgz) und du musst LOESCHEN eintippen.
Konfiguration (config.json), Schlüssel (.p8) und Programm bleiben unberührt.

  Nur die AUSGEWÄHLTE App/den Kunden   reset.py --customer ID --app ID
        Löscht den Datenordner dieser App (auch wenn sie nicht mehr in config.json steht, z. B. ein alter Ordner "my-app")
        und ihre Einträge in state.json. Nutzt die Auswahl aus "Auswahl ändern" (Plattform wird ignoriert).
  ALLES löschen                        reset.py
        Löscht data/customers, data/state.json, data/sync-history.json und reports/index.html. Danach beginnt der nächste Abruf wieder
        bei null: Rezensionen komplett neu, Stabilität ab der Historie, die Apple noch bereithält.
  Trockenlauf                          reset.py … --dry-run
        Zeigt nur, was gelöscht würde.

Hinweise
  - Google: Die API liefert nur die letzten 7 Tage. Gelöschte ältere Google-Rezensionen sind NUR über das Backup oder
    die Play-Console-CSV (Import) wiederherstellbar. Apple-Rezensionen und Stabilität kommen großteils wieder.
  - Wiederherstellen: tar xzf backups/backup-DATUM.tgz -C . (im Projektordner).
  - Zum Neuanfang danach: Hauptmenü Punkt 1 (Alles auf einmal).
"""

HELP_MARKDOWN = """
HILFE – MARKDOWN-DATEIEN
========================
Markdown (.md) sind einfache Textdateien mit Überschriften und Tabellen – gut zum Lesen, Bearbeiten und Verschicken.

  Dokumentation öffnen        ANLEITUNG.md (Kurzanleitung), README.md (kompakt und komplett), STAGE2.md (Stabilität).
  Zusammenfassungen öffnen    reports/markdown/<App>-<apple|google>.md: die letzten 14 Tage je App und Plattform, dazu
                              00-uebersicht.md (Tabelle aller Apps mit Links). Nach der Auswahl entscheidest du:
                              E = im Editor (Rohtext bearbeiten) oder Enter/B = im Browser (formatiert, mit Tabellen und Farben).
                              Der Browser zeigt eine erzeugte HTML-Kopie in reports/markdown/_html/ – Änderungen gehören in die .md-Datei.
  Neu erzeugen                report.py [Auswahl]: baut Bericht UND Markdown neu aus den gespeicherten JSON-Daten (kein Netzwerk).
                              Die Dateien werden dabei ersetzt – eigene Änderungen daran gehen verloren (Kopie speichern!).
  ZIP erzeugen                report.py --zip: packt alle Zusammenfassungen in reports/zusammenfassung-<Datum>.zip und zeigt
                              sie im Finder – bereit zum Versenden.

Editor
  Standard unter macOS: Standard-Texteditor (open -t). Eigener Editor per Umgebungsvariable, die erste gesetzte gilt:
      MD_EDITOR   z. B.  export MD_EDITOR="open -a 'Visual Studio Code'"     (oder "code", "nano", "vim")
      VISUAL / EDITOR   die üblichen Variablen. Terminal-Editoren (nano, vim) laufen direkt im Menü; danach geht es weiter.
  Dauerhaft: die export-Zeile in ~/.zshrc eintragen.
"""

class QuitMenu(Exception):
    """Q wurde gedrückt: Programm aus jedem Menü heraus beenden."""


class Menu:
    """Hält die aktuelle Auswahl (Kunde, App, Plattform, Zeitraum) und führt Befehle aus."""

    def __init__(self) -> None:
        self.customer: str | None = None
        self.app: str | None = None
        self.platform = "all"
        self.date_from: str | None = None
        self.date_to: str | None = None
        self.open_after = True
        self.pause_pending = False  # True, wenn seit dem letzten Menü etwas ausgegeben wurde (vor dem Leeren warten)
        self.note = ""  # Hinweis, der beim nächsten Menü unter dem Kopf erscheint (z. B. ungültige Eingabe)
        self.show_summary = True  # Auswahlzeile anzeigen; das Kurzmenü kennt keine Auswahl

    # ---- Hilfen ----
    def ask(self, prompt: str) -> str:
        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return "0"

    def say(self, *parts) -> None:
        """Gibt eine Meldung aus und merkt sich, dass vor dem nächsten Menü auf Enter gewartet wird."""
        print(*parts)
        self.pause_pending = True

    def pause_if_needed(self) -> None:
        """Wartet auf Enter, falls seit dem letzten Menü etwas ausgegeben wurde (nur auf echten Terminals)."""
        if self.pause_pending and TTY_IN and TTY_OUT:
            self.ask("\n" + paint("Weiter mit Enter …", "2"))
        self.pause_pending = False

    def screen(self) -> None:
        """Neuer, leerer Bildschirm mit Kopfzeile und, im großen Menü, der aktuellen Auswahl."""
        self.pause_if_needed()
        clear_screen()
        banner()
        print("  " + self.freshness())
        if self.show_summary:
            print("\n" + self.summary())
        if self.note:
            print("\n" + self.note)
            self.note = ""

    def choose(self, title: str, entries: list[tuple[str, str]], back: str = "Zurück", help_text: str = HELP_PICK,
               root: bool = False) -> str:
        """Zeigt nummerierte Einträge und liefert den gewählten Schlüssel oder '0' (zurück). H = Hilfe.

        Q beendet das Programm aus jedem Menü (QuitMenu). Im obersten Menü (`root`) gibt es kein „Zurück“,
        dort steht nur Q; 0 funktioniert dort still weiter.
        """
        while True:
            self.screen()
            cols = min(shutil.get_terminal_size((80, 24)).columns, 100)
            print("\n" + paint("╭─ ", "35") + paint(title, "1", "35") + " " + paint("─" * max(4, cols - len(title) - 8), "35"))
            bar = paint("│", "35")
            for i, (key, text) in enumerate(entries, 1):
                print(f"{bar} {paint(str(i), '1', '36')}  {ICONS.get(key, '•')} {text}")
            print(bar)
            print(f"{bar} {paint('H', '1')}  ❓ Hilfe zu diesem Menü")
            if not root:
                print(f"{bar} {paint('0', '1')}  ↩ {back}")
            print(f"{bar} {paint('Q', '1')}  ⏻ Beenden" + (f"   {back}" if root and back else ""))
            print(paint("╰" + "─" * (cols - 2), "35"))
            answer = self.ask(paint("➜ ", "1", "35") + "Auswahl: ")
            if answer.lower() == "h":
                clear_screen()
                print(help_text)
                self.ask("(Enter zum Fortfahren) ")
                continue
            if answer.lower() == "q":
                raise QuitMenu
            if answer == "0":
                return "0"
            if answer.isdigit() and 1 <= int(answer) <= len(entries):
                clear_screen()  # die gewählte Aktion startet auf leerem Bildschirm
                return entries[int(answer) - 1][0]
            keys = "eine Nummer, H oder Q (beenden)" if root else "eine Nummer, H, 0 (zurück) oder Q (beenden)"
            self.note = paint(f"Ungültige Eingabe „{answer}“. Bitte {keys} eingeben.", "31")

    def selection_args(self) -> list[str]:
        args: list[str] = []
        for flag, value in (("--customer", self.customer), ("--app", self.app)):
            if value:
                args += [flag, value]
        if self.platform != "all":
            args += ["--platform", self.platform]
        return args

    def summary(self) -> str:
        """Eine Zeile mit der aktuellen Auswahl (passt in ein 80-Zeichen-Terminal)."""
        def chip(label: str, value: str, active: bool) -> str:
            return f"{label}: " + (paint(value, "1", "36") if active else value)
        platform = {"all": "alle", "apple": "Apple", "google": "Google"}.get(self.platform, self.platform)
        period = f"{self.date_from or '…'} bis {self.date_to or '…'}" if (self.date_from or self.date_to) else "offen"
        return "  " + " · ".join([
            chip("Kunde", self.customer or "alle", bool(self.customer)),
            chip("App", self.app or "alle", bool(self.app)),
            chip("Plattform", platform, self.platform != "all"),
            chip("Zeitraum", period, bool(self.date_from or self.date_to)),
            chip("Browser", "ja" if self.open_after else "nein", self.open_after)])

    def freshness(self) -> str:
        """Kopfzeile: jüngster erfolgreicher Abruf (aus data/state.json) und Alter des Berichts."""
        last = None
        try:
            state = json.loads((load_config(CONFIG).data_dir / "state.json").read_text(encoding="utf-8"))
            stamps = [t.get("lastSuccessfulSync") for c in state.get("customers", {}).values()
                      for a in c.get("apps", {}).values() for t in a.values() if isinstance(t, dict)]
            last = max((x for x in stamps if x), default=None)
        except (OSError, ValueError, ToolError):
            pass
        report = self.report_path()
        built = (datetime.fromtimestamp(report.stat().st_mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                 if report.is_file() else None)
        return paint(f"Letzter Abruf: {ago(last) if last else 'noch nie'} · "
                     f"Bericht: {ago(built) if built else 'noch keiner'}", "2")

    def run(self, script: str, args: list[str]) -> int:
        """Führt ein Skript im selben Python aus und zeigt den Befehl zum Lernen an."""
        print("\n" + paint(f"▶ python {script} {' '.join(args)}", "1", "35") + "\n", flush=True)
        try:
            code = subprocess.call([sys.executable, str(ROOT / script), *args], cwd=ROOT)
        except KeyboardInterrupt:
            self.say("\nAbgebrochen.")
            return 130
        print("\n" + (paint(f"✔ Fertig (Exit-Code {code})", "1", "32") if code == 0
                      else paint(f"✖ Fehler (Exit-Code {code})", "1", "31")))
        self.pause_pending = True
        return code

    def make_report(self, open_it: bool = True) -> None:
        if self.run("report.py", self.selection_args()) == 0 and open_it:
            out = self.report_path()
            if out.is_file():
                webbrowser.open(out.as_uri())
                self.say(f"Bericht geöffnet: {out}")

    def report_path(self) -> Path:
        try:
            report_dir = load_config(CONFIG).report_dir
        except ToolError:
            report_dir = ROOT / DEFAULT_SETTINGS["reportDirectory"]
        return report_dir / "index.html"

    def config_or_none(self):
        try:
            return load_config(CONFIG)
        except ToolError as exc:
            self.say(f"\nKonfiguration nicht lesbar: {exc}")
            return None

    # ---- Menüs ----
    def main(self) -> None:
        while True:
            pick = self.choose("Hauptmenü", [
                ("everything", "ALLES AUF EINMAL: Rezensionen + Stabilität abrufen, Bericht erzeugen und öffnen"),
                ("fetch", "Daten abrufen …"),
                ("report", "Bericht erzeugen und im Browser öffnen"),
                ("open", "Letzten Bericht nur öffnen"),
                ("select", "Auswahl ändern (Kunde / App / Plattform / Zeitraum) …"),
                ("info", "Status und Übersicht …"),
                ("csv", "Google-Rezensionen aus CSV importieren"),
                ("markdown", "Markdown-Dateien: ansehen, im Editor öffnen, erzeugen, als ZIP versenden …"),
                ("reset", "Daten löschen und neu anfangen …"),
            ], back="", help_text=HELP_MAIN, root=True)
            if pick == "0":
                return
            {"everything": self.everything, "fetch": self.fetch_menu, "report": self.make_report, "select": self.select_menu,
             "info": self.info_menu, "csv": self.csv_import, "reset": self.reset_menu, "markdown": self.markdown_menu, "open": self.open_last}[pick]()

    def short(self) -> None:
        """Kurzmenü (kurzmenu.sh): nur alles abrufen, Status und Bericht anzeigen."""
        self.show_summary = False
        while True:
            pick = self.choose("Kurzmenü", [
                ("fetch", "Alles abrufen     " + paint("(collect.py --dataset all, report.py)", "2")),
                ("info", "Status            " + paint("(collect.py --status)", "2")),
                ("open", "Bericht anzeigen  " + paint("(reports/index.html)", "2")),
            ], back=paint("(großes Menü: menu.sh)", "2"), help_text=HELP_SHORT, root=True)
            if pick == "0":
                return
            if pick == "fetch":
                if self.run("collect.py", ["--dataset", "all"]) in (0, 1):
                    self.run("report.py", [])
            elif pick == "info":
                self.run("collect.py", ["--status"])
            else:
                if not self.report_path().is_file():
                    self.say("Noch kein Bericht vorhanden, er wird jetzt erzeugt …")
                    if self.run("report.py", []) != 0:
                        continue
                self.open_last()
                self.note = paint("🌐 Bericht im Browser geöffnet.", "32")

    def everything(self) -> None:
        """Ein Klick: Rezensionen, Stabilität und Testbetrieb abrufen (mit aktueller Auswahl), dann Bericht erzeugen und öffnen."""
        code = self.run("collect.py", self.selection_args() + ["--dataset", "all"])
        if code in (0, 1):
            self.make_report()
        else:
            self.say("Abruf mit Konfigurationsfehler beendet – Bericht wird nicht erzeugt.")

    def fetch_menu(self) -> None:
        while True:
            pick = self.choose("Daten abrufen", [
                ("normal", "Abrufen (automatisch: erstmals alles, danach nur Neues)"),
                ("full", "Vollständig neu lesen (--full-sync, löscht nichts)"),
                ("force", "Abrufen und Wartefrist ignorieren (--force)"),
                ("stab", "Stabilität abrufen: Abstürze und Sitzungen (nur Apple)"),
                ("test", "Testbetrieb abrufen: TestFlight und Google-Testspuren"),
                ("all", "Rezensionen, Stabilität UND Testbetrieb abrufen"),
                ("dry", "Probelauf, nichts speichern (--dry-run)"),
                ("range", "Nur einen Zeitraum abrufen (--from / --to)"),
                ("toggle", "Bericht nach dem Abruf automatisch öffnen: umschalten"),
            ], help_text=HELP_FETCH)
            if pick == "0":
                return
            if pick == "toggle":
                self.open_after = not self.open_after
                continue
            args = self.selection_args()
            if pick == "full":
                args.append("--full-sync")
            elif pick == "force":
                args.append("--force")
            elif pick == "stab":
                args += ["--dataset", "stability"]
            elif pick == "test":
                args += ["--dataset", "testing"]
            elif pick == "all":
                args += ["--dataset", "all"]
            elif pick == "dry":
                args.append("--dry-run")
            elif pick == "range":
                if not self.pick_range():
                    continue
                args += ["--from", self.date_from] if self.date_from else []
                args += ["--to", self.date_to] if self.date_to else []
            code = self.run("collect.py", args)
            if pick != "dry" and code in (0, 1) and self.open_after:
                self.make_report()

    def pick_range(self) -> bool:
        """Fragt Zeitraum ab; Enter lässt ein Datum leer. Liefert False bei ungültiger Eingabe."""
        for attr, label in (("date_from", "Von"), ("date_to", "Bis")):
            value = self.ask(f"{label} (YYYY-MM-DD, Enter = offen, aktuell {getattr(self, attr) or '–'}): ")
            if value and not DATE_RE.match(value):
                self.say("Ungültiges Datum.")
                return False
            setattr(self, attr, value or getattr(self, attr))
        return bool(self.date_from or self.date_to)

    def select_menu(self) -> None:
        cfg = self.config_or_none()
        if cfg is None:
            return
        while True:
            pick = self.choose("Auswahl ändern", [
                ("customer", "Kunde wählen"), ("app", "App wählen"), ("platform", "Plattform wählen"),
                ("range", "Zeitraum setzen"), ("clearrange", "Zeitraum löschen"), ("reset", "Alles zurücksetzen"),
            ], help_text=HELP_SELECT)
            if pick == "0":
                return
            if pick == "customer":
                entries = [(c["id"], f"{c['name']} ({c['id']})") for c in cfg.customers]
                chosen = self.choose("Kunde", [("", "Alle Kunden")] + entries)
                if chosen != "0":
                    self.customer, self.app = chosen or None, None
            elif pick == "app":
                entries = [(a["id"], f"{a['name']} ({a['id']})") for c in cfg.customers
                           if not self.customer or c["id"] == self.customer for a in c["apps"]]
                chosen = self.choose("App", [("", "Alle Apps")] + entries)
                if chosen != "0":
                    self.app = chosen or None
            elif pick == "platform":
                chosen = self.choose("Plattform", [("all", "Alle"), ("apple", "Apple"), ("google", "Google")])
                if chosen != "0":
                    self.platform = chosen
            elif pick == "range":
                self.pick_range()
            elif pick == "clearrange":
                self.date_from = self.date_to = None
            elif pick == "reset":
                self.customer = self.app = self.date_from = self.date_to = None
                self.platform = "all"

    def info_menu(self) -> None:
        while True:
            pick = self.choose("Status und Übersicht", [
                ("status", "Status je App (letzter Abruf, Anzahl, Fehler)"),
                ("apps", "Konfigurierte Apps anzeigen"),
                ("test", "Tests ausführen"),
            ], help_text=HELP_INFO)
            if pick == "0":
                return
            if pick == "status":
                self.run("collect.py", ["--status"])
            elif pick == "apps":
                self.run("collect.py", ["--list-apps"])
            else:
                subprocess.call([sys.executable, "-m", "pytest", "tests", "-q"], cwd=ROOT)
                self.pause_pending = True

    def csv_import(self) -> None:
        if not (self.customer and self.app):
            self.say("\nBitte zuerst unter „Auswahl ändern“ Kunde und App wählen.")
            self.say(HELP_CSV)
            return
        path = self.ask("Pfad der CSV-Datei(en) (Leerzeichen getrennt, H = Hilfe, Enter = abbrechen): ")
        if path.lower() == "h":
            self.say(HELP_CSV)
            return
        if path:
            self.run("collect.py", ["--import-google-csv", *path.split(), "--customer", self.customer,
                                    "--app", self.app])

    def markdown_menu(self) -> None:
        while True:
            pick = self.choose("Markdown-Dateien", [
                ("docs", "Dokumentation öffnen (Anleitung, README, Stufe 2) – Browser oder Editor"),
                ("summ", "Zusammenfassungen der letzten 14 Tage öffnen (je App/Plattform) – Browser oder Editor"),
                ("regen", "Zusammenfassungen neu erzeugen (mit aktueller Auswahl)"),
                ("zip", "ZIP zum Versenden erzeugen und im Finder zeigen"),
            ], help_text=HELP_MARKDOWN)
            if pick == "0":
                return
            if pick == "docs":
                self.pick_file("Dokumentation", [p for p in (ROOT / "ANLEITUNG.md", ROOT / "README.md", ROOT / "STAGE2.md") if p.is_file()])
            elif pick == "summ":
                folder = self.report_path().parent / "markdown"
                self.pick_file("Zusammenfassungen", sorted(folder.glob("*.md")) if folder.is_dir() else [])
            elif pick == "regen":
                self.run("report.py", self.selection_args())
            else:
                self.make_zip()

    def pick_file(self, title: str, files: list[Path]) -> None:
        """Dateiliste anzeigen; die gewählte Datei wird im Editor geöffnet. Wiederholt, bis 0 (zurück)."""
        if not files:
            self.say("\nKeine Dateien vorhanden. Unter „Zusammenfassungen neu erzeugen“ anlegen (oder Bericht erzeugen).")
            return
        entries = [(str(f), f.name + ("   – Übersicht aller Apps" if f.name == "00-uebersicht.md" else "")) for f in files]
        while True:
            chosen = self.choose(title, entries, help_text=HELP_MARKDOWN)
            if chosen == "0":
                return
            how = self.ask("Öffnen in  [E] Editor   [B] Browser (formatiert)   Enter = Browser: ").lower()
            (self.open_in_editor if how in ("e", "editor") else self.open_in_browser)(Path(chosen))

    def open_in_browser(self, path: Path) -> None:
        """Wandelt die Markdown-Datei in eine formatierte HTML-Seite um (reports/markdown/_html/) und öffnet sie."""
        from src.mdhtml import convert_file
        target = convert_file(path, self.report_path().parent / "markdown" / "_html")
        webbrowser.open(target.as_uri())
        self.say(f"\n{paint('🌐', '1', '35')} Im Browser geöffnet: {target}")

    def open_in_editor(self, path: Path) -> None:
        """Öffnet eine Datei im Editor: MD_EDITOR, VISUAL, EDITOR; sonst Standard-Texteditor des Systems."""
        custom = os.environ.get("MD_EDITOR") or os.environ.get("VISUAL") or os.environ.get("EDITOR")
        if custom:
            command = shlex.split(custom) + [str(path)]
        elif sys.platform == "darwin":
            command = ["open", "-t", str(path)]
        else:
            command = ["xdg-open", str(path)]
        self.say(f"\n{paint('✎', '1', '35')} Öffne {path.name} mit: {' '.join(shlex.quote(c) for c in command[:-1])}")
        try:
            subprocess.call(command)
        except FileNotFoundError:
            self.say(f"Editor nicht gefunden: {command[0]}. Setze MD_EDITOR, z. B. export MD_EDITOR=\"open -a 'Visual Studio Code'\"")

    def make_zip(self) -> None:
        """Erzeugt je App/Plattform eine Markdown-Datei (14 Tage) plus ZIP und zeigt den Ordner."""
        if self.run("report.py", self.selection_args() + ["--zip"]) == 0:
            self.say(f"Dateien: {self.report_path().parent / 'markdown'}")
            if sys.platform == "darwin":
                subprocess.call(["open", "-R", str(self.report_path().parent / "markdown" / "00-uebersicht.md")])

    def reset_menu(self) -> None:
        while True:
            pick = self.choose("Daten löschen und neu anfangen", [
                ("wipesel", "Nur die AUSGEWÄHLTE App/den ausgewählten Kunden löschen (Auswahl oben)"),
                ("wipeall", "ALLES löschen (alle Daten und Bericht) und von vorne beginnen"),
                ("preview", "Nur anzeigen, was gelöscht würde (Trockenlauf, löscht nichts)"),
            ], help_text=HELP_RESET)
            if pick == "0":
                return
            args = self.selection_args()
            if pick in ("wipesel", "preview") and not (self.customer or self.app):
                self.say("\nKeine App/kein Kunde ausgewählt. Bitte zuerst unter „Auswahl ändern“ wählen.")
                continue
            if pick == "wipeall":
                args = []
            elif "--platform" in args:  # Plattform-Auswahl gilt beim Löschen nicht
                i = args.index("--platform")
                del args[i:i + 2]
            if pick == "preview":
                args.append("--dry-run")
            self.run("reset.py", args)

    def open_last(self) -> None:
        out = self.report_path()
        if out.is_file():
            webbrowser.open(out.as_uri())
        else:
            self.say("\nNoch kein Bericht vorhanden. Bitte „Bericht erzeugen“ wählen.")


if __name__ == "__main__":
    menu = Menu()
    try:
        menu.short() if "--kurz" in sys.argv[1:] else menu.main()
    except (KeyboardInterrupt, QuitMenu):
        pass
    menu.pause_if_needed()
    clear_screen()
    print("Auf Wiedersehen 👋")
