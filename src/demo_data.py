"""Testdaten für den Debug-Modus (`kurzmenudebug.sh`, `demo.py`): erfundene, aber realistische Daten ohne Netz.

Zweck: Vorführung und Leistungstest des Berichts, ohne eine Anfrage an Apple, Google oder einen KI-Anbieter zu
senden und ohne die echten Daten unter `data/` anzufassen. Der Generator schreibt in einen eigenen Datenordner
(`data-debug/`) und eine eigene Konfiguration (`config/config.debug.json`); `collect.py --status`, `report.py` und die
KI-Analyse arbeiten darauf wie auf echten Daten, weil alle Dateien exakt dem Format der echten Abrufe folgen
(`TECHNIK.md`, Abschnitt 5). Erzeugt werden je App und Plattform `reviews.json` (über `merge.merge_reviews`),
`review-history.json`, `versions.json` (über `merge.build_versions`), `ratings-history.json`, für Apple zusätzlich
`stability-metrics.json`, `store-metrics.json` und `testflight.json`, für Google `google-testing.json`, dazu
`state.json` und `sync-history.json`. Nie erzeugt: `ai-analysis.json` (die KI-Analyse läuft, wenn gewünscht, echt).

Wählbar: Kategorien (Spiele, Krankenkassen, Navigation, Sport, KI, Nachrichten, Finanzen, Reisen, Büro), Umfang
(`VOLUMES`: steuert die Dichte der Kennzahlen und den vorgeschlagenen Bereich der Rezensionen), Zeitraum in Monaten
(`PERIODS`), Bereich der Rezensionen je App (einmal für alle Apps, gleichverteilt je App gezogen), Anzahl der Apps je
Kategorie (`apps`: die ersten N der Kategorie, None = alle) und ein Startwert (`seed`); gleiche Wahl ergibt gleiche Daten.

Apple und Google derselben App unterscheiden sich (`platform_profile`): Google bekommt eine um eine Stufe verschobene
Bewertungslage (abwechselnd besser und schlechter), einen anderen Trend, eine niedrigere Antwortquote und 60–110 % der
Rezensionszahl; so zeigen Vergleich und Filter je Plattform sichtbar andere Werte statt zweier Kopien.

Krankenkassen: bis zu 30 Apps eines Softwarehauses mit gemeinsamem Code (gleiche Versionen, gleiche Veröffentlichungstage),
nur anders konfiguriert. Jede Kasse hat ein eigenes Profil (Tier von „sehr gut“ bis „sehr schlecht“, Absturzrate,
Antwortquote, Trend, Nutzung), damit alle Statistiken des Berichts unterschiedliche Werte zeigen. Die Namen sind
an echte BKK- und IKK-Namen angelehnt und bewusst verändert; alle Zahlen sind erfunden.

Sicherheit: `ensure_debug_dir` verweigert jeden Datenordner, dessen Name nicht `debug` enthält oder der mit dem
Datenordner der echten Konfiguration zusammenfällt. Löschen und Schreiben geschieht ausschließlich unter diesem Ordner.
"""
from __future__ import annotations

import hashlib
import math
import random
import shutil
import zlib
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import DEFAULT_SETTINGS, base_dir_of, load_config
from .config import SCHEMA_VERSION as CONFIG_SCHEMA
from .errors import ConfigError, ToolError
from .merge import build_versions, derived_distribution, merge_reviews
from .models import SCHEMA_VERSION, iso_z, new_review
from .storage import write_json
from .sync import empty_state, get_target_state, target_dir

PERIODS = (3, 6, 9, 12, 18, 24)
DEFAULT_MONTHS = 24
DEBUG_CONFIG = Path("config") / "config.debug.json"
DEBUG_DATA_DIR = "./data-debug"
DEBUG_REPORT_DIR = "./reports-debug"
RATING_COUNTRIES = ("DE", "AT", "CH")
APPLE_COUNTRIES = (("DEU", 78), ("AUT", 12), ("CHE", 10))
IOS_VERSIONS = ("iOS 26.0", "iOS 18.6", "iOS 17.7")
DEVICES = ("iPhone", "iPad")
DOWNLOAD_TYPES = ("First-time download", "Redownload", "Auto-update", "Manual update")
SOURCE_TYPES = ("App Store search", "App Store browse", "Web referrer", "App referrer")
ENGAGEMENT_EVENTS = ("Impression", "Page view", "Tap")
TERRITORIES = (("DE", 78), ("AT", 12), ("CH", 10))
# Wettbewerber in der Debug-Konfiguration (Wunsch des Nutzers, 25.10.2026): echte, öffentliche Apple-App-IDs großer
# Krankenkassen-Apps (iTunes-Suche vom 25.10.2026), keine BKK/HKK/IKK. Für sie werden KEINE Testdaten erfunden; der Abruf
# `./ratings.sh competitors` holt ihre öffentlichen Rezensionen ohne Zugang. Sie hängen am ersten erzeugten Kunden.
DEMO_COMPETITORS = (
    ("barmer", "Meine BARMER", "BARMER", "956752981"),
    ("tk-app", "TK-App", "Techniker Krankenkasse", "1163694230"),
    ("meine-aok", "Meine AOK", "AOK Bundesverband", "1406830270"),
    ("dak-app", "DAK App", "DAK-Gesundheit", "1333473784"),
    ("meine-kkh", "Meine KKH", "Kaufmännische Krankenkasse KKH", "6737333371"),
    ("meine-knappschaft", "Meine KNAPPSCHAFT", "Knappschaft", "1433883383"),
)
# Fehlertext für das eine absichtlich fehlgeschlagene Ziel (zeigt die rote Markierung im Bericht und im Status)
DEMO_ERROR = "Testdaten: erfundener Fehler – Google-Dienstkonto ohne Berechtigung (HTTP 403)"


@dataclass(frozen=True)
class Volume:
    """Ein Umfang: Vorgabe für den Bereich der Rezensionen je App und Dichte der Kennzahlen."""

    key: str
    label: str
    reviews: tuple[int, int]   # vorgeschlagener Bereich der Rezensionen je App
    combos: int                # Zeilen je Tag in Stabilität (Version × System × Gerät), begrenzt die Dateigröße
    territories: int           # Länder in den Store-Kennzahlen (1 bis 3)
    download_types: int        # Download-Arten je Tag (1 bis 4)
    sources: int               # Quellen (Suche, Stöbern, Web, App) je Tag (1 bis 4)
    devices: int               # Geräte (iPhone, iPad) je Tag (1 oder 2)


# Zeilen je Tag und App in den Store-Kennzahlen: wenig ≈ 6, mittel ≈ 15, viele ≈ 50, sehr viele ≈ 120
VOLUMES: dict[str, Volume] = {
    "wenig": Volume("wenig", "Wenig Bewertungen", (5, 25), 2, 1, 1, 1, 1),
    "mittel": Volume("mittel", "Mittlere Anzahl Bewertungen", (20, 120), 4, 2, 2, 1, 2),
    "viele": Volume("viele", "Viele Bewertungen", (100, 600), 8, 3, 3, 2, 2),
    "sehr-viele": Volume("sehr-viele", "Sehr viele Bewertungen (Leistungstest)", (500, 3000), 12, 3, 4, 4, 2),
}
DEFAULT_VOLUME = "mittel"

# Sterneverteilung je Tier (Anteile 1 bis 5 Sterne)
TIERS: dict[str, tuple[int, ...]] = {
    "sehr-gut": (2, 3, 6, 19, 70), "gut": (5, 6, 10, 29, 50), "mittel": (18, 15, 20, 22, 25),
    "schlecht": (40, 22, 15, 12, 11), "sehr-schlecht": (62, 20, 9, 5, 4),
}
TIER_ORDER = tuple(TIERS)


@dataclass(frozen=True)
class AppSpec:
    """Eine erfundene App mit ihrem Profil; das Profil macht die Statistiken je App unterschiedlich."""

    ident: str                      # App-ID (Ordnername), z. B. "bkk-mobil-ohl"
    name: str                       # Anzeigename
    tier: str                       # Schlüssel in TIERS
    platforms: tuple[str, ...]      # ("apple",) oder ("apple", "google")
    crash: float                    # Abstürze je 1000 Sitzungen (Grundwert)
    reply: float                    # Anteil beantworteter negativer Rezensionen (0 bis 1)
    trend: str                      # "auf" (wird besser), "ab" (wird schlechter), "stabil"
    sessions: int                   # Sitzungen je Tag (Grundwert)
    audience: int | None            # Zielgruppe (Versicherte, Nutzer) oder None
    bad_release: bool               # eine Version mit Absturzsprung und Rezensionsschub
    failed: bool = False            # Google-Ziel steht auf „failed“ (Fehlerfall im Status)


