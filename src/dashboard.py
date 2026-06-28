"""
dashboard.py
------------
A single-screen, colour-coded terminal dashboard pulling together
everything else in this system: current tournament stage, Elo power
rankings, title odds, predictions for every remaining match, and
prediction accuracy -- all in one readable view.

Built with `rich` rather than a full TUI framework (textual) -- this is
a "compute once, render, print, exit" dashboard like every other
command in this CLI, not an interactive app, which keeps it simple and
predictable. An optional --watch mode re-renders on a timer for a
lightweight "leave it running on a second monitor" view, since a full
pipeline run (Elo + outcome model + a 10k-run bracket simulation) takes
about a second -- cheap enough to repeat on an interval.

Note: this command is read-only except for the prediction-accuracy log
(it opportunistically calls tracking.log_predictions /
update_outcomes so the log stays fresh whenever you look at the
dashboard). It does NOT re-download the dataset or rewrite
data/processed/*.csv -- that's still `python main.py update`'s job.
Run `update` first, then `dashboard` to view it.
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd
from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from src import data_loader, tracking
from src.bracket import ROUND_NAMES, simulate_knockout
from src.predictor import Predictor

# Order rounds chronologically so describe_stage can walk through them
# cumulatively. Matches the round names bracket.py already uses.
ROUND_ORDER = ["Round of 32", "Round of 16", "Quarter-final", "Semi-final",
               "Third-Place Play-off", "Final"]


def describe_stage(predictor: Predictor) -> str:
    """Human label for where the tournament currently stands, derived
    purely from how many matches have been played -- no hardcoded match
    counts, so it stays correct even if the bracket structure changes."""
    played, _ = data_loader.split_played_unplayed(predictor.wc_df)
    n_played = len(played)

    if n_played < config.GROUP_STAGE_MATCH_COUNT:
        return "Group Stage"

    n_knockout_played = n_played - config.GROUP_STAGE_MATCH_COUNT
    matches_per_round = Counter(ROUND_NAMES.values())

    cumulative = 0
    for round_name in ROUND_ORDER:
        cumulative += matches_per_round.get(round_name, 0)
        if n_knockout_played < cumulative:
            return round_name
    return "Tournament Complete"


def _pct(x: float) -> str:
    return f"{x:.0%}"


def build_header(predictor: Predictor) -> Panel:
    played, unplayed = data_loader.split_played_unplayed(predictor.wc_df)
    stage = describe_stage(predictor)
    now = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M")
    text = (
        f"[bold]FIFA World Cup {config.TOURNAMENT_YEAR}[/bold] -- Match Prediction Dashboard\n"
        f"Stage: [bold cyan]{stage}[/bold cyan]   "
        f"Played: [green]{len(played)}[/green]   "
        f"Remaining: [yellow]{len(unplayed)}[/yellow]   "
        f"Last rendered: {now}"
    )
    return Panel(text, box=box.ROUNDED, border_style="cyan")


def build_ratings_table(predictor: Predictor, n: int = 10) -> Table:
    table = Table(title=f"Top {n} Elo Power Rankings", box=box.SIMPLE_HEAVY, title_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Team")
    table.add_column("Elo", justify="right")
    for i, (team, rating) in enumerate(predictor.engine.top(n), start=1):
        table.add_row(str(i), team, f"{rating:.0f}")
    return table


def build_title_odds_table(bracket_df: pd.DataFrame, n: int = 10) -> Table:
    table = Table(title="Title Odds (Monte Carlo)", box=box.SIMPLE_HEAVY, title_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Team")
    table.add_column("Win Title", justify="right")
    table.add_column("")

    if bracket_df.empty:
        table.add_row("--", "Knockout stage not available yet", "", "")
        return table

    top = bracket_df.head(n)
    max_p = top["p_win_title"].max() or 1
    for i, row in enumerate(top.itertuples(index=False), start=1):
        bar_len = int(round((row.p_win_title / max_p) * 20))
        bar = "[green]" + "\u2588" * bar_len + "[/green]" + "\u2591" * (20 - bar_len)
        table.add_row(str(i), row.team, _pct(row.p_win_title), bar)
    return table


def build_predictions_table(predictor: Predictor, limit: int = 15) -> tuple[Table, int]:
    """Returns (table, n_omitted) -- n_omitted is how many additional
    unshown matches there are, so the caller can add a footer note."""
    preds = predictor.predict_remaining_matches()
    table = Table(title="Predictions -- Remaining Matches", box=box.SIMPLE_HEAVY, title_style="bold")
    table.add_column("Date", no_wrap=True)
    table.add_column("Home")
    table.add_column("Away")
    table.add_column("H", justify="right")
    table.add_column("D", justify="right")
    table.add_column("A", justify="right")
    table.add_column("Predicted", no_wrap=True)
    table.add_column("Stage", justify="center", no_wrap=True)

    if preds.empty:
        table.add_row("--", "No unplayed matches in the dataset", "", "", "", "", "", "")
        return table, 0

    shown = preds.head(limit)
    for r in shown.itertuples(index=False):
        stage_tag = "[dim]KO[/dim]" if r.is_knockout else "GRP"
        table.add_row(
            r.date, r.home_team, r.away_team,
            _pct(r.home_win_prob), _pct(r.draw_prob), _pct(r.away_win_prob),
            f"[bold green]{r.predicted_winner}[/bold green]", stage_tag,
        )
    return table, max(0, len(preds) - limit)


def build_accuracy_panel() -> Panel:
    log = tracking.load_log()
    if log.empty:
        return Panel("No predictions logged yet -- run `python main.py update`.",
                      title="Prediction Accuracy", box=box.ROUNDED, border_style="magenta")

    summary = tracking.accuracy_summary(log)
    lines = []
    for row in summary.itertuples(index=False):
        if row.n_matches == 0:
            lines.append(f"{row.slice:<12} -- no resolved matches yet")
        else:
            lines.append(
                f"{row.slice:<12} {row.n_matches:>3} matches   "
                f"accuracy {row.accuracy:.0%}   Brier {row.mean_brier_score:.3f}"
            )

    pending = log[log["notes"].fillna("").str.len() > 0]
    if not pending.empty:
        lines.append(f"\n[yellow]{len(pending)} match(es) awaiting shootout-winner info "
                      f"(see `python main.py accuracy`)[/yellow]")

    return Panel("\n".join(lines), title="Prediction Accuracy", box=box.ROUNDED, border_style="magenta")


def render(console: Console, n_simulations: int = 10_000, pred_limit: int = 15) -> None:
    df = data_loader.load_results()
    predictor = Predictor(df)

    try:
        bracket_df = simulate_knockout(predictor, n_simulations=n_simulations)
    except Exception:  # noqa: BLE001 - bracket is tournament-specific; dashboard shouldn't crash without it
        bracket_df = pd.DataFrame(columns=["team", "p_win_title"])

    # Keep the accuracy log current every time the dashboard is viewed.
    tracking.log_predictions(predictor)
    tracking.update_outcomes(predictor)

    console.print(build_header(predictor))
    console.print(Columns([build_ratings_table(predictor), build_title_odds_table(bracket_df)]))

    pred_table, n_omitted = build_predictions_table(predictor, limit=pred_limit)
    console.print(pred_table)
    if n_omitted:
        console.print(f"[dim]...and {n_omitted} more -- see `python main.py predict` for the full list.[/dim]")

    console.print(build_accuracy_panel())


def run_dashboard(n_simulations: int = 10_000, pred_limit: int = 15, watch: int | None = None) -> None:
    console = Console()
    if watch is None:
        render(console, n_simulations, pred_limit)
        return

    try:
        while True:
            console.clear()
            render(console, n_simulations, pred_limit)
            console.print(f"\n[dim]Refreshing every {watch}s -- Ctrl+C to stop.[/dim]")
            time.sleep(watch)
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")


if __name__ == "__main__":
    run_dashboard()
