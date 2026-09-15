#!/usr/bin/env python3
"""
NFL Wins Pool 2026 - data fetcher.

Runs on a GitHub Actions schedule (see .github/workflows/weekly.yml).
Pulls the published Google Sheet CSV Marz maintains by hand, and produces:
  - data.json              (current standings/teams/draft - consumed by index.html)
  - weekly_snapshots.json  (accumulated per-week history, used to build the
                             Weekly page's trend chart and W/L/T/BYE grid)

No API keys or secrets required - the sheet is published-to-web.

IMPORTANT - cumulative vs. delta:
The sheet only ever reports SEASON-TO-DATE totals per team (not a per-week
delta). To get a per-week result we always store the full cumulative
snapshot for each week we see, then DERIVE that week's W/L/BYE by
subtracting the previous week's cumulative snapshot at build time. Never
store a delta as the source of truth - always re-derive it from the two
cumulative snapshots on either side. (Recompute-from-cumulative, not
carry-the-delta-forward, is what keeps re-runs of this script idempotent.)
"""
import csv
import io
import json
import os
import urllib.request

CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vTHWvxpHyXj-5ivKStfcQM01b2Y2GKW9qmkTZfCRJKlG2KmHADmg9F0KfRH47feiljzXca3p0reudOO/"
    "pub?gid=779816994&single=true&output=csv"
)

DATA_JSON_PATH = "data.json"
SNAPSHOTS_PATH = "weekly_snapshots.json"
TOTAL_WEEKS = 18
NOT_DRAFTED_LABEL = "NOT DRAFTED"

NAME_TO_ABBR = {
    "Buffalo Bills": "BUF", "Miami Dolphins": "MIA", "New England Patriots": "NE", "New York Jets": "NYJ",
    "Baltimore Ravens": "BAL", "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Pittsburgh Steelers": "PIT",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX", "Tennessee Titans": "TEN",
    "Denver Broncos": "DEN", "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Dallas Cowboys": "DAL", "New York Giants": "NYG", "Philadelphia Eagles": "PHI", "Washington Commanders": "WAS",
    "Chicago Bears": "CHI", "Detroit Lions": "DET", "Green Bay Packers": "GB", "Minnesota Vikings": "MIN",
    "Atlanta Falcons": "ATL", "Carolina Panthers": "CAR", "New Orleans Saints": "NO", "Tampa Bay Buccaneers": "TB",
    "Arizona Cardinals": "ARI", "Los Angeles Rams": "LAR", "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA",
}


