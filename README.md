# app-ratings-reviews

A small command-line tool that collects app ratings, reviews, stability data, store figures and
test-build data from **Apple App Store Connect** and **Google Play**, stores everything locally as
JSON and builds a self-contained HTML report plus Markdown summaries you can send to customers.
Optionally it lets an AI model (cloud or fully local) read the reviews, watches competitor apps on
the App Store, and sends a notification after the daily run when something needs attention.

It is built for agencies and developers who look after several apps for several customers: one
configuration file, one command, one report.

- No database, no server, no backend. Everything lives in local JSON files.
- Read-only towards Apple and Google. The tool never changes anything in App Store Connect or the
  Play Console.
- Only one Python dependency (`cryptography`, for signing the API tokens).
- Safe to run as often as you like: reviews are de-duplicated, nothing is ever deleted except via
  an explicit `reset` (with backup and confirmation). Every run that changes data first packs
  `data/` into a ZIP under `backups/`.
- **AI analysis is optional** and off by default. If you switch it on, you choose the provider:
  OpenAI, Google Gemini, Anthropic Claude, Perplexity, xAI Grok, or a **local model** via Ollama,
  LM Studio or any OpenAI-compatible server on your own machine (no key, no cost, nothing leaves
  the computer).
- **Competitor apps** (Apple only) can be tracked from Apple's public review feed without any
  access to the other developer's account.
- **Notifications** after the daily run via e-mail, Slack or webhook, only when there are new
  1–2-star reviews, a traffic-light change or a crash jump.
