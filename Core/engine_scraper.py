import os
import json
import csv
import time
import math
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
import config

# Defined classifications from user feedback and analysis
DISPOSAL_DESC = {'Kick', 'Handball', 'Ground Kick'}

POSSESSION_DESC = {
    'Gather', 'Loose Ball Get', 'Hard Ball Get', 'Uncontested Mark', 'Contested Mark', 
    'Mark On Lead', 'Handball Received', 'Gather From Hitout', 'Gather from Opposition', 
    'Ruck Hard Ball Get', 'Loose Ball Get Crumb', 'Hard Ball Get Crumb', 
    'Free For', 'Free For: In Possession', 'Free Advantage', 'Free For: Off The Ball', 
    'Kickin play on'
}

DEFENSIVE_DESC = {'Spoil', 'Tackle', 'Contested Knock On'}
ERROR_DESC = {'Mark Fumbled', 'Mark Dropped', 'No Pressure Error', 'Out On Full After Kick'}
STOPPAGE_DESC = {'Centre Bounce', 'Ball Up Call'}
SCORE_DESC = {'Goal', 'Behind'}

# Chain Outcome Mapping
SCORE_STATES = {'goal', 'behind', 'rushed'}
TURNOVER_STATES = {'turnover', 'outOfBounds'}
STOPPAGE_STATES = {'ballUpCall', 'throwIn'}

MAX_WORKERS = 12
REQUEST_DELAY = 0.05

class AFLSpatialScraper:
    def __init__(self):
        self._token = None
        self._token_lock = threading.Lock()
        self._session = requests.Session()
        self._session.headers.update(config.AFL_HEADERS)

    def _ensure_token(self):
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
            return False

    def _fetch_match(self, match_id):
        if not self._ensure_token(): return None
        url = config.AFL_MATCH_PLAYS_URL.format(match_id)
        headers = {**{k: v for k, v in self._session.headers.items() if k.lower() != 'content-type'}, 'x-media-mis-token': self._token}
        for attempt in range(config.MAX_RETRIES):
            try:
                resp = requests.get(url, headers=headers, timeout=20)
                if resp.status_code == 404: return None
                if resp.status_code == 401:
                    self._refresh_token(); headers['x-media-mis-token'] = self._token
                    continue
                resp.raise_for_status()
                data = resp.json()
                return data[0] if isinstance(data, list) and data else data
            except Exception as e:
                if attempt == config.MAX_RETRIES - 1:
                    print(f"Failed to fetch {match_id}: {e}")
                    return None
                time.sleep(1.5 ** attempt)
        return None

    def _refresh_token(self):
        with self._token_lock: self._token = None
        return self._ensure_token()

    @staticmethod
    def _has_chain_data(data):
        return data and data.get('homeTeamId') is not None and len(data.get('matchChains', [])) > 0

    def _discover_segment(self, year):
        defaults = {'2021': '014', '2022': '014', '2023': '014', '2024': '014', '2025': '014', '2026': '014'}
        default = defaults.get(str(year), '014')
        if self._has_chain_data(self._fetch_match(f'CD_M{year}{default}0101')): return default
        for seg_num in range(1, 30):
            seg = f'{seg_num:03d}'
            if seg == default: continue
            if self._has_chain_data(self._fetch_match(f'CD_M{year}{seg}0101')): return seg
        return None

def get_grid_cell(nx, ny, v_l, v_w):
    if nx in ('', None) or ny in ('', None) or not v_l or not v_w: return ''
    a, b = v_l/2.0, v_w/2.0; u, v = nx/a, ny/b; r_sq = u**2+v**2
    if r_sq > 1.0: norm = math.sqrt(r_sq); u /= norm; v /= norm
    if u == 0 and v == 0: sx, sy = 0.0, 0.0
    elif abs(u) >= abs(v):
        if u > 0: sx = math.sqrt(u**2+v**2); sy = sx*(4/math.pi)*math.atan2(v, u)
        else: sx = -math.sqrt(u**2+v**2); sy = -sx*(4/math.pi)*math.atan2(v, -u)
    else:
        if v > 0: sy = math.sqrt(u**2+v**2); sx = sy*(4/math.pi)*math.atan2(u, v)
        else: sy = -math.sqrt(u**2+v**2); sx = -sy*(4/math.pi)*math.atan2(u, -v)
    col = max(0, min(4, int((sx+1.0)/2.0*5))); row = max(0, min(2, int((sy+1.0)/2.0*3)))
    cols = ['A','B','C','D','E']; rows = ['1','2','3']
    return f'{cols[col]}{rows[row]}'

