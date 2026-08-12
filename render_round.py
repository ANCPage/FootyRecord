"""Path B: render round images from the results DB (no compute).

Requires `python compute_round.py --season 2026 --round N` (or
`evaluate.py --save` for played rounds) to have run first.

Usage:
    python render_round.py --season 2026 --round 22
"""
import argparse

from generate_round_images import render_round_from_db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--season', type=int, default=2026)
    parser.add_argument('--round', type=int, required=True)
    args = parser.parse_args()
    render_round_from_db(args.season, args.round)


if __name__ == '__main__':
    main()
