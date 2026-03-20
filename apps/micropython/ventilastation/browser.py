import gc

from ventilastation.runtime import get_platform

_booted = False


def _browser_platform():
    platform = get_platform()
    if platform.name != "browser":
        raise RuntimeError("Browser API requires the browser platform")
    return platform


def set_buttons(buttons):
    _browser_platform().comms.set_buttons(buttons)


def clear_buttons():
    _browser_platform().comms.set_buttons(0)


def drain_input_updates():
    return _browser_platform().comms.drain_input_updates()


def drain_host_events():
    return _browser_platform().comms.drain_events()


def export_frame(full=False):
    gc.collect()
    return _browser_platform().display.export_frame(full=full)

def export_palette_chunk(offset=0, chunk_size=2048):
    return None


def export_assets(full=False, max_items=None):
    return []


def export_asset_chunk(slot, offset=0, chunk_size=2048):
    return None


def export_storage():
    return _browser_platform().storage.export_state()


def import_storage(files):
    _browser_platform().storage.import_state(files)


def boot_main():
    global _booted
    if _booted:
        return False
    import main as main_module

    setup = getattr(main_module, "setup", None)
    if setup:
        setup()
        _booted = True
        return True

    games_menu_class = getattr(main_module, "GamesMenu", None)
    menu_options = getattr(main_module, "MAIN_MENU_OPTIONS", None)
    if games_menu_class and menu_options is not None:
        director = __import__("ventilastation.director", None, None, ["director"]).director
        main_menu = games_menu_class(menu_options)
        main_menu.call_later(700, main_menu.load_images)
        director.push(main_menu)

        from apps.ventilagon_game import VentilagonIdle
        autostart = VentilagonIdle()
        autostart.call_later(700, autostart.load_images)
        director.push(autostart)

        _booted = True
        return True

    raise AttributeError(
        "Unable to bootstrap main module; available attrs: %s"
        % ",".join(sorted(dir(main_module)))
    )


def tick(count=1):
    director = __import__("ventilastation.director", None, None, ["director"]).director
    while count > 0:
        director.step_once()
        count -= 1
