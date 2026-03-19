from ventilastation.runtime import get_platform

SETTINGS_FILE = "ventilastation/settings.json"
_settings = {}


def load():
    global _settings

    try:
        _settings = get_platform().storage.read_json(SETTINGS_FILE)
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
        get_platform().storage.write_json(SETTINGS_FILE, _settings)
    except Exception:
        print("Error saving settings")
