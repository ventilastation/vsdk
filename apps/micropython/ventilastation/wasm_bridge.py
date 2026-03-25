import json
import sys
import ubinascii


def _serialize_binary(value, binary_mode):
    if binary_mode != "base64":
        return {"__bytes_meta__": len(value)}
    encoded = ubinascii.b2a_base64(bytes(value)).decode().strip()
    return {"__base64__": encoded}


def _serialize(value, binary_mode):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return _serialize_binary(value, binary_mode)
    if isinstance(value, (list, tuple, set)):
        return [_serialize(item, binary_mode) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize(item, binary_mode) for key, item in value.items()}
    return str(value)


def boot_runtime():
    import uos

    if "/apps/micropython" not in sys.path:
        sys.path.insert(0, "/apps/micropython")
    uos.chdir("/apps/micropython")
    from ventilastation.director import configure_runtime
    import ventilastation.browser as browser
    import main as main_module
    configure_runtime("browser")
    browser.boot_main()
    return bool(getattr(main_module, "__name__", None))


def step(count=1):
    from ventilastation.director import director
    remaining = int(count)
    while remaining > 0:
        director.step_once()
        remaining -= 1
    return None


def call(module_name, function_name, args_json):
    module = __import__(module_name, None, None, [function_name])
    function = getattr(module, function_name)
    args = json.loads(args_json)
    result = function(*args)
    binary_mode = "base64" if function_name == "export_frame" else "meta"
    return json.dumps(_serialize(result, binary_mode))


def invoke(module_name, function_name, args_json):
    try:
        result = json.loads(call(module_name, function_name, args_json))
        return json.dumps({"ok": True, "result": result})
    except Exception as error:
        error_type = sys.exc_info()[0]
        error_name = getattr(error_type, "__name__", str(error_type))
        return json.dumps({"ok": False, "error": error_name + ": " + str(error)})


def invoke_from_globals():
    main_globals = __import__("__main__").__dict__
    return invoke(
        main_globals.get("__vs_bridge_module_name"),
        main_globals.get("__vs_bridge_function_name"),
        main_globals.get("__vs_bridge_args_json"),
    )
