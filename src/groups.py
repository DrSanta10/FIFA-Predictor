"""
groups.py
---------
Group-stage standings and fixture bookkeeping.

Two independent ways of knowing "who is in which group" are cross-checked
on load:
  1. the static GROUPS_2026 lookup in config.py
  2. derive_groups_from_fixtures(): build a graph where two teams are
     connected if they played each other in the 2026 World Cup, and take
     the connected components. In a round-robin group of 4, each team
     plays the other 3, so every group is a complete graph component of
     size 4 -- no hardcoded list required.

If FIFA ever reshuffles a group (extremely unlikely once the draw has
happened) the dynamic version is the one actually used for standings, so
the system stays correct even if config.py drifts out of date.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.append(str(Path(__file__).resolve().parent.parent))
import config


def get_group_stage_matches(wc_df: pd.DataFrame) -> pd.DataFrame:
    """Return just the group stage: the chronologically-first
    GROUP_STAGE_MATCH_COUNT matches of the tournament, before knockout
    fixtures (which pair teams across different groups) start appearing.
    Every group-aware function in this module is built on top of this,
    so knockout results can never leak into group standings/tables.
    """
    return (
        wc_df.sort_values("date", kind="stable")
        .head(config.GROUP_STAGE_MATCH_COUNT)
        .reset_index(drop=True)
    )


def derive_groups_from_fixtures(wc_df: pd.DataFrame) -> dict[str, list[str]]:
    """Derive the group -> [teams] mapping purely from who plays whom in
    the group stage. Building this from ALL matches (including knockout
    rounds, where teams from different groups face each other) would
    merge separate groups into one connected component -- exactly the
    bug that caused `standings` to print one 40-team list and one 8-team
    list instead of 12 groups of 4.

    Returns groups keyed 0..N (no letters -- letters are then attached
    by matching against config.GROUPS_2026 in `get_groups`).
    """
    group_stage_df = get_group_stage_matches(wc_df)

    adjacency: dict[str, set[str]] = {}
    for row in group_stage_df.itertuples(index=False):
        adjacency.setdefault(row.home_team, set()).add(row.away_team)
        adjacency.setdefault(row.away_team, set()).add(row.home_team)

    visited: set[str] = set()
    components: list[list[str]] = []
    for team in adjacency:
        if team in visited:
            continue
        stack, comp = [team], set()
        while stack:
            t = stack.pop()
            if t in comp:
                continue
            comp.add(t)
            visited.add(t)
            stack.extend(adjacency[t] - comp)
        components.append(sorted(comp))

    return {str(i): comp for i, comp in enumerate(sorted(components, key=lambda c: c[0]))}


def get_groups(wc_df: pd.DataFrame) -> dict[str, list[str]]:
    """Best-effort official letters, falling back to the dynamic groups
    if a team in the live data isn't found in the static config (e.g. a
    spelling variant)."""
    dynamic = derive_groups_from_fixtures(wc_df)
    static_team_to_letter = {
        team: letter for letter, teams in config.GROUPS_2026.items() for team in teams
    }

    labelled = {}
    for comp in dynamic.values():
        letters = {static_team_to_letter.get(t) for t in comp}
        letters.discard(None)
        letter = sorted(letters)[0] if letters else f"?{comp[0][:3]}"
        labelled[letter] = sorted(comp)
    return dict(sorted(labelled.items()))


def compute_standings(wc_df: pd.DataFrame, groups: dict[str, list[str]]) -> pd.DataFrame:
    """Build a standings table for every group from played group-stage
    matches only (knockout results are deliberately excluded -- see
    get_group_stage_matches).

    Sort order: points, then goal difference, then goals scored (the
    first three of FIFA's official tiebreakers -- head-to-head and
    disciplinary points are not modelled here, see README).
    """
    team_to_group = {team: g for g, teams in groups.items() for team in teams}

    stats = {
        team: {"group": g, "played": 0, "won": 0, "drawn": 0, "lost": 0,
               "gf": 0, "ga": 0, "points": 0}
        for g, teams in groups.items() for team in teams
    }

    group_stage_df = get_group_stage_matches(wc_df)
    played = group_stage_df.dropna(subset=["home_score", "away_score"])
    for row in played.itertuples(index=False):
        if row.home_team not in team_to_group or row.away_team not in team_to_group:
            continue
        h, a = stats[row.home_team], stats[row.away_team]
        hs, as_ = int(row.home_score), int(row.away_score)

        h["played"] += 1; a["played"] += 1
        h["gf"] += hs; h["ga"] += as_
        a["gf"] += as_; a["ga"] += hs

        if hs > as_:
            h["won"] += 1; h["points"] += 3
            a["lost"] += 1
        elif hs < as_:
            a["won"] += 1; a["points"] += 3
            h["lost"] += 1
        else:
            h["drawn"] += 1; h["points"] += 1
            a["drawn"] += 1; a["points"] += 1

    rows = []
    for team, s in stats.items():
        rows.append({
            "group": s["group"], "team": team, "played": s["played"],
            "won": s["won"], "drawn": s["drawn"], "lost": s["lost"],
            "gf": s["gf"], "ga": s["ga"], "gd": s["gf"] - s["ga"],
            "points": s["points"],
        })

    table = pd.DataFrame(rows)
    table = table.sort_values(
        ["group", "points", "gd", "gf"], ascending=[True, False, False, False]
    ).reset_index(drop=True)
    table["position"] = table.groupby("group").cumcount() + 1
    return table


def remaining_group_fixtures(wc_df: pd.DataFrame, groups: dict[str, list[str]]) -> pd.DataFrame:
    """Group-stage matches that haven't been played yet (empty once the
    group stage is complete -- knockout fixtures are never included)."""
    team_to_group = {team: g for g, teams in groups.items() for team in teams}
    group_stage_df = get_group_stage_matches(wc_df)
    unplayed = group_stage_df[group_stage_df["home_score"].isna() | group_stage_df["away_score"].isna()].copy()
    is_group_match = unplayed["home_team"].isin(team_to_group) & unplayed["away_team"].isin(team_to_group)
    out = unplayed[is_group_match].copy()
    out["group"] = out["home_team"].map(team_to_group)
    return out.reset_index(drop=True)


if __name__ == "__main__":
    import data_loader

    df = data_loader.load_results()
    wc_df = data_loader.get_tournament(df)
    groups = get_groups(wc_df)

    print(f"Derived {len(groups)} groups:")
    for letter, teams in groups.items():
        print(f"  Group {letter}: {', '.join(teams)}")

    table = compute_standings(wc_df, groups)
    print("\nCurrent standings:")
    for letter in groups:
        sub = table[table["group"] == letter]
        print(f"\nGroup {letter}")
        print(sub[["position", "team", "played", "won", "drawn", "lost", "gd", "points"]]
              .to_string(index=False))

    remaining = remaining_group_fixtures(wc_df, groups)
    print(f"\n{len(remaining)} group-stage fixtures remaining.")
