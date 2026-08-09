import re

with open("Core/engine_data.py", "r") as f:
    code = f.read()

load_cache_logic = """
    def load_all_data(self):
        import pickle
        cache_dir = os.path.join(self.csv_dir, '.cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, 'ingestor_state.pkl')
        
        files = glob.glob(os.path.join(self.csv_dir, 'flattened_stats_202*.csv'))
        files = [f for f in files if 'simple' not in f]
        
        if os.path.exists(cache_path):
            cache_mtime = os.path.getmtime(cache_path)
            if all(os.path.getmtime(f) <= cache_mtime for f in files):
                print('Loading data and profiled teams from cache...')
                with open(cache_path, 'rb') as f:
                    state = pickle.load(f)
                self.__dict__.update(state)
                self._skip_profiling = True
                return
                
        self._skip_profiling = False
        print(f'Loading {len(files)} seasonal data files...')"""

code = re.sub(r'    def load_all_data\(self\):\n        files = glob\.glob[^\n]+\n        files = \[f for f in files if \'simple\' not in f\]\n        print\(f\'Loading \{len\(files\)\} seasonal data files\.\.\.\'\)', load_cache_logic, code, count=1)

profile_start_logic = """    def profile_all_teams(self):
        if getattr(self, '_skip_profiling', False):
            return
            
        sorted_matches = sorted(self.match_info.keys(), key=lambda x: (self.match_info[x]['season'], self.match_info[x]['round']))"""

code = re.sub(r'    def profile_all_teams\(self\):\n        sorted_matches = sorted\(self\.match_info\.keys\(\), key=lambda x: \(self\.match_info\[x\]\[\'season\'\], self\.match_info\[x\]\[\'round\'\]\)\)', profile_start_logic, code, count=1)

# Replace player_scores saving
player_score_old = """            self.team_player_history[h_team].append((m_id, h_player_scores))
            self.team_player_history[a_team].append((m_id, a_player_scores))"""
player_score_new = """            self.team_player_history[h_team].append((m_id, {k: dict(v) for k, v in h_player_scores.items()}))
            self.team_player_history[a_team].append((m_id, {k: dict(v) for k, v in a_player_scores.items()}))"""

code = code.replace(player_score_old, player_score_new)

# Add saving state at the end of profile_all_teams
# The end of profile_all_teams is before `def get_team_average_matrix`
cache_save_logic = """            if m_id in self.match_performance:
                from engine_core import MatchupEngine
                self.match_performance[m_id]['actual'] = sum(MatchupEngine.calculate_delta(h_mat, a_mat).values())

        import pickle
        cache_dir = os.path.join(self.csv_dir, '.cache')
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, 'ingestor_state.pkl')
        print("Saving state to cache...")
        with open(cache_path, 'wb') as f:
            pickle.dump(self.__dict__, f)

    def get_team_average_matrix"""

code = code.replace("""            if m_id in self.match_performance:
                from engine_core import MatchupEngine
                self.match_performance[m_id]['actual'] = sum(MatchupEngine.calculate_delta(h_mat, a_mat).values())

    def get_team_average_matrix""", cache_save_logic)


with open("Core/engine_data.py", "w") as f:
    f.write(code)

print("Injected caching logic.")
