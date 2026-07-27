"""Feature engineering for the match-outcome predictor (T1).

For each match (a row in the input DataFrame) we compute features that
are visible BEFORE kickoff. That means: we look at each team's prior
matches, never at the match being predicted. This is the cardinal rule
of time-series ML and the walkthrough doc has a whole section on it.

The feature set in this file matches the "Match-level / Team-level
rolling / Head-to-head / T1-specific" sections of features.md.

Outputs:
  - feature matrix X (DataFrame)
  - target vector y as strings 'H'/'D'/'A'
  - the original matches DataFrame for later inspection
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from .elo import compute_pre_match_elo

ROLLING_N = 5  # matches in the rolling form window


@dataclass
class FeatureSpec:
    name: str
    description: str
    group: str  # 'match' | 'team_form' | 'h2h' | 'elo' | 'venue'


FEATURE_SPECS: list[FeatureSpec] = [
    FeatureSpec("elo_home_pre", "Home team Elo rating before kickoff",                            "elo"),
    FeatureSpec("elo_away_pre", "Away team Elo rating before kickoff",                            "elo"),
    FeatureSpec("elo_delta",    "Elo difference (home - away). Single most predictive feature.",   "elo"),
    FeatureSpec("days_rest_home", "Days since home team's last match (proxy for fatigue)",         "match"),
    FeatureSpec("days_rest_away", "Days since away team's last match",                             "match"),
    FeatureSpec("days_rest_delta","Home rest minus away rest. Positive = home better rested.",     "match"),
    FeatureSpec("home_ppm_5",   "Home team points-per-match over last 5 league games",            "team_form"),
    FeatureSpec("away_ppm_5",   "Away team points-per-match over last 5",                          "team_form"),
    FeatureSpec("home_gd_5",    "Home team goal difference over last 5",                           "team_form"),
    FeatureSpec("away_gd_5",    "Away team goal difference over last 5",                           "team_form"),
    FeatureSpec("home_gf_5",    "Home team goals scored avg per match, last 5",                    "team_form"),
    FeatureSpec("away_gf_5",    "Away team goals scored avg per match, last 5",                    "team_form"),
    FeatureSpec("home_ga_5",    "Home team goals conceded avg per match, last 5",                  "team_form"),
    FeatureSpec("away_ga_5",    "Away team goals conceded avg per match, last 5",                  "team_form"),
    FeatureSpec("home_shots_for_5",   "Home shots per game, last 5",                                "team_form"),
    FeatureSpec("away_shots_for_5",   "Away shots per game, last 5",                                "team_form"),
    FeatureSpec("home_shots_on_target_5", "Home shots on target per game, last 5",                  "team_form"),
    FeatureSpec("away_shots_on_target_5", "Away shots on target per game, last 5",                  "team_form"),
    FeatureSpec("home_home_ppm_5", "Home team points-per-match in home games, last 5",              "team_form"),
    FeatureSpec("away_away_ppm_5", "Away team points-per-match in away games, last 5",              "team_form"),
    FeatureSpec("h2h_home_winrate_5", "Home win rate vs this opponent in the last 5 head-to-heads", "h2h"),
    FeatureSpec("h2h_avg_goals_5",    "Average total goals in last 5 head-to-heads",                "h2h"),
    FeatureSpec("home_yellows_5", "Home team yellow cards avg per match, last 5 (used by T3)",     "team_form"),
    FeatureSpec("away_yellows_5", "Away team yellow cards avg per match, last 5 (used by T3)",     "team_form"),
]


def _ftr_to_points(ftr: str, is_home: bool) -> int:
    if ftr == "D":
        return 1
    if (ftr == "H" and is_home) or (ftr == "A" and not is_home):
        return 3
    return 0


def _team_match_history(matches: pd.DataFrame, team: str) -> pd.DataFrame:
    """Return rows where the team appears, with a unified per-team
    perspective: gf, ga, points, shots_for, shots_against, etc."""
    is_home = matches["HomeTeam"] == team
    is_away = matches["AwayTeam"] == team
    rows = matches[is_home | is_away].copy()

    def per_match(row):
        if row["HomeTeam"] == team:
            return pd.Series({
                "Date": row["Date"],
                "is_home": True,
                "gf": row["FTHG"], "ga": row["FTAG"],
                "shots_for": row.get("HS"), "shots_against": row.get("AS"),
                "shots_on_for": row.get("HST"), "shots_on_against": row.get("AST"),
                "yellows": row.get("HY"), "reds": row.get("HR"),
                "points": _ftr_to_points(row["FTR"], is_home=True),
                "opponent": row["AwayTeam"],
            })
        return pd.Series({
            "Date": row["Date"],
            "is_home": False,
            "gf": row["FTAG"], "ga": row["FTHG"],
            "shots_for": row.get("AS"), "shots_against": row.get("HS"),
            "shots_on_for": row.get("AST"), "shots_on_against": row.get("HST"),
            "yellows": row.get("AY"), "reds": row.get("AR"),
            "points": _ftr_to_points(row["FTR"], is_home=False),
            "opponent": row["HomeTeam"],
        })

    out = rows.apply(per_match, axis=1)
    return out.sort_values("Date").reset_index(drop=True)


def _rolling_avg(series: pd.Series, n: int) -> pd.Series:
    return series.shift(1).rolling(window=n, min_periods=1).mean()


def _team_rolling_features(matches: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per-team chronological DataFrame of pre-match rolling features."""
    teams = sorted(set(matches["HomeTeam"]) | set(matches["AwayTeam"]))
    out: dict[str, pd.DataFrame] = {}
    for team in teams:
        hist = _team_match_history(matches, team)
        hist["ppm_5"] = _rolling_avg(hist["points"], ROLLING_N)
        hist["gf_5"] = _rolling_avg(hist["gf"], ROLLING_N)
        hist["ga_5"] = _rolling_avg(hist["ga"], ROLLING_N)
        hist["gd_5"] = hist["gf_5"] - hist["ga_5"]
        hist["shots_for_5"] = _rolling_avg(hist["shots_for"], ROLLING_N)
        hist["shots_on_for_5"] = _rolling_avg(hist["shots_on_for"], ROLLING_N)
        hist["yellows_5"] = _rolling_avg(hist["yellows"], ROLLING_N)
        hist["home_points"] = hist.apply(lambda r: r["points"] if r["is_home"] else np.nan, axis=1)
        hist["away_points"] = hist.apply(lambda r: r["points"] if not r["is_home"] else np.nan, axis=1)
        hist["home_ppm_5"] = hist["home_points"].shift(1).rolling(window=ROLLING_N, min_periods=1).mean()
        hist["away_ppm_5"] = hist["away_points"].shift(1).rolling(window=ROLLING_N, min_periods=1).mean()
        hist["days_since_last"] = hist["Date"].diff().dt.days
        out[team] = hist
    return out


