TEAM_DATA = {
    'CD_T10': {'name': 'Adelaide Crows', 'primary': '#002B5C', 'secondary': '#E21937'},
    'CD_T20': {'name': 'Brisbane Lions', 'primary': '#730040', 'secondary': '#FDB813'},
    'CD_T30': {'name': 'Carlton', 'primary': '#031A29', 'secondary': '#FFFFFF'},
    'CD_T40': {'name': 'Collingwood', 'primary': '#000000', 'secondary': '#FFFFFF'},
    'CD_T50': {'name': 'Essendon', 'primary': '#000000', 'secondary': '#CC2031'},
    'CD_T60': {'name': 'Fremantle', 'primary': '#2A1A54', 'secondary': '#FFFFFF'},
    'CD_T70': {'name': 'Geelong Cats', 'primary': '#1C3C63', 'secondary': '#FFFFFF'},
    'CD_T80': {'name': 'Hawthorn', 'primary': '#4D2004', 'secondary': '#FBBC08'},
    'CD_T90': {'name': 'Melbourne', 'primary': '#0F1131', 'secondary': '#CC2031'},
    'CD_T100': {'name': 'North Melbourne', 'primary': '#003087', 'secondary': '#FFFFFF'},
    'CD_T110': {'name': 'Port Adelaide', 'primary': '#008AAB', 'secondary': '#000000'},
    'CD_T120': {'name': 'Richmond', 'primary': '#000000', 'secondary': '#FFD200'},
    'CD_T130': {'name': 'St Kilda', 'primary': '#ED0F05', 'secondary': '#FFFFFF'},
    'CD_T140': {'name': 'Western Bulldogs', 'primary': '#014896', 'secondary': '#C70136'},
    'CD_T150': {'name': 'West Coast Eagles', 'primary': '#002B5C', 'secondary': '#F2AA00'},
    'CD_T160': {'name': 'Sydney Swans', 'primary': '#ED171F', 'secondary': '#FFFFFF'},
    'CD_T1000': {'name': 'Gold Coast Suns', 'primary': '#E11B0A', 'secondary': '#FFD200'},
    'CD_T1010': {'name': 'GWS Giants', 'primary': '#F15C22', 'secondary': '#231F20'}
}

# Legacy mapping for backwards compatibility
TEAM_MAP = {k: v['name'] for k, v in TEAM_DATA.items()}

def get_short_name(name: str) -> str:
    """
    Abbreviates long team names for visualization purposes.
    """
    short_names = {
        'North Melbourne': 'Nth Melb',
        'Port Adelaide': 'Port Adel',
        'West Coast Eagles': 'West Coast',
        'Gold Coast Suns': 'Gold Coast',
        'Sydney Swans': 'Sydney',
        'Geelong Cats': 'Geelong',
        'Western Bulldogs': 'Bulldogs',
        'Adelaide Crows': 'Adelaide',
        'Brisbane Lions': 'Brisbane',
        'GWS Giants': 'GWS'
    }
    return short_names.get(name, name)


# ---- Club card colours (2026-09-05, Austin's policy) -----------------------
# PRIMARY = the club's true identity colour on the cream card; ALTS = real
# clash colours, 'WHITE' = the club's genuine white away guernsey (rendered
# as ink-outlined white ribbons by the template). Policy: the fixture HOME
# always wears primary; the AWAY side wears primary too unless its primary
# clashes with the home primary (CIELAB dE < 60), then its best real alt.
TEAM_COLOURS = {
    'CD_T10':  ('#002B5C', ['#E21937', '#F2A900']),   # Adelaide
    'CD_T20':  ('#730040', ['#FDB813']),              # Brisbane (maroon/gold)
    'CD_T30':  ('#031A29', ['WHITE']),                # Carlton
    'CD_T40':  ('#101820', ['WHITE']),                # Collingwood
    'CD_T50':  ('#CC2031', ['#101820']),              # Essendon (red primary)
    'CD_T60':  ('#5A2A82', ['WHITE']),                # Fremantle
    'CD_T70':  ('#1C3C63', ['WHITE']),                # Geelong
    'CD_T80':  ('#4D2004', ['#FBBC08']),              # Hawthorn
    'CD_T90':  ('#0F1131', ['#CC2031', '#1A3B8E']),   # Melbourne
    'CD_T100': ('#1A3B8E', ['WHITE']),                # North Melbourne (royal)
    'CD_T110': ('#00A5AC', ['#101820']),              # Port Adelaide
    'CD_T120': ('#101820', ['#FFD200']),              # Richmond
    'CD_T130': ('#ED0F05', ['#101820']),              # St Kilda
    'CD_T140': ('#014896', ['#C70136']),              # Western Bulldogs
    'CD_T150': ('#002B5C', ['#F2AA00']),              # West Coast
    'CD_T160': ('#ED171F', ['WHITE']),                # Sydney
    'CD_T1000': ('#E11B0A', ['#FFD200']),             # Gold Coast
    'CD_T1010': ('#F15C22', ['#231F20']),             # GWS
}

CREAM_HEX = '#F1EDE3'


def _rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _dE(h1, h2):
    def f(t):
        t /= 255.0
        return t / 12.92 if t <= 0.04045 else ((t + 0.055) / 1.055) ** 2.4

    def lab(h):
        r, g, b = (f(v) * 100 for v in (_rgb(h) if isinstance(h, str) else h))
        X = r * 0.4124 + g * 0.3576 + b * 0.1805
        Y = r * 0.2126 + g * 0.7152 + b * 0.0722
        Z = r * 0.0193 + g * 0.1192 + b * 0.9505

        def g_(t):
            return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116
        fx, fy, fz = g_(X / 95.047), g_(Y / 100.0), g_(Z / 108.883)
        return (116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz))
    La, Aa, Ba = lab(h1)
    Lb, Ab, Bb = lab(h2)
    return ((La - Lb) ** 2 + (Aa - Ab) ** 2 + (Ba - Bb) ** 2) ** 0.5


def worn_colours(home_id: str, away_id: str):
    """(home_worn, away_worn) per the club-colour policy."""
    hp = TEAM_COLOURS[home_id][0]
    ap = TEAM_COLOURS[away_id][0]
    if _dE(hp, ap) >= 60.0:
        return hp, ap
    best, best_d = ap, _dE(hp, ap)
    for a in TEAM_COLOURS[away_id][1]:
        da = 60.0 if a == 'WHITE' else min(_dE(a, hp), _dE(a, CREAM_HEX))
        if da > best_d:
            best, best_d = a, da
    return hp, best
