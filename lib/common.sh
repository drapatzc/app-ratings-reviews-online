# lib/common.sh – gemeinsame Vorprüfungen für ratings.sh, menu.sh und kurzmenu.sh.
# Wird per "source" geladen. Erwartet, dass das aktuelle Verzeichnis der Projektordner ist
# (die aufrufenden Scripte wechseln vorher dorthin, auch wenn sie über einen Symlink gestartet wurden).

PY=".venv/bin/python"

# Legt die Python-Umgebung beim ersten Start an. Installiert nur die Laufzeit-Abhängigkeit (cryptography);
# pytest kommt erst mit ensure_dev_tools dazu, wenn die Tests laufen sollen.
ensure_venv() {
  [ -x "$PY" ] && return 0
  command -v python3 >/dev/null || { echo "python3 nicht gefunden. Bitte Python 3.10 oder neuer installieren."; exit 2; }
  echo "Python-Umgebung wird eingerichtet …"
  python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt || exit 1
}

# Installiert die Entwicklungswerkzeuge (pytest) bei Bedarf nach.
ensure_dev_tools() {
  ensure_venv
  "$PY" -c "import pytest" 2>/dev/null && return 0
  echo "Testwerkzeug pytest wird installiert …"
  .venv/bin/pip install -q -r requirements-dev.txt || exit 1
}

# Bricht mit Hinweis ab, wenn config/config.json fehlt.
require_config() {
  [ -f config/config.json ] && return 0
  echo "config/config.json fehlt. Vorlage kopieren und anpassen:"
  echo "  cp config/config.example.json config/config.json"
  exit 2
}
