"""Per-player goal extraction: counts, dedup, team attribution, schema guard.

Team attribution is the load-bearing property here: the side must come from the
feed's own stat_teamId, never from a player->club guess (audit 2026-09-14).
"""
import csv
import json
import os

import pytest

from Core.tools.goals_extract import extract, load, player_team, side_goals

HEADER = ['matchId', 'chain_period', 'stat_periodSeconds', 'x', 'y', 'stat_playerId',
          'stat_description', 'stat_teamId']


def _write(path, rows):
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(rows)


def _extract(tmp_path, rows):
    _write(os.path.join(tmp_path, 'flattened_stats_2099.csv'), rows)
    return extract(str(tmp_path), verbose=False)['matches']


def test_counts_goals_and_behinds(tmp_path):
    got = _extract(tmp_path, [
        ('M1', 1, 100, 1, 2, 'P1', 'Goal', 'T1'),
        ('M1', 1, 140, 1, 2, 'P2', 'Goal', 'T1'),
        ('M1', 1, 200, 1, 2, 'P2', 'Behind', 'T1'),
        ('M1', 2, 300, 3, 4, 'P3', 'Goal', 'T2'),
        ('M2', 1, 100, 5, 6, 'P1', 'Goal', 'T2'),
    ])
    assert got['M1']['players'] == {
        'P1': {'g': 1, 'b': 0, 'team': 'T1'},
        'P2': {'g': 1, 'b': 1, 'team': 'T1'},
        'P3': {'g': 1, 'b': 0, 'team': 'T2'},
    }
    assert got['M1']['teams'] == {'T1': {'g': 2, 'b': 1}, 'T2': {'g': 1, 'b': 0}}
    assert got['M2']['teams'] == {'T2': {'g': 1, 'b': 0}}


def test_duplicate_rows_are_counted_once(tmp_path):
    """The engine's ingest dedups on (chain_period, seconds, x, y, playerId) —
    the same goal appearing twice in the feed must not count twice."""
    got = _extract(tmp_path, [
        ('M1', 1, 100, 1, 2, 'P1', 'Goal', 'T1'),
        ('M1', 1, 100, 1, 2, 'P1', 'Goal', 'T1'),      # duplicate -> ignored
        ('M1', 1, 100, 1, 2, 'P1', 'Behind', 'T1'),    # different event -> counts
    ])
    assert got['M1']['players']['P1'] == {'g': 1, 'b': 1, 'team': 'T1'}


def test_non_scoring_rows_ignored(tmp_path):
    got = _extract(tmp_path, [
        ('M1', 1, 100, 1, 2, 'P1', 'Handball', 'T1'),
        ('M1', 1, 110, 1, 2, 'P1', '', 'T1'),
        ('M1', 1, 130, 1, 2, 'P1', 'Goal', 'T1'),
    ])
    assert len(got['M1']['players']) == 1


def test_playerless_scores_still_count_for_the_team(tmp_path):
    """A rushed behind has no player id but does have a team: the team total must
    include it, or team goals are understated (the fixed bug)."""
    got = _extract(tmp_path, [
        ('M1', 1, 100, 1, 2, '', 'Behind', 'T1'),      # rushed behind
        ('M1', 1, 140, 1, 2, 'P1', 'Goal', 'T1'),
    ])
    assert got['M1']['teams']['T1'] == {'g': 1, 'b': 1}
    assert 'P1' in got['M1']['players']


def test_a_player_appearing_for_the_opposition_is_attributed_to_the_feed_side(tmp_path):
    """The same player id can appear under two teams across a match's chains.
    The scorer's side is the one the FEED says he scored for."""
    got = _extract(tmp_path, [
        ('M1', 1, 100, 1, 2, 'P1', 'Goal', 'T1'),
        ('M1', 1, 140, 1, 2, 'P1', 'Behind', 'T2'),    # same id, other side
    ])
    assert got['M1']['teams'] == {'T1': {'g': 1, 'b': 0}, 'T2': {'g': 0, 'b': 1}}
    assert player_team(got['M1'], 'P1') == 'T2'        # last write is the feed's
    assert side_goals(got['M1'])['T1']['g'] == 1


def test_old_schema_cache_is_refused_not_guessed(tmp_path):
    path = os.path.join(str(tmp_path), 'goals.json')
    with open(path, 'w') as fh:
        json.dump({'CD_M1': {'P1': {'g': 1, 'b': 0}}}, fh)     # versionless (v1)
    with pytest.raises(SystemExit) as exc:
        load(path)
    assert 'regenerate' in str(exc.value)
