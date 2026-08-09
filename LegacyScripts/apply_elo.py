import re

with open('Core/engine_data.py', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Add team_elo_history to init
init_old = '''        self.actual_match_matrices = {}
        self.match_performance = {} # (match_id) -> {expected_delta: float, actual_delta: float}'''

init_new = '''        self.actual_match_matrices = {}
        self.match_performance = {} # (match_id) -> {expected_delta: float, actual_delta: float}
        self.team_elo_history = defaultdict(list) # team_id -> [(match_id, elo_before_match)]'''

code = code.replace(init_old, init_new)

# 2. Add elo state variables inside profile_all_teams before the loop
prof_start_old = '''        sorted_matches = sorted(self.match_info.keys(), key=lambda x: (self.match_info[x].season, self.match_info[x].round))
        print('Profiling teams using integrated edge-based decay logic...')
        for m_id in sorted_matches:'''

prof_start_new = '''        sorted_matches = sorted(self.match_info.keys(), key=lambda x: (self.match_info[x].season, self.match_info[x].round))
        print('Profiling teams using integrated edge-based decay logic...')
        
        ratings = defaultdict(lambda: 1500.0)
        current_season = 0
        
        for m_id in sorted_matches:'''
        
code = code.replace(prof_start_old, prof_start_new)

# 3. Add recording ELO before the match
elo_record_old = '''        for m_id in sorted_matches:
            info = self.match_info[m_id]
            h_team, a_team = info.home, info.away'''

elo_record_new = '''        for m_id in sorted_matches:
            info = self.match_info[m_id]
            h_team, a_team = info.home, info.away
            
            if info.season != current_season:
                current_season = info.season
                ratings.clear()
                
            self.team_elo_history[h_team].append((m_id, ratings[h_team]))
            self.team_elo_history[a_team].append((m_id, ratings[a_team]))'''

code = code.replace(elo_record_old, elo_record_new)

# 4. Add updating ELO after actual match matrices are set
elo_update_old = '''            if m_id in self.match_performance:
                from engine_core import MatchupEngine
                self.match_performance[m_id]['actual'] = sum(MatchupEngine.calculate_delta(h_mat, a_mat).values())

        import pickle'''

elo_update_new = '''            if m_id in self.match_performance:
                from engine_core import MatchupEngine
                actual_delta = sum(MatchupEngine.calculate_delta(h_mat, a_mat).values())
                self.match_performance[m_id]['actual'] = actual_delta
                
                # Update ELO
                actual_winner = self.actual_winners.get(m_id)
                if actual_winner and actual_winner != 'DRAW':
                    h_elo = ratings[h_team]
                    a_elo = ratings[a_team]
                    S_h = 1.0 if actual_winner == h_team else 0.0
                    S_a = 1.0 if actual_winner == a_team else 0.0
                    E_h = 1 / (1 + 10 ** ((a_elo - h_elo) / 400.0))
                    E_a = 1 - E_h
                    margin_mult = min(3.0, max(0.5, abs(actual_delta) / 10.0 + 1.0))
                    ratings[h_team] = h_elo + (config.config.elo_k * margin_mult) * (S_h - E_h)
                    ratings[a_team] = a_elo + (config.config.elo_k * margin_mult) * (S_a - E_a)

        import pickle'''

code = code.replace(elo_update_old, elo_update_new)

# 5. Add get_team_elo method to the end of the file
get_elo_func = '''
    def get_team_elo(self, team_id: str, season: int, round_num: int) -> float:
        history = self.team_elo_history.get(team_id, [])
        if not history: return 1500.0
        
        last_elo = 1500.0
        for m_id, elo in history:
            info = self.match_info.get(m_id)
            if not info: continue
            if info.season > season: break
            if info.season == season and info.round >= round_num: break
            if info.season == season:
                last_elo = elo
                
        return last_elo
'''

code += get_elo_func

with open('Core/engine_data.py', 'w', encoding='utf-8') as f:
    f.write(code)

print("Injected ELO into engine_data.py")
