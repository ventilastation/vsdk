try:
    import ujson as json
except ImportError:
    import json

from ventilastation.director import director
from ventilastation.runtime import get_platform
from ventilastation.scene import Scene

BOOT_INTENT_FILE = "ventilastation/boot.json"
LAST_EXIT_FILE = "ventilastation/native_last_exit.json"

APP_REGISTRY = {
    "native.voom": {
        "kind": "native",
        "native_app": "voom",
        "title": "Voom",
    },
    "native.launcher": {
        "kind": "native",
        "native_app": "launcher",
        "title": "Retro-Go Launcher",
    },
}


def get_app_spec(slug):
    return APP_REGISTRY.get(slug)


def is_native_app(slug):
    spec = get_app_spec(slug)
    return bool(spec and spec.get("kind") == "native")


def _storage():
    return get_platform().storage


def read_boot_intent():
    try:
        return _storage().read_json(BOOT_INTENT_FILE)
    except Exception:
        return None


def write_boot_intent(data):
    _storage().write_json(BOOT_INTENT_FILE, data)
    return data


def clear_boot_intent():
    write_boot_intent({"mode": "micropython"})


def read_last_exit():
    try:
        return _storage().read_json(LAST_EXIT_FILE)
    except Exception:
        return None


def write_last_exit(data):
    _storage().write_json(LAST_EXIT_FILE, data)
    return data


def build_boot_intent(slug):
    spec = get_app_spec(slug)
    if not spec:
        raise ValueError("Unknown native app slug: %s" % slug)
    return {
        "mode": "native",
        "slug": slug,
        "native_app": spec["native_app"],
        "return_mode": "micropython",
    }


def request_native_launch(slug):
    platform = get_platform()
    intent = write_boot_intent(build_boot_intent(slug))
    request = getattr(platform, "request_native_launch", None)
    availability_fn = getattr(platform, "is_native_app_available", None)
    last_exit_fn = getattr(platform, "native_last_exit_reason", None)

    available = availability_fn(intent["native_app"]) if availability_fn else None
    if request is None:
        return {
            "available": available,
            "intent": intent,
            "last_exit_reason": last_exit_fn() if last_exit_fn else None,
            "launched": False,
            "platform": platform.name,
        }

    launched = bool(request(intent))
    return {
        "available": available,
        "intent": intent,
        "last_exit_reason": last_exit_fn() if last_exit_fn else None,
        "launched": launched,
        "platform": platform.name,
    }


def _sync_wifi_to_nvs():
    """Copy wifi_config.json credentials into NVS so prboom-go can read them."""
    try:
        import esp32
        try:
            import ujson as _json
        except ImportError:
            import json as _json
        try:
            with open("wifi_config.json") as _f:
                cfg = _json.load(_f)
        except Exception:
            return
        ssid = cfg.get("ssid", "")
        password = cfg.get("password", "")
        if not ssid:
            return
        nvs = esp32.NVS("voom_wifi")
        nvs.set_blob("ssid", ssid.encode())
        nvs.set_blob("password", password.encode())
        nvs.commit()
    except Exception:
        pass


def _sync_pov_to_nvs():
    """Copy the current pov_column_offset into NVS so prboom-go/launcher can read it."""
    try:
        import esp32
        from ventilastation import povdisplay
        offset = povdisplay.get_column_offset()
        nvs = esp32.NVS("voom_pov")
        nvs.set_i32("col_offset", offset)
        nvs.commit()
    except Exception:
        pass


class NativeLaunchScene(Scene):
    def __init__(self, slug):
        super().__init__()
        self.slug = slug

    def on_enter(self):
        super().on_enter()
        self.call_later(1, self._launch)

    def _launch(self):
        _sync_wifi_to_nvs()
        _sync_pov_to_nvs()
        result = request_native_launch(self.slug)
        if result["launched"]:
            return

        clear_boot_intent()
        director.pop()


def launch_native_scene(slug):
    scene = NativeLaunchScene(slug)
    director.push(scene)
    return scene
