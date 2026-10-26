#!/bin/bash
# kurzmenudebug.sh – Kurzmenü im Debug-Modus: gleiche drei Punkte wie kurzmenu.sh, aber nur mit erfundenen Testdaten.
#   1 Testdaten erzeugen (löscht data-debug/, fragt Apps pro Gruppe, Kategorien, Umfang, Zeitraum; danach Bericht)
#   2 Status je App anzeigen (Testdaten, ohne Internet)
#   3 Bericht im Browser anzeigen (reports-debug/index.html, wird erzeugt, falls er fehlt)
#   H Hilfe, Q Beenden
# Es wird keine Anfrage an Apple oder Google gesendet. Die echten Daten (data/, reports/, config/config.json) bleiben
# unangetastet; Konfiguration ist config/config.debug.json (wird von demo.py erzeugt). Für echte Daten: kurzmenu.sh.
# Technisch: menu.py --kurz --debug. Funktioniert von jedem Ordner aus, auch als Symlink.

# Echten Speicherort ermitteln (Symlinks auflösen), damit Pfade zu config/, data-debug/ und reports-debug/ stimmen.
src="${BASH_SOURCE[0]}"
while [ -L "$src" ]; do
  dir="$(cd -P "$(dirname "$src")" && pwd)"
  src="$(readlink "$src")"
  [[ "$src" != /* ]] && src="$dir/$src"
done
cd "$(cd -P "$(dirname "$src")" && pwd)" || exit 1
# shellcheck source=lib/common.sh
. lib/common.sh

ensure_venv
# Keine require_config: die Debug-Konfiguration entsteht beim ersten „Testdaten erzeugen“.
exec "$PY" menu.py --kurz --debug "$@"
