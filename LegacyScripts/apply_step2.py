import re

# 1. Update engine_scraper.py
with open("Core/engine_scraper.py", "r") as f:
    code = f.read()

# _ensure_token update
ensure_token_old = """    def _ensure_token(self):
        with self._token_lock:
            if self._token: return True
            try:
                resp = self._session.post(config.AFL_AUTH_URL, json={}, timeout=15)
                resp.raise_for_status()
                self._token = resp.json().get('token')
                return self._token is not None
            except Exception: return False"""

ensure_token_new = """    def _ensure_token(self):
        with self._token_lock:
            if self._token: return True
            for attempt in range(config.MAX_RETRIES):
                try:
                    resp = self._session.post(config.AFL_AUTH_URL, json={}, timeout=15)
                    resp.raise_for_status()
                    self._token = resp.json().get('token')
                    return self._token is not None
                except Exception as e:
                    time.sleep(1.5 ** attempt)
            return False"""

code = code.replace(ensure_token_old, ensure_token_new)

# _fetch_match update
fetch_match_old = """            except Exception:
                if attempt == config.MAX_RETRIES - 1: return None
                time.sleep(1)"""

fetch_match_new = """            except Exception as e:
                if attempt == config.MAX_RETRIES - 1:
                    print(f"Failed to fetch {match_id}: {e}")
                    return None
                time.sleep(1.5 ** attempt)"""

code = code.replace(fetch_match_old, fetch_match_new)

with open("Core/engine_scraper.py", "w") as f:
    f.write(code)

# 2. Update engine_data.py
with open("Core/engine_data.py", "r") as f:
    code_data = f.read()

loop_old = """                for row in reader:
                    m_id = row['matchId']
                    r_num = int(row['round'])
                    if r_num > 24: continue 
                    if m_id not in self.match_info:
                        self.match_info[m_id] = {'season': int(row['season']), 'round': r_num, 'home': row['homeTeamId'], 'away': row['awayTeamId']}
                    if row['chain_finalState_class'] == 'SCORE' and row['stat_shotAtGoal'] != '':
                        match_scores[m_id][row['stat_teamId']] += 1
                    c_idx = row['chain_index']
                    c_id = f'{m_id}_{c_idx}'
                    chains_raw[c_id]['team'] = row['chain_teamId']
                    chains_raw[c_id]['outcome'] = row['chain_finalState_class']
                    chains_raw[c_id]['matchId'] = m_id
                    stat_key = (row['chain_period'], row['stat_periodSeconds'], row['x'], row['y'], row['stat_playerId'])
                    if stat_key in seen_stats: continue
                    seen_stats.add(stat_key)
                    if row['x'] and row['y'] and row['stat_class'] in ['POSSESSION', 'DISPOSAL', 'SCORE']:
                        grid_cell = _get_grid_cell(row['x'], row['y'], row['venueLength'], row['venueWidth'])
                        if grid_cell:
                            chains_raw[c_id]['grids'].append(grid_cell)
                            chains_raw[c_id]['players'].append(row['stat_playerId'])"""

loop_new = """                for row_idx, row in enumerate(reader):
                    try:
                        m_id = row['matchId']
                        if not m_id: continue
                        r_num = int(row['round'])
                        if r_num > 24: continue 
                        if m_id not in self.match_info:
                            self.match_info[m_id] = {'season': int(row['season']), 'round': r_num, 'home': row['homeTeamId'], 'away': row['awayTeamId']}
                        if row.get('chain_finalState_class') == 'SCORE' and row.get('stat_shotAtGoal') != '':
                            match_scores[m_id][row['stat_teamId']] += 1
                        c_idx = row['chain_index']
                        c_id = f'{m_id}_{c_idx}'
                        chains_raw[c_id]['team'] = row['chain_teamId']
                        chains_raw[c_id]['outcome'] = row['chain_finalState_class']
                        chains_raw[c_id]['matchId'] = m_id
                        stat_key = (row['chain_period'], row['stat_periodSeconds'], row['x'], row['y'], row['stat_playerId'])
                        if stat_key in seen_stats: continue
                        seen_stats.add(stat_key)
                        if row['x'] and row['y'] and row['stat_class'] in ['POSSESSION', 'DISPOSAL', 'SCORE']:
                            grid_cell = _get_grid_cell(row['x'], row['y'], row['venueLength'], row['venueWidth'])
                            if grid_cell:
                                chains_raw[c_id]['grids'].append(grid_cell)
                                chains_raw[c_id]['players'].append(row['stat_playerId'])
                    except Exception as e:
                        print(f"Skipping malformed row {row_idx} in {f_path}: {e}")
                        continue"""

code_data = code_data.replace(loop_old, loop_new)

with open("Core/engine_data.py", "w") as f:
    f.write(code_data)

# 3. Update generate_round_images.py
with open("generate_round_images.py", "r") as f:
    code_img = f.read()

# Enhance exception logging
img_err_old = """        except Exception as e:
            print(f"Error: {e}")"""

img_err_new = """        except Exception as e:
            print(f"Error processing {mid} ({h_n} vs {a_n}): {e}")"""

code_img = code_img.replace(img_err_old, img_err_new)

with open("generate_round_images.py", "w") as f:
    f.write(code_img)

print("Applied error handling and state recovery.")
