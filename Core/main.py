# ruff: noqa: E402  (imports follow the script-relative path bootstrap below)

import argparse
import logging

logging.basicConfig(level=logging.INFO, format='%(message)s')

from Core.config import config
from Core.engine_core import MatchupEngine
from Core.engine_data import DataIngestor
from Core.engine_scraper import update_all_data
from Core.mappings import TEAM_MAP
from Core.visualize_matchup import MatchupVisualizer


def build_parser():
    parser = argparse.ArgumentParser(description='AFL2 Strategic Prediction Engine')
    parser.add_argument('command', choices=['predict', 'predict_full', 'evaluate', 'profile', 'update'], help='Command to run')
    parser.add_argument('--teams', nargs=2, help='Two team IDs for predict command')
    parser.add_argument('--window', type=int, default=config.window_size, help=f'Sliding window size (default {config.window_size})')
    parser.add_argument('--target_round', type=int, default=None, help='Specific round to update (for update command)')
    parser.add_argument('--force', action='store_true', help='Force rebuild of the dataset (for update command)')
    return parser


def main():
    args = build_parser().parse_args()

    # Mutate global config object
    config.window_size = args.window

    if args.command == 'update':
        update_all_data(config.data_dir, year=2026, force_rebuild=args.force, target_round=args.target_round)
        return

    ingestor = DataIngestor(config.data_dir)
    ingestor.load_all_data()
    ingestor.profile_all_teams()

    if args.command == 'predict':
        if not args.teams:
            print('Error: --teams [TeamA] [TeamB] required for predict command.')
            return
        team_a, team_b = args.teams
        matrix_a = ingestor.get_team_average_matrix(team_a, window=args.window)
        matrix_b = ingestor.get_team_average_matrix(team_b, window=args.window)
        if not matrix_a or not matrix_b:
            print(f'Error: Could not find historical data for one or both teams: {team_a}, {team_b}')
            return
        delta_matrix = MatchupEngine.calculate_delta(matrix_a, matrix_b)
        print(f'Generating Full Tactical Analysis: {TEAM_MAP.get(team_a, team_a)} vs {TEAM_MAP.get(team_b, team_b)}')
        viz = MatchupVisualizer()
        viz.draw_full_matchup(team_a, team_b, matrix_a, matrix_b, delta_matrix)

    elif args.command == 'predict_full':
        if not args.teams:
            print('Error: --teams [TeamA] [TeamB] required for predict_full command.')
            return
        team_a, team_b = args.teams
        matrix_a = ingestor.get_team_average_matrix(team_a, window=args.window)
        matrix_b = ingestor.get_team_average_matrix(team_b, window=args.window)
        if not matrix_a or not matrix_b:
            print(f'Error: Could not find historical data for one or both teams: {team_a}, {team_b}')
            return
        delta_matrix = MatchupEngine.calculate_delta(matrix_a, matrix_b)
        print(f'Generating Full Tactical Analysis: {TEAM_MAP.get(team_a, team_a)} vs {TEAM_MAP.get(team_b, team_b)}')
        viz = MatchupVisualizer()
        viz.draw_full_matchup(team_a, team_b, matrix_a, matrix_b, delta_matrix)

    elif args.command == 'evaluate':
        print('Running full backtest...')
        pass

if __name__ == '__main__':
    main()
