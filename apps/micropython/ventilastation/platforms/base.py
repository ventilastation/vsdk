"""Platform container and lazy-import helpers shared by all platform variants.

A Platform bundles the four backends the director talks to (comms, display,
sprites, storage) plus the optional native-app launcher hooks. Concrete
platforms live in the sibling modules (desktop, hardware, headless, browser);
create_platform() in __init__ picks one by name.
"""


class Platform:
    def __init__(
        self,
        name,
        comms,
        display,
        sprites_backend,
        storage,
        hw_config=None,
        pixels=54,
        disable_gc=False,
        vs2_backend=None,
        native_launcher=None,
        native_available=None,
        native_last_exit_reason=None,
    ):
        self.name = name
        self.comms = comms
        self.display = display
        self.sprites = sprites_backend
        self.storage = storage
        self.hw_config = hw_config or ()
        self.pixels = pixels
        # On hardware the GPU task renders concurrently with Python; automatic
        # GC pauses would glitch the POV image, so the director disables GC and
        # collects at safe points instead.
        self.disable_gc = disable_gc
        self.vs2 = vs2_backend
        self.native_launcher = native_launcher
        self.native_available = native_available
        self.native_last_exit_reason_fn = native_last_exit_reason

    def initialize(self, settings_module):
        settings_module.load()
        self.display.init(self.pixels, *self.hw_config)
        self.display.set_gamma_mode(1)
        self.display.set_column_offset(settings_module.get("pov_column_offset", 0))

    def set_worker_host(self, worker_host):
        if hasattr(self.comms, "set_worker_host"):
            self.comms.set_worker_host(worker_host)
        if hasattr(self.display, "set_worker_host"):
            self.display.set_worker_host(worker_host)

    def request_native_launch(self, intent):
        if self.native_launcher is None:
            return False
        native_app = intent.get("native_app")
        if not native_app:
            return False
        return bool(self.native_launcher(native_app))

    def is_native_app_available(self, native_app):
        if self.native_available is None:
            return None
        return bool(self.native_available(native_app))

    def native_last_exit_reason(self):
        if self.native_last_exit_reason_fn is None:
            return None
        return self.native_last_exit_reason_fn()


class LazyModule:
    """Defer a backend module import until its first attribute access.

    Lets a platform reference modules that only import cleanly on that
    platform (e.g. vshw_povdisplay exists only in the ESP32 firmware).
    """

    def __init__(self, module_name):
        self.module_name = module_name
        self._module = None

    def _load(self):
        if self._module is None:
            self._module = __import__(self.module_name, None, None, ["*"])
        return self._module

    def __getattr__(self, name):
        return getattr(self._load(), name)


def load_attr(module_name, attr_name=None):
    if attr_name is None:
        return __import__(module_name, None, None, ["*"])
    module = __import__(module_name, None, None, [attr_name])
    return getattr(module, attr_name)


def optional_attr(module_name, attr_name):
    try:
        return load_attr(module_name, attr_name)
    except ImportError:
        return None
