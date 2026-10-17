# Warwick FPL rival feed · 2026/27

Automatically collects public official FPL data for league **2426424**, restricted to these seven entries: Pranav (6349748), Drew (2031878), Gopal (378938), Ben (6752830), Luca (942123), Atul & Suraj (7431627), Guto (4973768). This is a fixed cohort, not a changing top seven. No fantasy team names, credentials, email addresses or account-profile data are published.

## One-time setup

1. Use a **public** GitHub repository named `warwick-fpl`, with default branch `main`. Upload this project including `.github/workflows/refresh.yml`.
2. In **Settings → Pages → Build and deployment → Source**, select **GitHub Actions**.
3. In **Actions → Refresh Warwick FPL → Run workflow**, run it once. Subsequent runs are scheduled hourly at minute 23 UTC. The initial source upload also triggers a run.
4. Open `https://thunderjagg21-lgtm.github.io/warwick-fpl/`. A green feed status and seven populated manager records confirm collection; a successful Pages deployment alone does not.

Standard GitHub-hosted runners for public repositories and public GitHub Pages are available free. No paid services, external dependencies or custom tokens are required. The built-in repository token writes snapshots and deploys Pages. Repository policies must permit Actions to write contents.

## Use from ChatGPT

Give ChatGPT the dashboard URL once in the relevant conversation, then ask: “Fetch the Warwick feed and scout GW8 against GW7. Check freshness and missing data first.” In another conversation, include the URL again. ChatGPT must fetch the published URL upon request; this does not provide permanent memory or a live connection. The latest feed reflects the last successful scheduled fetch, not necessarily this instant.

Start with:
- `data/2026-27/status.json`: last attempt, failures, per-failure last success.
- `data/2026-27/index.json`: available historical gameweeks.
- `data/2026-27/gw8.md`: concise readable scouting data.
- `data/2026-27/gw8.json`: named players, current and previous picks, actual transfer records, chips/history, fixtures and live points.

Each source wrapper carries its official URL and successful `fetched_at`. To inspect detail use `managers/ENTRY/history.json`, `transfers.json`, `gwN.json`, `live/gwN.json`, `bootstrap.json`, `fixtures.json` and filtered `standings.json`. Paths are relative to `data/2026-27/`.

The JSON report contains squad in/out, XI in/out, captain before/after, chip and transfer cost. Squad changes are not paired transfers: use the actual transfer log for pairs and consider Free Hit reversions. Picks retain official multipliers and automatic substitutions. Starting XI in the summary means selection positions 1–11; assess actual scoring using multipliers and substitutions. Live scores/bonus may be provisional; do not double-deduct transfer costs from official totals. Remaining fixtures can be computed from the report's fixtures and player team IDs, including double gameweeks. The player dictionary uses the latest successfully fetched bootstrap metadata.

## Reliability and history

The first run backfills all gameweeks whose deadlines have passed. Future picks are never requested. HTTP 404 or malformed responses preserve last good data; 403/429 triggers a circuit breaker for the rest of the run. Transient errors receive bounded retries. Missing snapshots remain missing, never “no transfers”. Every snapshot is updated until FPL reports both `finished` and `data_checked`, then frozen to reduce traffic. To refresh a later official correction, remove that snapshot's `final` field and rerun. Git commits retain earlier versions. History is isolated under `2026-27`; a bootstrap whose first deadline is outside 2026 is rejected, preserving the archive.

On upstream failure, publish a degraded status and retain all good history. The workflow then reports failure so GitHub's configured workflow notifications can alert the owner. A crash or failed deployment may leave the previous site visible: always check timestamps. Scheduling is best effort and may be delayed or skipped; public-repository schedules can be disabled after 60 days of no repository activity. This feed normally commits status each run, but a prolonged interruption may require manually re-enabling Actions. No system can guarantee FPL will allow every GitHub runner; if persistent 403s occur, inspect the logs and use another permitted network/runner for the same collector. Do not bypass access controls or supply FPL credentials.

The league table endpoint's first page is filtered to the configured seven. If someone drops off that page they may be absent from the table; their individual picks/history continue to be tracked.

## Local checks and manual recovery

Requires Python 3.10+ with no packages:

```sh
python3 -m unittest discover -s tests -v
python3 scripts/collect.py
```

To recover from a prolonged runner outage, run the collector on a network permitted by FPL, commit `docs/` and manually run the workflow. Normal use never requires uploads. A manual workflow run refreshes on demand but still depends on FPL access.

## Verification before deployment

On 17 October 2026 the web tool could reach official bootstrap, fixtures and GW7 live endpoints, but could not retrieve tested entry picks/history/transfers endpoints. Local shell networking was unavailable. Therefore end-to-end collection must be verified by the first GitHub runner execution. No invented live data is bundled. Automated tests cover diffs, missing data, 403 preservation/circuit breaking, frozen history, season mismatch, future-deadline exclusion, and filtering to the seven names.

Official references: [FPL API bootstrap](https://fantasy.premierleague.com/api/bootstrap-static/), [GitHub Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages), [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [schedule limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
