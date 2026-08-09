from dataclasses import dataclass
from typing import Dict, List, Any

@dataclass(frozen=True)
class TransitionEdge:
    source: str
    target: str

@dataclass
class TeamProfile:
    team_id: str
    edges: Dict[TransitionEdge, float]

@dataclass(frozen=True)
class Coordinate:
    x: float
    y: float
    
    def to_grid(self, venue_length: float, venue_width: float) -> str:
        """Maps physical coordinates to the 5x3 AFL oval grid."""
        import math
        nx, ny = self.x, self.y
        if not venue_length or not venue_width:
            return ""
        a = venue_length / 2.0
        b = venue_width / 2.0
        u = nx / a
        v = ny / b
        r_sq = u**2 + v**2
        if r_sq > 1.0:
            norm = math.sqrt(r_sq)
            u /= norm
            v /= norm
        if u == 0 and v == 0:
            sx, sy = 0.0, 0.0
        elif abs(u) >= abs(v):
            if u > 0:
                sx = math.sqrt(u**2 + v**2)
                sy = sx * (4 / math.pi) * math.atan2(v, u)
            else:
                sx = -math.sqrt(u**2 + v**2)
                sy = -sx * (4 / math.pi) * math.atan2(v, -u)
        else:
            if v > 0:
                sy = math.sqrt(u**2 + v**2)
                sx = sy * (4 / math.pi) * math.atan2(u, v)
            else:
                sy = -math.sqrt(u**2 + v**2)
                sx = -sy * (4 / math.pi) * math.atan2(u, -v)
        col_idx = max(0, min(4, int((sx + 1.0) / 2.0 * 5)))
        row_idx = max(0, min(2, int((sy + 1.0) / 2.0 * 3)))
        return f"{['A', 'B', 'C', 'D', 'E'][col_idx]}{['1', '2', '3'][row_idx]}"

@dataclass
class Player:
    player_id: str
    name: str

@dataclass
class Team:
    team_id: str
    name: str
    primary_color: str
    secondary_color: str
    
    @property
    def is_dark(self) -> bool:
        from theme import is_dark_color
        return is_dark_color(self.primary_color)

@dataclass
class MatchInfo:
    season: int
    round: int
    home: str
    away: str
    match_id: str = ""
    home_score: int = 0
    away_score: int = 0
    
    @property
    def round_num(self) -> int:
        return self.round
        
    @property
    def home_team(self) -> Team:
        from mappings import TEAM_DATA
        t_data = TEAM_DATA.get(self.home, {'name': self.home, 'primary': '#333333', 'secondary': '#dddddd'})
        return Team(team_id=self.home, name=t_data['name'], primary_color=t_data['primary'], secondary_color=t_data['secondary'])
        
    @property
    def away_team(self) -> Team:
        from mappings import TEAM_DATA
        t_data = TEAM_DATA.get(self.away, {'name': self.away, 'primary': '#333333', 'secondary': '#dddddd'})
        return Team(team_id=self.away, name=t_data['name'], primary_color=t_data['primary'], secondary_color=t_data['secondary'])
        
    @property
    def winner(self):
        """Actual winner as a Team, or None on a draw (strict comparison)."""
        if self.home_score > self.away_score:
            return self.home_team
        if self.away_score > self.home_score:
            return self.away_team
        return None  # draw
