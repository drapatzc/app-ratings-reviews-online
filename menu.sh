#!/bin/bash
# menu.sh – startet das interaktive Menü (menu.py) von überall aus.
# Funktioniert auch als Symlink, z. B.: ln -s "$PWD/menu.sh" /usr/local/bin/bew
# Richtet beim ersten Start die Python-Umgebung (.venv) selbst ein; weitere Argumente gehen an menu.py.

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
exec "$PY" menu.py "$@"
