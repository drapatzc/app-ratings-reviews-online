#!/bin/bash
# kurzmenu.sh – kleines Menü mit den drei wichtigsten Funktionen (gleiche Optik und Bedienung wie das große Menü):
#   1 Alles abrufen (Rezensionen + Stabilität, danach Bericht und Markdown neu erzeugen, kein ZIP)
#   2 Status je App anzeigen (ohne Internet)
#   3 Bericht im Browser anzeigen (wird erzeugt, falls er fehlt)
#   H Hilfe, Q Beenden
# Technisch: menu.py --kurz. Funktioniert von jedem Ordner aus, auch als Symlink.

# Echten Speicherort ermitteln (Symlinks auflösen), damit Pfade zu config/, data/ und reports/ stimmen.
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
require_config
exec "$PY" menu.py --kurz "$@"
