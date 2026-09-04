#!/usr/bin/env python3
"""Arc-and-sector segmentation of the circular field.

5 concentric depth arcs from the goal (A outermost/deepest .. E hugging
the goal), 3 angular lanes (left/centre/right). The whorl's own geometry:
depth = radius from goal, lane = angle. All 15 nodes stay inside the
circle frame centred at midfield.
"""
import math

from Core.geometry import GRID_NAMES

GOAL = (0.5, 0.92)


def arc_positions():
    pos = {}
    for lane_i, row in enumerate(GRID_NAMES):
        theta = math.radians((lane_i - 1) * 32)
        for depth_i, name in enumerate(row):
            r = 0.13 + 0.45 * depth_i / 4.0
            pos[name] = (GOAL[0] + r * math.sin(theta),
                         GOAL[1] - r * math.cos(theta))
    pos['SCORE'] = GOAL
    return pos


def flip(pos_map):
    return {k: (1.0 - x, 1.0 - y) for k, (x, y) in pos_map.items()}
