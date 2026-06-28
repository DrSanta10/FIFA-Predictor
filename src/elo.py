"""
elo.py
------
A classic "World Football Elo" rating engine, following the methodology
popularised by eloratings.net:

  * every team starts at BASE_RATING (1500)
  * after each match, ratings move based on (a) whether the result was
    better/worse than expected given the pre-match rating gap, and
    (b) how big the winning margin was
  * the size of the move is scaled by a K-factor reflecting how
    important the competition is (World Cup finals move ratings more
    than a friendly)
  * a home-advantage bonus is added to the home side's rating when the
    match isn't at a neutral venue

Running `update_ratings_from_history()` walks the *entire* match history
in chronological order, so by the time it reaches today every team's
Elo rating reflects its actual long-run + recent international form.
Along the way it also records each match's pre-match rating gap and
actual result -- that's the training data `outcome_model.py` uses to
turn a rating gap into a calibrated win/draw/loss probability.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config


def classify_tournament(tournament: str) -> str:
    """Map a free-text tournament name to a K-factor bucket."""
    for substring, bucket in config.TOURNAMENT_CLASSIFICATION:
        if substring.lower() in tournament.lower():
            return bucket
    return "friendly"


def goal_diff_multiplier(goal_diff: int) -> float:
    """Elo's "G" factor: bigger wins move the rating more, with
    diminishing returns past a 3-goal margin."""
    diff = abs(goal_diff)
    if diff <= 1:
        return 1.0
    if diff == 2:
        return 1.5
    return (11 + diff) / 8


def win_expectancy(rating_diff: float) -> float:
    """Standard Elo expected-score formula. rating_diff is
    (rating_A + home_adv_if_any) - rating_B."""
    return 1.0 / (10 ** (-rating_diff / 400) + 1)


class EloEngine:
    def __init__(self, base_rating: float = config.BASE_RATING,
                 home_advantage: float = config.HOME_ADVANTAGE):
        self.base_rating = base_rating
        self.home_advantage = home_advantage
        self.ratings: dict[str, float] = {}
        # Training rows for the outcome model: one per completed match.
        self.training_rows: list[dict] = []

    def get_rating(self, team: str) -> float:
        return self.ratings.get(team, self.base_rating)

    def update_ratings_from_history(self, df: pd.DataFrame) -> "EloEngine":
        """Process every played match in `df`, in chronological order,
        updating self.ratings and self.training_rows as it goes.

        `df` should already be sorted by date ascending (data_loader does
        this). Rows with missing scores (future fixtures) are skipped.
        """
        for row in df.itertuples(index=False):
            if pd.isna(row.home_score) or pd.isna(row.away_score):
                continue
            self._process_match(
                home=row.home_team,
                away=row.away_team,
                home_score=int(row.home_score),
                away_score=int(row.away_score),
                tournament=row.tournament,
                neutral=bool(row.neutral),
                date=row.date,
            )
        return self

    def _process_match(self, home: str, away: str, home_score: int,
                        away_score: int, tournament: str, neutral: bool,
                        date) -> None:
        home_rating = self.get_rating(home)
        away_rating = self.get_rating(away)

        home_adv = 0 if neutral else self.home_advantage
        rating_diff = (home_rating + home_adv) - away_rating

        we_home = win_expectancy(rating_diff)
        we_away = 1 - we_home

        if home_score > away_score:
            w_home, w_away, outcome = 1.0, 0.0, "H"
        elif home_score < away_score:
            w_home, w_away, outcome = 0.0, 1.0, "A"
        else:
            w_home, w_away, outcome = 0.5, 0.5, "D"

        # Record the training example BEFORE we mutate the ratings, since
        # the model needs to learn from the rating gap as it stood going
        # into the match.
        self.training_rows.append({
            "date": date,
            "home_team": home,
            "away_team": away,
            "elo_diff": rating_diff,
            "neutral": neutral,
            "outcome": outcome,
            "tournament": tournament,
        })

        k = config.K_FACTORS[classify_tournament(tournament)]
        g = goal_diff_multiplier(home_score - away_score)

        self.ratings[home] = home_rating + k * g * (w_home - we_home)
        self.ratings[away] = away_rating + k * g * (w_away - we_away)

    def get_training_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.training_rows)

    def save(self, path: Path = config.ELO_RATINGS_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        ordered = dict(sorted(self.ratings.items(), key=lambda kv: -kv[1]))
        path.write_text(json.dumps(ordered, indent=2))

    def top(self, n: int = 20) -> list[tuple[str, float]]:
        return sorted(self.ratings.items(), key=lambda kv: -kv[1])[:n]


if __name__ == "__main__":
    import data_loader

    df = data_loader.load_results()
    engine = EloEngine().update_ratings_from_history(df)
    engine.save()
    print(f"Computed Elo ratings for {len(engine.ratings)} teams.")
    print(f"Training examples collected: {len(engine.training_rows):,}")
    print("\nTop 20 teams by current Elo rating:")
    for i, (team, rating) in enumerate(engine.top(20), start=1):
        print(f"{i:>2}. {team:<25} {rating:.1f}")
