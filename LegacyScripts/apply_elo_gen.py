import re

with open("generate_round_images.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Update imports
code = code.replace("from config import DATA_DIR, OUTPUT_DIR", "import config")
code = code.replace("DataIngestor(DATA_DIR)", "DataIngestor(config.DATA_DIR)")
code = code.replace("os.path.join(OUTPUT_DIR", "os.path.join(config.OUTPUT_DIR")

# 2. Update prediction logic in the main loop
old_pred = """        delta = MatchupEngine.calculate_delta(m_a, m_b)
        net_delta = sum(delta.values())
        
        h_name_mapped = TEAM_DATA.get(h_id, {'name': h_n})['name']
        a_name_mapped = TEAM_DATA.get(a_id, {'name': a_n})['name']
        
        round_tips.append({
            'home_name': h_name_mapped,
            'away_name': a_name_mapped,
            'winner_id': h_id if net_delta > 0 else a_id,
            'net_delta': net_delta,
            'actual_winner': ingestor.actual_winners.get(mid)
        })"""

new_pred = """        delta = MatchupEngine.calculate_delta(m_a, m_b)
        net_delta = sum(delta.values())
        
        # Add ELO component
        h_elo = ingestor.get_team_elo(h_id, target_season, target_round)
        a_elo = ingestor.get_team_elo(a_id, target_season, target_round)
        elo_diff = (h_elo - a_elo) / 100.0
        combined_score = net_delta + (config.config.elo_weight * elo_diff)
        
        h_name_mapped = TEAM_DATA.get(h_id, {'name': h_n})['name']
        a_name_mapped = TEAM_DATA.get(a_id, {'name': a_n})['name']
        
        round_tips.append({
            'home_name': h_name_mapped,
            'away_name': a_name_mapped,
            'winner_id': h_id if combined_score > 0 else a_id,
            'net_delta': combined_score,
            'actual_winner': ingestor.actual_winners.get(mid)
        })"""

code = code.replace(old_pred, new_pred)

# 3. Update seasonal summary evaluation loop
old_eval = """            d = MatchupEngine.calculate_delta(m_a, m_b)
            pred_w = m_info.home if sum(d.values()) > 0 else m_info.away"""

new_eval = """            d = MatchupEngine.calculate_delta(m_a, m_b)
            n_d = sum(d.values())
            h_elo_eval = ingestor.get_team_elo(m_info.home, target_season, m_info.round)
            a_elo_eval = ingestor.get_team_elo(m_info.away, target_season, m_info.round)
            e_d = (h_elo_eval - a_elo_eval) / 100.0
            c_s = n_d + (config.config.elo_weight * e_d)
            pred_w = m_info.home if c_s > 0 else m_info.away"""

code = code.replace(old_eval, new_eval)

with open("generate_round_images.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Updated generate_round_images.py with ELO logic.")