def fetch_csv_text():
    req = urllib.request.Request(CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8-sig")


def parse_csv(csv_text):
    """Returns (draft, team_meta, owner_teams, not_picked).
    draft: list of {pick, owner, team, name} ordered by pick.
    team_meta: {abbr: {pick?, owner?, team, name, w, l, pd, games, w2025}}
                (drafted teams have pick/owner; undrafted do not)
    """
    rows = [r for r in csv.reader(io.StringIO(csv_text)) if r and r[1].strip()]
    data_rows = rows[1:]  # skip header

    draft = []
    team_meta = {}
    owner_teams = {}
    not_picked = []

    for r in data_rows:
        owner = r[1].strip()
        fullname = r[2].strip()
        pick_raw = r[3].strip()
        w2025 = int(r[5]) if r[5].strip() else 0
        w = int(r[8]) if r[8].strip() else 0
        l = int(r[9]) if r[9].strip() else 0
        games = int(r[10]) if r[10].strip() else 0
        pd_str = r[15].strip() if len(r) > 15 else ""
        pd = int(pd_str) if pd_str not in ("",) else 0
        abbr = NAME_TO_ABBR.get(fullname)
        if abbr is None:
            print("WARNING: unrecognized team name in sheet:", fullname)
            continue
        pct = round(w / games, 4) if games > 0 else None

        if owner == NOT_DRAFTED_LABEL:
            not_picked.append({
                "team": abbr, "name": fullname, "pct": pct,
                "w2025": w2025, "pd": pd, "w": w, "l": l, "games": games,
            })
            continue

        pick = int(pick_raw)
        draft.append({"pick": pick, "owner": owner, "team": abbr, "name": fullname})
        team_meta[abbr] = {
            "pick": pick, "owner": owner, "team": abbr, "name": fullname,
            "w": w, "l": l, "t": 0, "pct": pct, "pd": pd, "games": games, "w2025": w2025,
        }
        owner_teams.setdefault(owner, []).append(abbr)

    draft.sort(key=lambda d: d["pick"])
    return draft, team_meta, owner_teams, not_picked


def compute_standings(owner_teams, team_meta):
    owners = sorted(owner_teams.keys(), key=lambda o: min(team_meta[tm]["pick"] for tm in owner_teams[o]))
    standings = []
    for o in owners:
        teams = owner_teams[o]
        w = sum(team_meta[tm]["w"] for tm in teams)
        l = sum(team_meta[tm]["l"] for tm in teams)
        t = 0
        pd = sum(team_meta[tm]["pd"] for tm in teams)
        gp = w + l + t
        pct = round((w + 0.5 * t) / gp, 4) if gp > 0 else None
        standings.append({"owner": o, "teams": teams, "w": w, "l": l, "t": t, "pd": pd, "pct": pct})

    standings.sort(key=lambda r: (-(r["pct"] if r["pct"] is not None else -1), -r["pd"]))
    top = standings[0]
    for i, r in enumerate(standings):
        r["rank"] = i + 1
        r["gb"] = 0 if i == 0 else round((((top["w"] - top["l"]) - (r["w"] - r["l"])) / 2), 1)
    return owners, standings


def compute_draft_value(draft, team_meta):
    def eff_pct(tm):
        return tm["pct"] if tm["pct"] is not None else round(tm["w2025"] / 17, 4)

    all_sorted = sorted(team_meta.values(), key=lambda x: -eff_pct(x))
    draft_value = []
    for d in draft:
        tm = team_meta[d["team"]]
        if tm["pct"] is None:
            continue
        optimal = eff_pct(all_sorted[d["pick"] - 1]) if d["pick"] - 1 < len(all_sorted) else tm["pct"]
        draft_value.append({
            "pick": d["pick"], "team": d["team"], "owner": d["owner"],
            "actual_pct": tm["pct"], "optimal_pct": round(optimal, 4),
            "value": round(tm["pct"] - optimal, 4),
        })
    return draft_value


def load_snapshots():
    if os.path.exists(SNAPSHOTS_PATH):
        with open(SNAPSHOTS_PATH) as f:
            return json.load(f)
    return {"weeks": [], "cumulative_by_week": {}}


def update_snapshots(snapshots, team_meta, not_picked):
    """Record this run's cumulative per-team totals under the current week
    key. The current week number = the max games played by any team this
    run (a team on bye that week will simply lag by one). Overwrites the
    same week's entry on re-run, so running this script twice in one week
    is always safe."""
    all_teams = dict(team_meta)
    for np in not_picked:
        all_teams[np["team"]] = np

    max_games = max((t["games"] for t in all_teams.values()), default=0)
    if max_games == 0:
        return snapshots, None  # season hasn't started yet - nothing to snapshot

    week_key = "w{}".format(max_games)
    cum = {abbr: {"w": t["w"], "l": t["l"], "games": t["games"], "pd": t["pd"]} for abbr, t in all_teams.items()}
    snapshots["cumulative_by_week"][week_key] = cum
    if week_key not in snapshots["weeks"]:
        snapshots["weeks"].append(week_key)
        snapshots["weeks"].sort(key=lambda w: int(w[1:]))
    return snapshots, week_key


def derive_week_result(prev, cur):
    """prev/cur are {"w","l","games"} cumulative dicts (prev may be None)."""
    prev_games = prev["games"] if prev else 0
    d_games = cur["games"] - prev_games
    if cur["games"] == 0:
        return "PEND"
    if d_games <= 0:
        return "BYE"
    d_w = cur["w"] - (prev["w"] if prev else 0)
    d_l = cur["l"] - (prev["l"] if prev else 0)
    if d_w > d_l:
        return "W"
    if d_l > d_w:
        return "L"
    return "T"


def build_weekly_data(snapshots, all_team_abbrs, owner_teams):
    weeks = snapshots["weeks"]
    cbw = snapshots["cumulative_by_week"]
    week_labels = {w: "Wk {}".format(w[1:]) for w in weeks}

    weekly_by_team = {abbr: {} for abbr in all_team_abbrs}
    for i, wk in enumerate(weeks):
        prev_wk = weeks[i - 1] if i > 0 else None
        for abbr in all_team_abbrs:
            cur = cbw[wk].get(abbr)
            if cur is None:
                weekly_by_team[abbr][wk] = {"result": "PEND"}
                continue
            prev = cbw[prev_wk].get(abbr) if prev_wk else None
            weekly_by_team[abbr][wk] = {"result": derive_week_result(prev, cur)}

    owner_weekly = {}
    for owner, teams in owner_teams.items():
        owner_weekly[owner] = {}
        cw = cl = ct = 0
        for i, wk in enumerate(weeks):
            prev_wk = weeks[i - 1] if i > 0 else None
            w = l = t = 0
            for abbr in teams:
                res = weekly_by_team[abbr][wk]["result"]
                if res == "W":
                    w += 1
                elif res == "L":
                    l += 1
                elif res == "T":
                    t += 1
            cw += w; cl += l; ct += t
            gp = cw + cl + ct
            pct = round((cw + 0.5 * ct) / gp, 4) if gp > 0 else None
            owner_weekly[owner][wk] = {"w": w, "l": l, "t": t, "pct": pct,
                                        "cum_pct": pct, "cum_w": cw, "cum_l": cl, "cum_t": ct}
    return weeks, week_labels, weekly_by_team, owner_weekly


def main():
    csv_text = fetch_csv_text()
    draft, team_meta, owner_teams, not_picked = parse_csv(csv_text)
    owners, standings = compute_standings(owner_teams, team_meta)
    draft_value = compute_draft_value(draft, team_meta)

    snapshots = load_snapshots()
    snapshots, current_week_key = update_snapshots(snapshots, team_meta, not_picked)
    with open(SNAPSHOTS_PATH, "w") as f:
        json.dump(snapshots, f, indent=2)

    all_team_abbrs = list(team_meta.keys()) + [np["team"] for np in not_picked]
    weeks, week_labels, weekly_by_team, owner_weekly = build_weekly_data(snapshots, all_team_abbrs, owner_teams)
    current_week_num = int(current_week_key[1:]) if current_week_key else 0

    team_rows = sorted(team_meta.values(), key=lambda x: x["pick"])
    for t in team_rows:
        t.pop("games", None)
    for np in not_picked:
        np.pop("games", None)

    from datetime import datetime, timezone
    data = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "current_week": current_week_num,
        "total_weeks": TOTAL_WEEKS,
        "week_order": weeks,
        "week_labels": week_labels,
        "owners_order": owners,
        "standings": standings,
        "team_rows": team_rows,
        "draft": draft,
        "not_picked": not_picked,
        "draft_value": draft_value,
        "owner_weekly": owner_weekly,
        "weekly_by_team": weekly_by_team,
    }
    with open(DATA_JSON_PATH, "w") as f:
        json.dump(data, f, indent=2)

    print("Wrote {} ({} owners, {} weeks tracked, current week {})".format(
        DATA_JSON_PATH, len(owners), len(weeks), current_week_num))


if __name__ == "__main__":
    main()
