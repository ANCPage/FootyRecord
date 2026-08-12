"""Shared matchup computation (reuse pass #7).

One implementation of matrices -> delta -> net -> Elo -> calibration outputs,
used by the server endpoints (simulate / predict-round / backtest-sweep) and
the round-image generator. Previously each call site re-implemented this block.
"""
from dataclasses import dataclass
from typing import Dict, Optional

from Core.calibration import align_margin
from Core.calibration import current as cal
from Core.engine_core import MatchupEngine, home_favored


@dataclass
class MatchupPrediction:
    home: str
    away: str
    m_home: dict
    m_away: dict
    delta: dict
    net_delta: float
    edge: float            # fitted logit — the value home_favored thresholds at 0
    h_elo: float
    a_elo: float
    elo_diff: float        # (h-a)/100 — margin-model feature scale
    winner_id: str
    prob_home: float
    margin_pred: float
    home_score: int
    away_score: int
    h_tier: str
    a_tier: str
    h_rank: int
    a_rank: int


def compute_matchup(ingestor, home_id: str, away_id: str, season: int,
                    round_num: int, window: Optional[int] = None,
                    elo_overrides: Optional[Dict[str, float]] = None
                    ) -> Optional[MatchupPrediction]:
    """Full prediction for one matchup from pre-match data (no leakage:
    matrices/Elos are as-of the round BEFORE `round_num`... as requested via
    up_to_* guards). Returns None when either team lacks profile data."""
    m_h, _ = ingestor.get_team_average_matrix(home_id, window=window,
                                              up_to_season=season,
                                              up_to_round=round_num,
                                              return_history_info=True)
    m_a, _ = ingestor.get_team_average_matrix(away_id, window=window,
                                              up_to_season=season,
                                              up_to_round=round_num,
                                              return_history_info=True)
    if (not m_h or not m_a) and window is not None and window != 50:
        # Fallback: wide-window profile when the requested window is too thin
        # (shared behaviour previously duplicated in the server endpoints).
        m_h, _ = ingestor.get_team_average_matrix(home_id, window=50,
                                                  up_to_season=season,
                                                  up_to_round=round_num,
                                                  return_history_info=True)
        m_a, _ = ingestor.get_team_average_matrix(away_id, window=50,
                                                  up_to_season=season,
                                                  up_to_round=round_num,
                                                  return_history_info=True)
    if not m_h or not m_a:
        return None

    delta = MatchupEngine.calculate_delta(m_h, m_a)
    net_delta = sum(delta.values())

    if elo_overrides and home_id in elo_overrides:
        h_elo = float(elo_overrides[home_id])
    else:
        h_elo = ingestor.get_team_elo(home_id, season, round_num)
    if elo_overrides and away_id in elo_overrides:
        a_elo = float(elo_overrides[away_id])
    else:
        a_elo = ingestor.get_team_elo(away_id, season, round_num)

    elo_diff = (h_elo - a_elo) / 100.0
    # size from the fit, direction from the raw signal (2026-08-11: the
    # fitted margin can never flip the delta)
    edge = align_margin(cal.margin(net_delta, elo_diff), net_delta, elo_diff)
    winner_id = home_id if home_favored(net_delta, h_elo, a_elo) else away_id
    prob_home = cal.prob_from_margin(edge)  # display-only transform
    margin_pred = round(edge)
    total = cal.total_mean
    home_score = max(10, round((total + margin_pred) / 2.0))
    away_score = max(10, round((total - margin_pred) / 2.0))

    rankings = ingestor.get_league_rankings(season, round_num)
    return MatchupPrediction(
        home=home_id, away=away_id,
        m_home=m_h, m_away=m_a, delta=delta,
        net_delta=net_delta, edge=edge,
        h_elo=h_elo, a_elo=a_elo, elo_diff=elo_diff,
        winner_id=winner_id, prob_home=prob_home,
        margin_pred=margin_pred, home_score=home_score, away_score=away_score,
        h_tier=ingestor.get_team_tier(h_elo),
        a_tier=ingestor.get_team_tier(a_elo),
        h_rank=rankings.get(home_id, 99), a_rank=rankings.get(away_id, 99),
    )
