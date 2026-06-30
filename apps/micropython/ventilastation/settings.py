# Persistent settings live in NVS so they survive firmware/filesystem reflashes
# and are shared with the native retro-go apps. pov_column_offset is stored under
# NVS namespace "voom_pov" / key "col_offset" (i32) — the exact key prboom-go and
# gwenesis read for the POV rotation calibration, so no separate sync is needed.
#
# On the desktop emulator there is no esp32 NVS module; settings then fall back to
# in-memory defaults (the POV calibration is hardware-only and irrelevant there).

_NVS_NAMESPACE = "voom_pov"

# setting key -> NVS i32 key. Add future int settings here.
_NVS_KEYS = {
    "pov_column_offset": "col_offset",
}

_DEFAULTS = {
    "pov_column_offset": 0,
}

_settings = {}


def _nvs():
    import esp32
    return esp32.NVS(_NVS_NAMESPACE)


def load():
    global _settings
    _settings = dict(_DEFAULTS)
    for key, nvs_key in _NVS_KEYS.items():
        try:
            _settings[key] = _nvs().get_i32(nvs_key)
        except Exception:
            # Key unset yet, or no NVS (desktop) — keep the default.
            pass


def get(key, default=None):
    return _settings.get(key, default)


def set(key, value):
    _settings[key] = value


def save():
    for key, nvs_key in _NVS_KEYS.items():
        if key not in _settings:
            continue
        try:
            nvs = _nvs()
            nvs.set_i32(nvs_key, int(_settings[key]))
            nvs.commit()
        except Exception:
            print("settings: NVS save skipped (no esp32?)")
