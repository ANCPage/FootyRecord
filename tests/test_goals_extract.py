"""Per-player goal extraction: counts, dedup, and the mirror of the engine's key."""
import csv
import os

from Core.tools.goals_extract import extract

HEADER = ['matchId', 'chain_period', 'stat_periodSeconds', 'x', 'y', 'stat_playerId',
          'stat_description', 'stat_teamId']


def _write(path, rows):
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(HEADER)
        w.writerows(rows)


def test_counts_goals_and_behinds(tmp_path):
    _write(os.path.join(tmp_path, 'flattened_stats_2099.csv'), [
        ('M1', 1, 100, 1, 2, 'P1', 'Goal', 'T1'),
        ('M1', 1, 140, 1, 2, 'P2', 'Goal', 'T1'),
        ('M1', 1, 200, 1, 2, 'P2', 'Behind', 'T1'),
        ('M1', 2, 300, 3, 4, 'P3', 'Goal', 'T2'),
        ('M2', 1, 100, 5, 6, 'P1', 'Goal', 'T2'),
    ])
    got = extract(str(tmp_path), verbose=False)
    assert got['M1'] == {'P1': {'g': 1, 'b': 0}, 'P2': {'g': 1, 'b': 1},
                         'P3': {'g': 1, 'b': 0}}
    assert got['M2'] == {'P1': {'g': 1, 'b': 0}}


def test_duplicate_rows_are_counted_once(tmp_path):
    """The engine's ingest dedups on (chain_period, seconds, x, y, playerId) —
    the same goal appearing twice in the feed must not count twice."""
    _write(os.path.join(tmp_path, 'flattened_stats_2099.csv'), [
        ('M1', 1, 100, 1, 2, 'P1', 'Goal', 'T1'),
        ('M1', 1, 100, 1, 2, 'P1', 'Goal', 'T1'),      # duplicate -> ignored
        ('M1', 1, 100, 1, 2, 'P1', 'Behind', 'T1'),    # different event -> counts
    ])
    got = extract(str(tmp_path), verbose=False)
    assert got['M1']['P1'] == {'g': 1, 'b': 1}


def test_non_scoring_rows_ignored(tmp_path):
    _write(os.path.join(tmp_path, 'flattened_stats_2099.csv'), [
        ('M1', 1, 100, 1, 2, 'P1', 'Handball', 'T1'),
        ('M1', 1, 110, 1, 2, 'P1', '', 'T1'),
        ('M1', 1, 120, 1, 2, '', 'Goal', 'T1'),
        ('M1', 1, 130, 1, 2, 'P1', 'Goal', 'T1'),
    ])
    got = extract(str(tmp_path), verbose=False)
    assert got['M1'] == {'P1': {'g': 1, 'b': 0}}
