"""
predictor.py
------------
Ties elo.py + outcome_model.py + groups.py together into the two things
this whole system exists to produce:

  1. predict_remaining_matches() -- for every unplayed World Cup 2026
     fixture currently in the data, a win/draw/loss probability and a
     single predicted winner.

  2. simulate_group_stage() -- since group outcomes are correlated
     (today's Mexico result affects who Mexico's other group rivals
     need to beat later), a single "most likely winner per match" pass
     isn't enough to answer "what's the probability Team X advances?".
     This runs a Monte Carlo simulation: replay the remaining group
     fixtures thousands of times, rolling weighted dice according to the
     model's probabilities each time, and track how often each team
     finishes top-2 (automatic Round of 32 qualification).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from src import data_loader, groups
from src.elo import EloEngine
from src.outcome_model import OutcomeModel


class Predictor:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.wc_df = data_loader.get_tournament(df)
        self.engine = EloEngine().update_ratings_from_history(df)
        self.model = OutcomeModel().fit(self.engine.get_training_dataframe())
        self.groups = groups.get_groups(self.wc_df)
        self._team_to_group = {t: g for g, teams in self.groups.items() for t in teams}

    def is_knockout_match(self, home: str, away: str) -> bool:
        """True if this fixture is a knockout match (no draw possible --
        decided by extra time / penalties if level after 90 minutes).
        Two teams are a group-stage match only if they're in the SAME
        group; anything else (including a match where one or both teams
        aren't in any group, e.g. future rounds) is treated as knockout.
        """
        g_home = self._team_to_group.get(home)
        g_away = self._team_to_group.get(away)
        return g_home is None or g_away is None or g_home != g_away

    # -- single-match prediction -------------------------------------------------

    def predict_match(self, home: str, away: str, neutral: bool = True,
                       is_knockout: bool | None = None) -> dict:
        elo_home = self.engine.get_rating(home)
        elo_away = self.engine.get_rating(away)
        home_adv = 0 if neutral else self.engine.home_advantage
        elo_diff = (elo_home + home_adv) - elo_away

        proba = self.model.predict_proba(elo_diff, neutral)

        if is_knockout is None:
            is_knockout = self.is_knockout_match(home, away)

        if is_knockout:
            # A draw isn't a real outcome here -- the match goes to extra
            # time/penalties if level after 90. Pick using the no-draw
            # win probability instead of a raw 3-way argmax, so a
            # genuinely close match doesn't get predicted as "Draw" (an
            # outcome that can't appear in the final result).
            p_home_advances = self.model.win_probability_no_draw(elo_diff, neutral)
            predicted_winner = home if p_home_advances >= 0.5 else away
        else:
            predicted = max(proba, key=proba.get)
            predicted_winner = {"H": home, "A": away, "D": "Draw"}[predicted]

        return {
            "home_team": home, "away_team": away,
            "elo_home": round(elo_home, 1), "elo_away": round(elo_away, 1),
            "home_win_prob": round(proba["H"], 4),
            "draw_prob": round(proba["D"], 4),
            "away_win_prob": round(proba["A"], 4),
            "predicted_winner": predicted_winner,
            "is_knockout": is_knockout,
        }

    def predict_remaining_matches(self) -> pd.DataFrame:
        """Predict every unplayed World Cup 2026 fixture currently in the
        dataset (group stage now; knockout rounds too, automatically,
        once they're confirmed and appear with real team names)."""
        _, unplayed = data_loader.split_played_unplayed(self.wc_df)
        rows = []
        for row in unplayed.itertuples(index=False):
            pred = self.predict_match(row.home_team, row.away_team, neutral=bool(row.neutral))
            pred["date"] = row.date.date().isoformat()
            rows.append(pred)
        cols = ["date", "home_team", "away_team", "elo_home", "elo_away",
                "home_win_prob", "draw_prob", "away_win_prob", "predicted_winner", "is_knockout"]
        return pd.DataFrame(rows)[cols] if rows else pd.DataFrame(columns=cols)

    # -- group stage Monte Carlo --------------------------------------------------

    def simulate_group_stage(self, n_simulations: int = 10_000, seed: int = 42) -> pd.DataFrame:
        """Monte Carlo simulation of the remaining group-stage matches.

        For each simulation: sample a result for every remaining fixture
        according to the model's H/D/A probabilities, add it to each
        team's current played-match record, then re-rank the group.
        Returns, per team: P(finish 1st), P(finish top 2 = auto-qualify),
        P(finish 3rd with enough points to maybe sneak in as a top-8
        third-place team -- see README on why the exact cutoff isn't
        computed here).
        """
        rng = np.random.default_rng(seed)
        remaining = groups.remaining_group_fixtures(self.wc_df, self.groups)
        base_table = groups.compute_standings(self.wc_df, self.groups)

        # Pre-compute outcome probabilities for each remaining fixture once.
        fixture_probs = []
        for row in remaining.itertuples(index=False):
            p = self.predict_match(row.home_team, row.away_team, neutral=bool(row.neutral))
            fixture_probs.append((row.home_team, row.away_team,
                                   p["home_win_prob"], p["draw_prob"], p["away_win_prob"]))

        finish_counts = {team: {"1st": 0, "2nd": 0, "3rd": 0, "4th": 0}
                          for team in base_table["team"]}

        base_stats = base_table.set_index("team")[["group", "won", "drawn", "lost", "gf", "ga", "points"]].to_dict("index")

        for _ in range(n_simulations):
            sim_stats = {t: dict(v) for t, v in base_stats.items()}

            for home, away, p_h, p_d, p_a in fixture_probs:
                probs = np.array([p_h, p_d, p_a])
                probs = probs / probs.sum()  # guard against rounding drift
                outcome = rng.choice(["H", "D", "A"], p=probs)
                # Sample a plausible scoreline consistent with the outcome
                # just for goal-difference purposes (keeps things simple:
                # 1-0 / 0-0 / 0-1 as the canonical margins).
                if outcome == "H":
                    hs, as_ = 1, 0
                    sim_stats[home]["won"] += 1; sim_stats[home]["points"] += 3
                    sim_stats[away]["lost"] += 1
                elif outcome == "A":
                    hs, as_ = 0, 1
                    sim_stats[away]["won"] += 1; sim_stats[away]["points"] += 3
                    sim_stats[home]["lost"] += 1
                else:
                    hs, as_ = 0, 0
                    sim_stats[home]["drawn"] += 1; sim_stats[home]["points"] += 1
                    sim_stats[away]["drawn"] += 1; sim_stats[away]["points"] += 1
                sim_stats[home]["gf"] += hs; sim_stats[home]["ga"] += as_
                sim_stats[away]["gf"] += as_; sim_stats[away]["ga"] += hs

            sim_df = pd.DataFrame.from_dict(sim_stats, orient="index").reset_index(names="team")
            sim_df["gd"] = sim_df["gf"] - sim_df["ga"]
            sim_df = sim_df.sort_values(
                ["group", "points", "gd", "gf"], ascending=[True, False, False, False]
            )
            sim_df["position"] = sim_df.groupby("group").cumcount() + 1

            for team, pos in zip(sim_df["team"], sim_df["position"]):
                finish_counts[team][{1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}[pos]] += 1

        rows = []
        for team, counts in finish_counts.items():
            rows.append({
                "team": team,
                "group": base_stats[team]["group"],
                "p_finish_1st": counts["1st"] / n_simulations,
                "p_finish_2nd": counts["2nd"] / n_simulations,
                "p_top2_autoqualify": (counts["1st"] + counts["2nd"]) / n_simulations,
                "p_finish_3rd": counts["3rd"] / n_simulations,
                "p_finish_4th": counts["4th"] / n_simulations,
            })
        out = pd.DataFrame(rows).sort_values(
            ["group", "p_top2_autoqualify"], ascending=[True, False]
        ).reset_index(drop=True)
        return out


if __name__ == "__main__":
    df = data_loader.load_results()
    predictor = Predictor(df)

    print("=" * 70)
    print("PREDICTIONS FOR EVERY REMAINING MATCH")
    print("=" * 70)
    preds = predictor.predict_remaining_matches()
    if preds.empty:
        print("No unplayed matches currently in the dataset.")
    else:
        for r in preds.itertuples(index=False):
            print(f"{r.date}  {r.home_team:<22} vs {r.away_team:<22}  "
                  f"H {r.home_win_prob:.0%} / D {r.draw_prob:.0%} / A {r.away_win_prob:.0%}  "
                  f"-> {r.predicted_winner}")

    print("\n" + "=" * 70)
    print("GROUP STAGE MONTE CARLO (10,000 simulations)")
    print("=" * 70)
    sim = predictor.simulate_group_stage()
    pd.set_option("display.width", 120)
    print(sim.to_string(index=False, float_format=lambda x: f"{x:.1%}"))
