# settings_manager.py
import json
from pathlib import Path

SETTINGS_PATH = Path(__file__).parent / "settings.json"

DEFAULT_SETTINGS = {
    "bar_position": "bottom_center",   # bottom_center/bottom_left/bottom_right/top_center/top_left/top_right
    "bar_style": "line",               # line/dot/button/tray_only
    "bar_size": "medium",              # small/medium/large (sadece line için)
    "bar_visible": True,
    "bar_opacity": 0.9,
    "window_width": 520,
    "window_height": 800,
    "hotkey_toggle": "ctrl+shift+b",
    "hotkey_show": "ctrl+shift+p",
    "killswitch_enabled": False,
}


def load_settings():
    if not SETTINGS_PATH.exists():
        return dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in DEFAULT_SETTINGS.items():
            if k not in data:
                data[k] = v
        return data
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(settings):
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


# Bar boyutları (sadece "line" tarzı için)
BAR_CONFIGS = {
    "small":  {"win_w": 160, "win_h": 16, "btn_w": 130, "btn_h": 8,  "radius": 4},
    "medium": {"win_w": 220, "win_h": 22, "btn_w": 180, "btn_h": 12, "radius": 6},
    "large":  {"win_w": 320, "win_h": 30, "btn_w": 270, "btn_h": 18, "radius": 9},
}


def get_bar_config(size):
    return BAR_CONFIGS.get(size, BAR_CONFIGS["medium"])


# Tarz bazlı boyutlar
STYLE_SIZES = {
    "line":   None,  # bar_size'tan alınır
    "dot":    {"win_w": 30,  "win_h": 30, "btn_w": 24,  "btn_h": 24, "radius": 12},
    "button": {"win_w": 110, "win_h": 36, "btn_w": 100, "btn_h": 30, "radius": 8},
    "tray_only": {"win_w": 1, "win_h": 1, "btn_w": 1, "btn_h": 1, "radius": 0},
}


def get_bar_style_config(style, size="medium"):
    """Tarz + boyut kombinasyonundan pencere/buton ölçüleri döner."""
    if style == "line":
        return get_bar_config(size)
    return STYLE_SIZES.get(style, STYLE_SIZES["line"])


def calc_position(position, win_w, win_h, screen_w, screen_h):
    """Konuma göre x, y hesaplar."""
    margin = 65      # görev çubuğu için alt boşluk
    margin_top = 10  # üst için

    if position == "bottom_center":
        x = int((screen_w / 2) - (win_w / 2))
        y = int(screen_h - margin - (win_h - 16))
    elif position == "bottom_left":
        x = 20
        y = int(screen_h - margin - (win_h - 16))
    elif position == "bottom_right":
        x = int(screen_w - win_w - 20)
        y = int(screen_h - margin - (win_h - 16))
    elif position == "top_center":
        x = int((screen_w / 2) - (win_w / 2))
        y = margin_top
    elif position == "top_left":
        x = 20
        y = margin_top
    elif position == "top_right":
        x = int(screen_w - win_w - 20)
        y = margin_top
    else:
        x = int((screen_w / 2) - (win_w / 2))
        y = int(screen_h - margin - (win_h - 16))

    return x, y