"""
outcome_model.py
-----------------
Elo gives us a single number (the rating gap) that summarises how much
better one team is than another. This module turns that number into
calibrated probabilities -- P(home win), P(draw), P(away win) -- by
fitting a multinomial logistic regression on real historical matches:
"whenever the rating gap was about X, how often did the home team
actually win/draw/lose?"

This is deliberately a small, transparent model (2 input features) on
purpose: with a clean, theory-driven feature like Elo gap, a simple
calibrated model out-predicts a complex black-box one trained on the
relatively small number of competitive matches available, and it's
easy to sanity check.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config


class OutcomeModel:
    def __init__(self):
        self.model: LogisticRegression | None = None
        self.classes_: list[str] = []

    def fit(self, training_df: pd.DataFrame,
            start_year: int = config.MODEL_TRAINING_START_YEAR) -> "OutcomeModel":
        df = training_df.copy()
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["date"].dt.year >= start_year]

        X = df[["elo_diff"]].to_numpy()
        # Add neutral-venue flag as a second feature -- on a neutral pitch
        # the home_advantage bonus baked into elo_diff doesn't apply, so
        # letting the model see that flag lets it adjust automatically.
        X = np.hstack([X, df[["neutral"]].astype(int).to_numpy()])
        y = df["outcome"].to_numpy()

        self.model = LogisticRegression(max_iter=1000)
        self.model.fit(X, y)
        self.classes_ = list(self.model.classes_)
        return self

    def predict_proba(self, elo_diff: float, neutral: bool) -> dict[str, float]:
        """Return {'H': p, 'D': p, 'A': p} for a single matchup, where H
        means the team with rating `elo_diff` advantage wins at home (or
        is just "team A" if neutral=True)."""
        if self.model is None:
            raise RuntimeError("Call fit() before predict_proba().")
        x = np.array([[elo_diff, int(neutral)]])
        proba = self.model.predict_proba(x)[0]
        return dict(zip(self.classes_, proba))

    def win_probability_no_draw(self, elo_diff: float, neutral: bool) -> float:
        """Probability that team A (the one with `elo_diff` advantage)
        progresses in a knockout match, where a draw after 90 minutes is
        resolved by extra time / penalties.

        Simplifying assumption: a drawn 90 minutes is treated as a coin
        flip between the two sides (penalty shootouts are notoriously
        close to 50/50 regardless of the pre-match favourite). This is a
        deliberate simplification -- see README for how to refine it.
        """
        proba = self.predict_proba(elo_diff, neutral)
        return proba["H"] + 0.5 * proba["D"]


if __name__ == "__main__":
    import data_loader
    from elo import EloEngine

    df = data_loader.load_results()
    engine = EloEngine().update_ratings_from_history(df)
    training_df = engine.get_training_dataframe()

    model = OutcomeModel().fit(training_df)
    print(f"Trained on {len(training_df[pd.to_datetime(training_df['date']).dt.year >= config.MODEL_TRAINING_START_YEAR]):,} matches "
          f"from {config.MODEL_TRAINING_START_YEAR} onward.")
    print(f"Classes: {model.classes_}")

    print("\nSample predictions (positive elo_diff = team A favoured):")
    for diff in [-300, -150, -50, 0, 50, 150, 300]:
        p = model.predict_proba(diff, neutral=True)
        print(f"  elo_diff={diff:>5}  ->  A win {p['A']:.1%}   Draw {p['D']:.1%}   H win {p['H']:.1%}")
