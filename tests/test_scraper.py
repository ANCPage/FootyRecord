"""Integration tests for the scraper with a mocked AFL API (audit #21).

Covers: auth token flow, 401 refresh-and-retry, 404 skip, and CSV output
with the cleaned header (no norm_x/norm_y, no x_norm/y_norm).
"""
import csv
import os

import Core.engine_scraper as sc


def fake_match_payload(match_id='CD_M20260140101'):
    return {
        'matchId': match_id,
        'homeTeamId': 'H', 'awayTeamId': 'A',
        'venueLength': 170, 'venueWidth': 130,
        'homeTeamDirectionQtr1': 1,
        'matchChains': [{
            'period': 1, 'finalState': 'goal', 'teamId': 'H',
            'stats': [{
                'playerId': 'P1', 'periodSeconds': 10, 'x': 70, 'y': 0,
                'description': 'Goal', 'teamId': 'H',
                'disposal': 0, 'shotAtGoal': 1, 'behindInfo': None,
                'displayOrder': 1,
            }],
        }],
    }


class FakeResp:
    def __init__(self, payload=None, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f'HTTP {self.status_code}')


def test_update_all_data_writes_clean_csv(tmp_path, monkeypatch):
    calls = {'get': 0}

    def fake_ensure_token(self):
        self._token = 'tok-123'
        return True

    def fake_get(url, headers=None, timeout=None):
        calls['get'] += 1
        return FakeResp(fake_match_payload())

    monkeypatch.setattr(sc.AFLSpatialScraper, '_ensure_token', fake_ensure_token)
    monkeypatch.setattr(sc.requests, 'get', fake_get)

    out = str(tmp_path)
    sc.update_all_data(out, year=2026, target_round=1)

    main_csv = os.path.join(out, 'flattened_stats_2026.csv')
    simple_csv = os.path.join(out, 'flattened_stats_2026_simple.csv')
    assert os.path.exists(main_csv) and os.path.exists(simple_csv)

    with open(main_csv, newline='', encoding='utf-8') as f:
        header = next(csv.reader(f))
    assert 'norm_x' not in header and 'norm_y' not in header
    assert 'grid' in header
    with open(simple_csv, newline='', encoding='utf-8') as f:
        header_s = next(csv.reader(f))
    assert 'x_norm' not in header_s and 'y_norm' not in header_s


def test_fetch_match_401_refreshes_token(monkeypatch):
    scraper = sc.AFLSpatialScraper()
    scraper._token = 'old-token'

    def refresh():
        scraper._token = 'new-token'
        return True

    monkeypatch.setattr(scraper, '_refresh_token', refresh)

    def fake_get(url, headers=None, timeout=None):
        if headers.get('x-media-mis-token') == 'old-token':
            return FakeResp(status=401)
        return FakeResp(fake_match_payload())

    monkeypatch.setattr(sc.requests, 'get', fake_get)
    data = scraper._fetch_match('CD_M20260140101')
    assert data is not None and data['homeTeamId'] == 'H'


def test_fetch_match_404_returns_none(monkeypatch):
    scraper = sc.AFLSpatialScraper()
    scraper._token = 'tok'

    def fake_get(url, headers=None, timeout=None):
        return FakeResp(status=404)

    monkeypatch.setattr(sc.requests, 'get', fake_get)
    assert scraper._fetch_match('CD_M2026999999') is None


def test_ensure_token_retries_then_fails(monkeypatch):
    scraper = sc.AFLSpatialScraper()

    def fake_post(url, json=None, timeout=None):
        return FakeResp(status=500)

    # auth goes through the SESSION, not module-level requests
    monkeypatch.setattr(scraper._session, 'post', fake_post)
    assert scraper._ensure_token() is False


def test_main_parser_builds():
    """Regression (2026-08-12): the packaging conversion broke `main.py update`
    — `from Core.config import config` binds the Settings INSTANCE, so the old
    `config.config.window_size` died with AttributeError at parser build time
    (the re-scrape recipe crashed before reaching the scraper). build_parser()
    must construct without raising; the update branch reads config.data_dir."""
    from Core.main import build_parser
    p = build_parser()
    ns = p.parse_args(['update', '--target_round', '24'])
    assert ns.command == 'update' and ns.target_round == 24
