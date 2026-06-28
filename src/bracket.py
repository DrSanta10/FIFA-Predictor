"""
bracket.py
----------
The actual, official 2026 World Cup knockout bracket (Round of 32 through
the Final), hardcoded from FIFA's published schedule now that the Round
of 32 draw is confirmed.

Why hardcoded rather than derived like groups.py: which third-placed
team lands in which Round of 32 slot depends on FIFA's "Annex C"
combination table (495 possible permutations), which only resolves into
concrete fixtures once the final group standings are known. Reproducing
that table from scratch would be guesswork; instead, this takes the
now-confirmed real fixtures and the official match-numbering scheme
(cross-checked against three independent published sources: the
official FIFA schedule, ESPN's bracket page, and Sky Sports' match list
-- all three agree) and chains a single-elimination Monte Carlo
simulation forward from there through to the Final.

If you're adapting this system for a different tournament, BRACKET below
is the one thing you'd need to replace -- `simulate_knockout` itself is
generic to any single-elimination bracket.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

# Match ID -> ("teams", (team_a, team_b))      for a confirmed Round of 32 fixture
#          -> ("winners_of", (match_id_a, match_id_b))  for every later round,
#             meaning "whoever wins match_id_a plays whoever wins match_id_b"
#
# FIFA's own match numbering already encodes the dependency order, so
# match IDs increase monotonically through the rounds.
BRACKET = {
    # --- Round of 32 (June 28 - July 4) ---
    73: ("teams", ("South Africa", "Canada")),
    74: ("teams", ("Germany", "Paraguay")),
    75: ("teams", ("Netherlands", "Morocco")),
    76: ("teams", ("Brazil", "Japan")),
    77: ("teams", ("France", "Sweden")),
    78: ("teams", ("Ivory Coast", "Norway")),
    79: ("teams", ("Mexico", "Ecuador")),
    80: ("teams", ("England", "DR Congo")),
    81: ("teams", ("United States", "Bosnia and Herzegovina")),
    82: ("teams", ("Belgium", "Senegal")),
    83: ("teams", ("Portugal", "Croatia")),
    84: ("teams", ("Spain", "Austria")),
    85: ("teams", ("Switzerland", "Algeria")),
    86: ("teams", ("Argentina", "Cape Verde")),
    87: ("teams", ("Colombia", "Ghana")),
    88: ("teams", ("Australia", "Egypt")),
    # --- Round of 16 (July 4-7) ---
    89: ("winners_of", (74, 77)),
    90: ("winners_of", (73, 75)),
    91: ("winners_of", (76, 78)),
    92: ("winners_of", (79, 80)),
    93: ("winners_of", (83, 84)),
    94: ("winners_of", (81, 82)),
    95: ("winners_of", (86, 88)),
    96: ("winners_of", (85, 87)),
    # --- Quarter-finals (July 9-12) ---
    97: ("winners_of", (89, 90)),
    98: ("winners_of", (93, 94)),
    99: ("winners_of", (91, 92)),
    100: ("winners_of", (95, 96)),
    # --- Semi-finals (July 14-15) ---
    101: ("winners_of", (97, 98)),
    102: ("winners_of", (99, 100)),
    # --- Third-place play-off (July 18) ---
    # The two semi-final LOSERS play each other -- the only match in the
    # bracket keyed off losers rather than winners.
    103: ("losers_of", (101, 102)),
    # --- Final (July 19) ---
    104: ("winners_of", (101, 102)),
}

ROUND_NAMES = {
    **{i: "Round of 32" for i in range(73, 89)},
    **{i: "Round of 16" for i in range(89, 97)},
    **{i: "Quarter-final" for i in range(97, 101)},
    **{i: "Semi-final" for i in range(101, 103)},
    103: "Third-Place Play-off",
    104: "Final",
}

# A match can only be resolved once both feeder matches are resolved.
# FIFA's numbering already increases in dependency order, so a simple
# sort is sufficient.
MATCH_ORDER = sorted(BRACKET)


def simulate_knockout(predictor, n_simulations: int = 10_000, seed: int = 7) -> pd.DataFrame:
    """Monte Carlo simulation of the entire knockout bracket, including
    the third-place play-off.

    For each simulation, walks every match in MATCH_ORDER, resolves the
    two teams involved (the confirmed Round of 32 pair, the winners of
    the two feeder matches, or -- for the third-place play-off -- the
    LOSERS of the two semi-finals), samples a winner using the model's
    no-draw win probability (extra time / penalties treated as a coin
    flip -- see OutcomeModel.win_probability_no_draw), and records which
    round each team reached.

    Returns one row per team still in the competition, with the
    fraction of simulations in which they reached the Round of 16,
    Quarter-finals, Semi-finals, the Final, finished third, and won the
    title outright.
    """
    rng = np.random.default_rng(seed)

    # Cache win probabilities per matchup -- cheap, and avoids recomputing
    # the same Elo lookup thousands of times inside the simulation loop.
    prob_cache: dict[tuple[str, str], float] = {}

    def p_team_a_wins(team_a: str, team_b: str) -> float:
        key = (team_a, team_b)
        if key not in prob_cache:
            elo_a = predictor.engine.get_rating(team_a)
            elo_b = predictor.engine.get_rating(team_b)
            elo_diff = elo_a - elo_b  # knockout matches are at designated/neutral venues
            prob_cache[key] = predictor.model.win_probability_no_draw(elo_diff, neutral=True)
        return prob_cache[key]

    # team -> round name -> number of simulations in which the team played
    # (i.e. reached) that round.
    stage_reached: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    champion_count: dict[str, int] = defaultdict(int)
    third_place_count: dict[str, int] = defaultdict(int)

    for _ in range(n_simulations):
        winners: dict[int, str] = {}
        losers: dict[int, str] = {}
        for match_id in MATCH_ORDER:
            kind, payload = BRACKET[match_id]
            if kind == "teams":
                team_a, team_b = payload
            elif kind == "winners_of":
                feeder_a, feeder_b = payload
                team_a, team_b = winners[feeder_a], winners[feeder_b]
            else:  # "losers_of" -- only Match 103, the third-place play-off
                feeder_a, feeder_b = payload
                team_a, team_b = losers[feeder_a], losers[feeder_b]

            round_name = ROUND_NAMES[match_id]
            stage_reached[team_a][round_name] += 1
            stage_reached[team_b][round_name] += 1

            winner = team_a if rng.random() < p_team_a_wins(team_a, team_b) else team_b
            loser = team_b if winner == team_a else team_a
            winners[match_id] = winner
            losers[match_id] = loser

        champion_count[winners[104]] += 1
        third_place_count[winners[103]] += 1

    rows = []
    for team in stage_reached:
        rows.append({
            "team": team,
            "p_reach_r16": stage_reached[team]["Round of 16"] / n_simulations,
            "p_reach_qf": stage_reached[team]["Quarter-final"] / n_simulations,
            "p_reach_sf": stage_reached[team]["Semi-final"] / n_simulations,
            "p_reach_final": stage_reached[team]["Final"] / n_simulations,
            "p_third_place": third_place_count[team] / n_simulations,
            "p_win_title": champion_count[team] / n_simulations,
        })

    return (
        pd.DataFrame(rows)
        .sort_values("p_win_title", ascending=False)
        .reset_index(drop=True)
    )


if __name__ == "__main__":
    from src import data_loader
    from src.predictor import Predictor

    df = data_loader.load_results()
    predictor = Predictor(df)
    result = simulate_knockout(predictor, n_simulations=10_000)

    pd.set_option("display.width", 120)
    print("Knockout-stage Monte Carlo (10,000 simulations):\n")
    print(result.to_string(index=False, float_format=lambda x: f"{x:.1%}"))
