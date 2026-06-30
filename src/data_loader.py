"""
data_loader.py
---------------
Everything related to getting match data INTO the system as a clean
pandas DataFrame:

  * downloading the historical results dataset
  * parsing it into proper types
  * merging in any manually-entered results (for same-day matches the
    upstream dataset hasn't picked up yet)
  * convenience filters (World Cup 2026 only / played / unplayed)

This is the only module that knows about the raw CSV format, so if you
ever swap data sources, this is the only file you should need to touch.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config


def download_dataset(url: str = config.RESULTS_CSV_URL,
                      dest: Path = config.RESULTS_CSV) -> Path:
    """Download the latest snapshot of the historical results CSV.

    Returns the path written to. Raises on network failure so callers can
    decide whether to fall back to a cached copy.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_dest = dest.with_suffix(".tmp")
    req = urllib.request.Request(url, headers={"User-Agent": "fifa-predictor/1.0"})
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read()
    tmp_dest.write_bytes(data)
    tmp_dest.replace(dest)
    return dest


def load_results(path: Path = config.RESULTS_CSV) -> pd.DataFrame:
    """Load the historical results CSV into a clean, typed DataFrame.

    Columns: date (datetime64), home_team, away_team, home_score (float,
    NaN = not played yet), away_score (float), tournament, city, country,
    neutral (bool), shootout_winner (str or NaN -- see note below).

    Note on shootout_winner: the upstream dataset records a knockout
    match decided by penalties as a plain draw (e.g. the actual 2022
    final shows Argentina 3-3 France, with no indication Argentina won
    on penalties). There's no way to recover the actual winner from the
    score alone, so this column starts out empty for every row and is
    only ever populated by a manual override (`main.py add-result
    ... --shootout-winner TeamName`) for *this* tournament's matches.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python main.py update` first to "
            "download the dataset."
        )

    df = pd.read_csv(
        path,
        dtype={"home_team": str, "away_team": str, "tournament": str},
        na_values=["NA", ""],
        keep_default_na=True,
    )
    df["date"] = pd.to_datetime(df["date"])
    df["home_score"] = pd.to_numeric(df["home_score"], errors="coerce")
    df["away_score"] = pd.to_numeric(df["away_score"], errors="coerce")
    df["neutral"] = df["neutral"].astype(str).str.upper().isin(["TRUE", "1", "YES"])
    df["shootout_winner"] = pd.NA
    df = df.sort_values("date", kind="stable").reset_index(drop=True)

    df = _apply_manual_overrides(df)
    return df


def _apply_manual_overrides(df: pd.DataFrame) -> pd.DataFrame:
    """Layer in manually-entered results (see `main.py add-result`).

    Useful when a match was played today but the upstream dataset hasn't
    been refreshed yet. Manual rows are matched on (home_team, away_team,
    tournament, year) -- NOT the exact date. The fixture date in the
    dataset reflects the host venue's local calendar date, which can
    easily differ from "today" in your own timezone by a day depending
    on kickoff time, so matching on the day alone is unreliable. Team
    names + tournament + year uniquely identify a fixture within a
    single tournament edition (no team plays the same opponent twice in
    one World Cup group stage or knockout bracket), so the exact date you
    pass to `add-result` only affects cosmetic display -- it can't cause
    a duplicate or a mismatch.

    If no existing row matches, a new one is appended using the date you
    provided (this only happens for a fixture that isn't in the dataset
    at all yet, e.g. a knockout match not yet confirmed).
    """
    if not config.MANUAL_RESULTS_FILE.exists():
        return df

    manual = pd.read_csv(config.MANUAL_RESULTS_FILE, parse_dates=["date"])
    if manual.empty:
        return df
    if "shootout_winner" not in manual.columns:
        manual["shootout_winner"] = pd.NA

    for _, row in manual.iterrows():
        tournament = row.get("tournament", config.TOURNAMENT_NAME)
        mask = (
            (df["home_team"] == row["home_team"])
            & (df["away_team"] == row["away_team"])
            & (df["tournament"] == tournament)
            & (df["date"].dt.year == row["date"].year)
        )
        shootout_winner = row.get("shootout_winner")
        if pd.isna(shootout_winner) or shootout_winner == "":
            shootout_winner = pd.NA

        if mask.any():
            df.loc[mask, "home_score"] = row["home_score"]
            df.loc[mask, "away_score"] = row["away_score"]
            if not pd.isna(shootout_winner):
                df.loc[mask, "shootout_winner"] = shootout_winner
        else:
            new_row = {
                "date": row["date"],
                "home_team": row["home_team"],
                "away_team": row["away_team"],
                "home_score": row["home_score"],
                "away_score": row["away_score"],
                "tournament": tournament,
                "city": row.get("city", ""),
                "country": row.get("country", ""),
                "neutral": row.get("neutral", True),
                "shootout_winner": shootout_winner,
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    return df.sort_values("date", kind="stable").reset_index(drop=True)


def append_manual_result(home: str, away: str, home_score: int, away_score: int,
                          date: str | None = None, neutral: bool = True,
                          shootout_winner: str | None = None,
                          city: str = "", country: str = "") -> None:
    """Record a result that isn't in the upstream dataset yet (see
    `main.py add-result` for the CLI entry point -- this is the shared
    logic behind it, also used by the web GUI's "Add result" form).
    """
    from datetime import date as _date

    config.RAW_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "date": date or _date.today().isoformat(),
        "home_team": home,
        "away_team": away,
        "home_score": home_score,
        "away_score": away_score,
        "tournament": config.TOURNAMENT_NAME,
        "city": city,
        "country": country,
        "neutral": neutral,
        "shootout_winner": shootout_winner or "",
    }
    if config.MANUAL_RESULTS_FILE.exists():
        existing = pd.read_csv(config.MANUAL_RESULTS_FILE)
        if "shootout_winner" not in existing.columns:
            existing["shootout_winner"] = ""
        existing = pd.concat([existing, pd.DataFrame([row])], ignore_index=True)
    else:
        existing = pd.DataFrame([row])
    existing.to_csv(config.MANUAL_RESULTS_FILE, index=False)


def get_tournament(df: pd.DataFrame,
                    name: str = config.TOURNAMENT_NAME,
                    year: int = config.TOURNAMENT_YEAR) -> pd.DataFrame:
    """Filter down to a single tournament edition, e.g. World Cup 2026."""
    mask = (df["tournament"] == name) & (df["date"].dt.year == year)
    return df.loc[mask].reset_index(drop=True)


def split_played_unplayed(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a DataFrame into (played, unplayed) based on score presence."""
    played_mask = df["home_score"].notna() & df["away_score"].notna()
    return df.loc[played_mask].reset_index(drop=True), df.loc[~played_mask].reset_index(drop=True)


if __name__ == "__main__":
    print("Downloading latest results dataset...")
    download_dataset()
    df = load_results()
    wc = get_tournament(df)
    played, unplayed = split_played_unplayed(wc)
    print(f"Total historical matches: {len(df):,}")
    print(f"World Cup {config.TOURNAMENT_YEAR} matches so far: {len(wc)}")
    print(f"  Played:   {len(played)}")
    print(f"  Unplayed: {len(unplayed)}")
