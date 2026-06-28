"""
Central configuration for the World Cup 2026 Match Outcome Prediction System.
Keeping these values in one place makes the system easy to retarget at a
different tournament (e.g. Euro 2028, World Cup 2030) later on.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

RESULTS_CSV = RAW_DIR / "international_results.csv"
ELO_RATINGS_FILE = PROCESSED_DIR / "elo_ratings.json"
PREDICTIONS_FILE = PROCESSED_DIR / "predictions.csv"
GROUP_TABLES_FILE = PROCESSED_DIR / "group_tables.csv"
BRACKET_ODDS_FILE = PROCESSED_DIR / "bracket_odds.csv"
PREDICTION_LOG_FILE = PROCESSED_DIR / "prediction_log.csv"
MANUAL_RESULTS_FILE = RAW_DIR / "manual_results.csv"
LOG_FILE = BASE_DIR / "logs" / "update.log"

# ---------------------------------------------------------------------------
# Historical data source
# ---------------------------------------------------------------------------
# Community-maintained dataset of full international match history
# (1872 - present), including the live 2026 World Cup fixture list with
# results filled in as matches are played. This single file is the backbone
# of the whole system: Elo ratings, the outcome model, and the list of
# "remaining matches to predict" are all derived from it.
RESULTS_CSV_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/"
    "master/results.csv"
)

# ---------------------------------------------------------------------------
# Tournament identity
# ---------------------------------------------------------------------------
TOURNAMENT_NAME = "FIFA World Cup"
TOURNAMENT_YEAR = 2026

# ---------------------------------------------------------------------------
# Elo rating engine settings
# ---------------------------------------------------------------------------
BASE_RATING = 1500
HOME_ADVANTAGE = 100  # Elo points added to the home side when not at a neutral venue

# K-factor (rating volatility) by competition importance.
# Values follow the widely-used World Football Elo Ratings methodology
# (eloratings.net). Matched against the `tournament` text in the dataset.
K_FACTORS = {
    "world_cup_finals": 60,
    "continental_final_or_cup": 50,
    "wc_or_continental_qualifier": 40,
    "minor_tournament": 30,
    "friendly": 20,
}

# Substrings used to classify a tournament name into one of the buckets above.
# Checked top-to-bottom; first match wins.
TOURNAMENT_CLASSIFICATION = [
    ("World Cup qualification", "wc_or_continental_qualifier"),
    ("FIFA World Cup", "world_cup_finals"),
    ("Copa América", "continental_final_or_cup"),
    ("UEFA Euro", "continental_final_or_cup"),
    ("African Cup of Nations", "continental_final_or_cup"),
    ("AFC Asian Cup", "continental_final_or_cup"),
    ("Gold Cup", "continental_final_or_cup"),
    ("Confederations Cup", "continental_final_or_cup"),
    ("qualification", "wc_or_continental_qualifier"),
    ("Friendly", "friendly"),
]

# ---------------------------------------------------------------------------
# Outcome model
# ---------------------------------------------------------------------------
# Only fit the home/draw/away classifier on matches from this year onward.
# The game has changed a lot since the 1800s/1900s; restricting to the
# modern era keeps the home/draw/away probabilities realistic.
MODEL_TRAINING_START_YEAR = 1995

# ---------------------------------------------------------------------------
# Group stage: Group letter -> the 4 teams in it.
# Verified two ways: (1) derived automatically from which teams play each
# other in the 2026 fixture list (see src/groups.py), and (2) cross-checked
# against official tournament reporting. Kept here as a static, human-
# readable lookup; src/groups.py re-derives it from data as a sanity check.
# ---------------------------------------------------------------------------
GROUPS_2026 = {
    "A": ["Mexico", "South Africa", "South Korea", "Czech Republic"],
    "B": ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"],
    "C": ["Brazil", "Morocco", "Haiti", "Scotland"],
    "D": ["United States", "Paraguay", "Australia", "Turkey"],
    "E": ["Germany", "Curaçao", "Ivory Coast", "Ecuador"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "New Zealand", "Egypt", "Iran"],
    "H": ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Norway", "Senegal", "Iraq"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Portugal", "Uzbekistan", "Colombia", "DR Congo"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

# Round-robin groups of 4 play 6 matches each (4 choose 2). Used to slice
# off the group stage from the chronological fixture list before the
# knockout rounds start linking teams across different groups -- see
# groups.derive_groups_from_fixtures for why this matters.
GROUP_STAGE_MATCH_COUNT = len(GROUPS_2026) * 6