@dataclass(frozen=True)
class Category:
    """Eine Kategorie: ein Kunde, seine Apps, die Textbausteine und das Versionsschema."""

    key: str
    label: str
    customer_id: str
    customer_name: str
    package_prefix: str
    apps: tuple[AppSpec, ...]
    phrases: dict[str, list[tuple[str, str]]]   # "pos", "mid", "neg": (Titel, Text)
    shared_versions: bool = False                # alle Apps der Kategorie teilen Versionen (gleicher Code)
    major: int = 2                               # Hauptversion zu Beginn


# ----------------------------------------------------------------------------------------------------------
# Textbausteine
# ----------------------------------------------------------------------------------------------------------

KASSE_POS = [
    ("Bonusprogramm super", "Das Bonusprogramm ist super. Punkte sammeln und einreichen klappt ohne Umwege."),
    ("Daten leicht ändern", "Man kann leicht seine persönlichen Daten ändern, ohne anrufen zu müssen."),
    ("Anmeldung verständlich", "Das Anmelden ist verständlich erklärt, ich war in fünf Minuten drin."),
    ("Familie umschalten", "Das Umschalten zwischen den Familienmitgliedern funktioniert gut und schnell."),
    ("Umfangreiche Anträge", "Die Dokumente und Anträge sind umfangreich, ich habe alles gefunden, was ich brauchte."),
    ("Schönes Design", "Ich mag das Design. Klar, aufgeräumt, ohne Schnickschnack."),
    ("Viele Funktionen", "Ich finde, die App hat viele nützliche Funktionen, die ich wirklich nutze."),
    ("Postfach einfach", "Das Postfach ist einfach zu steuern, Nachrichten der Kasse kommen zuverlässig an."),
    ("Vielseitige Einstellungen", "Die Einstellungen sind vielseitig, man kann fast alles anpassen."),
    ("Gesundheitsmodule", "Die Gesundheitsmodule sind vielversprechend, besonders der Vorsorgeplan."),
    ("Neue Karte bestellt", "Ich konnte einfach meine neue Gesundheitskarte anfordern, zwei Tage später war sie da."),
    ("eAU klappt", "Die Funktion eAU-Bescheinigung ist super, nichts mehr per Post schicken."),
    ("Tolle App", "Tolle App, alles an einem Ort."),
    ("Medikation", "Die Medikation gefällt mir, Erinnerungen und Liste in einem."),
    ("Vorsorgeplan", "Man kann einfach einen Vorsorgeplan anlegen. Super!"),
    ("Allergien eintragen", "In der App kann man sogar Allergien eingeben. Prima."),
    ("Impfungen", "Impfungen lassen sich leicht pflegen, der Impfpass ist endlich digital."),
    ("Schwangerschaft", "Alles rund um die Schwangerschaft ist genial gelöst, von Terminen bis Anträgen."),
    ("Kostenübersicht", "Die Kostenübersicht gefällt mir, man sieht sofort, was abgerechnet wurde."),
    ("Krankmeldung in 1 Minute", "Krankmeldung fotografiert, abgeschickt, fertig. So muss das sein."),
    ("Great app", "Works reliably, the login with Face ID is quick and the inbox is easy to use."),
]
KASSE_MID = [
    ("Wie funktioniert das Bonusprogramm?", "Wie funktioniert das Bonusprogramm? Eine kurze Erklärung in der App würde helfen."),
    ("Sportabzeichen fehlt", "Warum kann ich im Bonusprogramm mein Sportabzeichen nicht eingeben? Sonst ganz okay."),
    ("Passwort ändern?", "Wie kann ich das Passwort ändern? Habe die Stelle nicht gefunden, sonst solide App."),
    ("Benutzerkonto löschen", "Was passiert, wenn man das Benutzerkonto löscht? Dazu steht nichts in der App."),
    ("Service ausbauen", "Der Servicebereich muss weiter ausgebaut werden, der Rest ist in Ordnung."),
    ("Startseite zu lang", "Die erste Seite ist viel zu lang, man scrollt ewig bis zum Postfach."),
    ("Erst Startprobleme", "Nach der Installation musste ich zweimal neu starten, danach lief es."),
    ("Design-Kleinigkeiten", "Es gibt einige Designprobleme, zum Beispiel abgeschnittene Texte bei großer Schrift."),
    ("KI-Funktionen?", "Warum wurden keine KI-Funktionen eingebaut? Andere Kassen haben das schon."),
    ("Okay", "Macht, was sie soll. Nicht mehr, nicht weniger."),
    ("Wunsch: Widget", "Ein Widget für den Startbildschirm mit dem Postfach wäre schön."),
    ("Wird die App noch gepflegt?", "Seit Monaten kein Update, ich habe das Gefühl, die App wird nicht mehr weiterentwickelt."),
]
KASSE_NEG = [
    ("Ständig Werbung", "Ich bekomme ständig Werbung durch die Krankenkasse angezeigt. Ich will meine Unterlagen sehen, nicht Angebote."),
    ("Altmodisch", "Die App ist altmodisch und sieht nicht gut aus. Wirkt wie von 2015."),
    ("Postfach zu langsam", "Das Postfach ist zu langsam, jede Nachricht lädt sekundenlang."),
    ("App zu langsam", "Warum ist die App so langsam? Jeder Wechsel zwischen den Bereichen dauert."),
    ("Absturz beim Login", "Die App stürzt beim Login immer ab. Seit dem letzten Update komme ich nicht mehr rein."),
    ("Bonusprogramm kaputt", "Ich kann im Bonusprogramm keine Daten eingeben, der Speichern-Knopf tut nichts."),
    ("Keine Hauptadresse", "Ich kann keine Hauptadresse anlegen, es kommt immer eine Fehlermeldung."),
    ("Adresse nicht änderbar", "Ich kann keine Adressen ändern. Musste am Ende doch anrufen."),
    ("IBAN zu kompliziert", "Die Eingabe der IBAN ist zu kompliziert und wird ständig als ungültig abgelehnt."),
    ("Telefonnummer ungeprüft", "Die Telefonnummer wird nicht geprüft, man kann Unsinn eingeben."),
    ("Face ID geht nicht", "Face ID wird nicht erkannt, ich muss jedes Mal das Passwort tippen."),
    ("Login zu kompliziert", "Der Login-Prozess ist zu kompliziert: Brief, Code, App, nochmal Code."),
    ("Dunkelmodus fehlerhaft", "Der Dunkelmodus ist fehlerhaft, weiße Flächen mit weißer Schrift."),
    ("Krankengeld", "Ich kann mein Krankengeld nicht mitteilen, die Funktion fehlt einfach."),
    ("Keine Antwort", "Warum antwortet keiner im Postfach? Seit zwei Wochen keine Reaktion."),
    ("E-Mails fehlen", "Meine E-Mails werden nicht angezeigt, das Postfach bleibt leer."),
    ("Status falsch", "Mein Versichertenstatus ist falsch, in der App steht etwas anderes als auf der Karte."),
    ("2FA defekt", "Die Zwei-Faktor-Authentifizierung funktioniert nicht, der Code kommt nie an."),
    ("Datenschutz schwammig", "Der Datenschutz ist schwammig formuliert, ich weiß nicht, was mit meinen Daten passiert."),
    ("Geräte freischalten kaputt", "Die Funktion „Geräte freischalten“ ist kaputt, das neue Handy wird nicht angenommen."),
    ("Einverständnisse", "Ich kann die Einverständnisse nicht löschen, der Haken bleibt gesetzt."),
    ("Biometrie nicht abschaltbar", "Der biometrische Login lässt sich nicht ausschalten."),
    ("Installation unmöglich", "Ich kann die App nicht installieren, der Store meldet einen Fehler."),
    ("Startet nicht mehr", "Ich kann die App nicht mehr starten, sie schließt sich sofort wieder."),
    ("iOS 26", "Nach dem Update auf iOS 26 läuft die App nicht mehr. Bitte schnell beheben!"),
    ("iOS 17 nicht unterstützt", "Die App läuft nicht mehr auf iOS 17? Warum? Nicht jeder kauft jedes Jahr ein neues Handy."),
    ("Kamera langsam", "Warum ist die Kamerafunktion so langsam in der App? Das Foto der Rechnung dauert ewig."),
    ("AU scannen", "Warum kann ich meine AU nicht scannen? Der Knopf ist ausgegraut."),
    ("Crashes on login", "Crashes every time I try to log in since the latest update. Unusable."),
]
KASSE_REPLIES = [
    "Vielen Dank für Ihre Rückmeldung. Bitte melden Sie sich mit Ihrer Versichertennummer über das Kontaktformular, damit wir den Fall prüfen können.",
    "Danke für den Hinweis. Das Problem ist uns bekannt und wird mit dem nächsten Update behoben.",
    "Es tut uns leid, dass die App bei Ihnen nicht wie erwartet funktioniert. Bitte aktualisieren Sie auf die neueste Version und melden Sie sich erneut an.",
    "Vielen Dank für Ihr Lob, das freut unser Team sehr!",
]

