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
  debug-menu           short menu in DEBUG mode: fictional test data only, no Apple/Google requests (kurzmenudebug.sh)
  demo      [opt]      generate fictional test data into data-debug/ + config/config.debug.json (demo.py; --list-categories,
                       --categories a,b --volume wenig|mittel|viele|sehr-viele --months N --reviews MIN-MAX --seed N)
  fetch     [opt]      fetch reviews (first run: everything, then only new ones), then print statistics
  full      [opt]      re-read everything (--full-sync, never deletes)
  force     [opt]      fetch, ignore the wait period (--force)
  dry-run   [opt]      trial run, nothing is saved (--dry-run)
  range FROM TO [opt]  fetch only a period, format YYYY-MM-DD
  stability [opt]      fetch stability: crashes + sessions (Apple only, --dataset stability)
  store     [opt]      fetch store figures: downloads, installs/deletions, store views (Apple only, --dataset store)
  testdata  [opt]      fetch test operation data: Apple TestFlight + Google Play test tracks (--dataset testing)
  competitors [opt]    APPLE ONLY: fetch competitor apps (customers[].competitors) from Apple's public review feed + lookup,
                       no credentials (--dataset competitors; newest 500 reviews per country; Google has no public source;
                       nothing happens without entries)
  analyze   [opt]      AI analysis of stored reviews (--dataset ai): sentiment, summary, reply drafts; needs an enabled provider; rebuilds the report
  ask "QUESTION" [opt] ask the AI a free-text question about the stored reviews (ai.features.questions must be true)
  ai-themes [opt]      list AI theme suggestions; --accept NR adds one to config/themen.json, --ignore NR rejects it
  ai-usage             AI provider in use, token usage and estimated cost per month and per app (no network)
  ai-models            supported AI models per provider with list prices (no network)
  ai-questions [--delete NR | --clear]   stored questions and answers; delete one or all (no network)
  ai-serve [--port N]  local question service for the report (127.0.0.1 only, Ctrl+C stops); rebuild the report while it runs
  ai-report [opt]      ONE command: start the question service, rebuild the report, open it in the browser, keep serving until Ctrl+C
  all       [opt]      fetch reviews + stability + store figures + test data + competitors (Apple only) (+ AI analysis if a provider is enabled), build report, open browser
  daily     [opt]      FOR CI/cron: at most once per day (UTC): fetch everything + report/markdown/ZIP + notification, no browser
  notify    [opt]      notification after the daily run: new 1–2 ★, status change, crash jump via e-mail/Slack/webhook
                       (--dry-run shows the message, --test sends a test message; reads data only, no store API)
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
  tests) cmd=test ;; testbetrieb) cmd=testdata ;; wettbewerber) cmd=competitors ;; sicherung) cmd=backup ;; zuruecksetzen) cmd=reset ;; hilfe|-h|--help) cmd=help ;;
  ki|analysieren) cmd=analyze ;; frage) cmd=ask ;; ki-themen) cmd=ai-themes ;; ki-verbrauch) cmd=ai-usage ;; ki-modelle) cmd=ai-models ;; ki-dienst) cmd=ai-serve ;;
  ki-bericht) cmd=ai-report ;; ki-fragen) cmd=ai-questions ;; benachrichtigen|benachrichtigung) cmd=notify ;;
esac
ensure_venv
open_report() { open reports/index.html 2>/dev/null || xdg-open reports/index.html; }
case "$cmd" in
  menu)      exec $PY menu.py ;;
  debug-menu) exec $PY menu.py --kurz --debug ;;
  demo)      $PY demo.py "$@" ;;
  fetch)     $PY collect.py "$@" ;;
  full)      $PY collect.py --full-sync "$@" ;;
  force)     $PY collect.py --force "$@" ;;
  dry-run)   $PY collect.py --dry-run "$@" ;;
  range)     [ $# -ge 2 ] || { echo "Usage: ./ratings.sh range 2025-01-01 2025-12-31"; exit 2; }
             from="$1"; to="$2"; shift 2; $PY collect.py --from "$from" --to "$to" "$@" ;;
  stability) $PY collect.py --dataset stability "$@" ;;
  store)     $PY collect.py --dataset store "$@" ;;
  testdata)  $PY collect.py --dataset testing "$@" ;;
  competitors) $PY collect.py --dataset competitors "$@" ;;
  analyze)   # KI-Analyse, danach den Bericht neu erzeugen (sonst zeigt er den alten Stand ohne KI-Daten); kein Browser
             $PY collect.py --dataset ai "$@"; code=$?
             if [ $code -le 1 ]; then
               rargs=(); while IFS= read -r -d '' a; do rargs+=("$a"); done < <(report_args "$@")
               $PY report.py "${rargs[@]}" || code=1
             fi
             exit $code ;;
  ask)       [ $# -ge 1 ] || { echo "Usage: ./ratings.sh ask \"Welche Apps erwähnen das Bonusprogramm?\" [--customer ID --app ID]"; exit 2; }
             $PY ki.py ask "$@" ;;
  ai-themes) $PY ki.py themes "$@" ;;
  ai-usage)  $PY ki.py usage ;;
  ai-models) $PY ki.py models ;;
  ai-questions) $PY ki.py questions "$@" ;;
  ai-serve)  $PY ki.py serve "$@" ;;
  ai-report) $PY ki.py serve --report --open "$@" ;;
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
             # Benachrichtigung zuletzt: Ampel, KI-Sätze und der verlinkte Bericht sind dann aktuell. Bei notify.enabled false
             # endet notify.py still mit 0; ein Zustellfehler macht den Lauf fehlgeschlagen, blockiert aber nichts.
             if ! $PY notify.py; then
               echo "Fehler: Benachrichtigung fehlgeschlagen (notify.py, siehe Meldung oben)." >&2
               [ $code -eq 0 ] && code=1
             fi
             exit $code ;;
  notify)    $PY notify.py "$@" ;;
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
