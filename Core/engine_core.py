from models import TransitionEdge, TeamProfile
from typing import List, Dict, Tuple, Optional, Any
from models import TransitionEdge, TeamProfile

class Node:
    def __init__(self, name: str):
        self.name = name
        # Dictionary of destination_node_name -> score
        self.edges: Dict[str, float] = {}

class Graph:
    def __init__(self, team_id: str):
        self.team_id = team_id
        self.nodes: Dict[str, Node] = {}
        # Define 5x3 Grid
        self.grid_names = [
            ["A1", "B1", "C1", "D1", "E1"],
            ["A2", "B2", "C2", "D2", "E2"],
            ["A3", "B3", "C3", "D3", "E3"]
        ]
        # Initialize nodes
        for row in self.grid_names:
            for name in row:
                self.nodes[name] = Node(name)
        self.nodes["SCORE"] = Node("SCORE")
        
        self.max_r = 2
        self.max_c = 4
        
        # Coordinate map for rotation
        self.pos_map: Dict[str, Tuple[int, int]] = {
            name: (r, c) for r, row in enumerate(self.grid_names) for c, name in enumerate(row)
        }

    def rotate_node(self, name: str) -> str:
        """Rotates a node name 180 degrees."""
        if name == "SCORE": return "SCORE"
        if name not in self.pos_map: return name
        r, c = self.pos_map[name]
        new_r = self.max_r - r
        new_c = self.max_c - c
        return self.grid_names[new_r][new_c]

    def add_edge_score(self, start: str, end: str, score: float, current_team: str):
        """Adds a score to an edge, handles perspective rotation if needed."""
        target_start = start
        target_end = end
        
        if current_team != self.team_id:
            target_start = self.rotate_node(start)
            target_end = self.rotate_node(end)
            score = -score # Penalty for opponent success
            
        if target_start in self.nodes:
            current_score = self.nodes[target_start].edges.get(target_end, 0.0)
            self.nodes[target_start].edges[target_end] = current_score + score

    def get_edge_matrix(self) -> Dict[TransitionEdge, float]:
        """Returns a flat mapping of (start, end) -> score."""
        matrix = {}
        for name, node in self.nodes.items():
            for target, score in node.edges.items():
                matrix[TransitionEdge(name, target)] = score
        return matrix

def physical_placement(start: str, end: str, is_away_edge: bool = False,
                       frame: str = 'home') -> Tuple[str, str]:
    """Pure placement math used by vector_renderer (audit E4 / LFP->FB fix).

    frame='home' -> edge keys are already in the HOME team's frame (delta
        matrices, home-team profiles): draw zones as-is; only map the goal
        endpoint to the away end for away-owned edges.
    frame='team' -> keys are in the panel team's OWN frame (away-team profile):
        zones rotate 180 deg onto the home-oriented field; the goal maps to the
        goal the edge OWNER attacks (own move -> AWAY_G, opponent -> SCORE).
    """
    g = Graph("util")
    if frame == 'team':
        phys_start = g.rotate_node(start)
        phys_end = g.rotate_node(end)
    else:
        phys_start = start
        phys_end = end
    if (frame == 'team' and not is_away_edge) or (frame == 'home' and is_away_edge):
        if phys_start == 'SCORE':
            phys_start = 'AWAY_G'
        elif phys_start == 'AWAY_G':
            phys_start = 'SCORE'
        if phys_end == 'SCORE':
            phys_end = 'AWAY_G'
        elif phys_end == 'AWAY_G':
            phys_end = 'SCORE'
    return phys_start, phys_end

class MatchupEngine:
    @staticmethod
    def calculate_delta(team_a_matrix: Dict[TransitionEdge, float], 
                        team_b_matrix: Dict[TransitionEdge, float]) -> Dict[TransitionEdge, float]:
        """
        Calculates the Vector Delta between two teams.
        Both matrices are assumed to be in their respective 'base' attacking perspectives.
        To compare them, Team B's matrix is effectively rotated into Team A's frame.
        """
        # Note: In our Graph logic, 'team_b_matrix' already contains scores 
        # that were added relative to Team B's attacking perspective.
        # When comparing, Team A's edge (C2->D2) matches Team B's rotated edge (C2->B2).
        
        # Helper to rotate an edge key
        def rotate_edge(edge: TransitionEdge, g: Graph) -> TransitionEdge:
            return TransitionEdge(g.rotate_node(edge.source), g.rotate_node(edge.target))

        # Create a dummy graph for rotation utilities
        g = Graph("util")
        
        delta_matrix = {}
        # Union of Team A's edges and Team B's rotated edges to ensure mathematical symmetry
        all_possible_edges = set(team_a_matrix.keys()).union(
            rotate_edge(edge_b, g) for edge_b in team_b_matrix.keys()
        )
        
        for edge_a in all_possible_edges:
            val_a = team_a_matrix.get(edge_a, 0.0)
            edge_b_rotated = rotate_edge(edge_a, g)
            val_b = team_b_matrix.get(edge_b_rotated, 0.0)
            
            delta_matrix[edge_a] = val_a - val_b
            
        return delta_matrix