GENERIC_REPLIES = [
    "Danke für die Rückmeldung! Wir haben den Fehler gefunden und beheben ihn im nächsten Update.",
    "Vielen Dank für die Bewertung. Bitte schreiben Sie uns an den Support, damit wir den Fall anschauen können.",
    "Freut uns sehr, danke für die fünf Sterne!",
]

SPIELE = {
    "pos": [("Suchtgefahr", "Macht richtig Spaß, die Level sind abwechslungsreich und fair."),
            ("Tolles Spiel", "Grafik und Sound passen, läuft flüssig auf meinem alten Handy."),
            ("Fair ohne Zwang", "Man kann alles ohne Kauf erreichen, das ist heute selten."),
            ("Great game", "Clever levels, no forced ads. Well done."),
            ("Endlich Offline", "Spielt sich auch im Zug ohne Netz, super für Pendler.")],
    "mid": [("Zu kurz", "Nach drei Tagen durch. Mehr Level bitte!"),
            ("Werbung nach jedem Level", "Spiel ist gut, aber nach jedem Level ein Werbespot nervt."),
            ("Akku", "Zieht den Akku stark, sonst okay."),
            ("Nicht mehr gepflegt?", "Seit einem Jahr kein Update, wird das Spiel noch weiterentwickelt?")],
    "neg": [("Pay to win", "Ab Level 20 geht ohne Echtgeld nichts mehr. Schade."),
            ("Absturz im Bosskampf", "Stürzt im Bosskampf regelmäßig ab, Fortschritt weg."),
            ("Speicherstand verloren", "Nach dem Update war mein Speicherstand gelöscht. Nie wieder."),
            ("Lags since update", "Since the last update the game stutters constantly.")],
}
NAVIGATION = {
    "pos": [("Zuverlässige Routen", "Routenführung ist zuverlässig, auch auf Feldwegen."),
            ("Offline-Karten", "Offline-Karten laden schnell und sparen Datenvolumen."),
            ("Top für Radfahrer", "Die Radrouten meiden Hauptstraßen, genau richtig."),
            ("Accurate", "Accurate turn-by-turn directions, better than the built-in app.")],
    "mid": [("Sprachansage leise", "Sprachansagen sind zu leise im Auto."),
            ("Karten veraltet", "Einige neue Straßen fehlen noch, sonst gut."),
            ("Suche umständlich", "Die Adresssuche braucht zu viele Schritte.")],
    "neg": [("GPS springt", "Die Position springt ständig, Navigation unbrauchbar."),
            ("Absturz bei Routenberechnung", "Stürzt bei langen Routen jedes Mal ab."),
            ("Akku leer nach 1 Stunde", "Frisst den Akku in einer Stunde komplett leer."),
            ("Abo-Falle", "Nach der Testphase automatisch teures Abo. Unseriös.")],
}
SPORT = {
    "pos": [("Motiviert", "Die Trainingspläne motivieren, Fortschritt sichtbar."),
            ("Watch-Sync", "Synchronisation mit der Uhr klappt sofort."),
            ("Einfach gut", "Übersichtlich, schnell, keine Werbung."),
            ("Love it", "Great tracking and the statistics are detailed.")],
    "mid": [("Mehr Sportarten", "Klettern fehlt, sonst gut."),
            ("Export fehlt", "Ich würde gerne meine Daten als CSV exportieren."),
            ("Herzfrequenz ungenau", "Herzfrequenz manchmal daneben, Rest okay.")],
    "neg": [("Lauf nicht gespeichert", "Nach 10 km war der Lauf einfach weg. Datenverlust!"),
            ("Abo zu teuer", "Jedes Jahr teurer, die Funktionen bleiben gleich."),
            ("Stürzt beim Start ab", "Seit dem Update startet die App nicht mehr."),
            ("GPS falsch", "Die Strecke wird um 20 Prozent zu lang gemessen.")],
}
KI = {
    "pos": [("Spart Zeit", "Formuliert E-Mails in Sekunden, die Qualität stimmt."),
            ("Erstaunlich gut", "Die Zusammenfassungen sind präzise und auf den Punkt."),
            ("Datenschutz klar", "Transparent, was gesendet wird. Das schätze ich."),
            ("Impressive", "Fast answers, works offline for short texts.")],
    "mid": [("Manchmal daneben", "Erfindet gelegentlich Fakten, man muss gegenlesen."),
            ("Kontingent klein", "Zehn Anfragen am Tag sind zu wenig in der Gratisversion."),
            ("Deutsch holprig", "Auf Deutsch sind die Texte manchmal holprig.")],
    "neg": [("Antwort dauert ewig", "Jede Anfrage dauert eine Minute, dann Zeitüberschreitung."),
            ("Abo ohne Kündigung", "Abo lässt sich in der App nicht kündigen."),
            ("Absturz beim Einfügen", "Langen Text einfügen führt sofort zum Absturz."),
            ("Daten weg", "Alle gespeicherten Gespräche nach dem Update verschwunden.")],
}
NACHRICHTEN = {
    "pos": [("Schnell informiert", "Eilmeldungen kommen zuverlässig, Artikel laden schnell."),
            ("Angenehm zu lesen", "Schriftgröße einstellbar, Dunkelmodus gut gemacht."),
            ("Regional stark", "Endlich lokale Nachrichten in einer sauberen App."),
            ("Well made", "Clean layout, no clickbait.")],
    "mid": [("Zu viele Pushs", "Zu viele Push-Nachrichten, nicht alles ist eilig."),
            ("Kommentare fehlen", "Kommentarfunktion wäre schön."),
            ("Podcast hakt", "Podcasts stoppen beim Sperren des Bildschirms.")],
    "neg": [("Paywall überall", "Fast jeder Artikel kostenpflichtig, dafür noch Werbung."),
            ("Absturz beim Öffnen", "Stürzt beim Öffnen eines Artikels ab, seit Tagen."),
            ("Tracking", "Will Tracking über Apps hinweg, das geht gar nicht."),
            ("Login verloren", "Jeden Tag neu anmelden, Abo wird nicht erkannt.")],
}
FINANZEN = {
    "pos": [("Haushaltsbuch top", "Ausgaben erfassen geht schnell, Auswertungen sind klar."),
            ("Sicher und offline", "Daten bleiben auf dem Gerät, genau so will ich das."),
            ("Depot im Blick", "Kurse und Verteilung übersichtlich."),
            ("Solid", "Reliable, exports to CSV without fuss.")],
    "mid": [("CSV-Import hakt", "Import von Bankumsätzen klappt nur mit Nacharbeit."),
            ("iPad-Version", "Auf dem iPad wird viel Platz verschenkt."),
            ("Kategorien starr", "Eigene Kategorien nur in der Pro-Version.")],
    "neg": [("Daten verloren", "Nach dem Update waren alle Buchungen weg. Backup half nicht."),
            ("Sync kaputt", "iCloud-Sync zwischen iPhone und iPad funktioniert nicht mehr."),
            ("Zu teuer", "Preis verdoppelt, keine neuen Funktionen."),
            ("Crash on launch", "Opens and closes immediately on iOS 26.")],
}
REISEN = {
    "pos": [("Perfekt für Bahnfahrer", "Verbindungen, Verspätungen, Gleiswechsel: alles live."),
            ("Packliste genial", "Die Packliste merkt sich meine Reisen, nichts vergessen."),
            ("Übersichtlich", "Alle Buchungen an einem Ort, Offline-Tickets inklusive."),
            ("Great for trips", "Itinerary import from email works like magic.")],
    "mid": [("Push zu spät", "Verspätungsmeldung kam erst am Gleis."),
            ("Kartenansicht fehlt", "Eine Karte mit Stationen wäre hilfreich."),
            ("Englisch gemischt", "Teile der App nur auf Englisch.")],
    "neg": [("Ticket nicht angezeigt", "Ticket im Zug nicht ladbar, musste nachzahlen."),
            ("Absturz bei Suche", "Verbindungssuche stürzt ab, wenn man ein Datum wählt."),
            ("Daten weg nach Login", "Nach erneutem Login alle Reisen verschwunden."),
            ("Werbung", "Ständige Werbung für Hotels, die ich nicht will.")],
}
BUERO = {
    "pos": [("Scan in Sekunden", "Dokumente scannen, benennen, ablegen: schnell und sauber."),
            ("Aufgaben im Griff", "Endlich eine Aufgabenliste, die nicht nervt."),
            ("Ohne Konto nutzbar", "Kein Zwangskonto, alles lokal. Danke!"),
            ("Just works", "Fast OCR, reliable sync with the Mac app.")],
    "mid": [("OCR auf Deutsch", "Texterkennung macht bei Umlauten Fehler."),
            ("Widget fehlt", "Ein Widget für den Startbildschirm fehlt."),
            ("Teilen umständlich", "Teilen als PDF braucht drei Schritte.")],
    "neg": [("Scans verloren", "Zwanzig Scans einfach weg nach dem Update."),
            ("Stürzt bei großen PDFs ab", "Ab 30 Seiten stürzt die App ab."),
            ("Abo-Zwang", "Plötzlich Abo für Funktionen, die vorher frei waren."),
            ("Sync stuck", "Sync has been stuck for a week, support does not answer.")],
}

