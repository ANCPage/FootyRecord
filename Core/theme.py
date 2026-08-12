import os

from matplotlib.font_manager import FontProperties

from Core.config import FONTS_DIR

FASTER_ONE = os.path.join(FONTS_DIR, 'FasterOne.ttf')
WALLPOET = os.path.join(FONTS_DIR, 'Wallpoet.ttf')
ROBOTO = os.path.join(FONTS_DIR, 'Roboto-Regular.ttf')

# Standard colors
BG_COLOR = '#F4F1EA'
TEXT_COLOR = '#3E3A35'
SUB_TEXT_COLOR = '#6A655F'
HEADER_BG = '#3E3A35'
HEADER_TEXT = '#F4F1EA'

def mute_color(hex_color):
    """
    Blends hex_color with BG_COLOR to desaturate/mute it.
    70% hex_color + 30% BG_COLOR
    """
    if not hex_color or not str(hex_color).startswith('#') or len(str(hex_color)) != 7:
        return hex_color

    try:
        # Parse hex to RGB
        r1, g1, b1 = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
        r2, g2, b2 = int(BG_COLOR[1:3], 16), int(BG_COLOR[3:5], 16), int(BG_COLOR[5:7], 16)

        # Blend
        r = int(r1 * 0.7 + r2 * 0.3)
        g = int(g1 * 0.7 + g2 * 0.3)
        b = int(b1 * 0.7 + b2 * 0.3)

        return f"#{r:02x}{g:02x}{b:02x}".upper()
    except ValueError:
        return hex_color

def is_dark_color(hex_color: str) -> bool:
    """
    Checks if a hex color is dark enough for light text overlays.
    """
    if not hex_color:
        return False
    hex_color = str(hex_color).lstrip('#')
    if len(hex_color) != 6:
        return False
    try:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return (r * 0.299 + g * 0.587 + b * 0.114) < 60
    except ValueError:
        return False

def get_fonts():
    """
    Returns (prop_title, prop_sub, prop_body)
    - prop_title: Level 1 (FasterOne) - main headings/suptitles
    - prop_sub: Level 2 (Wallpoet) - sub-titles, table headers, primary data values
    - prop_body: Level 3 (Roboto-Regular) - small details, fine print
    """
    prop_title = FontProperties(fname=FASTER_ONE)
    prop_sub = FontProperties(fname=WALLPOET)
    prop_body = FontProperties(fname=ROBOTO)

    return prop_title, prop_sub, prop_body

def get_ordinal(n):
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f"{n}{suffix}"
