files = ["Core/engine_data.py", "Core/engine_core.py", "Core/visualize_story.py", "Core/visualize_matchup.py", "generate_round_images.py", "predict_game.py"]
for f in files:
    try:
        with open(f, "r", encoding="utf-8-sig") as fh:
            content = fh.read()
        with open(f, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
        print(f"Stripped BOM from {f}")
    except Exception as e:
        print(e)