# ----------------------------------------------------------------------------------------------------------
# Apps und Kategorien
# ----------------------------------------------------------------------------------------------------------

# Angelehnt an echte BKK-/IKK-Namen, bewusst verändert (keine echten Namen). Reihenfolge = Reihenfolge der Profile.
KASSEN_NAMES = (
    "BKK Mobil Ohl", "BKK Pfalz-Saar", "BKK Linden", "BKK ProVitalis", "BKK Firmos", "BKK Techniform",
    "BKK Herkulis", "BKK Melissa", "BKK Wörth", "BKK Diakonia", "BKK Werra-Weser", "BKK Freudenthal",
    "BKK Salzhütte", "BKK Mielau", "BKK Voralp", "BKK Exklusiv Plus", "BKK Euregia", "BKK 25",
    "BKK B. Brauer", "BKK Verbund Pro", "BKK Wirtschaft & Handel", "Energie-BKK Nord", "Novita BKK",
    "Pronovo BKK", "mhplus BKK Süd", "Bertelsheim BKK", "Heimat BKK Land", "IKK klassik", "IKK Südost",
    "IKK Berlin-Brandenburg",
)
# Tier je Kasse (3 sehr gut, 7 gut, 10 mittel, 7 schlecht, 3 sehr schlecht), gemischt, damit die Liste nicht sortiert wirkt
KASSEN_TIERS = ("gut", "mittel", "sehr-gut", "schlecht", "mittel", "gut", "sehr-schlecht", "mittel", "gut", "mittel",
                "schlecht", "mittel", "gut", "sehr-gut", "schlecht", "mittel", "gut", "mittel", "schlecht", "gut",
                "mittel", "sehr-schlecht", "schlecht", "mittel", "gut", "schlecht", "mittel", "sehr-gut", "schlecht",
                "sehr-schlecht")
TREND_CYCLE = ("stabil", "ab", "auf", "stabil", "auf", "ab")
CRASH_BY_TIER = {"sehr-gut": 0.2, "gut": 0.5, "mittel": 1.1, "schlecht": 2.2, "sehr-schlecht": 4.0}
REPLY_BY_TIER = {"sehr-gut": 0.8, "gut": 0.6, "mittel": 0.4, "schlecht": 0.2, "sehr-schlecht": 0.05}


def _slug(name: str) -> str:
    """App-ID aus dem Namen: Kleinbuchstaben, Umlaute aufgelöst, Bindestriche (passt zu `config.ID_RE`)."""
    table = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss", "&": "und", ".": "", ":": "", "+": "plus"})
    cleaned = name.lower().translate(table)
    return "-".join(part for part in "".join(ch if ch.isalnum() else " " for ch in cleaned).split())


def _kassen_apps() -> tuple[AppSpec, ...]:
    apps = []
    for index, (name, tier) in enumerate(zip(KASSEN_NAMES, KASSEN_TIERS)):
        jitter = ((index * 7) % 10) / 10  # 0,0 bis 0,9: macht gleiche Tiers unterschiedlich
        apps.append(AppSpec(
            ident=_slug(name), name=name, tier=tier, platforms=("apple", "google"),
            crash=round(CRASH_BY_TIER[tier] * (0.7 + 0.6 * jitter), 2),
            reply=round(min(0.95, REPLY_BY_TIER[tier] + 0.15 * jitter - 0.05), 2),
            trend=TREND_CYCLE[index % len(TREND_CYCLE)],
            sessions=int(400 + 2600 * ((index * 13) % 17) / 16),
            audience=int(40_000 + 860_000 * ((index * 11) % 23) / 22),
            bad_release=index % 4 == 1, failed=index == 18))
    return tuple(apps)


def _apps(specs: list[tuple[str, str, tuple[str, ...], float, str, int, bool]]) -> tuple[AppSpec, ...]:
    """Kurzform für die übrigen Kategorien: (Name, Tier, Plattformen, Antwortquote, Trend, Sitzungen, Absturzsprung)."""
    return tuple(AppSpec(ident=_slug(name), name=name, tier=tier, platforms=platforms, crash=CRASH_BY_TIER[tier],
                         reply=reply, trend=trend, sessions=sessions, audience=None, bad_release=bad)
                 for name, tier, platforms, reply, trend, sessions, bad in specs)


BOTH = ("apple", "google")
APPLE = ("apple",)

CATEGORIES: dict[str, Category] = {
    "krankenkassen": Category(
        "krankenkassen", "Krankenkassen-Apps", "kassenwerk", "Kassenwerk Software GmbH",
        "de.kassenwerk", _kassen_apps(), {"pos": KASSE_POS, "mid": KASSE_MID, "neg": KASSE_NEG},
        shared_versions=True, major=4),
    "spiele": Category(
        "spiele", "Spiele", "spielwerk", "Spielwerk Studios", "de.spielwerk", _apps([
            ("Turmwächter Legenden", "sehr-gut", BOTH, 0.5, "stabil", 9000, False),
            ("Pixelhof", "gut", BOTH, 0.3, "auf", 4000, False),
            ("Wortduell Arena", "mittel", APPLE, 0.2, "ab", 2500, True),
            ("Nitro Rennfieber", "schlecht", BOTH, 0.1, "stabil", 6000, True),
            ("Kristallreich Saga", "gut", APPLE, 0.4, "stabil", 1800, False)]), SPIELE, major=1),
    "navigation": Category(
        "navigation", "Navigations-Apps", "kartenwerk", "Kartenwerk GmbH", "de.kartenwerk", _apps([
            ("Wegfinder Pro", "gut", BOTH, 0.6, "stabil", 5000, False),
            ("Radroute Deutschland", "sehr-gut", BOTH, 0.7, "auf", 2200, False),
            ("Wanderkompass Alpen", "mittel", APPLE, 0.3, "ab", 900, True)]), NAVIGATION, major=3),
    "sport": Category(
        "sport", "Sport-Apps", "sportlabor", "Sportlabor UG", "de.sportlabor", _apps([
            ("LaufTakt", "gut", BOTH, 0.5, "auf", 3500, False),
            ("FitPlan 30", "mittel", BOTH, 0.3, "stabil", 2800, True),
            ("Kletterlogbuch", "sehr-gut", APPLE, 0.8, "stabil", 600, False)]), SPORT, major=2),
    "ki": Category(
        "ki", "KI-Apps", "ki-schmiede", "KI-Schmiede GmbH", "de.kischmiede", _apps([
            ("Textgeist", "gut", BOTH, 0.6, "auf", 4200, False),
            ("Bildzauber KI", "mittel", APPLE, 0.4, "ab", 1500, True),
            ("Notizdenker", "schlecht", BOTH, 0.2, "ab", 800, False)]), KI, major=1),
    "nachrichten": Category(
        "nachrichten", "Nachrichten-Apps", "medienhaus-nord", "Medienhaus Nord", "de.medienhausnord", _apps([
            ("Tagesblick", "mittel", BOTH, 0.3, "stabil", 12000, False),
            ("Regio-News Nord", "gut", BOTH, 0.5, "auf", 3000, False),
            ("Wirtschaftspuls", "schlecht", APPLE, 0.1, "ab", 2000, True)]), NACHRICHTEN, major=5),
    "finanzen": Category(
        "finanzen", "Finanz-Apps", "finanzfuchs", "Finanzfuchs Software", "de.finanzfuchs", _apps([
            ("Haushaltsbuch Kompakt", "sehr-gut", BOTH, 0.9, "stabil", 2600, False),
            ("Depotblick", "mittel", APPLE, 0.4, "auf", 1200, True)]), FINANZEN, major=6),
    "reisen": Category(
        "reisen", "Reise-Apps", "reisepilot", "Reisepilot GmbH", "de.reisepilot", _apps([
            ("Koffer & Karte", "gut", BOTH, 0.5, "stabil", 1900, False),
            ("Zugplaner Plus", "mittel", BOTH, 0.3, "ab", 7000, True)]), REISEN, major=2),
    "buero": Category(
        "buero", "Büro- und Produktivitäts-Apps", "buerowerk", "Bürowerk Apps", "de.buerowerk", _apps([
            ("Scan2Ordner", "gut", BOTH, 0.6, "auf", 2100, False),
            ("Aufgabenfluss", "sehr-gut", APPLE, 0.8, "stabil", 1400, False)]), BUERO, major=3),
}


