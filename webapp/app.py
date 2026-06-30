"""
app.py
------
Flask backend for the World Cup 2026 prediction GUI. Thin by design: it
doesn't reimplement any prediction logic -- every number it serves comes
straight from the same src/ modules the CLI uses (data_loader, elo,
outcome_model, groups, bracket, tracking), so the GUI and `python main.py`
are always looking at the same engine, never two competing
implementations of "what does the model think".

Run with:
    python webapp/app.py
then open http://127.0.0.1:5000 in a browser.

Endpoints:
    GET  /                  the single-page app
    GET  /api/snapshot      everything the page needs, as one JSON payload
    POST /api/update        re-download data, recompute, save (same as `main.py update`)
    POST /api/add-result    record a manual result (same as `main.py add-result`)
    GET  /api/teams         the 48 entrants + flag emoji, for the Add Result form
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, render_template, request

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config
from src import data_loader, groups, tracking
from src.bracket import simulate_knockout
from src.dashboard import describe_stage
from src.predictor import Predictor

app = Flask(__name__)


def _sanitize(obj):
    """Recursively replace NaN floats with None.

    Python's json module happily writes a literal NaN token (a
    non-standard extension), but a browser's JSON.parse follows the
    strict spec and throws a SyntaxError on it. Every accuracy summary
    row starts as NaN (n_matches == 0) before any match resolves, so
    without this the dashboard would fail to load on every fresh start.
    """
    if isinstance(obj, float) and math.isnan(obj):
        return None
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj

# In-memory cache: rebuilding from scratch (Elo replay + outcome model fit
# + a 10k-run bracket simulation) takes about a second, which is cheap
# enough to do on every /api/update, but we don't want every page load of
# /api/snapshot to pay that cost -- so it's cached here and only rebuilt
# on an explicit refresh or a new result being recorded.
_state: dict = {"predictor": None, "bracket_df": None, "loaded_at": None}


def _rebuild_state() -> None:
    df = data_loader.load_results()
    predictor = Predictor(df)
    try:
        bracket_df = simulate_knockout(predictor)
    except Exception:  # noqa: BLE001 - knockout bracket is tournament-specific; don't break the GUI without it
        bracket_df = pd.DataFrame(columns=["team", "p_win_title"])
    tracking.log_predictions(predictor)
    tracking.update_outcomes(predictor)
    _state.update(predictor=predictor, bracket_df=bracket_df, loaded_at=pd.Timestamp.now())


def _get_state() -> dict:
    if _state["predictor"] is None:
        _rebuild_state()
    return _state


@app.route("/")
def index():
    return render_template("index.html", tournament_year=config.TOURNAMENT_YEAR)


@app.route("/api/snapshot")
def api_snapshot():
    try:
        state = _get_state()
    except FileNotFoundError:
        return jsonify({"error": "no_data", "message":
                        "No data downloaded yet -- click \u201cRefresh data\u201d to get started."}), 409

    predictor: Predictor = state["predictor"]
    bracket_df: pd.DataFrame = state["bracket_df"]

    played, unplayed = data_loader.split_played_unplayed(predictor.wc_df)

    rankings = [
        {"rank": i, "team": team, "elo": round(rating)}
        for i, (team, rating) in enumerate(predictor.engine.top(20), start=1)
    ]

    title_odds = bracket_df.to_dict(orient="records") if not bracket_df.empty else []

    preds_df = predictor.predict_remaining_matches()
    predictions = preds_df.to_dict(orient="records") if not preds_df.empty else []

    standings = groups.compute_standings(predictor.wc_df, predictor.groups).to_dict(orient="records")

    log = tracking.load_log()
    summary = tracking.accuracy_summary(log)
    accuracy = {
        "summary": summary.to_dict(orient="records"),
        "pending": log[log["notes"].astype(str).str.len() > 0][
            ["home_team", "away_team", "notes"]
        ].to_dict(orient="records") if not log.empty else [],
        "log": log.sort_values("match_date").to_dict(orient="records") if not log.empty else [],
    }

    return jsonify(_sanitize({
        "meta": {
            "tournament_year": config.TOURNAMENT_YEAR,
            "stage": describe_stage(predictor),
            "played": len(played),
            "remaining": len(unplayed),
            "loaded_at": state["loaded_at"].isoformat() if state["loaded_at"] is not None else None,
        },
        "rankings": rankings,
        "title_odds": title_odds,
        "predictions": predictions,
        "standings": standings,
        "accuracy": accuracy,
    }))


@app.route("/api/teams")
def api_teams():
    try:
        state = _get_state()
    except FileNotFoundError:
        return jsonify({"teams": []})
    predictor: Predictor = state["predictor"]
    teams = sorted({t for ts in predictor.groups.values() for t in ts})
    return jsonify({"teams": teams})


@app.route("/api/update", methods=["POST"])
def api_update():
    download_error = None
    try:
        data_loader.download_dataset()
    except Exception as exc:  # noqa: BLE001 - fall back to whatever's cached on disk
        download_error = str(exc)

    try:
        _rebuild_state()
    except FileNotFoundError:
        return jsonify({"error": "no_data",
                         "message": "Couldn't download data and none is cached locally yet."}), 409

    predictor: Predictor = _state["predictor"]
    bracket_df: pd.DataFrame = _state["bracket_df"]

    config.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    predictor.engine.save()
    predictor.predict_remaining_matches().to_csv(config.PREDICTIONS_FILE, index=False)
    groups.compute_standings(predictor.wc_df, predictor.groups).to_csv(config.GROUP_TABLES_FILE, index=False)
    if not bracket_df.empty:
        bracket_df.to_csv(config.BRACKET_ODDS_FILE, index=False)

    return jsonify({"ok": True, "download_warning": download_error})


@app.route("/api/add-result", methods=["POST"])
def api_add_result():
    body = request.get_json(force=True)
    required = ["home", "away", "home_score", "away_score"]
    missing = [f for f in required if body.get(f) in (None, "")]
    if missing:
        return jsonify({"error": "missing_fields", "fields": missing}), 400

    try:
        data_loader.append_manual_result(
            home=body["home"], away=body["away"],
            home_score=int(body["home_score"]), away_score=int(body["away_score"]),
            date=body.get("date") or None,
            neutral=bool(body.get("neutral", True)),
            shootout_winner=body.get("shootout_winner") or None,
        )
    except Exception as exc:  # noqa: BLE001 - surface the actual problem to the form
        return jsonify({"error": "save_failed", "message": str(exc)}), 400

    _rebuild_state()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
