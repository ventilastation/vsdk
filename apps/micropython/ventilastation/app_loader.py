import sys

try:
    import uos as os
except ImportError:
    import os

from ventilastation.director import director
from ventilastation import api_guard
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


def slug_to_meta_path(root_path, slug):
    return root_path + "/" + "/".join(slug_to_parts(slug)) + "/meta.json"


def app_exists(root_path, slug):
    try:
        os.stat(slug_to_code_path(root_path, slug))
        return True
    except OSError:
        return False


def read_app_api(root_path, slug):
    try:
        import ujson as json
    except ImportError:
        import json
    try:
        with open(slug_to_meta_path(root_path, slug)) as handle:
            meta = json.load(handle)
    except (OSError, ValueError):
        return None
    if isinstance(meta, dict):
        return meta.get("api")
    return None


def app_api(slug):
    if app_exists(GAMES_ROOT, slug):
        return slug, read_app_api(GAMES_ROOT, slug)
    if app_exists(SYSTEM_ROOT, slug):
        return "system." + slug, read_app_api(SYSTEM_ROOT, slug)
    return None, None


def import_app_module(slug):
    ensure_project_root_on_path()
    if app_exists(GAMES_ROOT, slug):
        api_slug, declared_api = app_api(slug)
        api_guard.begin_app(api_slug, declared_api)
        return __import__(slug_to_entry_module_name("games", slug), None, None, ["main"])
    if app_exists(SYSTEM_ROOT, slug):
        api_slug, declared_api = app_api(slug)
        api_guard.begin_app(api_slug, declared_api)
        return __import__(slug_to_module_name("system", slug), None, None, ["main"])
    raise ImportError("Unknown app slug: %s" % slug)


def load_app(slug):
    if is_native_app(slug):
        return launch_native_scene(slug)
    module = import_app_module(slug)
    api_slug, declared_api = app_api(slug)
    scene = module.main()
    scene._vs_api_slug = api_slug
    scene._vs_declared_api = declared_api
    director.push(scene)
    return scene