def _h2h(matches: pd.DataFrame, home: str, away: str, before: pd.Timestamp, n: int = 5) -> tuple[float, float]:
    h2h_mask = (
        (((matches["HomeTeam"] == home) & (matches["AwayTeam"] == away)) |
         ((matches["HomeTeam"] == away) & (matches["AwayTeam"] == home))) &
        (matches["Date"] < before)
    )
    prev = matches[h2h_mask].sort_values("Date").tail(n)
    if prev.empty:
        return np.nan, np.nan
    home_wins = 0
    total_goals = 0
    for _, r in prev.iterrows():
        total_goals += int(r["FTHG"]) + int(r["FTAG"])
        if r["HomeTeam"] == home and r["FTR"] == "H":
            home_wins += 1
        elif r["AwayTeam"] == home and r["FTR"] == "A":
            home_wins += 1
    return home_wins / len(prev), total_goals / len(prev)


def build_features(matches: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    matches = compute_pre_match_elo(matches)
    per_team = _team_rolling_features(matches)

    def latest_for_team(team: str, before: pd.Timestamp) -> dict:
        hist = per_team[team]
        prior = hist[hist["Date"] < before]
        if prior.empty:
            return {
                "ppm_5": np.nan, "gf_5": np.nan, "ga_5": np.nan, "gd_5": np.nan,
                "shots_for_5": np.nan, "shots_on_for_5": np.nan,
                "yellows_5": np.nan,
                "home_ppm_5": np.nan, "away_ppm_5": np.nan,
                "days_since_last": np.nan,
            }
        last = prior.iloc[-1]
        return {
            "ppm_5": last["ppm_5"],
            "gf_5": last["gf_5"],
            "ga_5": last["ga_5"],
            "gd_5": last["gd_5"],
            "shots_for_5": last["shots_for_5"],
            "shots_on_for_5": last["shots_on_for_5"],
            "yellows_5": last["yellows_5"],
            "home_ppm_5": last["home_ppm_5"],
            "away_ppm_5": last["away_ppm_5"],
            "days_since_last": (before - last["Date"]).days,
        }

    feature_rows: list[dict] = []
    for _, row in matches.iterrows():
        home, away, when = row["HomeTeam"], row["AwayTeam"], row["Date"]
        h = latest_for_team(home, when)
        a = latest_for_team(away, when)
        h2h_wr, h2h_g = _h2h(matches, home, away, when)
        feature_rows.append({
            "elo_home_pre": row["elo_home_pre"],
            "elo_away_pre": row["elo_away_pre"],
            "elo_delta": row["elo_delta"],
            "days_rest_home": h["days_since_last"],
            "days_rest_away": a["days_since_last"],
            "days_rest_delta": (h["days_since_last"] or 0) - (a["days_since_last"] or 0),
            "home_ppm_5": h["ppm_5"], "away_ppm_5": a["ppm_5"],
            "home_gd_5":  h["gd_5"],  "away_gd_5":  a["gd_5"],
            "home_gf_5":  h["gf_5"],  "away_gf_5":  a["gf_5"],
            "home_ga_5":  h["ga_5"],  "away_ga_5":  a["ga_5"],
            "home_shots_for_5":      h["shots_for_5"],     "away_shots_for_5":      a["shots_for_5"],
            "home_shots_on_target_5":h["shots_on_for_5"],  "away_shots_on_target_5":a["shots_on_for_5"],
            "home_home_ppm_5": h["home_ppm_5"],
            "away_away_ppm_5": a["away_ppm_5"],
            "h2h_home_winrate_5": h2h_wr,
            "h2h_avg_goals_5": h2h_g,
            "home_yellows_5": h["yellows_5"],
            "away_yellows_5": a["yellows_5"],
        })

    X = pd.DataFrame(feature_rows).astype(float)
    y = matches["FTR"].astype(str)
    return X, y, matches


def feature_names() -> list[str]:
    return [f.name for f in FEATURE_SPECS]


def feature_descriptions() -> dict[str, str]:
    return {f.name: f.description for f in FEATURE_SPECS}
