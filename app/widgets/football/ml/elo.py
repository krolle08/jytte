"""Rolling Elo ratings per team.

Elo is the simplest "team strength" feature we can give the model.
It is updated chronologically as matches are played. We use a K-factor
of 20 (a moderate update rate) and a home-field advantage of 65 Elo
points added to the home team for that match only.

The walkthrough doc explains: why Elo, what the formula means, and
the trade-offs against more sophisticated rating systems (Glicko,
TrueSkill, model-based ratings).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

import pandas as pd


INITIAL_RATING = 1500.0
K_FACTOR = 20.0
HOME_ADV = 65.0


def _expected(home_r: float, away_r: float, home_adv: float = HOME_ADV) -> float:
    return 1.0 / (1.0 + 10.0 ** (-(home_r + home_adv - away_r) / 400.0))


def _outcome_score(ftr: str) -> tuple[float, float]:
    if ftr == "H":
        return 1.0, 0.0
    if ftr == "A":
        return 0.0, 1.0
    return 0.5, 0.5


def compute_pre_match_elo(matches: pd.DataFrame) -> pd.DataFrame:
    """Returns a copy of `matches` with two new columns added:
    `elo_home_pre` and `elo_away_pre` - the Elo ratings of each team
    BEFORE the match started. Ratings then get updated after."""
    if not matches["Date"].is_monotonic_increasing:
        matches = matches.sort_values("Date").reset_index(drop=True)

    ratings: dict[str, float] = defaultdict(lambda: INITIAL_RATING)
    home_pre: list[float] = []
    away_pre: list[float] = []

    for _, row in matches.iterrows():
        h = row["HomeTeam"]
        a = row["AwayTeam"]
        rh = ratings[h]
        ra = ratings[a]
        home_pre.append(rh)
        away_pre.append(ra)

        # update with actual result for next time we see these teams
        e_home = _expected(rh, ra)
        s_home, s_away = _outcome_score(row["FTR"])
        ratings[h] = rh + K_FACTOR * (s_home - e_home)
        ratings[a] = ra + K_FACTOR * (s_away - (1.0 - e_home))

    out = matches.copy()
    out["elo_home_pre"] = home_pre
    out["elo_away_pre"] = away_pre
    out["elo_delta"] = out["elo_home_pre"] - out["elo_away_pre"]
    return out
