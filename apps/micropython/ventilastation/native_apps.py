"""Native-app registry, ROM libraries, and return-to-launcher state.

Native partitions cannot return to a live MicroPython scene: they reboot into
the normal ``micropython`` partition instead.  This module therefore persists
the launcher stack before every hand-off and recreates it at the next boot.
"""

try:
    import uos as os
except ImportError:
    import os

from ventilastation.director import director
from ventilastation.runtime import get_platform
from ventilastation.scene import Scene

BOOT_INTENT_FILE = "ventilastation/boot.json"
LAST_EXIT_FILE = "ventilastation/native_last_exit.json"
LAUNCHER_STATE_FILE = "ventilastation/launcher_state.json"

# One descriptor drives the main-menu entry, dynamic ROM discovery, NVS launch
# payload, and post-reboot restoration.  ``rom_extensions`` are lower-case.
APP_REGISTRY = {
    "native.voom": {
        "kind": "native",
        "native_app": "voom",
        "title": "Voom",
    },
    "native.nes": {
        "kind": "native",
        "native_app": "retro-core",
        "title": "NES",
        "system": "nes",
        "rom_directory": "nes",
        "rom_extensions": (".nes", ".zip"),
    },
    "native.sms": {
        "kind": "native",
        "native_app": "retro-core",
        "title": "Master System",
        "system": "sms",
        "rom_directory": "sms",
        "rom_extensions": (".sms", ".zip"),
    },
    "native.gb": {
        "kind": "native",
        "native_app": "retro-core",
        "title": "Game Boy",
        "system": "gb",
        "rom_directory": "gb",
        "rom_extensions": (".gb", ".gbc", ".zip"),
    },
    "native.msx": {
        "kind": "native",
        "native_app": "fmsx",
        "title": "MSX",
        "rom_directory": "msx",
        # build_micropython_fs.py turns plain .rom files into .rom.gz in the
        # shared image; fMSX supports both forms plus its disk/tape media.
        "rom_extensions": (
            ".rom.gz", ".mx1.gz", ".mx2.gz", ".dsk.gz", ".fdi.gz",
            ".rom", ".mx1", ".mx2", ".dsk", ".cas", ".fdi",
        ),
    },
}


def get_app_spec(slug):
    return APP_REGISTRY.get(slug)


def is_native_app(slug):
    spec = get_app_spec(slug)
    return bool(spec and spec.get("kind") == "native")


def has_rom_library(slug):
    spec = get_app_spec(slug) or {}
    return bool(spec.get("rom_directory"))


def _storage():
    return get_platform().storage


def _read_json(filename):
    try:
        return _storage().read_json(filename)
    except Exception:
        return None


def _write_json(filename, data):
    _storage().write_json(filename, data)
    return data


def read_boot_intent():
    return _read_json(BOOT_INTENT_FILE)


def write_boot_intent(data):
    return _write_json(BOOT_INTENT_FILE, data)


def clear_boot_intent():
    write_boot_intent({"mode": "micropython"})


def read_last_exit():
    return _read_json(LAST_EXIT_FILE)


def write_last_exit(data):
    return _write_json(LAST_EXIT_FILE, data)


def _default_launcher_state():
    return {"main_slug": None, "submenu_slug": None, "rom_path": None}


def read_launcher_state():
    state = _read_json(LAUNCHER_STATE_FILE)
    if not isinstance(state, dict):
        return _default_launcher_state()
    result = _default_launcher_state()
    for key in result:
        value = state.get(key)
        result[key] = value if isinstance(value, str) else None
    if result["main_slug"] not in APP_REGISTRY:
        result["main_slug"] = None
    if result["submenu_slug"] not in APP_REGISTRY or not has_rom_library(result["submenu_slug"]):
        result["submenu_slug"] = None
        result["rom_path"] = None
    return result


def write_launcher_state(state):
    result = _default_launcher_state()
    for key in result:
        value = state.get(key) if isinstance(state, dict) else None
        result[key] = value if isinstance(value, str) else None
    return _write_json(LAUNCHER_STATE_FILE, result)


def remember_main_selection(slug):
    state = _default_launcher_state()
    state["main_slug"] = slug if slug in APP_REGISTRY else None
    return write_launcher_state(state)


def remember_rom_selection(slug, rom_path=None):
    if not has_rom_library(slug):
        return remember_main_selection(slug)
    return write_launcher_state({
        "main_slug": slug,
        "submenu_slug": slug,
        "rom_path": rom_path,
    })


def leave_rom_menu(slug):
    """Persist the D/back result: main menu open on this emulator."""
    return remember_main_selection(slug)


