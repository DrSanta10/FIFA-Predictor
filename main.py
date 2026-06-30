#!/usr/bin/env python3
"""
main.py
-------
Command-line entry point for the World Cup 2026 Match Outcome Prediction
System.

Typical daily workflow:

    python main.py update          # pull latest results, recompute everything, save outputs
    python main.py standings       # show current group tables
    python main.py predict         # show predictions for every remaining match
    python main.py simulate        # Monte Carlo group-stage qualification odds
    python main.py ratings         # show current Elo power rankings

If a match was played today but the upstream dataset hasn't caught up
yet, record it yourself so predictions stay current:

    python main.py add-result "Mexico" "Czech Republic" 2 1 --date 2026-06-24
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent))
import config
from src import data_loader, groups, tracking
from src.bracket import simulate_knockout
from src.dashboard import run_dashboard
from src.predictor import Predictor


def cmd_update(args: argparse.Namespace) -> None:
    print("Downloading latest results dataset...")
    try:
        data_loader.download_dataset()
        print(f"  Saved to {config.RESULTS_CSV}")
    except Exception as exc:  # noqa: BLE001 - we want to keep going on a cached copy
        print(f"  Download failed ({exc}); using cached copy if available.")

    df = data_loader.load_results()
    predictor = Predictor(df)
    predictor.engine.save()

    preds = predictor.predict_remaining_matches()
    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    preds.to_csv(config.PREDICTIONS_FILE, index=False)

    table = groups.compute_standings(predictor.wc_df, predictor.groups)
    table.to_csv(config.GROUP_TABLES_FILE, index=False)

    try:
        bracket_odds = simulate_knockout(predictor)
        bracket_odds.to_csv(config.BRACKET_ODDS_FILE, index=False)
        print(f"Knockout bracket odds saved to {config.BRACKET_ODDS_FILE}")
    except Exception as exc:  # noqa: BLE001 - bracket is tournament-specific; don't break `update` if it errors
        print(f"  Knockout bracket simulation skipped ({exc}).")

    n_logged = tracking.log_predictions(predictor)
    track_result = tracking.update_outcomes(predictor)
    print(f"Prediction tracking: logged {n_logged} new match(es), "
          f"resolved {track_result['newly_resolved']} since last update"
          + (f", {track_result['pending_shootout']} awaiting shootout info"
             if track_result["pending_shootout"] else "") + ".")

    played, unplayed = data_loader.split_played_unplayed(predictor.wc_df)
    print(f"\nWorld Cup {config.TOURNAMENT_YEAR}: {len(played)} played, {len(unplayed)} remaining.")
    print(f"Elo ratings saved to {config.ELO_RATINGS_FILE}")
    print(f"Predictions saved to {config.PREDICTIONS_FILE} ({len(preds)} matches)")
    print(f"Group tables saved to {config.GROUP_TABLES_FILE}")
    print("\nRun `python main.py predict` or `python main.py standings` to view them.")


def cmd_predict(args: argparse.Namespace) -> None:
    df = data_loader.load_results()
    predictor = Predictor(df)
    preds = predictor.predict_remaining_matches()

    if preds.empty:
        print("No unplayed World Cup matches currently in the dataset.")
        return

    print(f"Predictions for {len(preds)} remaining match(es):\n")
    for r in preds.itertuples(index=False):
        tag = " [knockout]" if r.is_knockout else ""
        print(f"{r.date}  {r.home_team:<22} vs {r.away_team:<22}  "
              f"H {r.home_win_prob:.0%} / D {r.draw_prob:.0%} / A {r.away_win_prob:.0%}  "
              f"-> predicted: {r.predicted_winner}{tag}")

    if args.save:
        preds.to_csv(config.PREDICTIONS_FILE, index=False)
        print(f"\nSaved to {config.PREDICTIONS_FILE}")


def cmd_standings(args: argparse.Namespace) -> None:
    df = data_loader.load_results()
    wc_df = data_loader.get_tournament(df)
    grp = groups.get_groups(wc_df)
    table = groups.compute_standings(wc_df, grp)

    for letter in grp:
        sub = table[table["group"] == letter]
        print(f"\nGroup {letter}")
        print(sub[["position", "team", "played", "won", "drawn", "lost", "gd", "points"]]
              .to_string(index=False))

    if args.save:
        table.to_csv(config.GROUP_TABLES_FILE, index=False)
        print(f"\nSaved to {config.GROUP_TABLES_FILE}")


def cmd_simulate(args: argparse.Namespace) -> None:
    df = data_loader.load_results()
    predictor = Predictor(df)
    sim = predictor.simulate_group_stage(n_simulations=args.n)

    pd.set_option("display.width", 120)
    print(f"Monte Carlo group-stage simulation ({args.n:,} runs):\n")
    print(sim.to_string(index=False, float_format=lambda x: f"{x:.1%}"))


def cmd_bracket(args: argparse.Namespace) -> None:
    df = data_loader.load_results()
    predictor = Predictor(df)
    result = simulate_knockout(predictor, n_simulations=args.n)

    pd.set_option("display.width", 120)
    print(f"Knockout-stage Monte Carlo simulation ({args.n:,} runs):\n")
    print(result.to_string(index=False, float_format=lambda x: f"{x:.1%}"))

    if args.save:
        result.to_csv(config.BRACKET_ODDS_FILE, index=False)
        print(f"\nSaved to {config.BRACKET_ODDS_FILE}")


def cmd_ratings(args: argparse.Namespace) -> None:
    df = data_loader.load_results()
    predictor = Predictor(df)
    print(f"Top {args.n} teams by current Elo rating:\n")
    for i, (team, rating) in enumerate(predictor.engine.top(args.n), start=1):
        print(f"{i:>3}. {team:<25} {rating:.1f}")


def cmd_accuracy(args: argparse.Namespace) -> None:
    log = tracking.load_log()
    if log.empty:
        print("No predictions logged yet -- run `python main.py update` first.")
        return

    summary = tracking.accuracy_summary(log)
    pd.set_option("display.width", 120)
    print("Prediction accuracy so far:\n")
    print(summary.to_string(index=False, formatters={
        "accuracy": lambda x: f"{x:.1%}" if pd.notna(x) else "n/a",
        "mean_brier_score": lambda x: f"{x:.3f}" if pd.notna(x) else "n/a",
    }))

    pending = log[log["notes"].fillna("").str.len() > 0]
    if not pending.empty:
        print(f"\n{len(pending)} match(es) awaiting shootout-winner info:")
        for _, row in pending.iterrows():
            print(f"  {row['home_team']} vs {row['away_team']}: {row['notes']}")

    if args.detail:
        print("\nFull log:")
        cols = ["match_date", "home_team", "away_team", "predicted_winner",
                "actual_winner", "correct", "brier_score"]
        print(log[cols].to_string(index=False))


def cmd_add_result(args: argparse.Namespace) -> None:
    data_loader.append_manual_result(
        home=args.home, away=args.away,
        home_score=args.home_score, away_score=args.away_score,
        date=args.date, neutral=args.neutral, shootout_winner=args.shootout_winner,
        city=args.city or "", country=args.country or "",
    )
    print(f"Recorded: {args.date}  {args.home} {args.home_score} - {args.away_score} {args.away}")
    if args.shootout_winner:
        print(f"  Shootout winner: {args.shootout_winner}")
    elif args.home_score == args.away_score:
        print("  Note: scores are level and no --shootout-winner was given. If this was a "
              "knockout match decided by penalties, re-run with --shootout-winner TeamName "
              "so accuracy tracking can record who actually advanced.")
    print("Re-run `python main.py update` to fold this into ratings and predictions.")


def cmd_dashboard(args: argparse.Namespace) -> None:
    try:
        run_dashboard(n_simulations=args.n, pred_limit=args.limit, watch=args.watch)
    except FileNotFoundError:
        print("No data downloaded yet -- run `python main.py update` first, then try the dashboard again.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="World Cup 2026 Match Outcome Prediction System"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_update = sub.add_parser("update", help="Refresh data, ratings, and predictions (run daily)")
    p_update.set_defaults(func=cmd_update)

    p_predict = sub.add_parser("predict", help="Show predictions for every remaining match")
    p_predict.add_argument("--save", action="store_true", help="Save predictions to CSV")
    p_predict.set_defaults(func=cmd_predict)

    p_standings = sub.add_parser("standings", help="Show current group standings")
    p_standings.add_argument("--save", action="store_true", help="Save standings to CSV")
    p_standings.set_defaults(func=cmd_standings)

    p_sim = sub.add_parser("simulate", help="Monte Carlo group-stage qualification odds")
    p_sim.add_argument("--n", type=int, default=10_000, help="Number of simulations")
    p_sim.set_defaults(func=cmd_simulate)

    p_bracket = sub.add_parser("bracket", help="Monte Carlo knockout-stage odds (Round of 32 -> Final)")
    p_bracket.add_argument("--n", type=int, default=10_000, help="Number of simulations")
    p_bracket.add_argument("--save", action="store_true", help="Save odds to CSV")
    p_bracket.set_defaults(func=cmd_bracket)

    p_ratings = sub.add_parser("ratings", help="Show current Elo power rankings")
    p_ratings.add_argument("--n", type=int, default=20, help="Number of teams to show")
    p_ratings.set_defaults(func=cmd_ratings)

    p_accuracy = sub.add_parser("accuracy", help="Show prediction accuracy tracked over time")
    p_accuracy.add_argument("--detail", action="store_true", help="List every logged match")
    p_accuracy.set_defaults(func=cmd_accuracy)

    p_dash = sub.add_parser("dashboard", help="Single-screen overview: rankings, odds, predictions, accuracy")
    p_dash.add_argument("--n", type=int, default=10_000, help="Number of bracket simulations")
    p_dash.add_argument("--limit", type=int, default=15, help="Max rows in the predictions table")
    p_dash.add_argument("--watch", type=int, default=None, metavar="SECONDS",
                         help="Re-render every SECONDS (Ctrl+C to stop). Default: render once and exit.")
    p_dash.set_defaults(func=cmd_dashboard)

    p_add = sub.add_parser("add-result", help="Manually record a result not yet in the dataset")
    p_add.add_argument("home", help="Home team name (must match dataset spelling)")
    p_add.add_argument("away", help="Away team name (must match dataset spelling)")
    p_add.add_argument("home_score", type=int)
    p_add.add_argument("away_score", type=int)
    p_add.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD, default today")
    p_add.add_argument("--city", default=None)
    p_add.add_argument("--country", default=None)
    p_add.add_argument("--neutral", type=lambda s: s.lower() != "false", default=True,
                        help="True/False - was it a neutral venue? Default True.")
    p_add.add_argument("--shootout-winner", default=None,
                        help="For a knockout match level after 90 minutes: which team "
                             "actually advanced on penalties (the dataset records the "
                             "score as a draw either way -- see README).")
    p_add.set_defaults(func=cmd_add_result)

    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
