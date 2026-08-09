import sys
import os
from collections import defaultdict

sys.path.append(os.path.join(os.getcwd(), 'Core'))
from engine_data import DataIngestor
from engine_core import MatchupEngine
import config

def get_decayed_matrix(ingestor, team_id, window=25, up_to_season=None, up_to_round=None, decay_factor=1.0):
    history = ingestor.team_history.get(team_id, [])
    filtered_history = []
    for m_id, mat in history:
        info = ingestor.match_info.get(m_id)
        if up_to_season is not None and up_to_round is not None:
            if info and (info.season > up_to_season or (info.season == up_to_season and info.round >= up_to_round)):
                continue
        filtered_history.append(mat)
    
    history = filtered_history[-window:]
    if not history: 
        return {}
        
    avg_matrix = defaultdict(float)
    n = len(history)
    
    if decay_factor == 1.0:
        weights = [1.0 / n for _ in range(n)]
    else:
        weights = [decay_factor ** (n - 1 - i) for i in range(n)]
        total_w = sum(weights)
        if total_w > 0:
            weights = [w / total_w for w in weights]
        
    for i, mat in enumerate(history):
        w = weights[i]
        for edge, score in mat.items(): 
            avg_matrix[edge] += score * w
            
    return dict(avg_matrix)

def run_experiment():
    csv_path = 'CSV_DATA'
    ingestor = DataIngestor(csv_path)
    ingestor.load_all_data()
    ingestor.profile_all_teams()
    
    # Calculate Multi-season ELO (Continuous)
    multi_elo_history = defaultdict(list)
    multi_ratings = defaultdict(lambda: 1500.0)
    
    # Calculate Multi-season ELO (Soft Reset)
    soft_elo_history = defaultdict(list)
    soft_ratings = defaultdict(lambda: 1500.0)
    
    sorted_matches = sorted(ingestor.match_info.keys(), key=lambda x: (ingestor.match_info[x].season, ingestor.match_info[x].round))
    
    current_season_multi = 0
    current_season_soft = 0
    
    for m_id in sorted_matches:
        info = ingestor.match_info[m_id]
        h_team, a_team = info.home, info.away
        
        # Soft Reset Logic: at the start of a new season (excluding the very first), pull towards 1500
        if current_season_soft != 0 and info.season != current_season_soft:
            for t in soft_ratings:
                soft_ratings[t] = (soft_ratings[t] * 0.70) + (1500.0 * 0.30)
        current_season_soft = info.season
        
        multi_elo_history[h_team].append((m_id, multi_ratings[h_team]))
        multi_elo_history[a_team].append((m_id, multi_ratings[a_team]))
        
        soft_elo_history[h_team].append((m_id, soft_ratings[h_team]))
        soft_elo_history[a_team].append((m_id, soft_ratings[a_team]))
        
        perf = ingestor.match_performance.get(m_id)
        if perf:
            actual_delta = perf.get('actual', 0.0)
            actual_winner = ingestor.actual_winners.get(m_id)
            if actual_winner and actual_winner != 'DRAW':
                # Update Multi
                h_elo = multi_ratings[h_team]
                a_elo = multi_ratings[a_team]
                S_h = 1.0 if actual_winner == h_team else 0.0
                S_a = 1.0 if actual_winner == a_team else 0.0
                E_h = 1 / (1 + 10 ** ((a_elo - h_elo) / 400.0))
                E_a = 1 - E_h
                margin_mult = min(3.0, max(0.5, abs(actual_delta) / 10.0 + 1.0))
                multi_ratings[h_team] = h_elo + (config.config.elo_k * margin_mult) * (S_h - E_h)
                multi_ratings[a_team] = a_elo + (config.config.elo_k * margin_mult) * (S_a - E_a)
                
                # Update Soft
                h_elo_s = soft_ratings[h_team]
                a_elo_s = soft_ratings[a_team]
                E_h_s = 1 / (1 + 10 ** ((a_elo_s - h_elo_s) / 400.0))
                E_a_s = 1 - E_h_s
                soft_ratings[h_team] = h_elo_s + (config.config.elo_k * margin_mult) * (S_h - E_h_s)
                soft_ratings[a_team] = a_elo_s + (config.config.elo_k * margin_mult) * (S_a - E_a_s)

    def get_elo(history_dict, team_id, season, round_num):
        history = history_dict.get(team_id, [])
        if not history: return 1500.0
        last_elo = 1500.0
        for m_id, elo in history:
            info = ingestor.match_info.get(m_id)
            if not info: continue
            if info.season > season: break
            if info.season == season and info.round >= round_num: break
            last_elo = elo
        return last_elo

    seasons = [2023, 2024, 2025]
    
    baseline_correct = {s: 0 for s in seasons}
    modified_correct = {s: 0 for s in seasons}
    soft_correct = {s: 0 for s in seasons}
    totals = {s: 0 for s in seasons}
    
    window = 25
    decay_factor = 0.80
    
    for season in seasons:
        matches = [m for m, info in ingestor.match_info.items() if info.season == season]
        matches.sort(key=lambda x: (ingestor.match_info[x].round, x))
        
        for m_id in matches:
            info = ingestor.match_info[m_id]
            h_team, a_team = info.home, info.away
            
            actual_winner = ingestor.actual_winners.get(m_id)
            if not actual_winner or actual_winner == 'DRAW':
                continue
                
            totals[season] += 1
            
            # --- Baseline System ---
            m_a_base = get_decayed_matrix(ingestor, h_team, window=window, up_to_season=season, up_to_round=info.round, decay_factor=1.0)
            m_b_base = get_decayed_matrix(ingestor, a_team, window=window, up_to_season=season, up_to_round=info.round, decay_factor=1.0)
            
            if m_a_base and m_b_base:
                delta_base = MatchupEngine.calculate_delta(m_a_base, m_b_base)
                net_delta_base = sum(delta_base.values())
                
                h_elo_base = ingestor.get_team_elo(h_team, season, info.round)
                a_elo_base = ingestor.get_team_elo(a_team, season, info.round)
                elo_diff_base = (h_elo_base - a_elo_base) / 100.0
                combined_base = net_delta_base + (config.config.elo_weight * elo_diff_base)
                
                pred_base = h_team if combined_base > 0 else a_team
                if pred_base == actual_winner:
                    baseline_correct[season] += 1

            # --- Modified System (Continuous ELO) ---
            m_a_mod = get_decayed_matrix(ingestor, h_team, window=window, up_to_season=season, up_to_round=info.round, decay_factor=decay_factor)
            m_b_mod = get_decayed_matrix(ingestor, a_team, window=window, up_to_season=season, up_to_round=info.round, decay_factor=decay_factor)
            
            if m_a_mod and m_b_mod:
                delta_mod = MatchupEngine.calculate_delta(m_a_mod, m_b_mod)
                net_delta_mod = sum(delta_mod.values())
                
                h_elo_mod = get_elo(multi_elo_history, h_team, season, info.round)
                a_elo_mod = get_elo(multi_elo_history, a_team, season, info.round)
                elo_diff_mod = (h_elo_mod - a_elo_mod) / 100.0
                combined_mod = net_delta_mod + (config.config.elo_weight * elo_diff_mod)
                
                pred_mod = h_team if combined_mod > 0 else a_team
                if pred_mod == actual_winner:
                    modified_correct[season] += 1
                    
            # --- Modified System (Soft Reset ELO) ---
            if m_a_mod and m_b_mod:
                h_elo_soft = get_elo(soft_elo_history, h_team, season, info.round)
                a_elo_soft = get_elo(soft_elo_history, a_team, season, info.round)
                elo_diff_soft = (h_elo_soft - a_elo_soft) / 100.0
                combined_soft = net_delta_mod + (config.config.elo_weight * elo_diff_soft)
                
                pred_soft = h_team if combined_soft > 0 else a_team
                if pred_soft == actual_winner:
                    soft_correct[season] += 1

    print(f"{'Season':<10} | {'Baseline (Flat/Reset)':<25} | {'Mod (0.8 Decay/Cont)':<25} | {'Mod (0.8 Decay/Soft 30%)':<25}")
    print("-" * 95)
    for s in seasons:
        tot = totals[s]
        if tot == 0: continue
        base_acc = (baseline_correct[s] / tot) * 100
        mod_acc = (modified_correct[s] / tot) * 100
        soft_acc = (soft_correct[s] / tot) * 100
        
        str_base = f"{baseline_correct[s]}/{tot} ({base_acc:.2f}%)"
        str_mod = f"{modified_correct[s]}/{tot} ({mod_acc:.2f}%)"
        str_soft = f"{soft_correct[s]}/{tot} ({soft_acc:.2f}%)"
        print(f"{s:<10} | {str_base:<25} | {str_mod:<25} | {str_soft:<25}")

if __name__ == '__main__':
    run_experiment()
