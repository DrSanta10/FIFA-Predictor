"""
tracking.py
------------
Answers "how good are these predictions, actually?" by keeping a
permanent log of every prediction this system has ever made for a World
Cup 2026 match, and reconciling it against real results as they come in.

Two-phase design, both driven by `python main.py update`:

  1. log_predictions() -- the FIRST time a fixture shows up as unplayed,
     its prediction is written to the log and locked in. Re-running
     `update` the next day does NOT overwrite it, even though the
     model's Elo ratings (and therefore its predictions) keep moving --
     we want to know how good a same-day forecast was, not grade
     ourselves on whichever prediction happened to be made closest to
     kickoff. This is a deliberate choice; see README.

  2. update_outcomes() -- for every logged match that's since been
     played, fills in what actually happened and whether the locked-in
     prediction was right, plus a Brier score (lower = better-calibrated
     probabilities, not just a better top pick).

Penalty shootouts are the one wrinkle: the upstream dataset records a
shootout-decided knockout match as a plain draw with no indication of
who actually advanced (see data_loader.load_results). Those matches are
left unresolved in the log -- excluded from accuracy stats, with a note
-- until you record the actual winner via
`main.py add-result ... --shootout-winner TeamName`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config

LOG_COLUMNS = [
    "date_logged", "match_date", "home_team", "away_team", "is_knockout",
    "elo_home", "elo_away", "home_win_prob", "draw_prob", "away_win_prob",
    "predicted_winner", "actual_outcome", "actual_winner", "correct",
    "brier_score", "notes",
]

# Pending/unresolved cells use "" (empty string), consistently, rather
# than NaN. This sidesteps a real pandas gotcha: a brand-new column of
# all-NaN gets inferred as float64, and pandas then refuses to write a
# string ("H"/"A"/"Draw"/etc.) into it later in the same session. Using
# "" keeps these columns as plain object/string dtype from creation all
# the way through a save/load round-trip (read with keep_default_na=False
# so an empty CSV cell comes back as "" rather than NaN again).
PENDING = ""


def _empty_log() -> pd.DataFrame:
    return pd.DataFrame(columns=LOG_COLUMNS)


def load_log() -> pd.DataFrame:
    """Load the full prediction log (empty DataFrame if none logged yet)."""
    if config.PREDICTION_LOG_FILE.exists():
        return pd.read_csv(config.PREDICTION_LOG_FILE, keep_default_na=False)
    return _empty_log()


def _save_log(log: pd.DataFrame) -> None:
    config.PREDICTION_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    log.to_csv(config.PREDICTION_LOG_FILE, index=False)


def _is_resolved(value) -> bool:
    return value != PENDING and pd.notna(value)


def log_predictions(predictor, today: str | None = None) -> int:
    """Log any currently-unplayed fixture that isn't in the log yet.
    Returns how many new rows were added."""
    today = today or pd.Timestamp.now().date().isoformat()
    log = load_log()
    existing_keys = set(zip(log["home_team"], log["away_team"])) if not log.empty else set()

    preds = predictor.predict_remaining_matches()
    new_rows = []
    for r in preds.itertuples(index=False):
        key = (r.home_team, r.away_team)
        if key in existing_keys:
            continue
        new_rows.append({
            "date_logged": today,
            "match_date": r.date,
            "home_team": r.home_team,
            "away_team": r.away_team,
            "is_knockout": r.is_knockout,
            "elo_home": r.elo_home,
            "elo_away": r.elo_away,
            "home_win_prob": r.home_win_prob,
            "draw_prob": r.draw_prob,
            "away_win_prob": r.away_win_prob,
            "predicted_winner": r.predicted_winner,
            "actual_outcome": PENDING,
            "actual_winner": PENDING,
            "correct": PENDING,
            "brier_score": PENDING,
            "notes": "",
        })

    if new_rows:
        log = pd.concat([log, pd.DataFrame(new_rows)], ignore_index=True)
        _save_log(log)
    return len(new_rows)


def update_outcomes(predictor) -> dict:
    """Resolve any logged match that's since been played.

    Returns a small summary dict: {"newly_resolved": int, "pending_shootout": int}.
    """
    log = load_log()
    if log.empty:
        return {"newly_resolved": 0, "pending_shootout": 0}

    played_lookup = {
        (row.home_team, row.away_team): row
        for row in predictor.wc_df.itertuples(index=False)
        if pd.notna(row.home_score) and pd.notna(row.away_score)
    }

    newly_resolved = 0
    pending_shootout = 0

    for idx, log_row in log.iterrows():
        if _is_resolved(log_row["actual_outcome"]):
            continue  # already resolved, leave as-is

        match = played_lookup.get((log_row["home_team"], log_row["away_team"]))
        if match is None:
            continue  # not played yet

        home_score, away_score = match.home_score, match.away_score
        is_knockout = bool(log_row["is_knockout"])

        if home_score != away_score:
            outcome = "H" if home_score > away_score else "A"
            actual_winner = log_row["home_team"] if outcome == "H" else log_row["away_team"]
        elif not is_knockout:
            outcome, actual_winner = "D", "Draw"
        else:
            # Knockout match level after 90 -- decided by penalties, but
            # the dataset doesn't record who won the shootout.
            shootout_winner = getattr(match, "shootout_winner", None)
            if pd.isna(shootout_winner) or shootout_winner == "" or shootout_winner is None:
                log.at[idx, "notes"] = (
                    "Awaiting shootout winner -- run `main.py add-result "
                    f'"{log_row["home_team"]}" "{log_row["away_team"]}" '
                    f"{int(home_score)} {int(away_score)} --shootout-winner TeamName`"
                )
                pending_shootout += 1
                continue
            outcome = "H" if shootout_winner == log_row["home_team"] else "A"
            actual_winner = shootout_winner

        log.at[idx, "actual_outcome"] = outcome
        log.at[idx, "actual_winner"] = str(actual_winner)
        log.at[idx, "correct"] = str(int(actual_winner == log_row["predicted_winner"]))
        log.at[idx, "brier_score"] = str(round(_brier_score(log_row, outcome, is_knockout), 6))
        log.at[idx, "notes"] = ""
        newly_resolved += 1

    _save_log(log)
    return {"newly_resolved": newly_resolved, "pending_shootout": pending_shootout}


def _brier_score(log_row: pd.Series, outcome: str, is_knockout: bool) -> float:
    """Lower is better (0 = perfect certainty in the right outcome).

    Group matches: standard 3-way Brier score against H/D/A.
    Knockout matches: a draw isn't a real final outcome, so the 3-way
    probabilities are collapsed to a 2-way "did the home team advance?"
    probability (home_win_prob + half of draw_prob) before scoring --
    consistent with how the predicted_winner itself was chosen for
    knockout matches (see Predictor.predict_match).
    """
    p_h, p_d, p_a = float(log_row["home_win_prob"]), float(log_row["draw_prob"]), float(log_row["away_win_prob"])
    if not is_knockout:
        return (p_h - (1.0 if outcome == "H" else 0.0)) ** 2 \
             + (p_d - (1.0 if outcome == "D" else 0.0)) ** 2 \
             + (p_a - (1.0 if outcome == "A" else 0.0)) ** 2

    p_home_advances = p_h + 0.5 * p_d
    p_away_advances = p_a + 0.5 * p_d
    return (p_home_advances - (1.0 if outcome == "H" else 0.0)) ** 2 \
         + (p_away_advances - (1.0 if outcome == "A" else 0.0)) ** 2


def accuracy_summary(log: pd.DataFrame | None = None) -> pd.DataFrame:
    """One row per slice (Overall / Group stage / Knockout) with match
    count, accuracy, and mean Brier score, computed only over resolved
    matches (unresolved/pending-shootout rows are excluded)."""
    if log is None:
        log = load_log()
    resolved = log[log["actual_outcome"].apply(_is_resolved)].copy()

    def _row(label: str, subset: pd.DataFrame) -> dict:
        if subset.empty:
            return {"slice": label, "n_matches": 0, "accuracy": float("nan"), "mean_brier_score": float("nan")}
        return {
            "slice": label,
            "n_matches": len(subset),
            "accuracy": subset["correct"].astype(int).mean(),
            "mean_brier_score": subset["brier_score"].astype(float).mean(),
        }

    is_ko = resolved["is_knockout"].astype(str).isin(["True", "true", "1"])
    rows = [
        _row("Overall", resolved),
        _row("Group stage", resolved[~is_ko]),
        _row("Knockout", resolved[is_ko]),
    ]
    return pd.DataFrame(rows)


if __name__ == "__main__":
    from src import data_loader
    from src.predictor import Predictor

    df = data_loader.load_results()
    predictor = Predictor(df)

    n_new = log_predictions(predictor)
    result = update_outcomes(predictor)
    print(f"Logged {n_new} new prediction(s). "
          f"Resolved {result['newly_resolved']} match(es) this run "
          f"({result['pending_shootout']} pending shootout info).")

    print("\nAccuracy so far:")
    pd.set_option("display.width", 120)
    summary = accuracy_summary()
    print(summary.to_string(index=False, formatters={
        "accuracy": lambda x: f"{x:.1%}" if pd.notna(x) else "n/a",
        "mean_brier_score": lambda x: f"{x:.3f}" if pd.notna(x) else "n/a",
    }))
