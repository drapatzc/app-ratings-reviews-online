# app-ratings-reviews

A small command-line tool that collects app ratings, reviews, stability data and test-build data from
**Apple App Store Connect** and **Google Play**, stores everything locally as JSON and builds a
self-contained HTML report plus Markdown summaries you can send to customers.

It is built for agencies and developers who look after several apps for several customers: one
configuration file, one command, one report.

- No database, no server, no backend. Everything lives in local JSON files.
- Read-only towards Apple and Google. The tool never changes anything in App Store Connect or the
  Play Console.
- Only one Python dependency (`cryptography`, for signing the API tokens).
- Safe to run as often as you like: reviews are de-duplicated, nothing is ever deleted except via
  an explicit `reset` (with backup and confirmation).

---

## Contents

1. [What the tool does](#what-the-tool-does)
2. [Requirements](#requirements)
3. [Installation](#installation)
4. [Setting up Apple (App Store Connect)](#setting-up-apple-app-store-connect)
5. [Setting up Google (Play Console)](#setting-up-google-play-console)
6. [Configuration](#configuration)
7. [Working with the tool](#working-with-the-tool)
8. [Commands (`ratings.sh`)](#commands-ratingssh)
9. [Menus](#menus)
10. [Files and folders](#files-and-folders)
11. [Daily automatic run](#daily-automatic-run)
12. [Known limitations](#known-limitations)
13. [Troubleshooting](#troubleshooting)

---

## What the tool does

| Data | Source | Command |
|---|---|---|
| **Reviews** (text, stars, title, territory, developer response) | Apple: App Store Connect API `customerReviews`; Google: Play Developer API `reviews.list` | `fetch` |
| **Official store rating** (average + count per country) | Apple: public iTunes Lookup API | part of `fetch` (`ratingCountries`) |
| **App versions** | Apple: `appStoreVersions` | part of `fetch` |
| **Stability**: crashes and sessions per day / version / OS / device | Apple Analytics Reports ("App Crashes", "App Sessions Standard") | `stability` |
| **Test operation**: TestFlight builds, installs, sessions, crashes | Apple TestFlight (`builds`, `betaBuildUsages`, `betaFeedbackCrashSubmissions`) | `testdata` |
| **Test operation**: test tracks and crash rates per version code | Google: `edits/tracks` + Play Developer Reporting API | `testdata` |
| **Historic Google reviews** | Play Console CSV export | `import-csv` |

From the stored data the tool generates:

- `reports/index.html` – an interactive, self-contained HTML report (no external resources), with
  help, imprint and privacy pages next to it.
- `reports/markdown/*.md` – one summary per app and platform covering the last 14 days, plus an
  overview file `00-uebersicht.md`.
- Optionally `reports/zusammenfassung-<date>.zip` – all summaries packed for sending.

**How fetching works:**

- First run per app: everything available is fetched. After that the run is incremental (Apple:
  newest pages back to "last success minus `overlapDays`"; Google: the API only returns the last
  7 days anyway).
- Every `fullSyncIntervalDays` (default 30) a full re-read happens automatically, to catch later
  edits of old Apple reviews.
- If an app was fetched successfully less than `minRefreshMinutes` ago (default 30), it is skipped
  without any API request. `force` overrides this.
- Errors in one app do not stop the others. Data fetched before an error is saved anyway.
- HTTP 429 and 5xx are retried automatically with backoff (respecting `Retry-After`).
- Tokens, JWTs and private keys are removed from all log and error output.

---

## Requirements

- macOS, Linux (recommended for servers) or Windows
- Python **3.10** or newer, with `venv` and `pip`
- Outgoing HTTPS access to:
  - `api.appstoreconnect.apple.com`, `itunes.apple.com` and Apple's download hosts for analytics reports
  - `androidpublisher.googleapis.com`, `oauth2.googleapis.com`, `playdeveloperreporting.googleapis.com`
- No incoming port is needed. A proxy can be set via `HTTPS_PROXY`.

---

## Installation

```bash
git clone <repo-url> ~/app-ratings-reviews
cd ~/app-ratings-reviews

# Python environment (optional – ratings.sh, menu.sh and kurzmenu.sh do this on first start)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt

# Configuration and key folder
cp config/config.example.json config/config.json
mkdir -p keys && chmod 700 keys
chmod 600 config/config.json
```

Then put your keys into `keys/` (see the Apple and Google sections below), fill in
`config/config.json` and check the setup:

```bash
./ratings.sh apps        # shows all configured apps, validates config.json (no network)
./ratings.sh dry-run     # real API calls, but nothing is saved
./ratings.sh all         # the real first run: fetch everything, build report, open browser
```

**Optional: start the menu from anywhere**

```bash
ln -s "$PWD/menu.sh" /usr/local/bin/bew          # big menu
ln -s "$PWD/kurzmenu.sh" /usr/local/bin/bewk     # short menu
```

The scripts resolve symlinks, so paths to `config/`, `data/` and `reports/` stay correct.

---

## Setting up Apple (App Store Connect)

You need this **once per developer account** (i.e. per customer who has their own Apple account).

### 1. Create a team API key

1. Open [App Store Connect](https://appstoreconnect.apple.com) → **Users and Access** →
   **Integrations** → **App Store Connect API** → **Team Keys**.
2. Click **Generate API Key** (or **+**). Use a **team key**, not an individual key.
   Only the Account Holder or an Admin can do this.
3. Name: e.g. `app-ratings-reviews`.
4. Access / role:
   - **App Manager** – required for stability (Analytics) and TestFlight data.
   - **Customer Support** – is enough if you only want reviews.
5. Download the file `AuthKey_<KeyID>.p8`. **It can only be downloaded once.**
6. Note the **Issuer ID** (shown above the key list) and the **Key ID** (in the list and in the file name).

| Value | Format | Where it goes in `config.json` |
|---|---|---|
| Issuer ID | UUID, e.g. `11111111-2222-3333-4444-555555555555` | `credentials.apple.issuerId` |
| Key ID | 10 characters, e.g. `ABC123DEFG` | `credentials.apple.keyId` |
| Private key | file `AuthKey_ABC123DEFG.p8` (starts with `-----BEGIN PRIVATE KEY-----`) | `credentials.apple.privateKeyFile` (path) **or** `privateKeyEnvironmentVariable` |
| App ID | number, e.g. `1540650069` | `apps[].platforms.apple.appId` |

Store the key like this:

```bash
mv ~/Downloads/AuthKey_ABC123DEFG.p8 keys/customer-a.p8
chmod 600 keys/customer-a.p8
```

The tool creates the short-lived JWT itself (ES256, 15 minutes). You never have to generate a
token by hand. The key text must **never** be put into `config.json` – the tool refuses to start
if it finds a private key there.

### 2. Find the numeric App ID

App Store Connect → your app → **App Information** → **Apple ID**.
Or take it from the App Store URL: `https://apps.apple.com/app/id1540650069` → `1540650069`.

### 3. Enable Analytics reports (only for stability data)

The tool only **reads** an existing analytics report request – it never creates one.
For every app you want stability data for, create **once** an analytics report request with
access type **ONGOING** in App Store Connect (App → **Analytics** → reports / via the API
`POST /v1/analyticsReportRequests` with `accessType: ONGOING`).

- Apple only provides data **from the moment the request was created** onwards.
- It can take one to two days until the first report instances are available.
- The first `stability` run per app needs roughly 100–150 requests; later runs only load new
  report instances.

Without an ONGOING request, `stability` reports the error
"Keine laufende Analytics-Berichtsanfrage (ONGOING) für diese App" for that app.

### 4. TestFlight

Nothing extra to set up. The key needs the **App Manager** role. No tester names, e-mail
addresses, comments or crash logs are stored.

---

## Setting up Google (Play Console)

Only needed if you have Android apps. Otherwise set `"enabled": false` for the `google` platform
or leave the entry out.

> **Note:** The Google integration is implemented and tested against mocks, but has not yet been
> verified against a real Play Console account. Check the results carefully on first use.

### 1. Google Cloud project and service account

One Cloud project is enough for all customers.

1. Open the [Google Cloud Console](https://console.cloud.google.com) and create a project
   (e.g. `app-ratings-reviews`).
2. **APIs & Services** → **Library** → enable:
   - **Google Play Android Developer API** (reviews, test tracks)
   - **Google Play Developer Reporting API** (crash rates, only needed for `testdata`)
3. **IAM & Admin** → **Service Accounts** → **Create service account**. No project roles needed.
4. Open the service account → **Keys** → **Add key** → **Create new key** → **JSON**.
   Save the downloaded file:

   ```bash
   mv ~/Downloads/<project>-xxxx.json keys/customer-a-google.json
   chmod 600 keys/customer-a-google.json
   ```

### 2. Invite the service account in the Play Console

The owner (or an admin) of the Play Console account must do this:

1. [Play Console](https://play.google.com/console) → **Users and permissions** → **Invite new users**.
2. E-mail address: the `client_email` of the service account
   (e.g. `ratings@my-project.iam.gserviceaccount.com`).
3. Permissions (account-wide or per app):
   - **View app information (read-only)**
   - **Reply to reviews** / view reviews
   - optional: **View app quality information** (for crash rates)
4. Send the invitation. **Permissions can take up to 48 hours to become active.**

One service account can be invited into several Play Console accounts (several customers).

### 3. Package name

Take it from the Play Store URL: `https://play.google.com/store/apps/details?id=de.company.app` →
`de.company.app`.

| Value | Format | Where it goes in `config.json` |
|---|---|---|
| Service account key | JSON file with `client_email`, `private_key`, `token_uri` | `credentials.google.serviceAccountFile` (path) **or** `serviceAccountEnvironmentVariable` |
| Package name | e.g. `de.company.app` | `apps[].platforms.google.packageName` |

### 4. Older Google reviews (CSV import)

The Google API only returns reviews from the **last 7 days**. For older reviews:

1. Play Console → **Download reports** → **Reviews** → pick the app and month(s).
2. You get files like `reviews_<package>_YYYYMM.csv` (usually UTF-16).
3. Import them:

   ```bash
   ./ratings.sh import-csv ~/Downloads/reviews_de.company.app_*.csv --customer customer-a --app my-app
   ```

Duplicates are detected; changed reviews go into `review-history.json`.

---

## Configuration

File: `config/config.json` (copy of `config/config.example.json`). This file is in `.gitignore`
and must never be committed.

### Full example

```json
{
  "schemaVersion": 1,
  "settings": {
    "outputDirectory": "./data",
    "reportDirectory": "./reports",
    "defaultStartDate": "2024-01-01",
    "defaultEndDate": null,
    "requestTimeoutSeconds": 30,
    "maxRetries": 3,
    "incrementalSync": true,
    "overlapDays": 7,
    "minRefreshMinutes": 30,
    "fullSyncIntervalDays": 30,
    "fetchAppleVersions": true,
    "logLevel": "INFO"
  },
  "customers": [
    {
      "id": "customer-a",
      "name": "Customer A",
      "enabled": true,
      "credentials": {
        "apple": {
          "issuerId": "11111111-2222-3333-4444-555555555555",
          "keyId": "ABC123DEFG",
          "privateKeyFile": "./keys/customer-a.p8"
        },
        "google": {
          "serviceAccountFile": "./keys/customer-a-google.json"
        }
      },
      "apps": [
        {
          "id": "my-app",
          "name": "My App",
          "enabled": true,
          "platforms": {
            "apple": {
              "enabled": true,
              "appId": "1234567890",
              "countries": [],
              "ratingCountries": ["DE", "AT", "CH"]
            },
            "google": {
              "enabled": true,
              "packageName": "de.company.app",
              "languages": []
            }
          }
        }
      ]
    }
  ]
}
```

### `settings`

| Key | Meaning | Default |
|---|---|---|
| `outputDirectory` | Folder for the JSON data (relative to the project folder or absolute) | `./data` |
| `reportDirectory` | Folder for the HTML report and Markdown files | `./reports` |
| `defaultStartDate` / `defaultEndDate` | Limits for full fetches, by review creation date (`YYYY-MM-DD` or `null`) | `null` |
| `requestTimeoutSeconds` | Timeout per HTTP request in seconds | `30` |
| `maxRetries` | Retries on 429, 5xx and network errors | `3` |
| `incrementalSync` | Fetch incrementally by default | `true` |
| `overlapDays` | Safety overlap in days for incremental Apple fetches | `7` |
| `minRefreshMinutes` | Minimum minutes between two successful fetches of the same app (`force` ignores it) | `30` |
| `fullSyncIntervalDays` | After this many days a full re-read happens automatically | `30` |
| `fetchAppleVersions` | Also fetch the list of App Store versions | `true` |
| `logLevel` | `DEBUG`, `INFO`, `WARNING` or `ERROR` | `INFO` |

### `customers[]`

| Key | Meaning |
|---|---|
| `id` | Technical ID. Becomes the folder name under `data/customers/`. Letters, digits, `.`, `_`, `-`. **Do not rename later.** |
| `name` | Display name in menus and reports |
| `enabled` | `false` = this customer is never fetched |
| `credentials.apple` | `issuerId`, `keyId` and either `privateKeyFile` or `privateKeyEnvironmentVariable` |
| `credentials.google` | Either `serviceAccountFile` or `serviceAccountEnvironmentVariable` |
| `apps[]` | List of apps of this customer |

Each customer has their own credentials because Apple keys are bound to a developer account.
If several "customers" share one Apple account, just enter the same key for each of them.

### `apps[]`

| Key | Meaning |
|---|---|
| `id` | Technical ID, folder name under `data/customers/<customer>/apps/`. **Do not rename later** – a new ID creates a new, empty folder. |
| `name` | Display name |
| `enabled` | `false` = this app is never fetched |
| `platforms.apple.appId` | Numeric App Store ID |
| `platforms.apple.countries` | Limit reviews to these territories (e.g. `["DEU"]`). Empty `[]` = all (recommended). |
| `platforms.apple.ratingCountries` | Countries for which the official store rating is fetched (one request per app and country per run). `[]` = off. |
| `platforms.google.packageName` | Android package name |
| `platforms.google.languages` | Keep only reviews in these languages (e.g. `["de", "en"]`). Empty `[]` = all. |
| `platforms.<x>.enabled` | Switch a single platform off |

### Keys via environment variables (e.g. for CI)

Instead of `privateKeyFile` / `serviceAccountFile` you can name an environment variable. The
variable may contain either a **file path** or the **key text itself**:

```json
"apple":  { "issuerId": "…", "keyId": "…", "privateKeyEnvironmentVariable": "APPLE_PRIVATE_KEY" },
"google": { "serviceAccountEnvironmentVariable": "GOOGLE_APPLICATION_CREDENTIALS" }
```

```bash
export APPLE_PRIVATE_KEY="$HOME/keys/AuthKey_ABC123DEFG.p8"
export GOOGLE_APPLICATION_CREDENTIALS="$HOME/keys/customer-a-google.json"
```

The configuration is validated on every start. Errors are listed in plain words, e.g.
"apple.appId fehlt oder ist keine numerische App-Store-ID".

---

## Working with the tool

There are three ways to use it:

| Entry point | For whom |
|---|---|
| `./kurzmenu.sh` | Day-to-day use: three buttons – fetch everything, status, open report |
| `./menu.sh` (or `./ratings.sh menu`) | Full interactive menu, no need to remember any options |
| `./ratings.sh <command>` | Command line, scripts, cron, CI |

All three set up the Python environment (`.venv`) automatically on the first start.
The menus always print the real command before running it (`▶ python collect.py …`), so you learn
the command line along the way.

**Typical first day:**

```bash
./ratings.sh apps          # are all apps there?
./ratings.sh dry-run       # do the keys work?
./ratings.sh fetch         # first fetch of reviews
./ratings.sh stability     # Apple Analytics (takes a while the first time)
./ratings.sh testdata      # TestFlight builds and Google test tracks
./ratings.sh report        # build and open the report
./ratings.sh status        # per app: ok, partial or error
```

**Typical day afterwards:**

```bash
./ratings.sh all           # everything in one go, then the browser opens
```

---

## Commands (`ratings.sh`)

`[opt]` = any option of `collect.py`, e.g. `--customer customer-a --app my-app --platform apple`.

| Command | What it does |
|---|---|
| `menu` | Start the interactive menu |
| `fetch [opt]` | Fetch reviews (first run: everything, then only new ones), print statistics |
| `full [opt]` | Re-read all reviews (`--full-sync`). Never deletes anything. |
| `force [opt]` | Like `fetch`, but ignores the `minRefreshMinutes` wait period |
| `dry-run [opt]` | Trial run: real API calls, nothing is saved |
| `range FROM TO [opt]` | Fetch only reviews created in this period (`YYYY-MM-DD`). Does not move the sync state forward. |
| `stability [opt]` | Fetch crashes and sessions (Apple only) |
| `testdata [opt]` | Fetch Apple TestFlight and Google Play test-track data |
| `all [opt]` | Reviews + stability + test data, then build the report and open the browser |
| `daily [opt]` | For cron/CI: fetch everything at most once per day (UTC), always rebuild report + Markdown + ZIP, no browser |
| `report` | Build the report (+ Markdown summaries of the last 14 days) and open it |
| `markdown [opt]` | Only Markdown + ZIP for sending |
| `open` | Open the last report without rebuilding it |
| `status` | Status per app (no network) |
| `apps` | List configured apps and validate the config (no network) |
| `import-csv FILE… --customer ID --app ID` | Import Google Play Console CSV exports |
| `test` | Run the automated tests (installs `pytest` on first use) |
| `backup` | Pack `data/` into `backup-<date>.tgz` |
| `reset [opt]` | Delete data and start over (backup + confirmation). Partial: `--app ID` / `--customer ID`. `--dry-run` only shows what would be deleted. |
| `help` | Show the command overview |

The old German command names still work (`abrufen`, `voll`, `probe`, `zeitraum`, `stabilitaet`,
`testbetrieb`, `alles`, `taeglich`, `bericht`, `oeffnen`, `csv`, `tests`, `sicherung`,
`zuruecksetzen`, `hilfe`).

### Options of `collect.py`

| Option | Meaning |
|---|---|
| `--config PATH` | Other config file (default `config/config.json`) |
| `--customer ID` | Only this customer |
| `--app ID` | Only this app |
| `--platform apple\|google\|all` | Only this platform (default `all`) |
| `--from YYYY-MM-DD` / `--to YYYY-MM-DD` | Period by review creation date |
| `--incremental` / `--full-sync` | Force incremental or full fetch |
| `--force` | Ignore `minRefreshMinutes` |
| `--dry-run` | Fetch, but save nothing |
| `--dataset reviews\|stability\|testing\|all` | What to fetch (default `reviews`) |
| `--once-per-day` | At most one successful run per calendar day (UTC). Failed runs may be repeated. |
| `--status` / `--list-apps` | Show state / apps, no API access |
| `--import-google-csv FILE…` | CSV import (needs `--customer` and `--app`) |
| `--log-level LEVEL` | Overrides `settings.logLevel` |

### Options of `report.py`

| Option | Meaning |
|---|---|
| `--customer ID` / `--app ID` / `--platform …` | Report only for this selection |
| `--data-dir PATH` | Other data folder |
| `--output FILE` | Other output file (default `<reportDirectory>/index.html`) |
| `--days N` | Period of the Markdown summaries in days (default 14) |
| `--until YYYY-MM-DD` | End of the Markdown period (default: latest data) |
| `--zip` | Additionally pack the Markdown files as ZIP |
| `--no-markdown` | Do not create Markdown summaries |

`report.py` never accesses the network. It only reads the local JSON files.

### Exit codes

| Code | Meaning |
|---|---|
| `0` | Everything OK |
| `1` | At least one app failed or was only partially fetched (data fetched so far is saved) |
| `2` | Configuration or usage error |

---

## Menus

The menu texts are in German. Keys in every menu: **number** = select, **H** = help for this
menu, **0** = one level back, **Q** = quit, **Ctrl+C** = cancel a running fetch (data already
fetched is kept).

The header shows when the last successful fetch happened and how old the report is. The big menu
also shows the current selection (customer / app / platform / period / open browser).

### Short menu (`./kurzmenu.sh`)

| No. | Entry | What it does |
|---|---|---|
| 1 | Alles abrufen (fetch everything) | Reviews, stability and test data for all apps, then rebuild report and Markdown (no ZIP, no browser) |
| 2 | Status | Last successful fetch, number of reviews, stability state and errors per app (no network) |
| 3 | Bericht anzeigen (show report) | Opens `reports/index.html`; builds it first if it does not exist |

### Main menu (`./menu.sh`)

| No. | Entry | What it does |
|---|---|---|
| 1 | ALLES AUF EINMAL (all at once) | `collect.py --dataset all` with the current selection, then report + browser |
| 2 | Daten abrufen … (fetch data) | Submenu with all fetch variants |
| 3 | Bericht erzeugen (build report) | `report.py` with the current selection, then open the browser |
| 4 | Letzten Bericht nur öffnen (open last report) | Opens the existing report without rebuilding |
| 5 | Auswahl ändern … (change selection) | Submenu: customer, app, platform, period |
| 6 | Status und Übersicht … (status and overview) | Submenu: status, app list, tests |
| 7 | Google-Rezensionen aus CSV importieren | CSV import; customer **and** app must be selected first |
| 8 | Markdown-Dateien … | Submenu: open documentation and summaries, regenerate, ZIP |
| 9 | Daten löschen und neu anfangen … (delete data) | Submenu with backup and confirmation |

#### 2 – Daten abrufen (fetch data)

| No. | Entry | Command |
|---|---|---|
| 1 | Abrufen (automatic) – first everything, then only new | `collect.py` |
| 2 | Vollständig neu lesen (full re-read) | `--full-sync` |
| 3 | Wartefrist ignorieren (ignore wait period) | `--force` |
| 4 | Stabilität abrufen (stability, Apple only) | `--dataset stability` |
| 5 | Testbetrieb abrufen (TestFlight + Google test tracks) | `--dataset testing` |
| 6 | Rezensionen, Stabilität UND Testbetrieb | `--dataset all` |
| 7 | Probelauf (dry run) | `--dry-run` |
| 8 | Nur einen Zeitraum (period only) – asks for the dates | `--from … --to …` |
| 9 | Toggle: open report automatically after fetching | – |

Entries 1, 2, 3, 7 and 8 only fetch **reviews**. For everything use entry 6.

#### 5 – Auswahl ändern (change selection)

Customer, app, platform, set period, clear period, reset everything. The selection only lives in
the menu (it is not written to `config.json`) and applies to all fetches and to the report.
Disabled customers/apps (`"enabled": false`) are never fetched, even if selected.

#### 6 – Status und Übersicht (status and overview)

Status per app (`--status`), configured apps (`--list-apps`), run tests. Nothing here uses the
network or changes data.

#### 8 – Markdown-Dateien

Open documentation, open the 14-day summaries (in the editor with **E**, or formatted in the
browser with **Enter**/**B**), regenerate them, create a ZIP and reveal it in Finder.

Editor: on macOS the default text editor (`open -t`). Your own editor via the first set variable
of `MD_EDITOR`, `VISUAL`, `EDITOR`, e.g.:

```bash
export MD_EDITOR="open -a 'Visual Studio Code'"     # or "code", "nano", "vim"
```

Regenerating overwrites the Markdown files – save a copy if you edited them.

#### 9 – Daten löschen (delete data)

| No. | Entry | Command |
|---|---|---|
| 1 | Delete only the selected app / customer | `reset.py --customer ID --app ID` |
| 2 | Delete EVERYTHING (all data and the report) | `reset.py` |
| 3 | Only show what would be deleted | `reset.py … --dry-run` |

A backup is always created in `backups/` first, and you have to type `LOESCHEN` to confirm.
Configuration, keys and program code are never touched.

---

## Files and folders

```
app-ratings-reviews/
├── ratings.sh              one entry point for all commands
├── menu.sh                 big interactive menu
├── kurzmenu.sh             short menu (3 functions)
├── collect.py              fetching (Apple / Google)
├── report.py               HTML report + Markdown (offline)
├── reset.py                delete data with backup
├── menu.py                 menu logic
├── lib/common.sh           shared checks (venv, config)
├── src/                    the actual implementation (API clients, sync, storage, report)
├── templates/              HTML templates for report, help, imprint, privacy
├── config/
│   ├── config.example.json template
│   └── config.json         your configuration (not in git)
├── keys/                   your .p8 and service-account JSON files (not in git)
├── data/                   collected data (not in git)
├── reports/                generated report (not in git)
└── backups/                backups made by reset (not in git)
```

### Data layout

```
data/
├── state.json                     sync state per customer/app/platform
├── sync-history.json              log of all runs
├── last-daily.json                marker for --once-per-day
└── customers/<customer>/apps/<app>/
    ├── apple/
    │   ├── reviews.json           all reviews
    │   ├── review-history.json    changes to existing reviews
    │   ├── versions.json          App Store versions
    │   ├── ratings-history.json   official store rating snapshots
    │   ├── stability-metrics.json crashes and sessions
    │   └── testflight.json        TestFlight builds and usage
    └── google/
        ├── reviews.json
        ├── review-history.json
        └── google-testing.json    test tracks and crash rates
```

Each review has the unique key `platform:storeAppId:reviewId`, so repeated fetches never create
duplicates. JSON files are written atomically with restricted permissions (`600`). A damaged JSON
file is never overwritten – the run stops with an error instead. A lock file (`data/.lock`)
prevents two runs at the same time.

**Never commit:** `config/config.json`, `keys/`, `data/`, `reports/`, `backups/`.
Note that `.gitignore` covers `*.p8`, `service-account*.json` and `config/config.json`; if you
name your Google key differently (e.g. `customer-a-google.json`), add `keys/` to `.gitignore`.

---

## Daily automatic run

A daily run is **required** if you use Google, because the Google API only returns the last
7 days. Use `./ratings.sh daily`: it fetches at most once per calendar day (UTC), always rebuilds
the report, Markdown and ZIP, and never opens a browser. A failed run may be repeated on the same
day.

**cron (Linux / macOS):**

```cron
30 6 * * * cd /home/ratings/app-ratings-reviews && ./ratings.sh daily >> logs-daily.txt 2>&1
```

**macOS alternative:** a `launchd` agent that runs the same command.

**CI (e.g. GitHub Actions):** put the key contents into secrets, expose them as environment
variables and reference them via `privateKeyEnvironmentVariable` / `serviceAccountEnvironmentVariable`.
Keep `data/` between runs (cache or artifact), otherwise older Google reviews get lost.

**Publishing the report:** `reports/` is static and has no external dependencies. Share it via a
web server with password protection or VPN, or set `reportDirectory` to a network drive.
Only share `reports/`, never `config/`, `data/` or `keys/`.

**Backup:** `./ratings.sh backup` packs `data/`. Also include `config/` and `keys/` in your
regular backup. Restore with `tar xzf backups/backup-<date>.tgz -C .` in the project folder.

---

## Known limitations

- **Apple reviews** come with text but without app version, OS, device or language. Star-only
  ratings without text and the star distribution cannot be fetched via the API (the official
  average and count come from the public iTunes Lookup API per `ratingCountries`).
- **Apple:** later edits of old reviews are only detected during full syncs (automatic every
  `fullSyncIntervalDays`).
- **Apple stability** data only exists from the date the ONGOING analytics request was created.
  Apple hides rows with very few devices, so totals and rates are approximations.
  Crash rate = crashes per 1000 sessions (not comparable with Google).
- **Google** returns only reviews from the last 7 days and only reviews with text. There is no
  creation date, only "last modified". Quota: 200 GET requests per hour and app.
- **Google crash rates** are not split into test and production; they are assigned to tracks via
  the version code.
- Averages and distributions in the report are computed from the collected reviews and are not
  the official store totals.

---

## Troubleshooting

| Message | Cause and fix |
|---|---|
| `config/config.json fehlt` | `cp config/config.example.json config/config.json` and fill it in |
| `Konfiguration fehlerhaft: …` | The list says exactly which field is wrong. Check with `./ratings.sh apps`. |
| `Die Konfiguration enthält anscheinend einen privaten Schlüssel` | Key text was pasted into `config.json`. Move it to a file in `keys/` and use `privateKeyFile`. |
| `Zugangsdaten fehlen` | `privateKeyFile` / environment variable not set or empty |
| `Schlüsseldatei nicht gefunden` | Wrong path in `privateKeyFile` / `serviceAccountFile` (relative to the project folder) |
| HTTP 401 (Apple) | Issuer ID, Key ID and `.p8` do not match, or the key was revoked. Compare the Key ID with the file name. |
| HTTP 403 (Apple) | The key's role is too low – use **App Manager** for stability and TestFlight |
| `Keine laufende Analytics-Berichtsanfrage (ONGOING)` | Create an ONGOING analytics report request for this app (see Apple step 3) |
| `Google lehnte das Service Account ab` | JSON file wrong, or the service account was not invited / permissions not active yet (up to 48 h) |
| HTTP 403 (Google) | API not enabled in the Cloud project, or missing Play Console permission |
| `Ein anderer collect.py-Lauf ist aktiv` | Another run is still going. `data/.lock` shows the lock. |
| `Beschädigte JSON-Datei` | The file is left untouched. Restore it from a backup. |
| Status `skipped` | The app was fetched less than `minRefreshMinutes` ago. Use `force`. |
| Status `partial` | Some requests failed; everything fetched so far is saved. Run again later. |

For more detail, the generated report includes a help page (`reports/hilfe.html`) with the same
setup steps in German and English.
