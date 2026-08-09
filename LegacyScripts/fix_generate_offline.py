import re

with open('generate_round_images.py', 'r', encoding='utf-8') as f:
    code = f.read()

# Replace the API fetching block with local data from ingestor
old_block = '''    token = get_token()
    if not token: return

    target_season = int(args.comp_id[:4])
    base_images_dir = os.path.join(config.OUTPUT_DIR, str(target_season), f'R{args.round}')'''

new_block = '''    target_season = int(args.comp_id[:4])
    base_images_dir = os.path.join(config.OUTPUT_DIR, str(target_season), f'R{args.round}')'''

code = code.replace(old_block, new_block)

old_loop = '''    for g in range(1, 11):
        mid = f'CD_M{args.comp_id}{args.round:02d}{g:02d}'
        data = fetch_match_data(mid, token)
        if not data or 'match' not in data: continue
            
        m = data['match']
        r_data = data.get('matchRoster', {})
        h_id, a_id = m['homeTeamId'], m['awayTeamId']
        h_n, a_n = m['homeTeam']['name'], m['awayTeam']['name']
        print(f'Game {g}: {h_n} ({h_id}) vs {a_n} ({a_id})')
        print(f'\\nProcessing Game {g}: {h_n} vs {a_n}')'''

new_loop = '''    for g in range(1, 11):
        mid = f'CD_M{args.comp_id}{args.round:02d}{g:02d}'
        if mid not in ingestor.match_info: continue
        
        info = ingestor.match_info[mid]
        h_id, a_id = info.home, info.away
        h_n = TEAM_DATA.get(h_id, {'name': h_id})['name']
        a_n = TEAM_DATA.get(a_id, {'name': a_id})['name']
        r_data = {}
        
        print(f'Game {g}: {h_n} ({h_id}) vs {a_n} ({a_id})')
        print(f'\\nProcessing Game {g}: {h_n} vs {a_n}')'''

code = code.replace(old_loop, new_loop)

with open('generate_round_images.py', 'w', encoding='utf-8') as f:
    f.write(code)
