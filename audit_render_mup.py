import sys
sys.path.insert(0, 'Core')
from engine_data import DataIngestor
from engine_core import MatchupEngine
from visualize_matchup import MatchupVisualizer

csv_path = 'CSV_DATA'
ingestor = DataIngestor(csv_path)
ingestor.load_all_data()
ingestor.profile_all_teams()

h_id, a_id = 'CD_T80', 'CD_T100'  # Hawthorn vs North Melbourne (R21 G6)

m_a = ingestor.get_team_average_matrix(h_id)
m_b = ingestor.get_team_average_matrix(a_id)
delta = MatchupEngine.calculate_delta(m_a, m_b)

viz = MatchupVisualizer()
viz.draw_full_matchup(
    h_id, a_id, m_a, m_b, delta,
    save_prefix='audit_G6_Hawthorn_Norf',
    is_mobile=False,
    elo_a=ingestor.get_team_elo(h_id, 2026, 21),
    elo_b=ingestor.get_team_elo(a_id, 2026, 21),
    rank_a=None, rank_b=None, tier_a=None, tier_b=None,
)
print("saved audit_G6_Hawthorn_Norf.png")
