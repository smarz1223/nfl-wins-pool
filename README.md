# NFL Wins Pool 2026

Live standings site for the 10-owner NFL wins pool. Pulls from the published
Google Sheet automatically once a week — no manual data entry into the site.

## Files in this repo

| File | Purpose |
|---|---|
| `index.html` | The site. Loads `data.json` on every page view. |
| `data.json` | Current standings/teams/draft — rewritten by the Action every week. Don't hand-edit; it gets overwritten. |
| `weekly_snapshots.json` | Accumulated week-by-week history, used to build the Weekly page's trend chart and W/L/BYE grid. Don't hand-edit. |
| `fetch_data.py` | Pulls the published sheet CSV and rebuilds the two JSON files above. |
| `.github/workflows/weekly.yml` | Runs `fetch_data.py` automatically every Tuesday morning. |
| `CNAME` | Tells GitHub Pages this site lives at `nflwins.redplanetanalytics.com`. |

No API keys or secrets are needed — the Google Sheet is published-to-web, so
the script just downloads it like any public URL.

## One-time setup

### 1. Create the repository
On github.com, under your `smarz1223` account: **New repository** → name it
something like `nfl-wins-pool` → **Public** → Create repository (don't
initialize with a README, since you're uploading one).

### 2. Upload the files
On the new repo's page, click **Add file → Upload files**, then drag in
everything from this folder — **including the `.github` folder**. Dragging
a folder (not just its contents) preserves the `.github/workflows/weekly.yml`
path; if your browser only lets you drop individual files, create the path
by hand instead: **Add file → Create new file**, type
`.github/workflows/weekly.yml` as the filename (the slashes create the
folders automatically), then paste in the workflow content.

Commit directly to `main`.

### 3. Turn on GitHub Pages
Repo → **Settings → Pages**:
- Source: **Deploy from a branch**
- Branch: `main`, folder `/ (root)`
- Save

### 4. Allow the Action to commit
Repo → **Settings → Actions → General → Workflow permissions**:
- Select **Read and write permissions**
- Save

This lets the weekly job push the refreshed `data.json` back to the repo.

### 5. Point the subdomain at it (Cloudflare)
Same pattern as `mlbwins` and `barry`:
- Cloudflare → RedPlanetAnalytics.com → DNS → **Add record**
- Type: `CNAME`, Name: `nflwins`, Target: `smarz1223.github.io`
- Proxy status: **DNS only** (grey cloud)

Then back in GitHub: Repo → **Settings → Pages → Custom domain** → enter
`nflwins.redplanetanalytics.com` → Save. GitHub will verify it against the
CNAME file already in the repo.

### 6. Run it once manually
Repo → **Actions** tab → **Weekly NFL Wins Pool data refresh** →
**Run workflow** → Run workflow. This generates a fresh `data.json` right
away instead of waiting for Tuesday. Refresh the site after ~30 seconds to
confirm it loads.

## Ongoing operation

Nothing to do. Every Tuesday at 7am ET the Action re-pulls the sheet and
commits the update. If you ever need to force a refresh (e.g. you corrected
a score in the sheet), just re-run the workflow manually from the Actions
tab — it's safe to run as many times as you want in the same week; it won't
create duplicate weeks or double-count games.

## If the site shows "Error loading data.json"

That means `data.json` isn't in the repo yet (first-time setup, step 6 not
done) or the last workflow run failed. Check the **Actions** tab for a red
X and open the run to see the error — the most common cause is the
published sheet's URL or column layout having changed.
