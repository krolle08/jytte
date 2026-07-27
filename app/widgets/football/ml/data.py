"""Historical EPL match data loader.

Source: football-data.co.uk (free CSVs, no auth). One CSV per season.
We cache them under /data/football/raw/ so subsequent training runs do
not re-download. Each CSV has these columns we care about:

  Date HomeTeam AwayTeam FTHG FTAG FTR HTHG HTAG HTR
  HS AS HST AST HF AF HC AC HY AY HR AR Referee

Where:
  FTHG / FTAG = full-time home / away goals
  FTR         = full-time result, H / D / A
  HS / AS     = home / away total shots
  HST / AST   = shots on target
  HY / AY     = yellow cards
  HR / AR     = red cards
  HF / AF     = fouls

The columns are the same across seasons going back ~20 years.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import httpx
import pandas as pd

log = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("JYTTE_DATA_DIR", "/data")) / "football" / "raw"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# season suffix as used on football-data.co.uk URLs: e.g. 2324 = 2023-24
SEASONS = ["1920", "2021", "2122", "2223", "2324", "2425"]
LEAGUE_CODE = "E0"  # English Premier League

USEFUL_COLS = [
    "Date", "HomeTeam", "AwayTeam",
    "FTHG", "FTAG", "FTR",
    "HTHG", "HTAG", "HTR",
    "HS", "AS", "HST", "AST",
    "HF", "AF", "HC", "AC",
    "HY", "AY", "HR", "AR",
    "Referee",
]


def _csv_url(season: str) -> str:
    return f"https://www.football-data.co.uk/mmz4281/{season}/{LEAGUE_CODE}.csv"


def _csv_path(season: str) -> Path:
    return DATA_DIR / f"epl-{season}.csv"


def download_season(season: str, force: bool = False) -> Path:
    path = _csv_path(season)
    if path.exists() and not force:
        return path
    url = _csv_url(season)
    log.info("downloading %s -> %s", url, path)
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        r = client.get(url)
        r.raise_for_status()
        path.write_bytes(r.content)
    return path


def ensure_all_seasons() -> list[Path]:
    paths: list[Path] = []
    for s in SEASONS:
        try:
            paths.append(download_season(s))
        except Exception as e:
            log.warning("season %s download failed: %s", s, e)
    return paths


def load_all() -> pd.DataFrame:
    """Returns a tidy DataFrame of all available historical matches,
    sorted chronologically. Missing columns are filled with NaN so the
    feature engineer can decide how to handle them."""
    ensure_all_seasons()
    frames: list[pd.DataFrame] = []
    for season in SEASONS:
        path = _csv_path(season)
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path, encoding="latin-1")
        except Exception as e:
            log.warning("failed to read %s: %s", path, e)
            continue
        for col in USEFUL_COLS:
            if col not in df.columns:
                df[col] = pd.NA
        df = df[USEFUL_COLS].copy()
        df["season"] = season
        frames.append(df)

    if not frames:
        raise RuntimeError("no football CSVs available")

    df = pd.concat(frames, ignore_index=True)
    df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["Date", "HomeTeam", "AwayTeam", "FTR"])
    df = df.sort_values("Date").reset_index(drop=True)
    return df
