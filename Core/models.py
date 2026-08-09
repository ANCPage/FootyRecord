from dataclasses import dataclass
from typing import Dict


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
        from geometry import xy_to_grid
        return xy_to_grid(self.x, self.y, venue_length, venue_width)

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
