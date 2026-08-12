from typing import Any, Dict, List, Tuple

import Core.config as config


class EloEngine:
    def __init__(self, elo_k: float = None, regression_factor: float = 0.75,
                 mean_rating: float = 1500.0, results_based: bool = False):
        self.elo_k = elo_k if elo_k is not None else config.config.elo_k
        self.regression_factor = regression_factor
        self.mean_rating = mean_rating
        self.results_based = results_based  # E1 A/B: train on scoreboard, not delta sign
        self.team_elo_by_round = {}  # team_id -> {(season, round): elo}
        self.season_start_elos = {}  # team_id -> {season: elo}

    @staticmethod
    def elo_update(h_elo: float, a_elo: float, actual_delta: float,
                   elo_k: float = None, divisor: float = None) -> Tuple[float, float, float]:
        """Single source of truth for the Elo update formula (audit #1/#2).

        Winner comes from the sign of `actual_delta` (delta-Elo design, E1;
        the results-based A/B variant passes the score margin here instead).
        Margin scaling uses the dynamic divisor (calibration.py:
        median|delta|/1.1; config value is the bootstrap fallback).
        Returns (delta_home, delta_away, margin_mult).
        """
        if elo_k is None:
            elo_k = config.config.elo_k
        if actual_delta > 0:
            elo_winner = 'H'
        elif actual_delta < 0:
            elo_winner = 'A'
        else:
            return 0.0, 0.0, 0.0  # draw -> no update
        S_h = 1.0 if elo_winner == 'H' else 0.0
        S_a = 1.0 - S_h
        E_h = 1 / (1 + 10 ** ((a_elo - h_elo) / 400.0))
        E_a = 1 - E_h
        if divisor is None:
            from calibration import current as cal
            divisor = getattr(cal, 'margin_divisor', None) or config.config.elo_margin_divisor
        margin_mult = min(3.0, max(0.5,
                                   abs(actual_delta) / divisor + 1.0))
        return (elo_k * margin_mult * (S_h - E_h),
                elo_k * margin_mult * (S_a - E_a),
                margin_mult)

    def compute_elo_history(self, sorted_matches: List[str], match_info: Dict[str, Any],
                            actual_match_matrices: Dict[str, Tuple[Dict, Dict]]) -> Dict[str, List[Tuple[str, float]]]:
        """
        Runs ELO simulation over all matches and returns:
        team_elo_history: team_id -> [(match_id, elo_before_match)]
        Additionally populates team_elo_by_round and season_start_elos.
        """
        from engine_core import MatchupEngine

        ratings = {}  # team_id -> current_elo
        team_elo_history = {}  # team_id -> [(match_id, elo_before_match)]
        self.team_elo_by_round = {}
        self.season_start_elos = {}

        current_season = None

        # E1 A/B: results-trained variant uses score margins with their own
        # dynamic divisor (median |score margin| / 1.1) instead of delta sign.
        if self.results_based:
            margins = [abs(match_info[m].home_score - match_info[m].away_score)
                       for m in sorted_matches
                       if match_info[m].home_score + match_info[m].away_score > 0
                       and match_info[m].home_score != match_info[m].away_score]
            score_divisor = (sorted(margins)[len(margins) // 2] / 1.1) if margins else 30.0
        else:
            score_divisor = None

        for m_id in sorted_matches:
            info = match_info[m_id]
            h_team, a_team = info.home, info.away

            # Initialize ratings if not present
            if h_team not in ratings: ratings[h_team] = self.mean_rating
            if a_team not in ratings: ratings[a_team] = self.mean_rating

            # Handle season roll-over regression
            if info.season != current_season:
                if current_season is not None:
                    for team in list(ratings.keys()):
                        ratings[team] = self.mean_rating + (ratings[team] - self.mean_rating) * self.regression_factor
                current_season = info.season
                # Record start of season ELOs
                for team in list(ratings.keys()):
                    if team not in self.season_start_elos:
                        self.season_start_elos[team] = {}
                    self.season_start_elos[team][current_season] = ratings[team]

            # Record ELO rating BEFORE this match in team_elo_history
            if h_team not in team_elo_history: team_elo_history[h_team] = []
            if a_team not in team_elo_history: team_elo_history[a_team] = []

            team_elo_history[h_team].append((m_id, ratings[h_team]))
            team_elo_history[a_team].append((m_id, ratings[a_team]))

            # Update ratings if match was actually played
            if m_id in actual_match_matrices:
                if self.results_based:
                    # Results-trained: winner = scoreboard, magnitude = margin
                    # (missing scores / draws -> zero delta -> no update, but
                    # the round-rating recording below still runs)
                    if info.home_score + info.away_score == 0:
                        actual_delta = 0.0
                    else:
                        actual_delta = float(info.home_score - info.away_score)
                else:
                    h_mat, a_mat = actual_match_matrices[m_id]
                    actual_delta = sum(MatchupEngine.calculate_delta(h_mat, a_mat).values())
                d_h, d_a, _ = self.elo_update(ratings[h_team], ratings[a_team],
                                              actual_delta, divisor=score_divisor)
                ratings[h_team] += d_h
                ratings[a_team] += d_a

            # Store post-match rating for the round
            for team in [h_team, a_team]:
                if team not in self.team_elo_by_round:
                    self.team_elo_by_round[team] = {}
                self.team_elo_by_round[team][(info.season, info.round)] = ratings[team]

        # Append final post-match ELO ratings
        if sorted_matches:
            last_mid = sorted_matches[-1]
            last_info = match_info[last_mid]
            for team in [last_info.home, last_info.away]:
                post_mid = f"POST_{last_mid}"
                if team not in team_elo_history: team_elo_history[team] = []
                team_elo_history[team].append((post_mid, ratings[team]))

        return team_elo_history

    def get_team_elo(self, team_id: str, season: int, round_num: int) -> float:
        """
        Retrieves ELO rating of a team before a specific round.
        """
        # Clamp round_num to prevent recursion stack overflow
        round_num = min(round_num, 25)

        # If round_num is 1, return the rating at the start of this season
        if round_num <= 1:
            return self.season_start_elos.get(team_id, {}).get(season, 1500.0)

        # Check if we have the ELO at the end of round_num - 1
        key = (season, round_num - 1)
        if team_id in self.team_elo_by_round and key in self.team_elo_by_round[team_id]:
            return self.team_elo_by_round[team_id][key]

        # Fallback to the ELO of the previous round
        return self.get_team_elo(team_id, season, round_num - 1)

    def get_team_tier(self, elo: float) -> str:
        """Distribution-relative tier via the ACTIVE calibration (top-4 ELITE /
        next-4 CONTENDER / next-5 MID-TABLE, dynamic cutoffs from the live Elo
        field); absolute thresholds only as the no-fit fallback."""
        from calibration import current as cal
        return cal.tier(elo)

    def get_league_rankings(self, season: int, round_num: int) -> Dict[str, int]:
        from mappings import TEAM_DATA
        team_elos = []
        for team_id in TEAM_DATA.keys():
            elo = self.get_team_elo(team_id, season, round_num)
            team_elos.append((team_id, elo))

        team_elos.sort(key=lambda x: x[1], reverse=True)
        return {team_id: rank for rank, (team_id, elo) in enumerate(team_elos, 1)}
