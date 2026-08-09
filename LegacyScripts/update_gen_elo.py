import re

with open("generate_round_images.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Update round_tips collection to include ELO
old_tips_append = """        round_tips.append({
            'home_name': h_name_mapped,
            'away_name': a_name_mapped,
            'winner_id': h_id if combined_score > 0 else a_id,
            'net_delta': combined_score,
            'actual_winner': ingestor.actual_winners.get(mid)
        })"""

new_tips_append = """        round_tips.append({
            'home_name': h_name_mapped,
            'away_name': a_name_mapped,
            'winner_id': h_id if combined_score > 0 else a_id,
            'net_delta': combined_score,
            'actual_winner': ingestor.actual_winners.get(mid),
            'home_elo': h_elo,
            'away_elo': a_elo
        })"""

code = code.replace(old_tips_append, new_tips_append)

# 2. Update visualizer calls to pass ELO
code = code.replace(
    "viz.draw_full_matchup(h_id, a_id, m_a, m_b, delta, save_prefix=prefix, is_mobile=False)",
    "viz.draw_full_matchup(h_id, a_id, m_a, m_b, delta, save_prefix=prefix, is_mobile=False, elo_a=h_elo, elo_b=a_elo)"
)

code = code.replace(
    "viz.draw_expectation_vs_actual(h_id, a_id, delta, actual_delta, save_prefix=prefix, is_mobile=False)",
    "viz.draw_expectation_vs_actual(h_id, a_id, delta, actual_delta, save_prefix=prefix, is_mobile=False, elo_a=h_elo, elo_b=a_elo)"
)

code = code.replace(
    "story_viz.draw_variance_map(h_id, a_id, variance_matrix, delta, actual_delta, driver_annotations, net_delta, sum(actual_delta.values()), f\"STORY_{prefix}.png\", is_mobile=False)",
    "story_viz.draw_variance_map(h_id, a_id, variance_matrix, delta, actual_delta, driver_annotations, net_delta, sum(actual_delta.values()), f\"STORY_{prefix}.png\", is_mobile=False, elo_a=h_elo, elo_b=a_elo)"
)

code = code.replace(
    "viz.draw_full_matchup(h_id, a_id, m_a, m_b, delta, save_prefix=prefix, is_mobile=True, mobile_format=m_format)",
    "viz.draw_full_matchup(h_id, a_id, m_a, m_b, delta, save_prefix=prefix, is_mobile=True, mobile_format=m_format, elo_a=h_elo, elo_b=a_elo)"
)

code = code.replace(
    "viz.draw_expectation_vs_actual(h_id, a_id, delta, actual_delta, save_prefix=prefix, is_mobile=True, mobile_format=m_format)",
    "viz.draw_expectation_vs_actual(h_id, a_id, delta, actual_delta, save_prefix=prefix, is_mobile=True, mobile_format=m_format, elo_a=h_elo, elo_b=a_elo)"
)

code = code.replace(
    "story_viz.draw_variance_map(h_id, a_id, variance_matrix, delta, actual_delta, driver_annotations, net_delta, sum(actual_delta.values()), f\"STORY_{prefix}.png\", is_mobile=True, mobile_format=m_format)",
    "story_viz.draw_variance_map(h_id, a_id, variance_matrix, delta, actual_delta, driver_annotations, net_delta, sum(actual_delta.values()), f\"STORY_{prefix}.png\", is_mobile=True, mobile_format=m_format, elo_a=h_elo, elo_b=a_elo)"
)

with open("generate_round_images.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Updated generate_round_images.py to pass ELO values to visualizers.")