def _isdir(path):
    try:
        return bool(os.stat(path)[0] & 0x4000)
    except OSError:
        return False


def _rom_source_dir(spec, roms_root=None):
    directory = spec["rom_directory"]
    if roms_root is not None:
        return roms_root.rstrip("/") + "/" + directory

    # On the board the shared LittleFS partition is mounted at /.  On the
    # desktop emulator the source tree is more useful than an absent /roms.
    for path in ("roms/" + directory, "apps/retro-go/roms/" + directory):
        if _isdir(path):
            return path
    return "roms/" + directory


def _display_basename(filename):
    name = filename
    # A .rom source becomes .rom.gz in the LittleFS image. Both suffixes are
    # file format details rather than part of the title.
    if name.lower().endswith(".gz"):
        name = name[:-3]
    name = name.rsplit(".", 1)[0] if "." in name else name
    printable = []
    for char in name:
        code = ord(char)
        printable.append(char if 32 <= code <= 126 else "?")
    return "".join(printable)


def trim_rom_label(label, max_chars=21):
    """Keep a tile within one third of the 256-column display."""
    if len(label) <= max_chars:
        return label
    if max_chars <= 3:
        return label[:max_chars]
    return label[:max_chars - 3] + "..."


def list_roms(slug, roms_root=None):
    """Return sorted runtime ROM descriptors for one native library."""
    spec = get_app_spec(slug)
    if not spec or not has_rom_library(slug):
        return []
    source_dir = _rom_source_dir(spec, roms_root)
    try:
        filenames = os.listdir(source_dir)
    except OSError:
        return []

    filenames.sort()
    entries = []
    for filename in filenames:
        path = source_dir + "/" + filename
        if _isdir(path):
            continue
        lower_filename = filename.lower()
        if not any(lower_filename.endswith(extension) for extension in spec["rom_extensions"]):
            continue
        entries.append({
            "filename": filename,
            "label": trim_rom_label(_display_basename(filename)),
            "path": "/vfs/roms/%s/%s" % (spec["rom_directory"], filename),
        })
    return entries


def build_boot_intent(slug, rom_path=None):
    spec = get_app_spec(slug)
    if not spec:
        raise ValueError("Unknown native app slug: %s" % slug)
    if has_rom_library(slug) and not rom_path:
        raise ValueError("Native ROM library needs a selected ROM: %s" % slug)
    return {
        "mode": "native",
        "slug": slug,
        "native_app": spec["native_app"],
        "system": spec.get("system"),
        "rom": rom_path,
        "launcher_state": read_launcher_state(),
        "return_mode": "micropython",
    }


def consume_native_return():
    """Promote a pending native hand-off to durable launcher state once."""
    intent = read_boot_intent()
    if not isinstance(intent, dict) or intent.get("mode") != "native":
        return read_launcher_state()
    saved_state = intent.get("launcher_state")
    if isinstance(saved_state, dict):
        write_launcher_state(saved_state)
    write_last_exit({
        "slug": intent.get("slug"),
        "native_app": intent.get("native_app"),
        "rom": intent.get("rom"),
        "reason": "returned_to_micropython",
    })
    clear_boot_intent()
    return read_launcher_state()


def request_native_launch(slug, rom_path=None):
    platform = get_platform()
    intent = write_boot_intent(build_boot_intent(slug, rom_path))
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


def _write_native_launch_nvs(spec, rom_path):
    """Write generic native launch arguments to the shared NVS namespace."""
    try:
        import esp32
        nvs = esp32.NVS("vs_native")
        nvs.set_blob("app", spec["native_app"].encode())
        system = spec.get("system")
        if system:
            nvs.set_blob("system", system.encode())
        if rom_path:
            nvs.set_blob("rom", rom_path.encode())
        nvs.commit()
    except Exception:
        pass


class NativeLaunchScene(Scene):
    def __init__(self, slug, rom_path=None):
        super().__init__()
        self.slug = slug
        self.rom_path = rom_path

    def on_enter(self):
        super().on_enter()
        self.call_later(1, self._launch)

    def _launch(self):
        spec = get_app_spec(self.slug) or {}
        if has_rom_library(self.slug):
            remember_rom_selection(self.slug, self.rom_path)
        else:
            remember_main_selection(self.slug)
        _write_native_launch_nvs(spec, self.rom_path)
        result = request_native_launch(self.slug, self.rom_path)
        if result["launched"]:
            return

        clear_boot_intent()
        director.pop()


def launch_native_scene(slug, rom_path=None):
    scene = NativeLaunchScene(slug, rom_path)
    director.push(scene)
    return scene