# ----------------------------------------------------------------------------------------------------------
# Auswahl und Sicherheit
# ----------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class DemoOptions:
    """Die Wahl des Nutzers für einen Lauf des Generators."""

    categories: tuple[str, ...]
    volume: str = DEFAULT_VOLUME
    months: int = DEFAULT_MONTHS
    reviews: tuple[int, int] | None = None   # Bereich je App; None = Vorgabe des Umfangs
    seed: int | None = None                  # None = aus der Wahl abgeleitet
    apps: int | None = None                  # höchstens so viele Apps je Kategorie (die ersten N); None = alle

    def review_range(self) -> tuple[int, int]:
        return self.reviews or VOLUMES[self.volume].reviews

    def apps_of(self, category: "Category") -> tuple[AppSpec, ...]:
        """Die Apps einer Kategorie nach der gewählten Obergrenze (Reihenfolge der Definition bleibt)."""
        return category.apps if self.apps is None else category.apps[:self.apps]

    def effective_seed(self) -> int:
        if self.seed is not None:
            return self.seed
        text = f"{','.join(self.categories)}|{self.volume}|{self.months}|{self.review_range()}|{self.apps}"
        return zlib.crc32(text.encode("utf-8"))


def parse_range(text: str) -> tuple[int, int]:
    """Liest „MIN-MAX“ (auch „MIN“ allein) als Bereich ganzer Zahlen ab 0; ungültig → ConfigError."""
    parts = [part.strip() for part in text.replace("–", "-").split("-") if part.strip()]
    try:
        numbers = [int(part) for part in parts]
    except ValueError as exc:
        raise ConfigError(f"Bereich '{text}' ist ungültig (erwartet MIN-MAX, z. B. 20-120).") from exc
    if not numbers or len(numbers) > 2 or min(numbers) < 0:
        raise ConfigError(f"Bereich '{text}' ist ungültig (erwartet MIN-MAX, z. B. 20-120).")
    low, high = numbers[0], numbers[-1]
    if low > high:
        low, high = high, low
    return low, high


def validate_options(opts: DemoOptions) -> None:
    """Prüft Kategorien, Umfang und Zeitraum; Fehler als ConfigError mit Handlungsanweisung."""
    unknown = [key for key in opts.categories if key not in CATEGORIES]
    if unknown or not opts.categories:
        raise ConfigError(f"Unbekannte oder fehlende Kategorie {unknown}. Erlaubt: {', '.join(CATEGORIES)}.")
    if opts.volume not in VOLUMES:
        raise ConfigError(f"Unbekannter Umfang '{opts.volume}'. Erlaubt: {', '.join(VOLUMES)}.")
    if not isinstance(opts.months, int) or opts.months < 1 or opts.months > 120:
        raise ConfigError(f"Zeitraum muss zwischen 1 und 120 Monaten liegen (gewählt: {opts.months}).")
    if opts.apps is not None and (not isinstance(opts.apps, int) or isinstance(opts.apps, bool) or opts.apps < 1):
        raise ConfigError(f"Apps je Kategorie muss eine ganze Zahl >= 1 sein oder leer bleiben (gewählt: {opts.apps}).")


def ensure_debug_dir(path: Path, real_data_dir: Path | None) -> Path:
    """Erlaubt nur Ordner mit „debug“ im Namen, die nicht der echte Datenordner sind. Schutz der echten Daten."""
    resolved = path.expanduser().resolve()
    if "debug" not in resolved.name.lower():
        raise ConfigError(f"Testdaten dürfen nur in einen Ordner mit „debug“ im Namen geschrieben werden, nicht nach {resolved}.")
    if real_data_dir is not None and resolved == real_data_dir.resolve():
        raise ConfigError(f"{resolved} ist der Datenordner der echten Konfiguration und wird nicht angefasst.")
    return resolved


# ----------------------------------------------------------------------------------------------------------
# Generator
# ----------------------------------------------------------------------------------------------------------

def _store_id(ident: str) -> str:
    """Zehnstellige, stabile Apple-App-ID aus der App-ID (fest je Name, nie eine echte ID)."""
    return str(6_000_000_000 + zlib.crc32(ident.encode("utf-8")) % 900_000_000)


