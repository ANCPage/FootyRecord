"""Path B: render round images from the results DB (no compute).

Requires `python compute_round.py --season 2026 --round N` to have run first.

Usage:
    python render_round.py --season 2026 --round 22
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Core'))



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--season', type=int, default=2026)
    parser.add_argument('--round', type=int, required=True)
    args = parser.parse_args()

    # Delegate to the shared generator's render path (Path B only).
    import generate_round_images
    sys.argv = ['generate_round_images.py',
                f'--comp_id={args.season}014', f'--round={args.round}',
                '--render-only']
    generate_round_images.main()


if __name__ == '__main__':
    main()
