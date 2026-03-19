from ventilastation.runtime import get_platform


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
    return _browser_platform().display.export_frame(full=full)


def export_assets(full=False):
    return _browser_platform().sprites.export_assets(full=full)


def export_storage():
    return _browser_platform().storage.export_state()


def import_storage(files):
    _browser_platform().storage.import_state(files)
