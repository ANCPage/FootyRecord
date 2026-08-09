import re

with open("generate_round_images.py", "r", encoding="utf-8") as f:
    code = f.read()

# Calculate rankings at the start of the round
rankings_calc = """    # Calculate league rankings once for the round
    rankings = ingestor.get_league_rankings(target_season, target_round)
    
    for g in range(1, 11):"""

# Need to find the correct spot to insert target_season and target_round if not already available
# They are calculated inside the loop currently. Let's move them out.

code = code.replace(
    "    for g in range(1, 11):",
    "    target_season = int(args.comp_id[:4])\n    target_round = args.round\n    rankings = ingestor.get_league_rankings(target_season, target_round)\n\n    for g in range(1, 11):"
)

# Update the loop logic to avoid re-calculating target_season/round
code = re.sub(r'        target_season = int\(args\.comp_id\[:4\]\)\n        target_round = args\.round', '', code)

# Update round_tips collection to include rank/tier
old_tips = """        round_tips.append({
            'home_name': h_name_mapped,
            'away_name': a_name_mapped,
            'winner_id': h_id if combined_score > 0 else a_id,
            'net_delta': combined_score,
            'actual_winner': ingestor.actual_winners.get(mid),
            'home_elo': h_elo,
            'away_elo': a_elo,
            'home_id': h_id, 'away_id': a_id, 'away_name': a_name_mapped,
        })"""

new_tips = """        h_rank = rankings.get(h_id)
        a_rank = rankings.get(a_id)
        h_tier = ingestor.get_team_tier(h_elo)
        a_tier = ingestor.get_team_tier(a_elo)
        
        round_tips.append({
            'home_name': h_name_mapped,
            'away_name': a_name_mapped,
            'winner_id': h_id if combined_score > 0 else a_id,
            'net_delta': combined_score,
            'actual_winner': ingestor.actual_winners.get(mid),
            'home_elo': h_elo,
            'away_elo': a_elo,
            'home_rank': h_rank,
            'away_rank': a_rank,
            'home_tier': h_tier,
            'away_tier': a_tier,
            'home_id': h_id, 'away_id': a_id, 'away_name': a_name_mapped,
        })"""

code = code.replace(old_tips, new_tips)

# Update visualizer calls
code = code.replace(
    "viz.draw_full_matchup(h_id, a_id, m_a, m_b, delta, save_prefix=prefix, is_mobile=False, elo_a=h_elo, elo_b=a_elo)",
    "viz.draw_full_matchup(h_id, a_id, m_a, m_b, delta, save_prefix=prefix, is_mobile=False, elo_a=h_elo, elo_b=a_elo, rank_a=h_rank, rank_b=a_rank, tier_a=h_tier, tier_b=a_tier)"
)

code = code.replace(
    "viz.draw_expectation_vs_actual(h_id, a_id, delta, actual_delta, save_prefix=prefix, is_mobile=False, elo_a=h_elo, elo_b=a_elo)",
    "viz.draw_expectation_vs_actual(h_id, a_id, delta, actual_delta, save_prefix=prefix, is_mobile=False, elo_a=h_elo, elo_b=a_elo, rank_a=h_rank, rank_b=a_rank, tier_a=h_tier, tier_b=a_tier)"
)

code = code.replace(
    "story_viz.draw_variance_map(h_id, a_id, variance_matrix, delta, actual_delta, driver_annotations, net_delta, sum(actual_delta.values()), f\"STORY_{prefix}.png\", is_mobile=False, elo_a=h_elo, elo_b=a_elo)",
    "story_viz.draw_variance_map(h_id, a_id, variance_matrix, delta, actual_delta, driver_annotations, net_delta, sum(actual_delta.values()), f\"STORY_{prefix}.png\", is_mobile=False, elo_a=h_elo, elo_b=a_elo, rank_a=h_rank, rank_b=a_rank, tier_a=h_tier, tier_b=a_tier)"
)

code = code.replace(
    "viz.draw_full_matchup(h_id, a_id, m_a, m_b, delta, save_prefix=prefix, is_mobile=True, mobile_format=m_format, elo_a=h_elo, elo_b=a_elo)",
    "viz.draw_full_matchup(h_id, a_id, m_a, m_b, delta, save_prefix=prefix, is_mobile=True, mobile_format=m_format, elo_a=h_elo, elo_b=a_elo, rank_a=h_rank, rank_b=a_rank, tier_a=h_tier, tier_b=a_tier)"
)

code = code.replace(
    "viz.draw_expectation_vs_actual(h_id, a_id, delta, actual_delta, save_prefix=prefix, is_mobile=True, mobile_format=m_format, elo_a=h_elo, elo_b=a_elo)",
    "viz.draw_expectation_vs_actual(h_id, a_id, delta, actual_delta, save_prefix=prefix, is_mobile=True, mobile_format=m_format, elo_a=h_elo, elo_b=a_elo, rank_a=h_rank, rank_b=a_rank, tier_a=h_tier, tier_b=a_tier)"
)

code = code.replace(
    "story_viz.draw_variance_map(h_id, a_id, variance_matrix, delta, actual_delta, driver_annotations, net_delta, sum(actual_delta.values()), f\"STORY_{prefix}.png\", is_mobile=True, mobile_format=m_format, elo_a=h_elo, elo_b=a_elo)",
    "story_viz.draw_variance_map(h_id, a_id, variance_matrix, delta, actual_delta, driver_annotations, net_delta, sum(actual_delta.values()), f\"STORY_{prefix}.png\", is_mobile=True, mobile_format=m_format, elo_a=h_elo, elo_b=a_elo, rank_a=h_rank, rank_b=a_rank, tier_a=h_tier, tier_b=a_tier)"
)

# Update journey plot calls
code = code.replace(
    "ladder_viz.draw_team_journey(team_id, ingestor, target_season, target_round, os.path.join(desktop_dir, f'JOURNEY_{team_name_clean}.png'), is_mobile=False)",
    "t_elo = ingestor.get_team_elo(team_id, target_season, target_round + 1)\nt_rank = rankings.get(team_id)\nt_tier = ingestor.get_team_tier(t_elo)\nladder_viz.draw_team_journey(team_id, ingestor, target_season, target_round, os.path.join(desktop_dir, f'JOURNEY_{team_name_clean}.png'), is_mobile=False, elo=t_elo, rank=t_rank, tier=t_tier)"
)

code = code.replace(
    "ladder_viz.draw_team_journey(team_id, ingestor, target_season, target_round, os.path.join(insta_post_dir, f'JOURNEY_{team_name_clean}.png'), is_mobile=True, mobile_format='post')",
    "ladder_viz.draw_team_journey(team_id, ingestor, target_season, target_round, os.path.join(insta_post_dir, f'JOURNEY_{team_name_clean}.png'), is_mobile=True, mobile_format='post', elo=t_elo, rank=t_rank, tier=t_tier)"
)

code = code.replace(
    "ladder_viz.draw_team_journey(team_id, ingestor, target_season, target_round, os.path.join(insta_reels_dir, f'JOURNEY_{team_name_clean}.png'), is_mobile=True, mobile_format='reel')",
    "ladder_viz.draw_team_journey(team_id, ingestor, target_season, target_round, os.path.join(insta_reels_dir, f'JOURNEY_{team_name_clean}.png'), is_mobile=True, mobile_format='reel', elo=t_elo, rank=t_rank, tier=t_tier)"
)

with open("generate_round_images.py", "w", encoding="utf-8", newline="") as f:
    f.write(code)

print("Updated generate_round_images.py to pass Rankings/Tiers to visualizers.")
