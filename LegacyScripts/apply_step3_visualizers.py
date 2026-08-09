import re
import os
from typing import Dict, List, Tuple

def update_file(filepath):
    with open(filepath, "r") as f:
        code = f.read()
        
    code = code.replace("edge[0]", "edge.source")
    code = code.replace("edge[1]", "edge.target")
    
    if "from models import TransitionEdge" not in code:
        if "from theme import" in code:
            code = code.replace("from theme import", "from models import TransitionEdge\nfrom theme import")
        elif "from engine_data import" in code:
            code = code.replace("from engine_data import", "from models import TransitionEdge\nfrom engine_data import")

    if filepath.endswith("generate_round_images.py"):
        code = code.replace("actual_edge = (rotate(edge.source), rotate(edge.target))", "actual_edge = TransitionEdge(rotate(edge.source), rotate(edge.target))")

    with open(filepath, "w") as f:
        f.write(code)

update_file("Core/visualize_story.py")
update_file("Core/visualize_matchup.py")
update_file("generate_round_images.py")
update_file("predict_game.py")
print("Updated visualizer scripts to use TransitionEdge attributes.")