def classify_stat(desc):
    if desc in DISPOSAL_DESC: return 'DISPOSAL'
    if desc in POSSESSION_DESC: return 'POSSESSION'
    if desc in DEFENSIVE_DESC: return 'DEFENSIVE'
    if desc in ERROR_DESC: return 'ERROR'
    if desc in STOPPAGE_DESC: return 'STOPPAGE'
    if desc in SCORE_DESC: return 'SCORE'
    return 'OTHER'

def classify_chain_outcome(state):
    if state in SCORE_STATES: return 'SCORE'
    if state in TURNOVER_STATES: return 'TURNOVER'
    if state in STOPPAGE_STATES: return 'STOPPAGE'
    return 'OTHER'

def process_single_match(data, year, r, g, wf, ws):
    match_id = data.get('matchId'); h_t, a_t = data.get('homeTeamId'), data.get('awayTeamId')
    h_dir = data.get('homeTeamDirectionQtr1'); v_l, v_w = data.get('venueLength'), data.get('venueWidth')
    seen = set()
    for c_idx, chain in enumerate(data.get('matchChains', [])):
        period = chain.get('period'); oc = classify_chain_outcome(chain.get('finalState'))
        to = str(c_idx+1) if oc == 'TURNOVER' and c_idx+1 < len(data.get('matchChains', [])) else ''
        for stat in chain.get('stats', []):
            pid = stat.get('playerId')
            if not pid: continue
            sec, sx, sy, desc = stat.get('periodSeconds'), stat.get('x'), stat.get('y'), stat.get('description')
            sc = classify_stat(desc); key = (period, sec, sx, sy, pid)
            if key in seen: continue
            seen.add(key)
            gc = get_grid_cell(sx, sy, v_l, v_w)
            wf.writerow([year, r, g, match_id, h_t, a_t, v_w, v_l, h_dir, c_idx, chain.get('teamId'), chain.get('initialState'), chain.get('finalState'), oc, to, period, chain.get('periodSeconds'), stat.get('displayOrder'), desc, sc, sec, pid, stat.get('teamId'), stat.get('disposal'), stat.get('shotAtGoal'), stat.get('behindInfo'), sx, sy, gc])
            ws.writerow([match_id, c_idx, period, sec, pid, stat.get('teamId'), desc, sc, oc, to, gc])

def update_all_data(output_dir, year=2026, force_rebuild=False, target_round=None):
    os.makedirs(output_dir, exist_ok=True); scraper = AFLSpatialScraper()
    hf = ['season','round','game','matchId','homeTeamId','awayTeamId','venueWidth','venueLength','homeTeamDirectionQtr1','chain_index','chain_teamId','chain_initialState','chain_finalState','chain_finalState_class','chain_turnoverTo_chainId','chain_period','chain_periodSeconds','stat_displayOrder','stat_description','stat_class','stat_periodSeconds','stat_playerId','stat_teamId','stat_disposal','stat_shotAtGoal','stat_behindInfo','x','y','grid']
    hs = ['matchId','chain_id','period','period_sec','player_id','team_id','description','stat_class','outcome','turnover_to_chain','grid']
    
    print(f'Updating Season {year}...')
    seg = scraper._discover_segment(year)
    if not seg: return

    csv_f = os.path.join(output_dir, f'flattened_stats_{year}.csv')
    csv_s = os.path.join(output_dir, f'flattened_stats_{year}_simple.csv')
    
    existing_matches = set()
    if not force_rebuild and os.path.exists(csv_s):
        with open(csv_s, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None) # skip header
            for row in reader:
                if row: existing_matches.add(row[0])
                
    mode = 'w' if force_rebuild or not os.path.exists(csv_f) else 'a'
    
    # Target specific round if requested, otherwise check rounds 0 to 24
    r_range = [target_round] if target_round is not None else range(0, 25)
    cands = [(r, g, f'CD_M{year}{seg}{r:02d}{g:02d}') for r in r_range for g in range(1, 12)]
    cands = [c for c in cands if c[2] not in existing_matches]
    
    if not cands:
        print("All requested matches are already downloaded. Use --force to rebuild.")
        return

    with open(csv_f, mode, newline='', encoding='utf-8') as ff, open(csv_s, mode, newline='', encoding='utf-8') as fs:
        wf, ws = csv.writer(ff), csv.writer(fs)
        if mode == 'w':
            wf.writerow(hf); ws.writerow(hs)
            
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futs = {pool.submit(scraper._fetch_match, mid): (r, g, mid) for r, g, mid in cands}
            for fut in as_completed(futs):
                r, g, mid = futs[fut]; data = fut.result()
                if scraper._has_chain_data(data): 
                    process_single_match(data, year, r, g, wf, ws)
                    print(f'  Added {mid} to dataset')
