import re

with open('Core/engine_data.py', 'r', encoding='utf-8') as f:
    code = f.read()

new_methods = '''
    def get_team_tier(self, elo: float) -> str:
        if elo >= 1600: return "ELITE"
        if elo >= 1550: return "CONTENDER"
        if elo >= 1450: return "MID-TABLE"
        return "REBUILDING"

    def get_league_rankings(self, season: int, round_num: int) -> Dict[str, int]:
        from mappings import TEAM_DATA
        team_elos = []
        for team_id in TEAM_DATA.keys():
            elo = self.get_team_elo(team_id, season, round_num)
            team_elos.append((team_id, elo))
        
        # Sort by ELO descending
        team_elos.sort(key=lambda x: x[1], reverse=True)
        
        return {team_id: rank for rank, (team_id, elo) in enumerate(team_elos, 1)}
'''

code += new_methods

with open('Core/engine_data.py', 'w', encoding='utf-8', newline='') as f:
    f.write(code)

print("Added ranking and tier methods to engine_data.py")
