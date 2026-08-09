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