- The report is bilingual (German / English switch in the header), works offline, and can be
  printed or copied to the clipboard as a formatted monthly report.

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
10. [Stability and store figures (Apple)](#stability-and-store-figures-apple)
11. [Competitor apps (Apple)](#competitor-apps-apple)
12. [AI analysis (optional)](#ai-analysis-optional)
13. [Notifications after the daily run](#notifications-after-the-daily-run)
14. [The report](#the-report)
15. [Debug mode with generated test data](#debug-mode-with-generated-test-data)
16. [Files and folders](#files-and-folders)
17. [Daily automatic run](#daily-automatic-run)
18. [Known limitations](#known-limitations)
19. [Troubleshooting](#troubleshooting)

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
| **Store figures**: downloads by type/source/country/device, installations and deletions, store impressions, page views and taps | Apple Analytics Reports ("App Downloads Standard", "App Store Installation and Deletion Standard", "App Store Discovery and Engagement Standard") | `store` |
| **Competitor apps** (Apple only): newest reviews, official rating, version, store profile | Apple public customer-review RSS feed + iTunes Lookup, no credentials | `competitors` |
| **AI analysis** (optional): summary, sentiment, measures, themes, reply drafts, free-text questions | Your chosen provider (OpenAI, Gemini, Anthropic, Perplexity, xAI) or a local model (Ollama, LM Studio, …) | `analyze`, `ask` |
| **Historic Google reviews** | Play Console CSV export | `import-csv` |

From the stored data the tool generates:

- `reports/index.html` – an interactive, self-contained HTML report (no external resources), with
  help, imprint and privacy pages next to it.
- `reports/markdown/*.md` – one summary per app and platform covering the last 14 days, plus an
  overview file `00-uebersicht.md`.
- Optionally `reports/zusammenfassung-<date>.zip` – all summaries packed for sending.
- Optionally a **notification** (e-mail, Slack, webhook) after `daily`, only when something new
  and noteworthy happened since the last message.

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
| App ID | number, e.g. `1234567890` | `apps[].platforms.apple.appId` |

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
Or take it from the App Store URL: `https://apps.apple.com/app/id1234567890` → `1234567890`.

### 3. Enable Analytics reports (only for stability and store figures)

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
| `backupDirectory` / `backupKeep` | Folder for the ZIP backups of `data/` taken before every run that changes data, and how many newest ones to keep (`0` = all) | `./backups`, `30` |
| `reportUrl` | Address under which your team reaches the published report. It is the link in every notification (`null` = file path) | `null` |
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
| `audience` | Optional size of the target group (e.g. number of customers of the provider), integer ≥ 1 or `null`. Only with this value the report computes "downloads per 1000 of the audience"; nothing is ever estimated. |

### `customers[].competitors[]` (optional, Apple only)

Third-party Apple apps that are evaluated next to your own, without access to the other
developer's account. The template is in `config.example.json`.

| Key | Meaning |
|---|---|
| `id` | Technical ID, unique also against `apps[]`; folder name under `data/customers/<customer>/competitors/` |
| `name`, `vendor` | Display name and (optional) developer / company name |
| `enabled` | `false` = never fetched |
| `audience` | Optional, like for your own apps |
| `apple.appId` | Numeric App Store ID |
| `apple.countries` | **Required.** Two-letter country codes; the public feed is per country (e.g. `["DE", "AT", "CH"]`) |

There is no `google` block: Google offers no public source. Without any entries nothing changes in
the report. Details in [Competitor apps (Apple)](#competitor-apps-apple).

### `ai` (optional)

The block is off by default. Copy it from `config.example.json`. The AI is active only if a
provider has `"enabled": true` **and** the environment variable named in
`apiKeyEnvironmentVariable` contains a key (`local` needs no key). If several providers are
enabled, **the first one in the list wins**. Without an active provider there is no AI command and
no AI content in the report.

| Key | Meaning | Default |
|---|---|---|
| `providers[]` | Ordered list of `{name, enabled, model, apiKeyEnvironmentVariable}`. `name` is one of `openai`, `gemini`, `anthropic`, `perplexity`, `xai`, `local` (`ollama` is still accepted as an alias of `local`) | all disabled |
| `providers[].model` | Model name at the provider. `./ratings.sh ai-models` lists the supported models with list prices | `claude-sonnet-5-5`, `gpt-6-luna`, `gemini-3.8-flash`, `openai/gpt-5.6-terra`, `grok-4.7`, `llama3.1:8b` |
| `providers[].priceInputPerMillion` / `priceOutputPerMillion` | Your own prices in US dollars per million tokens for the cost estimate (always both) | list price |
| `providers[].url` (only `local`) | Address of the local OpenAI-compatible server; only `127.0.0.1`, `localhost`, `::1` or `https` is allowed | `http://127.0.0.1:11434/v1/chat/completions` |
| `providers[].label` (only `local`) | Display name instead of "local model", e.g. `LM Studio` (max. 40 characters) | – |
| `language` | Language of the AI texts (`de`, `en`) | `de` |
| `maxReviewsPerRequest` | Reviews per sentiment request (in addition to the character budget) | `60` |
| `maxCharsPerRequest` | Character budget per request (about 30,000 tokens). Batches are built by size; a summary that does not fit runs in two stages | `120000` |
| `maxReviewChars` | Characters per review; longer texts are cut and marked as cut | `1500` |
| `summaryReviews` | Newest reviews an app summary is based on | `80` |
| `maxReviewsPerQuestion` | Newest reviews of the selection that a free-text question receives | `300` |
| `monthlyTokenLimit` | Hard limit per calendar month (input + output); afterwards an error instead of a request | `2000000` |
| `requestTimeoutSeconds` | Timeout for a single AI request (a model often needs 30–90 s for 60 reviews; local models need more) | `180` |
| `sendReviewText` | `false`: only stars, date and version are sent; sentiment, drafts and quotes are then not available | `true` |
| `analyzeCompetitors` | Also analyse competitor apps (never reply drafts or measures for third-party apps) | `true` |
| `features` | `summary`, `sentiment`, `themes`, `versions`, `comparison`, `replyDrafts`, `measures` on; `questions` off (each question costs a request) | see template |
| `servicePort` | Port of the local question service (`ai-serve`), bound to `127.0.0.1` only; `0` = any free port | `8765` |

Keys never go into the file: `apiKey` and similar fields are rejected by the validation.

### `notify` (optional)

Notification after the daily run. Off by default; template in `config.example.json`.

| Key | Meaning | Default |
|---|---|---|
| `enabled` | Switch for the whole step | `false` |
| `language` | Language of the message (`de`, `en`) | `de` |
| `triggers` | `negativeReviews`, `ampelChange` (traffic light), `crashJump`, each on or off | all `true` |
| `quietOnFirstRun` | The first run only remembers the current state and sends nothing | `true` |
| `maxReviewsPerMessage` | This many new 1–2-star reviews are listed individually; the rest is counted ("… and 4 more, see report") | `10` |
| `channels[]` | List of channels, each with `type` and `enabled`; **all** enabled channels are served | empty |

| Channel `type` | Fields |
|---|---|
| `email` | `host`, `port` (587), `security` (`starttls`, `ssl`; `none` only to `127.0.0.1`/`localhost`), `username` (omit for a local relay without login), `passwordEnvironmentVariable`, `from`, `to` (list) |
| `slack` | `webhookUrlEnvironmentVariable` |
| `webhook` | `urlEnvironmentVariable`, optional `secretEnvironmentVariable` (HMAC-SHA256 over the body, header `X-Ratings-Signature: sha256=<hmac>`) |

Password, webhook address and secret come **only from environment variables**. A configuration
containing `password`, `webhookUrl`, `url`, `secret` or `token` in plain text is rejected.

### Word lists and preset questions (versioned, no secrets)

- `config/themen.json` – the topics for the report section "Topics and words": per topic `id`,
  `de`, `en`, `kind` (`problem`, `wunsch`, `lob`, `bedienung`, `thema`), optional `bereich`
  (`app` or `anbieter`, for the question "is it the app or the provider?"), `terms` (lower-case;
  match at word start, up to three characters only as whole word, `*` prefix also inside a word,
  `=` prefix only the whole word) and optional `nicht` (phrases in which a hit does not count,
  e.g. "no errors"). German and English, plus basic terms in NL/ES/IT/FR/PT/RU. Edit, rebuild the
  report, done – the matching runs in the browser.
- `config/fragen.json` – up to 40 preset questions for the AI (20 shipped, management
  perspective), each with `de` and `en`. They appear in the report behind "Choose questions …"
  when `ai.features.questions` is on.

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
./ratings.sh stability     # Apple Analytics: crashes and sessions (takes a while the first time)
./ratings.sh store         # Apple Analytics: downloads, installs, store views
./ratings.sh testdata      # TestFlight builds and Google test tracks
./ratings.sh competitors   # competitor apps, if configured (Apple only, no credentials)
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
| `store [opt]` | Fetch store figures: downloads, installations/deletions, store views (Apple only) |
| `testdata [opt]` | Fetch Apple TestFlight and Google Play test-track data |
| `competitors [opt]` | **Apple only:** fetch competitor apps (`customers[].competitors`) from Apple's public review feed and iTunes Lookup, no credentials. Nothing happens without entries. |
| `all [opt]` | Reviews + stability + store figures + test data + competitors (+ AI analysis if a provider is enabled), then build the report and open the browser |
| `daily [opt]` | For cron/CI: fetch everything at most once per day (UTC), always rebuild report + Markdown + ZIP, then send the notification (if enabled), no browser |
| `analyze [opt]` | AI analysis of the stored reviews (sentiment, summary, measures, reply drafts, theme suggestions); needs an enabled provider; rebuilds the report afterwards |
| `ask "QUESTION" [opt]` | Free-text question to the stored reviews (needs `ai.features.questions`); `--app` repeatable, `--from`, `--to`, `--stars-min`, `--stars-max` narrow the selection |
| `ai-themes [--accept NR \| --ignore NR]` | List AI theme suggestions; accept one into `config/themen.json` or reject it |
| `ai-usage` | Active provider, token usage and estimated cost per month and per customer/app (no network) |
| `ai-models` | Supported models per provider with list prices (no network) |
| `ai-questions [--delete NR \| --clear]` | Stored questions and answers; delete one or all (no network) |
| `ai-serve [--port N]` | Local question service for the report (`127.0.0.1` only, Ctrl+C stops). Rebuild the report while it runs to get the question box. |
| `ai-report [opt]` | One command: start the question service, rebuild the report, open it in the browser, keep serving until Ctrl+C |
| `notify [--dry-run \| --test]` | Notification step on its own: `--dry-run` shows the message the daily run would send now, `--test` sends a test message to all enabled channels. Reads `data/` only, no store API. |
| `demo [opt]` | Generate fictional test data into `data-debug/` (see [Debug mode](#debug-mode-with-generated-test-data)) |
| `debug-menu` | Short menu in debug mode: test data only, no request to Apple or Google |
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
`testbetrieb`, `wettbewerber`, `alles`, `taeglich`, `bericht`, `oeffnen`, `csv`, `tests`,
`sicherung`, `zuruecksetzen`, `hilfe`, `ki`, `frage`, `ki-themen`, `ki-verbrauch`, `ki-modelle`,
`ki-dienst`, `ki-bericht`, `ki-fragen`, `benachrichtigen`).

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
| `--dataset reviews\|stability\|store\|testing\|competitors\|ai\|all` | What to fetch (default `reviews`). `ai` analyses the stored reviews with the active provider; with `all` the AI runs only if a provider is active, otherwise it is skipped silently. |
| `--no-backup` | Skip the ZIP backup of `data/` before the run (otherwise every run that changes data creates one under `backups/`; never on `--dry-run`) |
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

`ki.py` is the entry point behind the `ai-*` commands: `ki.py ask "QUESTION" [--customer ID]
[--app ID …] [--platform P] [--from D] [--to D] [--stars-min N] [--stars-max N] [--no-save]`,
`ki.py questions [--delete NR | --clear]`, `ki.py themes [--accept NR [--bereich app|anbieter] |
--ignore NR]`, `ki.py usage`, `ki.py models`, `ki.py serve [--port N] [--report] [--open]`.
`notify.py [--dry-run | --test]` is the notification step.

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
| 1 | Alles abrufen (fetch everything) | Reviews, stability, store figures, test data and competitors for all apps (+ AI analysis if a provider is enabled), then rebuild report and Markdown (no ZIP, no browser) |
| 2 | Status | Last successful fetch, number of reviews, stability state and errors per app (no network) |
| 3 | Bericht anzeigen (show report) | Opens `reports/index.html`; builds it first if it does not exist |
| 4 | Bericht mit Fragen an die KI anzeigen | Starts the local question service, rebuilds the report and opens it (only with an enabled AI provider) |

The header line shows whether an AI provider is active ("KI aus" = AI off).

### Main menu (`./menu.sh`)

| No. | Entry | What it does |
|---|---|---|
| 1 | ALLES AUF EINMAL (all at once) | `collect.py --dataset all` with the current selection, then report + browser. With an active AI provider the line reads "+ KI-Analyse (provider / model)", otherwise "(KI aus)". |
| 2 | Daten abrufen … (fetch data) | Submenu with all fetch variants |
| 3 | Bericht erzeugen (build report) | `report.py` with the current selection, then open the browser |
| 4 | Letzten Bericht nur öffnen (open last report) | Opens the existing report without rebuilding |
| 5 | Bericht mit KI-Fragedienst erzeugen und öffnen | `ki.py serve --report --open`: local question service, report with the current selection, browser; runs until Ctrl+C. Only with an enabled provider. |
| 6 | Auswahl ändern … (change selection) | Submenu: customer, app, platform, period |
| 7 | Status und Übersicht … (status and overview) | Submenu: status, app list, tests, notification dry run and test message |
| 8 | Google-Rezensionen aus CSV importieren | CSV import; customer **and** app must be selected first |
| 9 | KI-Analyse … (AI analysis) | Analyse (only new reviews are sent), dry run, ask a question, stored questions, accept or reject theme suggestions, provider and usage. Only with an enabled provider. |
| 10 | Markdown-Dateien … | Submenu: open documentation and summaries, regenerate, ZIP |
| 11 | Daten löschen und neu anfangen … (delete data) | Submenu with backup and confirmation |

#### 2 – Daten abrufen (fetch data)

| No. | Entry | Command |
|---|---|---|
| 1 | Abrufen (automatic) – first everything, then only new | `collect.py` |
| 2 | Vollständig neu lesen (full re-read) | `--full-sync` |
| 3 | Wartefrist ignorieren (ignore wait period) | `--force` |
| 4 | Stabilität abrufen (stability, Apple only) | `--dataset stability` |
| 5 | Testbetrieb abrufen (TestFlight + Google test tracks) | `--dataset testing` |
| 6 | Alles (reviews, stability, store figures, test data, competitors, AI) | `--dataset all` |
| 7 | Probelauf (dry run) | `--dry-run` |
| 8 | Nur einen Zeitraum (period only) – asks for the dates | `--from … --to …` |
| 9 | Toggle: open report automatically after fetching | – |

Entries 1, 2, 3, 7 and 8 only fetch **reviews**. For everything use entry 6. The exact numbering
may differ slightly between versions; the menu always prints the real command before running it.

#### 6 – Auswahl ändern (change selection)

Customer, app, platform, set period, clear period, reset everything. The selection only lives in
the menu (it is not written to `config.json`) and applies to all fetches and to the report.
Disabled customers/apps (`"enabled": false`) are never fetched, even if selected.

#### 7 – Status und Übersicht (status and overview)

Status per app (`--status`), configured apps (`--list-apps`), run tests, notification dry run
(`notify.py --dry-run`) and test message (`notify.py --test`). Apart from the test message,
nothing here uses the network or changes data.

#### 9 – KI-Analyse (AI analysis)

Only usable with an enabled provider (see [AI analysis](#ai-analysis-optional)). Analyse (only new
or changed reviews are sent), dry run (shows what would be sent, no request), ask a free-text
question, list stored questions, accept or reject theme suggestions (with confirmation), show
provider and usage, and "enable questions in the report" (starts the local question service).

#### 10 – Markdown-Dateien

Open documentation, open the 14-day summaries (in the editor with **E**, or formatted in the
browser with **Enter**/**B**), regenerate them, create a ZIP and reveal it in Finder.

Editor: on macOS the default text editor (`open -t`). Your own editor via the first set variable
of `MD_EDITOR`, `VISUAL`, `EDITOR`, e.g.:

```bash
export MD_EDITOR="open -a 'Visual Studio Code'"     # or "code", "nano", "vim"
```

Regenerating overwrites the Markdown files – save a copy if you edited them.

#### 11 – Daten löschen (delete data)

| No. | Entry | Command |
|---|---|---|
| 1 | Delete only the selected app / customer | `reset.py --customer ID --app ID` |
| 2 | Delete EVERYTHING (all data and the report) | `reset.py` |
| 3 | Only show what would be deleted | `reset.py … --dry-run` |

A backup is always created in `backups/` first, and you have to type `LOESCHEN` to confirm.
Configuration, keys and program code are never touched.

---

## Stability and store figures (Apple)

Both come from Apple **Analytics Reports** and need an existing `ONGOING` report request per app
(see Apple step 3). The tool only reads; it never creates or changes anything at Apple.

**Stability** (`./ratings.sh stability`, part of `all` and `daily`) reads "App Crashes" and
"App Sessions Standard" and writes `apple/stability-metrics.json` per app (per day, app version,
OS version and device type: crashes and sessions).

- Incremental: report instances already loaded are never loaded again; later corrections by Apple
  replace the affected day. `--full-sync` reloads everything.
- The first run needs about 100–150 requests per app, afterwards only a few. Apple allows roughly
  3,600 requests per hour.
- Crash rate = crashes ÷ sessions × 1000, only where sessions exist. Fewer than 5 crashes are
  flagged as "small sample".
- Data exists only from the day the report request was created. Apple hides rows with very few
  devices, so totals are approximations. Apple reports the device type (iPhone/iPad), not the
  model.
- In the report: section "Stability" with totals, tables by app version, OS version and device
  type, and a weekly curve of crash rate against negative reviews. That is a **coincidence in
  time, not a cause**: Apple reviews carry no app version.

**Store figures** (`./ratings.sh store`, part of `all` and `daily`) reads "App Downloads Standard",
"App Store Installation and Deletion Standard" and "App Store Discovery and Engagement Standard"
and writes `apple/store-metrics.json` per app (per day: downloads by type, source, country and
device; installations and deletions by country and device; impressions, page views and taps by
source). First run about 230 requests per app, afterwards a few per day. Apple adds noise to the
counts (occasionally `-1`). Active devices cannot be summed and are not stored. In the report
they appear under "Downloads & Store".

Google stability and store figures are not implemented (see Known limitations).

---

## Competitor apps (Apple)

Add third-party Apple apps under `customers[].competitors` (see Configuration) and run
`./ratings.sh competitors` (also part of `all` and `daily`). The source is Apple's **public**
customer-review feed (`itunes.apple.com/<country>/rss/customerreviews/…`, 50 reviews per page, at
most 10 pages = newest 500 reviews per country) plus the iTunes Lookup (rating, count, version,
store profile). No credentials, nothing is requested from the other developer's account.

- Incremental: per country the fetch stops after the first page without an unknown review;
  `--full-sync` reads all pages. The same review in two country feeds counts once.
- Stored separately under `data/customers/<customer>/competitors/<id>/apple/` (`reviews.json`
  with the store profile, `review-history.json`, `ratings-history.json`, `ai-analysis.json` with
  AI).
- **Without entries nothing changes**: no tab, no badge, no row in the report. With entries the
  report gets the tab "Competitors": your own Apple apps of the selected customer against the
  competitors (vendor, store rating, total ratings, reviews and average of the last 90 days, share
  of 1–2 stars, version, traffic-light reason by the same rules), with AI praise and criticism side
  by side, and a store profile per competitor opened by click.
- Competitors appear in the app filter with the prefix "Wettbewerber:" / "Competitor:" and carry
  a badge everywhere. They flow into other figures only if you select them explicitly in the app
  filter; overview, key figures, charts and the review list otherwise show your own apps only.
- The AI analyses them too (`ai.analyzeCompetitors`, default `true`), without reply drafts or
  measures. The notification never reports them. The Markdown overview gets a section
  "Competitors" (no file per competitor).

Limits of the public feed (checked live in October 2026): only the newest 500 reviews per
country, older ones never; the history grows only through regular runs. No developer replies, no
language, no device (app version yes). No crashes, downloads or sessions. The date is the feed's
`updated`. Google has no official public source, so there are deliberately no Google competitors.

---

## AI analysis (optional)

A language model reads the stored reviews and delivers what numbers alone cannot show. Provider of
your choice: **OpenAI, Google Gemini, Anthropic Claude, Perplexity, xAI Grok** in the cloud, or a
**local model** on your own machine (Ollama, LM Studio, llama.cpp, vLLM, LocalAI, Jan or any other
OpenAI-compatible server): no key, no cost, nothing leaves the computer, but slower and weaker at
summaries. The AI is active only with an enabled provider (and a key for cloud providers), see
[`ai`](#ai-optional).

### What the AI delivers

Per app and platform, stored in `ai-analysis.json`. There is no separate AI tab: every AI text
sits in the section that answers the question, and everything follows the filter.

- **Summary per app** in three sentences (praise, criticism, what changed recently) with main
  praise, main criticism, an assessment (product, update or provider problem) and up to five
  verbatim quotes (overview, traffic-light table "What do users say?").
- **Measures per app**: at most five suggestions what to do next, with responsibility
  (development, support, provider, store, product), expected effect and the share of negative
  reviews they address (the share is computed by the tool, not the AI). Overview "What we should
  do" and the monthly report; `ai.features.measures`.
- **Sentiment per review** (delighted, satisfied, wish, angry, resigned) and urgency, also where
  the stars mislead (three stars but angry; threatens to switch). Sentiment bar and tiles in the
  Reviews tab, columns and filters "Sentiment (AI)" / "Urgency (AI)" in the review list, fields
  `aiSentiment`, `aiUrgency`, `aiIssue` in the CSV export.
- **Themes** the AI recognises freely, suggestions for new entries in `config/themen.json`, and
  the **most requested features** with trend (buttons under "Topics and words").
- **Effect of updates**: per release which complaints are new and which disappeared; complaints
  that occur only in the newest version ("What an update changed", "Comparison by version").
- **App comparison**: share of angry users, main praise, main criticism, assessment ("Apps
  compared"), and **churn**: share of reviews threatening to switch or delete ("Key figures per
  app").
- **Reply drafts** for open 1–2-star reviews under "Support replies", for copying only; nothing is
  ever sent to a store.
- **Competitors**: the same summary, sentiment and themes for competitor apps, if configured.
- **Questions to the data**: "Which apps mention the bonus programme?", answered with quotes.
  Via `./ratings.sh ask`, or directly in the report with the local question service (below).

Every AI statement carries the label "KI"/"AI" with provider, model and date. Numbers in the
report always come from the data, never from the AI.

### Switching it on

1. Copy the `ai` block from `config/config.example.json` into `config/config.json` and set
   `"enabled": true` for one provider. If several are enabled, the first in the list counts.
2. Put the key into the environment variable named in `apiKeyEnvironmentVariable`, e.g.
   `export ANTHROPIC_API_KEY="…"` in `~/.zshrc`. The key itself never goes into the file. Not
   needed for `local`.
3. `./ratings.sh ai-usage` shows which provider is active. `./ratings.sh analyze` analyses and
   rebuilds the report. With `./ratings.sh all` and the menu entry "Alles auf einmal" the AI runs
   automatically as soon as a provider is active.

### Local instead of cloud: provider `local`

If you do not want to hand reviews to a cloud provider, run the model on your own machine. The
price is time and quality: a batch of reviews takes minutes instead of seconds on a laptop, and
small models keep the required JSON format and the rule "verbatim quotes only" less reliably. The
tool's validation then discards more, and summaries get shorter. For sentiment, themes and
urgency a local model is fine; summaries show the difference.

1. Install Ollama (the default of `local`): macOS and Windows via the installer from
   [ollama.com](https://ollama.com), Linux with `curl -fsSL https://ollama.com/install.sh | sh`.
   Ollama then runs in the background (macOS: menu-bar icon; otherwise `ollama serve`).
2. Pull a model, e.g. `ollama pull llama3.1:8b` (about 5 GB, once). `ollama list` shows what is
   there.
3. Enlarge the context window, otherwise the batches do not fit: Ollama starts models with 4096
   tokens by default. Set `OLLAMA_CONTEXT_LENGTH=16384` (macOS: `launchctl setenv
   OLLAMA_CONTEXT_LENGTH 16384` and restart Ollama; Linux: in the systemd unit; Windows: system
   environment variable).
4. Enable `local` in `config/config.json` and allow smaller batches and more time:

   ```json
   "ai": {
     "providers": [{ "name": "local", "enabled": true, "model": "llama3.1:8b" }],
     "maxReviewsPerRequest": 15,
     "maxCharsPerRequest": 24000,
     "summaryReviews": 40,
     "requestTimeoutSeconds": 600
   }
   ```

`./ratings.sh ai-usage` then shows "local: active (local, no key)"; `./ratings.sh analyze
--dry-run` shows what would be sent, `./ratings.sh analyze` starts. If Ollama is not running, the
tool reports a network error to `127.0.0.1:11434`.

| Model | RAM | Notes |
|---|---|---|
| `llama3.1:8b` | from 8 GB | Default. Reliable JSON, decent German, runs on any current Mac or laptop |
| `gemma3:12b` | from 12 GB | Better German and more careful summaries, a bit slower |
| `qwen3:14b` | from 16 GB | Strongest summaries among the small models, clearly slower |
| `mistral-small3.2` | from 16 GB | Good middle ground between speed and care |
| `llama3.2:3b` | from 4 GB | Small and fast; shorter texts, quotes more often unusable. Enough for sentiment and themes |

Any model the local server offers works; the name goes into `"model"`. The ranking is based on
model class and experience with strict JSON output, not on a benchmark with your reviews. On Apple
Silicon the GPU is used automatically; 16 GB of shared memory is enough for the 8B and 12B models.

**LM Studio, llama.cpp (`llama-server`), vLLM, LocalAI, Jan** or any other local service with an
OpenAI-compatible endpoint uses the same provider: add `"url"` to the `local` entry, e.g.
`"http://127.0.0.1:1234/v1/chat/completions"` for LM Studio or
`"http://127.0.0.1:8080/v1/chat/completions"` for `llama-server`, and optionally `"label": "LM
Studio"`. Only addresses on the own machine (`127.0.0.1`, `localhost`, `::1`) or `https` are
allowed: an Ollama in the company network under another address works only via `https`, because
the reviews would otherwise cross the network unencrypted. A local server behind a proxy with
access protection may still get `apiKeyEnvironmentVariable`; the value is then sent as a Bearer
token. Costs show as 0 dollars; the monthly token limit still counts.

### Cost

- Only **new or changed** reviews are sent (compared by content hash). The summary of an app is
  regenerated only when its basis changes. `./ratings.sh analyze --dry-run` shows what would be
  sent, without a request.
- Every request stays below `maxCharsPerRequest`; long texts are cut to `maxReviewChars`; a
  summary that does not fit runs in two stages. A model's context is never blown.
- `monthlyTokenLimit` is a hard brake per month (default 2 million tokens). `./ratings.sh
  ai-usage` shows usage and estimated cost per month and per customer/app; the same table is
  printed at the end of every AI run. The estimate is tokens × list price in US dollars
  (`./ratings.sh ai-models` lists models and prices, as of October 2026); your own prices go into
  `priceInputPerMillion` / `priceOutputPerMillion`. The provider's invoice is what counts. For 90
  reviews the complete analysis with the default model costs a few cents.
- Free-text questions are off by default (`ai.features.questions`), because every question costs
  a request.
- AI requests have their own timeout (`ai.requestTimeoutSeconds`, default 180 s). Truncated
  answers (output limit reached) are detected and reported as such. Details of a run are in
  `data/logs/collect.log` and `data/logs/ki.log` (debug level, rotating, keys removed).

### Questions directly in the report

`./ratings.sh ai-report` starts a local question service, rebuilds the report and opens it in one
step (main menu entry 5, short menu entry 4). `./ratings.sh ai-serve` is the service alone. It is
the only network access the report ever makes, and it exists only while the terminal is open:

- Bound to `127.0.0.1` only. A report built while the service runs gets an input box under
  "Questions to the data" and may talk to exactly this port (CSP `connect-src`); the published
  report on a server has no service and only shows stored answers.
- A question refers to the **complete filter selection** of the report: selected apps, period,
  stars, topic, search, sentiment (up to 3,000 review IDs are sent to the service, which forwards
  only the newest up to the budget). The tab "AI questions" appears only while the service runs.
- "Choose questions …" opens the preset list from `config/fragen.json`; a click asks the question
  immediately.
- Up to 100 questions are stored in `data/ai-questions.json` (oldest drop out); the report shows
  the newest 10 with "Show all". Delete in the report (button next to each question) or with
  `./ratings.sh ai-questions --delete NR` / `--clear`.
- Protection: random token per start in `data/ai-service.json` (mode 0600, deleted on exit), only
  origin `null`/`127.0.0.1`/`localhost`, requests up to 4 KB, one question at a time, the same
  token budget as elsewhere.

### Honesty, security and privacy

- Quotes are checked against the original text and discarded otherwise; a question without a
  verbatim quote is answered as "unclear". The AI cannot trigger anything: reply drafts are never
  sent, theme suggestions enter the topic list only after your confirmation
  (`./ratings.sh ai-themes --accept NR`), data is never deleted or overwritten.
- **What leaves the computer** per review: title and text (switch off with
  `"sendReviewText": false`), stars, date, app version, language, country, the app name and
  whether a developer reply exists. Reviews are numbered, without store ID. **Never:** user names
  (not stored at all), review IDs, credentials, customer names, store figures, crash data. The
  measures request contains no texts, only counts from previous answers.
- The key is read from the environment variable only, rejected in the configuration, and removed
  from logs, error messages and the report. It is sent only in the HTTP header.
- Exactly one provider receives data, the one you chose (all five cloud providers are based in
  the USA). Check the provider's API terms before enabling: inputs must not be used for training.
  With `local` there is no recipient at all. The report's privacy page (section 4a) names
  recipients, fields and legal basis.
- All results live locally in `data/` (`ai-analysis.json` per app, `ai-questions.json`,
  `ai-usage.json`, `ai-themes.json`) with mode 0600, never in git. `reset` deletes them with a
  backup like all other data.

---

## Notifications after the daily run

After every `./ratings.sh daily` the tool checks the data and sends a short message **only** if
something noteworthy happened since the last message:

| Trigger | What is reported | Setting |
|---|---|---|
| **New 1–2-star reviews** | Every review with one or two stars fetched since the last run: app, stars, date, country, version, title, text (shortened) and, if the AI analysis runs, its key sentence ("AI: login fails since update") | `triggers.negativeReviews` |
| **Traffic-light change** | An app turns yellow or red, or is green again, with the reasons as the report shows them ("3 × 1–2 ★ in 7 days", "store below 4 ★"). An improvement from red to yellow is not reported | `triggers.ampelChange` |
| **Crash jump** | The crash rate per 1,000 sessions rose by at least half or is above 2, new since the last run (Apple only, from 500 sessions) | `triggers.crashJump` |

Competitor apps are never reported. The rules are the same as in the report; the notification
invents no thresholds of its own. Every message ends with the link to the report
(`settings.reportUrl`, otherwise the file path) and, if AI sentences are included, with provider
and model. Reviewer names do not occur because they are not stored.

Example (e-mail or Slack, subject or first line in bold):

```
Ratings: 2 new 1–2 ★ · status red: Scanbox

STATUS
- Scanbox (Apple): yellow → red – 3 × 1–2 ★ in 7 days

NEW 1–2-★ REVIEWS
- Scanbox (Apple), 1 ★, 2026-10-24, DEU, version 2.4.1
  "Login no longer works"
  Since the update I cannot get in, the card is not recognised.
  AI: login fails since update (urgency high)
- Scanbox (Apple), 2 ★, 2026-10-23, AUT
  Constant crashes when opening the inbox.

Report: https://ratings.company.internal/
Sentences starting with "AI:" come from the stored AI analysis (anthropic (claude-sonnet-5-5)); numbers never come from the AI.
Generated by app-ratings-reviews on 2026-10-25 at 06:35 UTC.
```

**How it runs.** `daily` does four things in order: fetch (`collect.py --dataset all
--once-per-day`, with AI if enabled), report and Markdown (`report.py --zip`), then `notify.py`.
It runs last on purpose, so that traffic lights, AI sentences and the linked report are up to
date. The step needs no access to Apple, Google or the AI: it reads `data/` and remembers in
`data/notify-state.json` when it last ran, which traffic-light level each app had and whether a
crash reason existed. Therefore:

- An incident is reported once, even if `daily` runs several times a day.
- **The first run reports nothing**; it only remembers the state (`quietOnFirstRun`). Otherwise
  you would get a message with every 1–2-star review ever fetched.
- If no channel could deliver, the remembered state stays and the next run retries with the same
  incidents. If at least one channel delivered, the incident counts as reported; the run still
  ends with exit code 1 so the failure shows up in the log.
- With `notify.enabled: false` (default) the step ends silently.

**Setting it up.**

1. Choose a channel and get access. *E-mail:* SMTP server, port, username and password of a
   mailbox that may send (often an "app password"); STARTTLS on 587 or SSL on 465; unencrypted
   only to a relay on the same machine. *Slack:* create an app with "Incoming Webhooks" and a
   webhook for the channel; the address `https://hooks.slack.com/services/…` is the secret.
   *Webhook:* an HTTPS address accepting a JSON POST (Teams workflow, n8n, Zapier, your own
   service), optionally with a shared secret for the header `X-Ratings-Signature`.
2. Put the secrets into environment variables, never into `config.json`, e.g.
   `RATINGS_SMTP_PASSWORD`, `RATINGS_SLACK_WEBHOOK`, `RATINGS_WEBHOOK_URL`,
   `RATINGS_WEBHOOK_SECRET`. In a scheduler they belong into the systemd unit, the launchd plist,
   the Task Scheduler or the CI secrets.
3. Add the `notify` block to `config/config.json` (template in `config.example.json`), set
   `enabled: true` on the block and on the channel, and set `settings.reportUrl`.

   ```json
   "settings": { "reportUrl": "https://ratings.company.internal/" },
   "notify": {
     "enabled": true,
     "language": "en",
     "channels": [
       { "type": "email", "enabled": true, "host": "smtp.company.com", "port": 587, "security": "starttls",
         "username": "report@company.com", "passwordEnvironmentVariable": "RATINGS_SMTP_PASSWORD",
         "from": "report@company.com", "to": ["boss@company.com", "support@company.com"] },
       { "type": "slack", "enabled": true, "webhookUrlEnvironmentVariable": "RATINGS_SLACK_WEBHOOK" }
     ]
   }
   ```

4. Test: `./ratings.sh notify --test` sends a test message to all enabled channels;
   `./ratings.sh notify --dry-run` shows the message the daily run would send now, without
   sending or remembering anything. Both are also in the menu under "Status und Übersicht".

**Privacy.** Per reported review: stars, date, country, version, title and text (max. 300
characters), the app name, the traffic-light reasons and the AI key sentence. Recipients are only
the addresses, mail server, Slack workspace or webhook service you configured. Reviews are public
texts but may contain details the author wrote in, so recipients belong inside the company, not
on open lists. SMTP only with STARTTLS or SSL and certificate check, webhooks only via HTTPS.
Secrets are removed from logs (`security.redact`, including the secret part of a Slack address).
No new AI request is made for a notification.

---

## The report

`reports/index.html` is a single file without network access (no CDN, strict CSP, no `innerHTML`),
light and dark, **bilingual** (switch `DE | EN` in the header; the choice is stored in the browser,
`?lang=en` forces English; number formats follow the language).

- **Filter at the top** steers everything below: customer and app (multi-select with checkboxes
  and search), platform, period and free-text search always visible; "Advanced" with language,
  country, app version, OS, device, topic, stars, developer reply, from/to and "text only".
- **Tabs**: Overview, Reviews, Stability, Downloads & Store, Charts, plus Competitors (only with
  competitors) and AI questions (only while the question service runs). Test operation is a
  separate page via the production/test switch in the header. Every section can be collapsed; the
  red "i" next to a heading opens an explanation of the section.
- **Overview**: three answer cards for the last 30 days ("How is it going overall?", "What is
  striking right now?" with traffic lights, "What did the last update change?"), a traffic-light
  table per app (store rating, new reviews, crashes per 1,000, downloads per week, reason; click a
  row to select the app), "Questions and answers" (six cards with a plain-language answer each
  and "reliable" or "little data"), and "More figures" with key figures per app, comparison by
  version and the effect of updates.
- **Reviews**: overall rating, key figures, topics and words (topics from `config/themen.json`,
  typical words of negative vs. positive reviews, rising terms), sortable review list with detail
  view and CSV/JSON export, and "Support replies" (reply rate, median reply time, stars improved
  after a reply, open 1–2-star reviews).
- **Downloads & Store**: "Apps compared" per Apple app (downloads per 1,000 of the audience,
  impression → download, store rating, crashes per 1,000 sessions, deletions per 100 installs,
  share on the newest version, median from three apps) with a button "Print app report" (one
  page per app with ranks, median and findings).
- **Charts**: 19 charts in groups (overview, ratings, downloads and store, stability and usage),
  Apple and Google side by side, release markers under the time charts, a weekly overview of
  sessions, crashes and downloads.
- **Print and clipboard**: next to "Reset filter", "Print report" / "Copy to clipboard" produce
  the complete report (all available reports grouped by tab) or, per card, the monthly report,
  topics, stability, downloads & store or ten charts. Every printout starts with date, time and
  the active filter. "Copy to clipboard" puts formatted HTML (styles embedded, charts as PNG) plus
  plain text on the clipboard for Word, Outlook, Teams or Jira. PDF via the browser's print dialog
  with a suggested file name like `Monthly-report-<selection>-YYYYMMDD-HHMMSS.pdf`. Nothing is
  sent anywhere.
- URL parameters: `?dark`, `?light`, `?static` (no bar animation), `?lang=de|en`,
  `?tab=start|rez|stabil|store|charts|rivals|ask`, `?alle` (all sections open), `?chart=<id>`.
- Next to `index.html` the tool writes `hilfe.html` (help), `impressum.html` (imprint) and
  `datenschutz.html` (privacy) in the same style.

Official store values and self-computed values are always kept apart and labelled as such.

---

## Debug mode with generated test data

For presentations and performance tests without loading or endangering real data. Everything runs
in its own set: `config/config.debug.json`, `data-debug/`, `reports-debug/` (all in `.gitignore`,
regenerated on every run). The real files are never read or written; the generator refuses any
data folder without "debug" in its name, and the placeholder credentials have no key, so a store
fetch is impossible.

```bash
./ratings.sh debug-menu                                   # short menu on test data (kurzmenudebug.sh)
./ratings.sh demo --list-categories
./ratings.sh demo --categories krankenkassen,sport --volume viele --months 12 --reviews 50-400
python report.py --config config/config.debug.json        # report from the test data
```

- **Categories**: health insurers (30 apps of one software house with shared code and versions,
  profiles from "very good" to "very bad"), games, navigation, sport, AI, news, finance, travel,
  office. Every app has its own profile (star distribution, trend, crash rate, reply rate,
  usage, one version with a crash jump). One Google target is deliberately set to "error".
- **Volume**: `wenig` (5–25 reviews per app), `mittel` (20–120), `viele` (100–600), `sehr-viele`
  (500–3000); also drives the density of stability and store figures. **Period**: 3 to 24 months.
  `--reviews MIN-MAX` overrides the range, `--apps N` keeps only the first N apps per category,
  `--seed N` changes the random start; the same choice always gives the same data.
- **Files**: exactly the format of real fetches. `ai-analysis.json` is never invented: if a
  provider is enabled, the debug menu asks whether the real AI should analyse the test data (this
  costs real requests; usage goes to `data-debug/ai-usage.json`).
- **Size**: with all categories and 24 months the report is about 20 MB at `wenig` and 50 MB at
  `mittel`; `sehr-viele` is meant for performance tests.

---

## Files and folders

```
app-ratings-reviews/
├── ratings.sh              one entry point for all commands
├── menu.sh                 big interactive menu
├── kurzmenu.sh             short menu (4 functions)
├── kurzmenudebug.sh        short menu on generated test data only
├── collect.py              fetching (Apple / Google / competitors / AI)
├── report.py               HTML report + Markdown (offline)
├── ki.py                   AI commands: ask, questions, themes, usage, models, serve
├── notify.py               notification after the daily run
├── demo.py                 generator for fictional test data
├── reset.py                delete data with backup
├── menu.py                 menu logic
├── lib/common.sh           shared checks (venv, config)
├── src/                    the actual implementation (API clients, sync, storage, report, AI, notify)
├── templates/              HTML templates for report, help, imprint, privacy (report split into templates/report/)
├── config/
│   ├── config.example.json template
│   ├── themen.json         word lists for "Topics and words" (versioned)
│   ├── fragen.json         preset AI questions (versioned)
│   └── config.json         your configuration (not in git)
├── keys/                   your .p8 and service-account JSON files (not in git)
├── data/                   collected data (not in git)
├── reports/                generated report (not in git)
├── data-debug/, reports-debug/, config/config.debug.json   debug mode (not in git)
└── backups/                ZIP backups before every data-changing run and by reset (not in git)
```

### Data layout

```
data/
├── state.json                     sync state per customer/app/platform
├── sync-history.json              log of all runs
├── last-daily.json                marker for --once-per-day
├── notify-state.json              last notification run, traffic light per app (only with notify)
├── ai-usage.json                  tokens and cost per month and app (only with AI)
├── ai-questions.json              stored questions and answers (only with AI)
├── ai-themes.json                 rejected theme suggestions (only with AI)
├── ai-service.json                token of the running question service (only while it runs)
├── logs/                          collect.log, ki.log, notify.log (rotating, keys removed)
├── customers/<customer>/apps/<app>/
│   ├── apple/
│   │   ├── reviews.json           all reviews
│   │   ├── review-history.json    changes to existing reviews
│   │   ├── versions.json          App Store versions
│   │   ├── ratings-history.json   official store rating snapshots
│   │   ├── stability-metrics.json crashes and sessions
│   │   ├── store-metrics.json     downloads, installs/deletions, store views
│   │   ├── testflight.json        TestFlight builds and usage
│   │   └── ai-analysis.json       AI results (only with AI)
│   └── google/
│       ├── reviews.json
│       ├── review-history.json
│       ├── google-testing.json    test tracks and crash rates
│       └── ai-analysis.json
└── customers/<customer>/competitors/<id>/apple/     (only with competitors)
    ├── reviews.json               newest reviews + store profile
    ├── review-history.json
    ├── ratings-history.json
    └── ai-analysis.json
```

Each review has the unique key `platform:storeAppId:reviewId`, so repeated fetches never create
duplicates. JSON files are written atomically with restricted permissions (`600`); the same goes
for the report, the Markdown files and the ZIP, so a browser or web server never sees a half
file. A damaged JSON file is never overwritten – the run stops with an error instead. A lock file
(`data/.lock`) prevents two runs at the same time.

**Backup before every run:** `collect.py` packs `data/` (without `logs/`) into
`backups/data-<UTC time>.zip` before it changes anything; the newest 30 are kept
(`settings.backupKeep`). If the backup fails (disk full), the run does not start. `--no-backup`
switches it off, dry runs never back up. Restore: stop the run, move `data/` aside, `unzip` the
ZIP in the project folder.

**Never commit:** `config/config.json`, `keys/`, `data/`, `reports/`, `backups/`.
Note that `.gitignore` covers `*.p8`, `service-account*.json` and `config/config.json`; if you
name your Google key differently (e.g. `customer-a-google.json`), add `keys/` to `.gitignore`.

---

## Daily automatic run

A daily run is **required** if you use Google, because the Google API only returns the last
7 days. Use `./ratings.sh daily`: it fetches at most once per calendar day (UTC), always rebuilds
the report, Markdown and ZIP, and never opens a browser. A failed run may be repeated on the same
day. The order is: fetch (`collect.py --dataset all --once-per-day`, with AI if a provider is
enabled), report + Markdown + ZIP, then the notification (`notify.py`, silent unless
`notify.enabled`). If the report or the notification fails, the message is in the log and the
exit code is at least 1.

**cron (Linux / macOS):**

```cron
30 6 * * * cd /home/ratings/app-ratings-reviews && ./ratings.sh daily >> logs-daily.txt 2>&1
```

**macOS alternative:** a `launchd` agent that runs the same command.

**CI (e.g. GitHub Actions):** put the key contents into secrets, expose them as environment
variables and reference them via `privateKeyEnvironmentVariable` / `serviceAccountEnvironmentVariable`.
AI keys (`ANTHROPIC_API_KEY` etc.) and notification secrets (`RATINGS_SMTP_PASSWORD`,
`RATINGS_SLACK_WEBHOOK`, `RATINGS_WEBHOOK_URL`, `RATINGS_WEBHOOK_SECRET`) go the same way.
Keep `data/` between runs (cache, artifact or a data branch), otherwise older Google reviews get
lost and every day would be a new first run. Run this only in a **private** repository: `data/`
contains review texts.

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
- **Google stability and store figures** are not implemented (no Android app to test against).
- **Competitors** (Apple public feed): only the newest 500 reviews per country, no developer
  replies, no language or device, no crashes or downloads. Nothing for Google.
- **AI texts** are suggestions of a language model, not measurements; model names, prices and
  endpoints change. The cost estimate is based on list prices; the provider's invoice counts.
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
| No AI command, "kein Anbieter freigeschaltet" | No provider has `enabled: true`, or its environment variable is empty. `./ratings.sh ai-usage` shows the state. |
| Network error to `127.0.0.1:11434` | The local model server is not running. Start Ollama (`ollama serve`) or check `url` of the `local` provider. |
| AI answers are "no valid JSON" or quotes are discarded | Model too small or context window too short. For Ollama set `OLLAMA_CONTEXT_LENGTH=16384`, reduce `maxReviewsPerRequest`, or use a larger model. |
| `monthlyTokenLimit` reached | Hard brake. Raise the limit in `ai` or wait for the next month. |
| "Benachrichtigung ist ausgeschaltet" on `notify --test` | `notify.enabled` is `false` |
| "Umgebungsvariable … ist nicht gesetzt" | Set the variable in the scheduler (not only in your shell); in CI as a secret |
| SMTP 535 / "Slack-Webhook abgelehnt" | Wrong username or password (often an app password is needed) / webhook deleted or address copied wrongly |
| Notification arrives although nothing is new | `data/notify-state.json` was deleted; this is a first run again (silent if `quietOnFirstRun`) |
| No notification despite new 1–2-star reviews | `./ratings.sh notify --dry-run` shows what is pending; log in `data/logs/notify.log` |

For more detail, the generated report includes a help page (`reports/hilfe.html`) with the same
setup steps in German and English.
