import gc
try:
    import utime as _time
except ImportError:
    import time as _time

from ventilastation.runtime import get_platform

_booted = False
_export_frame_counter = 0
_export_profile_totals = {
    "sampleCount": 0,
    "browserExportUs": 0,
    "browserExportUsMax": 0,
    "gcUs": 0,
    "gcUsMax": 0,
    "displayCallUs": 0,
    "displayCallUsMax": 0,
    "gcCount": 0,
}


def _ticks_us():
    ticks_us = getattr(_time, "ticks_us", None)
    if ticks_us is not None:
        return ticks_us()
    perf_counter = getattr(_time, "perf_counter", None)
    if perf_counter is not None:
        return int(perf_counter() * 1000000)
    return 0


def _ticks_diff_us(end, start):
    ticks_diff = getattr(_time, "ticks_diff", None)
    if ticks_diff is not None:
        return ticks_diff(end, start)
    return end - start


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


def _consume_traceback_messages():
    comms = _browser_platform().comms
    events = getattr(comms, "events", None)
    if events is None:
        return []

    remaining = []
    messages = []
    for event in events:
        if isinstance(event, dict) and event.get("command") == "traceback":
            payload = event.get("data", b"")
            if isinstance(payload, str):
                messages.append(payload)
                continue
            try:
                messages.append(bytes(payload).decode("utf-8"))
            except Exception:
                messages.append(str(payload))
            continue
        remaining.append(event)
    comms.events = remaining
    return messages


def export_frame(full=False):
    global _export_frame_counter, _export_profile_totals
    started_at = _ticks_us()
    _export_frame_counter += 1
    gc_started_at = started_at
    did_collect = full or (_export_frame_counter % 60) == 0
    if did_collect:
        gc.collect()
    after_gc_at = _ticks_us()
    frame = _browser_platform().display.export_frame(full=full)
    finished_at = _ticks_us()
    browser_export_us = _ticks_diff_us(finished_at, started_at)
    gc_us = _ticks_diff_us(after_gc_at, gc_started_at) if did_collect else 0
    display_call_us = _ticks_diff_us(finished_at, after_gc_at)
    _export_profile_totals["sampleCount"] += 1
    _export_profile_totals["browserExportUs"] += browser_export_us
    _export_profile_totals["displayCallUs"] += display_call_us
    if browser_export_us > _export_profile_totals["browserExportUsMax"]:
        _export_profile_totals["browserExportUsMax"] = browser_export_us
    if display_call_us > _export_profile_totals["displayCallUsMax"]:
        _export_profile_totals["displayCallUsMax"] = display_call_us
    if did_collect:
        _export_profile_totals["gcCount"] += 1
        _export_profile_totals["gcUs"] += gc_us
        if gc_us > _export_profile_totals["gcUsMax"]:
            _export_profile_totals["gcUsMax"] = gc_us
    if isinstance(frame, dict):
        profile = frame.get("python_profile")
        if not isinstance(profile, dict):
            profile = {}
            frame["python_profile"] = profile
        sample_count = _export_profile_totals["sampleCount"] or 1
        gc_count = _export_profile_totals["gcCount"] or 1
        profile["sampleCount"] = sample_count
        profile["browserExportMs"] = _export_profile_totals["browserExportUs"] / sample_count / 1000.0
        profile["browserExportMsMax"] = _export_profile_totals["browserExportUsMax"] / 1000.0
        profile["gcMs"] = (_export_profile_totals["gcUs"] / gc_count / 1000.0) if _export_profile_totals["gcCount"] else 0.0
        profile["gcMsMax"] = _export_profile_totals["gcUsMax"] / 1000.0
        profile["didCollectGc"] = bool(did_collect)
        profile["gcCount"] = _export_profile_totals["gcCount"]
        profile["displayCallMs"] = _export_profile_totals["displayCallUs"] / sample_count / 1000.0
        profile["displayCallMsMax"] = _export_profile_totals["displayCallUsMax"] / 1000.0
    return frame


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

        # from apps.ventilagon_game import VentilagonIdle
        # autostart = VentilagonIdle()
        # autostart.call_later(700, autostart.load_images)
        # director.push(autostart)

        _booted = True
        return True

    raise AttributeError(
        "Unable to bootstrap main module; available attrs: %s"
        % ",".join(sorted(dir(main_module)))
    )


def configure_worker_host(worker_host):
    if isinstance(worker_host, str):
        worker_host = __import__(worker_host)
    _browser_platform().set_worker_host(worker_host)


def tick(count=1):
    director = __import__("ventilastation.director", None, None, ["director"]).director
    try:
        while count > 0:
            director.step_once()
            count -= 1
    except Exception as error:
        messages = _consume_traceback_messages()
        if messages:
            raise RuntimeError("Scene lifecycle error\n\n%s" % messages[-1])
        raise error