def _uuid_like(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def _weighted(rng: random.Random, pairs) -> str:
    return rng.choices([item for item, _ in pairs], [weight for _, weight in pairs])[0]


class DemoGenerator:
    """Erzeugt alle Dateien eines Laufs. Zufall nur über `self.rng` (reproduzierbar durch den Startwert)."""

    def __init__(self, opts: DemoOptions, now: datetime | None = None):
        validate_options(opts)
        self.opts = opts
        self.volume = VOLUMES[opts.volume]
        self.rng = random.Random(opts.effective_seed())
        self.now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
        self.start = self.now - timedelta(days=int(opts.months * 30.44))
        self.now_iso = iso_z(self.now)
        self.counts = {"reviews": 0, "stability": 0, "store": 0, "apps": 0, "targets": 0}

    # ---- Versionen ----
    def releases(self, category: Category, app: AppSpec) -> list[dict]:
        """Veröffentlichungen im Zeitraum (plus die Version davor), nach Nutzerwunsch (24.10.2026): eine Funktionsversion
        etwa alle zwei bis drei Monate (`1.0`, `1.1`, `1.2`, …), nach manchen davon ein bis zwei Fehlerbehebungen
        (`1.3.1`, `1.3.2`) wenige Tage bis Wochen später, nach fünf bis sieben kleinen Versionen eine neue Hauptversion
        (`2.0`). Apps einer Kategorie mit gemeinsamem Code teilen die Liste, sonst hat jede App ihre eigene."""
        rng = random.Random(f"{self.opts.effective_seed()}|{category.key}|{'' if category.shared_versions else app.ident}")
        out = []
        moment = self.start - timedelta(days=rng.randint(15, 70))
        major, minor, build = category.major, 0, rng.randint(100, 400)
        next_major_after = rng.randint(5, 7)
        while moment < self.now - timedelta(days=3):
            out.append({"version": f"{major}.{minor}", "build": str(build), "releasedAt": iso_z(moment)})
            fixes = rng.choice((0, 0, 1, 1, 2))
            fix_moment = moment
            for patch in range(1, fixes + 1):
                fix_moment += timedelta(days=rng.randint(3, 21))
                build += rng.randint(1, 4)
                if fix_moment < self.now - timedelta(days=1):
                    out.append({"version": f"{major}.{minor}.{patch}", "build": str(build), "releasedAt": iso_z(fix_moment)})
            moment += timedelta(days=rng.randint(60, 92))
            build += rng.randint(5, 20)
            minor += 1
            if minor >= next_major_after:
                major, minor, next_major_after = major + 1, 0, rng.randint(5, 7)
        return out

    @staticmethod
    def active_version(releases: list[dict], moment_iso: str) -> dict:
        current = releases[0]
        for release in releases:
            if release["releasedAt"] <= moment_iso:
                current = release
        return current

    def bad_release(self, app: AppSpec, releases: list[dict]) -> dict | None:
        """Die Version mit Absturzsprung: die letzte Funktionsversion (ohne Patch-Teil), die mindestens 30 Tage alt ist;
        die Fehlerbehebung danach beendet den Sprung im Verlauf sichtbar."""
        if not app.bad_release:
            return None
        limit = iso_z(self.now - timedelta(days=30))
        features = [release for release in releases if release["version"].count(".") == 1 and release["releasedAt"] <= limit]
        return features[-1] if len(features) > 1 else None

    # ---- Rezensionen ----
    def rating_weights(self, app: AppSpec, frac: float) -> list[float]:
        """Sterneverteilung zum Zeitpunkt `frac` (0 = Beginn, 1 = heute): Trend mischt das Nachbar-Tier dazu."""
        base = TIERS[app.tier]
        index = TIER_ORDER.index(app.tier)
        if app.trend == "stabil":
            return list(base)
        neighbour_index = index + 1 if app.trend == "ab" else index - 1
        neighbour = TIERS[TIER_ORDER[max(0, min(len(TIER_ORDER) - 1, neighbour_index))]]
        return [(1 - frac) * old + frac * new for old, new in zip(base, neighbour)]

    def review_moment(self, releases: list[dict], bad: dict | None) -> datetime:
        """Zeitpunkt einer Rezension: gleichverteilt, mit Schub in den 14 Tagen nach jeder Veröffentlichung."""
        span = (self.now - self.start).total_seconds()
        roll = self.rng.random()
        if bad and roll < 0.25:
            base = datetime.fromisoformat(bad["releasedAt"].replace("Z", "+00:00"))
            return min(self.now, base + timedelta(seconds=self.rng.uniform(0, 14 * 86400)))
        if roll < 0.4:
            release = self.rng.choice(releases)
            base = datetime.fromisoformat(release["releasedAt"].replace("Z", "+00:00"))
            moment = base + timedelta(seconds=self.rng.uniform(0, 14 * 86400))
            if self.start <= moment <= self.now:
                return moment
        return self.start + timedelta(seconds=self.rng.uniform(0, span))

    def review_text(self, category: Category, rating: int, version: str, bad: dict | None, moment_iso: str) -> tuple[str, str]:
        pool = category.phrases["pos" if rating >= 4 else "mid" if rating == 3 else "neg"]
        title, text = self.rng.choice(pool)
        if rating <= 2 and bad and bad["releasedAt"] <= moment_iso and self.rng.random() < 0.5:
            text = f"{text} Seit Version {version} ist es noch schlimmer geworden."
        elif rating == 4 and self.rng.random() < 0.3:
            text = f"{text} Ein Stern Abzug für kleine Bedienfehler."
        return title, text

    def reviews_for(self, category: Category, app: AppSpec, platform: str, store_id: str, releases: list[dict],
                    count: int) -> list[dict]:
        bad = self.bad_release(app, releases)
        span = (self.now - self.start).total_seconds() or 1
        replies = KASSE_REPLIES if category.key == "krankenkassen" else GENERIC_REPLIES
        out = []
        for index in range(count):
            moment = self.review_moment(releases, bad)
            moment_iso = iso_z(moment)
            frac = max(0.0, min(1.0, (moment - self.start).total_seconds() / span))
            weights = self.rating_weights(app, frac)
            release = self.active_version(releases, moment_iso)
            if bad and bad["releasedAt"] <= moment_iso and release["version"] == bad["version"]:
                weights = [weights[0] + 25, weights[1] + 10, weights[2], weights[3], weights[4]]
            rating = self.rng.choices([1, 2, 3, 4, 5], weights)[0]
            title, text = self.review_text(category, rating, release["version"], bad, moment_iso)
            reply = None
            if (rating <= 2 and self.rng.random() < app.reply) or (rating >= 4 and self.rng.random() < app.reply * 0.1):
                replied = moment + timedelta(hours=self.rng.uniform(4, 120))
                reply_text = replies[-1] if rating >= 4 else self.rng.choice(replies[:-1])
                reply = {"text": reply_text, "repliedAt": iso_z(min(replied, self.now)), "state": "PUBLISHED"}
            review_id = f"demo-{platform}-{index:06d}"
            if platform == "apple":
                fields = {"country": _weighted(self.rng, APPLE_COUNTRIES), "appVersion": release["version"]}
            else:
                fields = {"language": "en" if title.isascii() and " " in title and self.rng.random() < 0.8 else "de",
                          "appVersion": release["version"], "buildNumber": release["build"],
                          "operatingSystem": "Android", "osVersion": str(self.rng.choice((13, 14, 15, 16))),
                          "device": self.rng.choice(("Pixel 8", "Galaxy S24", "Galaxy A54", "Xperia 10 V", "Fairphone 5"))}
            out.append(new_review(category.customer_id, app.ident, platform, store_id, review_id, rating=rating, title=title,
                                  text=text, createdAt=moment_iso, developerReply=reply,
                                  raw={"source": "demo", "hinweis": "erfundene Testdaten"}, **fields))
        return out

    def rating_snapshots(self, app: AppSpec, platform: str, releases: list[dict], existing: dict[str, dict]) -> list[dict]:
        """Monatliche Store-Stände je Land (Apple) plus die aus Rezensionen abgeleitete Verteilung."""
        snaps: list[dict] = []
        if platform == "apple":
            total_now = max(20, len(existing) * self.rng.randint(6, 12))
            moment = self.start
            while moment <= self.now:
                frac = (moment - self.start).total_seconds() / ((self.now - self.start).total_seconds() or 1)
                weights = self.rating_weights(app, frac)
                average = round(sum(stars * weight for stars, weight in zip((1, 2, 3, 4, 5), weights)) / sum(weights), 2)
                for country, share in TERRITORIES:
                    total = int(total_now * share / 100 * (0.35 + 0.65 * frac))
                    moment_iso = iso_z(moment)
                    snaps.append({"capturedAt": moment_iso, "origin": "store-official", "source": "itunes-lookup",
                                  "country": country, "appVersion": self.active_version(releases, moment_iso)["version"],
                                  "total": total, "average": round(average + self.rng.uniform(-0.15, 0.15), 2),
                                  "distribution": None,
                                  "currentVersion": {"average": round(average + self.rng.uniform(-0.3, 0.3), 2),
                                                     "total": max(0, int(total * 0.12))}})
                moment += timedelta(days=30)
        derived = derived_distribution(existing)
        if derived["total"]:
            snaps.append({"capturedAt": self.now_iso, "origin": "derived-from-collected-reviews", "source": "reviews.json",
                          "country": None, "appVersion": None, **derived})
        return snaps

    # ---- Kennzahlen (Apple) ----
    def days(self):
        day = self.start.date()
        while day <= self.now.date():
            yield day
            day += timedelta(days=1)

    def stability(self, app: AppSpec, releases: list[dict], store_id: str) -> dict:
        doc = {"schemaVersion": SCHEMA_VERSION, "platform": "apple", "storeAppId": store_id,
               "source": "App Store Connect API – Analytics Reports", "reports": ["App Crashes", "App Sessions Standard"],
               "instances": [], "crashes": [], "sessions": []}
        bad = self.bad_release(app, releases)
        combos = [(share, os_name, device) for share in (0.7, 0.25, 0.05) for os_name in IOS_VERSIONS for device in DEVICES]
        combos = combos[:self.volume.combos]
        for day in self.days():
            day_iso = f"{day.isoformat()}T12:00:00Z"
            current = self.active_version(releases, day_iso)
            older = [release for release in releases if release["releasedAt"] < current["releasedAt"]]
            previous = older[-1] if older else current
            ancient = older[-2] if len(older) > 1 else previous
            weekday = 0.8 if day.weekday() >= 5 else 1.0
            daily = app.sessions * weekday * self.rng.uniform(0.85, 1.15)
            doc["instances"].append(_uuid_like(f"{store_id}|{day}|stability"))
            for share, os_name, device in combos:
                version = current if share == 0.7 else previous if share == 0.25 else ancient
                os_share = {IOS_VERSIONS[0]: 0.6, IOS_VERSIONS[1]: 0.3, IOS_VERSIONS[2]: 0.1}[os_name]
                device_share = 0.8 if device == "iPhone" else 0.2
                sessions = max(1, int(daily * share * os_share * device_share))
                rate = app.crash
                if bad and version["version"] == bad["version"] and bad["releasedAt"] <= day_iso \
                        and day_iso <= iso_z(datetime.fromisoformat(bad["releasedAt"].replace("Z", "+00:00")) + timedelta(days=21)):
                    rate *= 6
                if os_name == IOS_VERSIONS[0]:
                    rate *= 1.2  # das neueste System stürzt etwas öfter ab (frische Fehler)
                crashes = int(sessions * rate / 1000 + (1 if self.rng.random() < (sessions * rate / 1000) % 1 else 0))
                doc["sessions"].append({"date": day.isoformat(), "appVersion": version["version"], "osVersion": os_name,
                                        "device": device, "sessions": sessions,
                                        "durationSeconds": int(sessions * self.rng.uniform(60, 140))})
                if crashes > 0:
                    doc["crashes"].append({"date": day.isoformat(), "appVersion": version["version"], "osVersion": os_name,
                                           "device": device, "crashes": crashes, "uniqueDevices": max(1, int(crashes * 0.7))})
        doc["limitations"] = ["Testdaten: erfundene Werte für Vorführung und Leistungstest, keine Messung."]
        self.counts["stability"] += len(doc["crashes"]) + len(doc["sessions"])
        return doc

    def store_metrics(self, app: AppSpec, releases: list[dict], store_id: str) -> dict:
        doc = {"schemaVersion": SCHEMA_VERSION, "platform": "apple", "storeAppId": store_id,
               "source": "App Store Connect API – Analytics Reports",
               "reports": ["App Downloads Standard", "App Store Installation and Deletion Standard",
                           "App Store Discovery and Engagement Standard"],
               "instances": [], "downloads": [], "installs": [], "engagement": []}
        quality = {"sehr-gut": 1.4, "gut": 1.1, "mittel": 0.9, "schlecht": 0.6, "sehr-schlecht": 0.4}[app.tier]
        # Detailtiefe je Umfang: Länder, Geräte, Download-Arten und Quellen begrenzen die Zeilen je Tag
        territories = TERRITORIES[:self.volume.territories]
        devices = DEVICES[:self.volume.devices]
        download_types = DOWNLOAD_TYPES[:self.volume.download_types]
        sources = SOURCE_TYPES[:self.volume.sources]
        for day in self.days():
            day_iso = f"{day.isoformat()}T12:00:00Z"
            release_boost = 1.0
            for release in releases:
                if 0 <= (datetime.fromisoformat(day_iso.replace("Z", "+00:00"))
                         - datetime.fromisoformat(release["releasedAt"].replace("Z", "+00:00"))).days <= 3:
                    release_boost = 4.0
            base = app.sessions / 25 * quality * self.rng.uniform(0.7, 1.3)
            doc["instances"].append(_uuid_like(f"{store_id}|{day}|store"))
            for territory, share in territories:
                for download_type in download_types:
                    for source in sources:
                        factor = {"First-time download": 1.0, "Redownload": 0.2, "Auto-update": 2.5 * release_boost,
                                  "Manual update": 0.3 * release_boost}[download_type]
                        source_share = {"App Store search": 0.5, "App Store browse": 0.3, "Web referrer": 0.15,
                                        "App referrer": 0.05}[source]
                        for device in devices:
                            counts = int(base * share / 100 * factor * source_share * (0.8 if device == "iPhone" else 0.2) + self.rng.random())
                            if counts > 0:
                                doc["downloads"].append({"date": day.isoformat(), "downloadType": download_type, "sourceType": source,
                                                         "territory": territory, "device": device, "counts": counts})
                for device in devices:
                    installs = int(base * share / 100 * (0.8 if device == "iPhone" else 0.2) + self.rng.random())
                    deletes = int(installs * (0.15 if quality > 1 else 0.45) + self.rng.random())
                    for event, counts in (("Install", installs), ("Delete", deletes)):
                        if counts > 0:
                            doc["installs"].append({"date": day.isoformat(), "event": event, "territory": territory,
                                                    "device": device, "counts": counts})
            for source in sources:
                impressions = int(base * 40 * {"App Store search": 0.5, "App Store browse": 0.35, "Web referrer": 0.1,
                                               "App referrer": 0.05}[source])
                for event, counts in (("Impression", impressions), ("Page view", int(impressions * 0.12)), ("Tap", int(impressions * 0.05))):
                    if counts > 0:
                        doc["engagement"].append({"date": day.isoformat(), "event": event, "sourceType": source, "counts": counts})
        doc["limitations"] = ["Testdaten: erfundene Werte für Vorführung und Leistungstest, keine Messung."]
        self.counts["store"] += len(doc["downloads"]) + len(doc["installs"]) + len(doc["engagement"])
        return doc

    def testflight(self, app: AppSpec, releases: list[dict], store_id: str) -> dict:
        builds, crashes = [], []
        for release in releases[-6:]:
            uploaded = datetime.fromisoformat(release["releasedAt"].replace("Z", "+00:00")) - timedelta(days=5)
            expires = uploaded + timedelta(days=90)
            build_id = _uuid_like(f"{store_id}|build|{release['build']}")
            builds.append({"id": build_id, "build": release["build"], "version": release["version"], "storePlatform": "IOS",
                           "uploadedAt": iso_z(uploaded), "expiresAt": iso_z(expires), "expired": expires < self.now,
                           "processingState": "VALID",
                           "usage": {"periodStart": (self.now - timedelta(days=365)).date().isoformat(),
                                     "periodEnd": self.now.date().isoformat(),
                                     "installCount": self.rng.randint(5, 60), "crashCount": self.rng.randint(0, 4),
                                     "sessionCount": self.rng.randint(50, 900), "inviteCount": self.rng.randint(5, 40),
                                     "feedbackCount": self.rng.randint(0, 3), "capturedAt": self.now_iso}})
            if app.bad_release and release is self.bad_release(app, releases):
                for index in range(self.rng.randint(1, 3)):
                    crashes.append({"id": _uuid_like(f"{build_id}|crash|{index}"), "createdAt": iso_z(uploaded + timedelta(days=1 + index)),
                                    "buildId": build_id, "osVersion": IOS_VERSIONS[0].split(" ")[1], "device": "iPhone 16",
                                    "appPlatform": "IOS"})
        return {"schemaVersion": SCHEMA_VERSION, "platform": "apple", "storeAppId": store_id,
                "source": "App Store Connect API – TestFlight", "builds": builds, "crashes": crashes,
                "limitations": ["Testdaten: erfundene Werte, keine echten TestFlight-Builds."]}

    def google_testing(self, app: AppSpec, releases: list[dict], package: str) -> dict:
        current, previous = releases[-1], releases[-2] if len(releases) > 1 else releases[-1]
        tracks = [{"track": "internal", "releases": [{"name": f"{current['version']} (intern)", "status": "completed",
                                                      "versionCodes": [str(int(current["build"]) + 2)], "userFraction": None}]},
                  {"track": "beta", "releases": [{"name": current["version"], "status": "completed",
                                                  "versionCodes": [current["build"]], "userFraction": None}]},
                  {"track": "production", "releases": [{"name": previous["version"], "status": "completed",
                                                        "versionCodes": [previous["build"]], "userFraction": None}]}]
        rates = []
        for offset in range(min(90, (self.now - self.start).days), 2, -1):
            day = (self.now - timedelta(days=offset)).date().isoformat()
            for code, factor in ((current["build"], 1.0), (previous["build"], 0.7)):
                rate = round(app.crash / 1000 * factor * self.rng.uniform(0.6, 1.4), 5)
                rates.append({"id": f"{day}|{code}", "date": day, "versionCode": code, "crashRate": rate,
                              "userPerceivedCrashRate": round(rate * 0.6, 5), "distinctUsers": self.rng.randint(20, 400)})
        return {"schemaVersion": SCHEMA_VERSION, "platform": "google", "packageName": package,
                "source": "Google Play – Testspuren und Play Developer Reporting API (nicht live geprüft)",
                "tracks": tracks, "tracksCapturedAt": self.now_iso, "crashRates": rates,
                "limitations": ["Testdaten: erfundene Werte, keine echten Google-Daten."]}

    # ---- Ein Ziel (App und Plattform) ----
    def platform_profile(self, app: AppSpec, platform: str) -> AppSpec:
        """Profil einer App je Plattform: Apple = Definition; Google = Stufe verschoben (gerade Position besser, ungerade
        schlechter, an den Enden gespiegelt), nächster Trend im Zyklus, Antwortquote 60 %."""
        if platform != "google":
            return app
        index = TIER_ORDER.index(app.tier)
        shift = -1 if zlib.crc32(app.ident.encode("utf-8")) % 2 == 0 else 1
        if not 0 <= index + shift < len(TIER_ORDER):
            shift = -shift
        trend = TREND_CYCLE[(TREND_CYCLE.index(app.trend) + 1) % len(TREND_CYCLE)]
        return replace(app, tier=TIER_ORDER[index + shift], trend=trend, reply=round(app.reply * 0.6, 3))

    def write_target(self, data_dir: Path, state: dict, category: Category, app: AppSpec, platform: str,
                     releases: list[dict], count: int) -> dict:
        store_id = _store_id(app.ident) if platform == "apple" else f"{category.package_prefix}.{app.ident.replace('-', '')}"
        app = self.platform_profile(app, platform)
        directory = target_dir(data_dir, category.customer_id, app.ident, platform)
        incoming = self.reviews_for(category, app, platform, store_id, releases, count)
        existing: dict[str, dict] = {}
        history: list[dict] = []
        first_seen = iso_z(self.start + timedelta(days=1))
        merge_reviews(existing, incoming, history, first_seen)
        # Einige beantwortete 1–2-Sterne-Rezensionen wurden später hochgesetzt: zweite Zusammenführung erzeugt die Historie
        changed = []
        for review in list(existing.values()):
            if review["rating"] <= 2 and review.get("developerReply") and self.rng.random() < 0.35:
                better = dict(review)
                better["rating"] = review["rating"] + 2
                better["text"] = f"{review['text']} Update: Der Support hat sich gemeldet, Problem gelöst."
                better["updatedAt"] = iso_z(min(self.now, datetime.fromisoformat(review["createdAt"].replace("Z", "+00:00"))
                                                + timedelta(days=self.rng.randint(3, 20))))
                changed.append(better)
        merge_reviews(existing, changed, history, self.now_iso)
        reviews_doc = {"schemaVersion": SCHEMA_VERSION, "customerId": category.customer_id, "appId": app.ident,
                       "platform": platform, "storeAppId": store_id,
                       "reviews": sorted(existing.values(), key=lambda review: (review.get("createdAt") or "", review["id"]),
                                         reverse=True)}
        write_json(directory / "reviews.json", reviews_doc)
        write_json(directory / "review-history.json", {"schemaVersion": SCHEMA_VERSION, "changes": history})
        store_versions = [{"version": release["version"], "build": None, "releasedAt": release["releasedAt"],
                           "createdAt": iso_z(datetime.fromisoformat(release["releasedAt"].replace("Z", "+00:00")) - timedelta(days=7)),
                           "state": "READY_FOR_SALE" if release is releases[-1] else "REPLACED_WITH_NEW_VERSION",
                           "storePlatform": "IOS" if platform == "apple" else "ANDROID"} for release in releases]
        versions = build_versions(platform, store_id, existing, store_versions, {"versions": []}, self.now_iso)
        for entry in versions["versions"]:
            if entry.get("releasedAt"):
                entry["releasedAtSource"] = "demo"
        write_json(directory / "versions.json", versions)
        write_json(directory / "ratings-history.json", {"schemaVersion": SCHEMA_VERSION, "platform": platform, "storeAppId": store_id,
                                                        "snapshots": self.rating_snapshots(app, platform, releases, existing)})
        keys = {platform: len(existing)}
        if platform == "apple":
            stability = self.stability(app, releases, store_id)
            write_json(directory / "stability-metrics.json", stability)
            keys["apple-stability"] = len(stability["crashes"]) + len(stability["sessions"])
            store = self.store_metrics(app, releases, store_id)
            write_json(directory / "store-metrics.json", store)
            keys["apple-store-metrics"] = len(store["downloads"]) + len(store["installs"]) + len(store["engagement"])
            testflight = self.testflight(app, releases, store_id)
            write_json(directory / "testflight.json", testflight)
            keys["apple-testflight"] = len(testflight["builds"])
        else:
            testing = self.google_testing(app, releases, store_id)
            write_json(directory / "google-testing.json", testing)
            keys["google-testing"] = len(testing["crashRates"])
        for key, total in keys.items():
            tstate = get_target_state(state, category.customer_id, app.ident, key, create=True)
            tstate.update(lastSuccessfulSync=self.now_iso, lastFullSync=self.now_iso, lastAttempt=self.now_iso,
                          lastError=None, reviewCount=total, status="ok", lastApiRequests=0)
            if key == "google" and app.failed:
                tstate.update(status="failed", lastError=DEMO_ERROR, lastSuccessfulSync=iso_z(self.now - timedelta(days=9)))
        self.counts["reviews"] += len(existing)
        self.counts["targets"] += 1
        return {"customer": category.customer_id, "app": app.ident, "platform": platform,
                "status": "failed" if (platform == "google" and app.failed) else "ok", "mode": "full",
                "apiRequests": 0, "responses": 0, "retries": 0, "durationSeconds": 0.0, "new": len(existing), "updated": len(changed),
                "unchanged": 0, "total": len(existing), "errors": [DEMO_ERROR] if (platform == "google" and app.failed) else [],
                "lastSuccessfulSync": self.now_iso}

    # ---- Konfiguration ----
    def config_document(self, source: Path | None) -> dict:
        """Debug-Konfiguration: erfundene Kunden und Apps, Platzhalter-Zugänge (nie gültig), KI-Block aus der echten Datei."""
        customers = []
        for key in self.opts.categories:
            category = CATEGORIES[key]
            customers.append({
                "id": category.customer_id, "name": category.customer_name, "enabled": True,
                "credentials": {"apple": {"issuerId": "00000000-0000-0000-0000-000000000000", "keyId": "DEMO000000",
                                          "privateKeyEnvironmentVariable": "DEMO_APPLE_PRIVATE_KEY_NICHT_SETZEN"},
                                "google": {"serviceAccountEnvironmentVariable": "DEMO_GOOGLE_SERVICE_ACCOUNT_NICHT_SETZEN"}},
                "apps": [{"id": app.ident, "name": app.name, "enabled": True, "audience": app.audience, "platforms": {
                    **({"apple": {"enabled": True, "appId": _store_id(app.ident), "countries": [],
                                  "ratingCountries": list(RATING_COUNTRIES)}} if "apple" in app.platforms else {}),
                    **({"google": {"enabled": True, "packageName": f"{category.package_prefix}.{app.ident.replace('-', '')}",
                                   "languages": []}} if "google" in app.platforms else {})}}
                         for app in self.opts.apps_of(category)]})
        if customers:  # Wettbewerber nur beim ersten Kunden; echte öffentliche Apps, siehe DEMO_COMPETITORS
            customers[0]["competitors"] = [
                {"id": ident, "name": name, "enabled": True, "vendor": vendor,
                 "apple": {"appId": app_id, "countries": list(RATING_COUNTRIES)}}
                for ident, name, vendor, app_id in DEMO_COMPETITORS]
        doc: dict[str, Any] = {
            "schemaVersion": CONFIG_SCHEMA,
            "_hinweis": "Von demo.py erzeugt: erfundene Apps und Testdaten für den Debug-Modus (kurzmenudebug.sh). "
                        "Wird bei jedem Lauf überschrieben. Zugangsdaten sind Platzhalter ohne Schlüssel; ein Abruf bei "
                        "Apple oder Google ist damit unmöglich.",
            "settings": {**DEFAULT_SETTINGS, "outputDirectory": DEBUG_DATA_DIR, "reportDirectory": DEBUG_REPORT_DIR,
                         "minRefreshMinutes": 0, "defaultStartDate": self.start.date().isoformat()},
            "customers": customers,
        }
        if source and source.is_file():
            try:
                raw = load_config(source, strict=False).raw
            except ToolError:
                raw = {}
            if isinstance(raw.get("ai"), dict):
                doc["ai"] = raw["ai"]
        return doc

    # ---- Lauf ----
    def run(self, data_dir: Path, report_dir: Path | None, config_path: Path, source_config: Path | None) -> dict:
        """Löscht den Debug-Datenordner, erzeugt alle Dateien und die Debug-Konfiguration; liefert die Zähler."""
        if data_dir.exists():
            shutil.rmtree(data_dir)
        if report_dir is not None and report_dir.exists() and "debug" in report_dir.name.lower():
            shutil.rmtree(report_dir)
        data_dir.mkdir(parents=True, exist_ok=True)
        state = empty_state()
        results = []
        low, high = self.opts.review_range()
        for key in self.opts.categories:
            category = CATEGORIES[key]
            for app in self.opts.apps_of(category):
                releases = self.releases(category, app)
                count = self.rng.randint(low, high)
                self.counts["apps"] += 1
                for platform in app.platforms:
                    per_platform = count if platform == "apple" else max(0, int(count * self.rng.uniform(0.6, 1.1)))
                    results.append(self.write_target(data_dir, state, category, app, platform, releases, per_platform))
        write_json(data_dir / "state.json", state)
        write_json(data_dir / "sync-history.json", {"schemaVersion": 1, "runs": [{
            "startedAt": self.now_iso, "finishedAt": self.now_iso, "durationSeconds": 0.0,
            "options": {"customer": None, "app": None, "platform": "all", "from": None, "to": None, "fullSync": True,
                        "demo": {"categories": list(self.opts.categories), "volume": self.opts.volume, "months": self.opts.months,
                                 "reviews": list(self.opts.review_range()), "seed": self.opts.effective_seed()}},
            "results": results}]})
        write_json(config_path, self.config_document(source_config))
        return dict(self.counts)


def generate(opts: DemoOptions, root: Path, config_path: Path | None = None, source_config: Path | None = None,
             now: datetime | None = None) -> dict:
    """Einstieg: prüft die Wahl, schützt die echten Daten und erzeugt alles unter `root`.

    `config_path`: Ziel der Debug-Konfiguration (Standard `config/config.debug.json` unter `root`); Daten- und
    Berichtsordner (`./data-debug`, `./reports-debug`) liegen relativ zu ihrem Projektordner (`config.base_dir_of`),
    genau wie `load_config` sie später auflöst. `source_config`: echte Konfiguration, aus der nur der KI-Block übernommen
    wird (Standard `config/config.json` unter `root`, falls vorhanden).
    """
    validate_options(opts)
    config_path = (config_path or root / DEBUG_CONFIG).resolve()
    base = base_dir_of(config_path)
    source_config = source_config if source_config is not None else root / "config" / "config.json"
    real_data_dir = None
    if source_config.is_file():
        try:
            real_data_dir = load_config(source_config, strict=False).data_dir
        except ToolError:
            real_data_dir = None
    data_dir = ensure_debug_dir(base / DEBUG_DATA_DIR, real_data_dir)
    report_dir = (base / DEBUG_REPORT_DIR).resolve()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    generator = DemoGenerator(opts, now)
    counts = generator.run(data_dir, report_dir, config_path, source_config)
    counts.update(dataDir=str(data_dir), reportDir=str(report_dir), config=str(config_path), seed=opts.effective_seed(),
                  months=opts.months, volume=opts.volume, reviewRange=list(opts.review_range()), appsPerCategory=opts.apps)
    return counts
