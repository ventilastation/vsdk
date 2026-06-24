import sys

try:
    import uos as os
except ImportError:
    import os

from ventilastation.director import director
from ventilastation.native_apps import is_native_app, launch_native_scene

def _find_project_root():
    try:
        os.stat("games")
        return ""
    except OSError:
        return "../.."

PROJECT_ROOT = _find_project_root()
GAMES_ROOT = PROJECT_ROOT + "/games" if PROJECT_ROOT else "games"
SYSTEM_ROOT = PROJECT_ROOT + "/system" if PROJECT_ROOT else "system"


def ensure_project_root_on_path():
    if PROJECT_ROOT not in sys.path:
        sys.path.append(PROJECT_ROOT)


def slug_to_parts(slug):
    return [part for part in str(slug).split(".") if part]


def slug_to_module_name(root_package, slug):
    return root_package + "." + ".".join(slug_to_parts(slug)) + ".code"


def slug_to_entry_module_name(root_package, slug):
    parts = slug_to_parts(slug)
    return slug_to_module_name(root_package, slug) + "." + parts[-1]


def slug_to_code_path(root_path, slug):
    return root_path + "/" + "/".join(slug_to_parts(slug)) + "/code"


def app_exists(root_path, slug):
    try:
        os.stat(slug_to_code_path(root_path, slug))
        return True
    except OSError:
        return False


def import_app_module(slug):
    ensure_project_root_on_path()
    if app_exists(GAMES_ROOT, slug):
        return __import__(slug_to_entry_module_name("games", slug), None, None, ["main"])
    if app_exists(SYSTEM_ROOT, slug):
        return __import__(slug_to_module_name("system", slug), None, None, ["main"])
    raise ImportError("Unknown app slug: %s" % slug)


def load_app(slug):
    if is_native_app(slug):
        return launch_native_scene(slug)
    module = import_app_module(slug)
    scene = module.main()
    director.push(scene)
    return scene
