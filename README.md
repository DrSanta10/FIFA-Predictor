# World Cup 2026 Match Outcome Prediction System

Predicts the winner of every remaining match at the 2026 FIFA World Cup,
using a team-strength model (Elo ratings) calibrated on **~150 years of
real international football results**, and re-trains/updates itself
every time you run it so it stays current as the tournament progresses.

Terminal-based for now, by design -- a GUI comes later once the
prediction core is solid (see [Roadmap](#roadmap)).

## How it works

```
                 ┌─────────────────────────┐
                 │ historical_results.csv  │   1872 -> today, incl. live
                 │ (auto-downloaded)        │   2026 World Cup fixtures
                 └────────────┬─────────────┘
                              │
                    chronological replay
                              ▼
                 ┌─────────────────────────┐
                 │   Elo rating engine      │  src/elo.py
                 │ (every team's strength)  │
                 └────────────┬─────────────┘
                              │ rating gap + outcome,
                              │ for every historical match
                              ▼
                 ┌─────────────────────────┐
                 │  Outcome probability     │  src/outcome_model.py
                 │  model (logistic regr.)  │  rating gap -> P(H)/P(D)/P(A)
                 └────────────┬─────────────┘
                              │
                  ┌───────────┴────────────┐
                  ▼                        ▼
       ┌─────────────────────┐   ┌─────────────────────────┐
       │      Predictor        │   │   Knockout bracket       │  src/bracket.py
       │ src/predictor.py       │   │   (Round of 32 -> Final) │
       │ - every remaining match│   │   official bracket tree, │
       │ - group-stage Monte    │   │   Monte Carlo simulation │
       │   Carlo                │   └─────────────────────────┘
       └─────────────────────┘
                              │
                              ▼
                      main.py (CLI)
```

1. **Data**: a community-maintained, continuously-updated CSV of every
   international football result since 1872, including the live 2026
   World Cup fixture list (results filled in as matches are played,
   `NA` for matches still to come). One download gives us both the
   training history and the list of "what's left to predict."

2. **Elo ratings** (`src/elo.py`): the classic
   [World Football Elo](https://www.eloratings.net/about) methodology.
   Every team starts at 1500 and moves up/down after each match based on
   whether the result beat expectations and by how much, scaled by how
   important the competition was (World Cup matches move ratings more
   than friendlies). This produces a single "current strength" number
   per team, e.g. Argentina ≈ 2214, far stronger than a team like Jordan
   ≈ 1500-1600.

3. **Outcome model** (`src/outcome_model.py`): Elo gives you a strength
   *gap* between two teams. A multinomial logistic regression, fit on
   ~29,000 real matches since 1995, converts that gap into actual
   win/draw/loss probabilities ("teams with a 150-point Elo edge at home
   have historically won about 58% of the time").

4. **Predictor** (`src/predictor.py`): applies the model to every match
   still marked as unplayed, and runs a 10,000-iteration Monte Carlo
   simulation of the rest of the group stage to estimate each team's
   probability of finishing top-2 (auto-qualifying for the Round of 32).

5. **Knockout bracket** (`src/bracket.py`): once the group stage ends,
   the Round of 32 draw is fixed -- FIFA's third-place "Annex C" combination
   table resolves into concrete fixtures, and the bracket through to the
   Final is single-elimination from there. This module hardcodes that
   confirmed bracket (cross-checked against three independent published
   sources) and runs a 10,000-iteration Monte Carlo simulation through
   every round, tracking how often each team reaches the Round of 16,
   Quarter-finals, Semi-finals, the Final, and wins the title outright.

## Setup

```bash
git clone <your-repo-url>
cd fifa-predictor
pip install -r requirements.txt
python main.py update
```

## Daily usage

```bash
python main.py update          # 1. refresh data + ratings + predictions (run this first, daily)
python main.py dashboard       # 2. single-screen overview of everything below, nicely formatted
python main.py standings       # 3. current group tables
python main.py predict         # 4. predictions for every remaining match
python main.py simulate        # 5. Monte Carlo group-qualification odds
python main.py bracket         # 6. Monte Carlo knockout odds (Round of 32 -> Final, incl. 3rd place)
python main.py ratings         # 7. current Elo power rankings (top 20)
python main.py accuracy        # 8. how good have the predictions actually been?
```

### Dashboard

`python main.py dashboard` is the fastest way to see everything at a
glance -- current stage, top Elo rankings, title odds with a bar chart,
the next several predictions, and an accuracy snapshot, all in one
colour-coded screen (built with [rich](https://github.com/Textualize/rich)):

```
╭──────────────────────────────────────────────────────────────────╮
│ FIFA World Cup 2026 -- Match Prediction Dashboard                │
│ Stage: Round of 32   Played: 72   Remaining: 16   Last rendered: │
│ 2026-06-28 23:41                                                 │
╰──────────────────────────────────────────────────────────────────╯
 Top 10 Elo Power Rankings        Title Odds (Monte Carlo)
   1  Argentina    2218             1  Argentina   25%  ████████████████████
   2  Spain        2189             2  France      18%  ███████████████░░░░░
   3  France       2178             3  Spain       17%  ██████████████░░░░░░
   ...
```

It's read-only except for keeping the accuracy log current -- it
doesn't re-download data or touch `data/processed/*.csv` (that's still
`update`'s job). Add `--watch 60` to re-render every 60 seconds (handy
on a second monitor during matchdays); a full refresh -- Elo, the
outcome model, and a 10,000-run bracket simulation -- takes about a
second, so frequent watch intervals are cheap. Add `--limit N` to show
more/fewer rows in the predictions table (default 15), or `--n` to
change the bracket simulation count.

Sample `predict` output:

```
2026-06-27  Jordan        vs Argentina   H 3% / D 13% / A 84%   -> predicted: Argentina
2026-06-27  Panama        vs England     H 9% / D 20% / A 71%   -> predicted: England
2026-06-27  Croatia       vs Ghana       H 70% / D 20% / A 10%  -> predicted: Croatia
```

Sample `bracket` output (once the knockout stage has started):

```
     team  p_reach_r16  p_reach_qf  p_reach_sf  p_reach_final  p_win_title
Argentina        93.3%       78.5%       58.1%          40.4%        25.1%
   France        88.0%       64.5%       47.9%          30.6%        18.3%
    Spain        81.6%       57.4%       45.8%          28.3%        17.0%
  England        81.9%       49.0%       28.7%          13.6%         6.4%
```

### If today's result isn't in the dataset yet

The upstream dataset is community-maintained and usually catches up
within a day, but if you want today's result reflected immediately:

```bash
python main.py add-result "Mexico" "Czech Republic" 2 1 --date 2026-06-24
python main.py update
```

Team names must match the dataset's spelling exactly (run
`python main.py ratings --n 50` to check how a team is spelled).

**On the `--date` value and timezones:** the dataset records each
fixture under the host venue's local calendar date (e.g. US Eastern/
Central, not SAST or whatever timezone you're watching from), and a
late kickoff can mean the "date" differs from what you'd call today
where you are. You don't need to work out the exact host-venue date
though -- matching is done on **team names + tournament + year**, not
the exact day, so as long as the team names and year are right, your
entry will correctly update the existing fixture (not create a
duplicate) no matter which timezone's "today" you used.

**On penalty shootouts:** the upstream dataset records a knockout match
decided by penalties as a plain draw -- e.g. the real 2022 final shows
Argentina 3-3 France, with no indication Argentina actually won. If
`add-result` sees level scores on what it knows is a knockout match
(per `Predictor.is_knockout_match`), it'll remind you to add
`--shootout-winner TeamName`:

```bash
python main.py add-result "Brazil" "Japan" 1 1 --date 2026-06-29 --shootout-winner "Japan"
```

Without that, the match still counts as played (so it won't keep
showing up in `predict`), but `accuracy` will mark it "awaiting
shootout winner" and exclude it from the stats until you supply one.

### Tracking prediction accuracy over time

`python main.py update` also logs every currently-unplayed match to
`data/processed/prediction_log.csv` *the first time it sees it*, and
fills in the actual result (and whether the prediction was right) once
the match has been played. Re-running `update` daily does NOT overwrite
an already-logged prediction, even though the model's Elo ratings (and
therefore what it *would* predict today) keep moving -- the log is
meant to answer "how good was the forecast we actually made", not "how
good would today's model have looked in hindsight".

```bash
python main.py accuracy            # overall / group-stage / knockout accuracy + Brier score
python main.py accuracy --detail   # every logged match, predicted vs. actual
```

Brier score is the calibration metric here (lower is better, 0 =
perfect confidence in the right outcome) -- it rewards well-calibrated
probabilities, not just picking the right name. A model that says "60%"
for a coin-flip match and is right scores better than one that said
"95%" and happened to be right too, because 95% was overconfident.

### Automating the daily update

`.github/workflows/daily_update.yml` runs `python main.py update`
automatically every day at 06:00 UTC via GitHub Actions and commits the
refreshed `data/processed/` files back to the repo, so your predictions
stay current without you running anything by hand. Trigger it manually
any time from the **Actions** tab, or adjust the cron schedule (e.g. add
extra runs on matchdays).

Prefer running it yourself? A cron entry works just as well:

```
0 6 * * * cd /path/to/fifa-predictor && python main.py update >> logs/update.log 2>&1
```

## Project structure

```
fifa-predictor/
├── main.py                  # CLI entry point
├── config.py                # paths, Elo constants, group lookup
├── requirements.txt
├── .github/workflows/
│   └── daily_update.yml     # scheduled auto-update
├── data/
│   ├── raw/                 # downloaded + manually-entered results
│   └── processed/           # elo_ratings.json, predictions.csv, group_tables.csv,
│                            # bracket_odds.csv, prediction_log.csv
└── src/
    ├── data_loader.py       # download / parse / filter match data
    ├── elo.py               # Elo rating engine
    ├── outcome_model.py     # Elo gap -> win/draw/loss probability
    ├── groups.py            # group standings + remaining fixtures
    ├── bracket.py            # official knockout bracket + Monte Carlo sim
    ├── predictor.py         # ties it all together + group Monte Carlo
    ├── tracking.py          # prediction accuracy log over time
    └── dashboard.py         # single-screen rich terminal overview
```

## Methodology notes & known limitations

Being upfront about these so you know exactly what you're looking at
(and where the obvious next improvements are):

- **Group tiebreakers**: standings use points -> goal difference -> goals
  scored, which covers FIFA's first three tiebreak criteria. Head-to-head
  results and disciplinary (fair-play) points aren't modelled, so in a
  three-way tiebreak edge case the table here could differ from the
  official one.
- **Knockout bracket**: implemented in `src/bracket.py` as a hardcoded
  match tree (Round of 32 through the Final), built from FIFA's official
  schedule once the Round of 32 draw was confirmed and cross-checked
  against two other independently published brackets. It isn't derived
  automatically the way groups.py derives groups, because which
  third-placed team lands in which Round of 32 slot depends on FIFA's
  "Annex C" combination table (495 possible permutations) -- reproducing
  that table from scratch would be guesswork, whereas the *resolved*
  fixtures (now public) are not. If you reuse this for a future
  tournament, `BRACKET` in `src/bracket.py` is the one thing you'd need
  to replace once that tournament's draw is confirmed; the Monte Carlo
  logic itself is generic to any single-elimination bracket.
- **Third-place play-off**: implemented (Match 103 in `src/bracket.py`,
  keyed off the two semi-final *losers* rather than winners -- the one
  match in the bracket that works this way).
- **Penalty shootouts and the dataset**: the upstream dataset has no
  concept of a shootout winner -- a knockout match level after 90
  minutes is recorded as a plain draw regardless of who actually
  advanced. This affects two things: (1) `predict_match` for a knockout
  fixture never predicts "Draw" (it uses the no-draw win probability
  instead, since a draw isn't a real final outcome), and (2) accuracy
  tracking can't auto-resolve a shootout-decided match -- you supply the
  real winner via `add-result ... --shootout-winner TeamName`, after
  which it's scored like any other match. Until then it's excluded from
  the accuracy stats rather than silently guessed at.
- **Penalty shootouts and the model**: for the no-draw win probability
  itself (used in `predict` for knockout fixtures and throughout
  `bracket.py`), a 90-minute draw is treated as a coin flip between the
  two sides, slightly weighted by the same Elo-based 3-way model (P(team
  A advances) = P(A wins in 90) + half of P(draw in 90)). Real shootouts
  are close to 50/50 regardless of the pre-match favourite, but this is
  a deliberate simplification -- see `OutcomeModel.win_probability_no_draw`.
- **Accuracy tracking locks in the first prediction, not the latest
  one**: a match is logged the first time it appears as unplayed, and
  that prediction is never overwritten on later `update` runs even
  though the Elo ratings (and so what the model would say today) keep
  moving. This is deliberate -- it answers "how good was the call we
  actually made" rather than letting the log fill up with whichever
  prediction happened to be freshest right before kickoff.
- **Scorelines in the Monte Carlo sim** use simple 1-0/0-0 placeholders
  to get goal difference roughly right; it's tuned for *qualification
  probability*, not for predicting exact final scores.
- **Home advantage**: applied only when the `neutral` flag in the
  dataset is False. The US/Mexico/Canada teams get a genuine home boost
  for matches in their own country; everyone else plays at a
  designated-neutral venue per the dataset.

## Roadmap

- [x] Knockout bracket Monte Carlo (Round of 32 -> Final)
- [x] Third-place play-off simulation
- [x] Track prediction accuracy over time (logged automatically by `update`; see `accuracy`)
- [x] Simple terminal dashboard (`python main.py dashboard`, built with `rich`)
- [ ] GUI (Streamlit or a small Flask/React app) once the CLI is battle-tested
