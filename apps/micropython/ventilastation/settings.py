import ujson
SETTINGS_FILE = "ventilastation/settings.json"
_settings = {}

def load():
    global _settings

    try:
        with open(SETTINGS_FILE, "r") as f:
            _settings = ujson.load(f)
            return
    except Exception:
        _settings = {
            "pov_column_offset": 0,
        }
        save()

def get(key, default=None):
    return _settings.get(key, default)

def set(key, value):
    _settings[key] = value

def save():
    print("Saving settings...")
    try:
        with open(SETTINGS_FILE, "w") as f:
            ujson.dump(_settings, f)
    except Exception:
        print("Error saving settings")