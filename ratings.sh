#!/bin/bash
# ratings.sh – one entry point for all commands (sets up the venv itself, no "source" needed).
# Usage: ./ratings.sh <command> [more options for collect.py, e.g. --app scanbox --platform apple]
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

# Nur die Optionen, die report.py versteht (--customer, --app, --platform), aus "$@" übernehmen.
report_args() {
  local out=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --customer|--app|--platform) [ $# -ge 2 ] && out+=("$1" "$2"); shift 2 ;;
      --customer=*|--app=*|--platform=*) out+=("$1"); shift ;;
      *) shift ;;
    esac
  done
  [ ${#out[@]} -gt 0 ] && printf '%s\0' "${out[@]}"
  return 0
}

show_help() {
cat <<'TXT'
Commands:
  menu                 interactive menu
  fetch     [opt]      fetch reviews (first run: everything, then only new ones), then print statistics
  full      [opt]      re-read everything (--full-sync, never deletes)
  force     [opt]      fetch, ignore the wait period (--force)
  dry-run   [opt]      trial run, nothing is saved (--dry-run)
  range FROM TO [opt]  fetch only a period, format YYYY-MM-DD
  stability [opt]      fetch stability: crashes + sessions (Apple only, --dataset stability)
  testdata  [opt]      fetch test operation data: Apple TestFlight + Google Play test tracks (--dataset testing)
  all       [opt]      fetch reviews + stability + test data, build report, open browser
  daily     [opt]      FOR CI/cron: at most once per day (UTC): fetch everything + report/markdown/ZIP, no browser
  report               build report (+ markdown summaries of the last 14 days) and open it
  markdown  [opt]      only markdown + ZIP for sending (reports/markdown/, reports/zusammenfassung-DATE.zip)
  open                 only open the last report
  status               status per app (no network)
  apps                 show configured apps (no network)
  import-csv FILE… --customer ID --app ID    import a Google Play console CSV
  test                 run the automated tests
  backup               pack data/ as backup-DATE.tgz
  reset     [opt]      delete data and start over (backup + confirmation). Partial: --app ID / --customer ID. --dry-run only shows
  help                 this overview
[opt] = any collect.py option, e.g.: --customer customer --app scanbox --platform apple
TXT
}

cmd="${1:-help}"; shift 2>/dev/null
# Old German names keep working silently.
case "$cmd" in
  abrufen) cmd=fetch ;; voll) cmd=full ;; probe) cmd=dry-run ;; zeitraum) cmd=range ;; stabilitaet) cmd=stability ;;
  alles) cmd=all ;; taeglich) cmd=daily ;; bericht) cmd=report ;; oeffnen) cmd=open ;; csv) cmd=import-csv ;;
  tests) cmd=test ;; testbetrieb) cmd=testdata ;; sicherung) cmd=backup ;; zuruecksetzen) cmd=reset ;; hilfe|-h|--help) cmd=help ;;
esac
ensure_venv
open_report() { open reports/index.html 2>/dev/null || xdg-open reports/index.html; }
case "$cmd" in
  menu)      exec $PY menu.py ;;
  fetch)     $PY collect.py "$@" ;;
  full)      $PY collect.py --full-sync "$@" ;;
  force)     $PY collect.py --force "$@" ;;
  dry-run)   $PY collect.py --dry-run "$@" ;;
  range)     [ $# -ge 2 ] || { echo "Usage: ./ratings.sh range 2025-01-01 2025-12-31"; exit 2; }
             from="$1"; to="$2"; shift 2; $PY collect.py --from "$from" --to "$to" "$@" ;;
  stability) $PY collect.py --dataset stability "$@" ;;
  testdata)  $PY collect.py --dataset testing "$@" ;;
  all)       $PY collect.py --dataset all "$@"; code=$?
             if [ $code -le 1 ]; then $PY report.py && open_report; fi
             exit $code ;;
  daily)     # Abruf höchstens einmal pro Tag; der Bericht wird immer neu erzeugt. Fehler des Berichts erscheinen
             # im Log und machen den Lauf fehlgeschlagen (Exit-Code mindestens 1).
             $PY collect.py --dataset all --once-per-day "$@"; code=$?
             rargs=(); while IFS= read -r -d '' a; do rargs+=("$a"); done < <(report_args "$@")
             if ! $PY report.py --zip "${rargs[@]}" >/dev/null; then
               echo "Fehler: Bericht konnte nicht erzeugt werden (report.py, siehe Meldung oben)." >&2
               [ $code -eq 0 ] && code=1
             fi
             exit $code ;;
  report)    $PY report.py "$@" && open_report ;;
  markdown)  $PY report.py --zip "$@" ;;
  open)      open_report ;;
  status)    $PY collect.py --status ;;
  apps)      $PY collect.py --list-apps ;;
  import-csv) $PY collect.py --import-google-csv "$@" ;;
  test)      ensure_dev_tools; $PY -m pytest tests -q ;;
  backup)    f="backup-$(date +%F).tgz"; tar czf "$f" data && echo "Saved: $f" ;;
  reset)     $PY reset.py "$@" ;;
  help)      show_help ;;
  *)         echo "Unknown command: $cmd"; show_help; exit 2 ;;
esac
