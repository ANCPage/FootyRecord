with open("generate_round_images.py", "r", encoding="utf-8") as f:
    code = f.read()

# Ensure tip object contains IDs for lookup
code = code.replace(
    "'away_name': a_name_mapped,",
    "'home_id': h_id, 'away_id': a_id, 'away_name': a_name_mapped,"
)

with open("generate_round_images.py", "w", encoding="utf-8") as f:
    f.write(code)
