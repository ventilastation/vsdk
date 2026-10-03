try:
    import ujson as json
except ImportError:
    import json


try:
    import uos as _os
except ImportError:
    import os as _os


class FileStorage:
    def read_json(self, filename):
        with open(filename, "r") as handle:
            return json.load(handle)

    def write_json(self, filename, data):
        # Serialise first, so data that cannot be written as JSON raises
        # before any file is touched. Then write a temporary file and rename
        # it over the real one (atomic on LittleFS, as in updater.py), so a
        # power cut leaves either the old file or the new one, never a
        # truncated one.
        text = json.dumps(data)
        temporary = filename + ".tmp"
        with open(temporary, "w") as handle:
            handle.write(text)
        try:
            _os.rename(temporary, filename)
        except OSError:
            # Some filesystems will not rename over an existing file.
            _os.remove(filename)
            _os.rename(temporary, filename)

    def makedirs(self, path):
        """Make a directory if it is not there yet."""
        try:
            _os.mkdir(path)
        except OSError:
            pass


class MemoryStorage:
    def __init__(self):
        self.files = {}

    def read_json(self, filename):
        if filename not in self.files:
            raise OSError(filename)
        return self.files[filename]

    def write_json(self, filename, data):
        self.files[filename] = data

    def makedirs(self, path):
        pass


class RuntimeContext:
    """The one place that holds the configured platform and director.

    director.configure_runtime() creates it; everything else reads it
    through get_runtime()/get_platform()/get_director().
    """

    def __init__(self, platform, director=None):
        self.platform = platform
        self.director = director


_runtime = None


def set_runtime(runtime):
    global _runtime
    _runtime = runtime


def get_runtime():
    if _runtime is None:
        raise RuntimeError("Ventilastation runtime has not been configured")
    return _runtime


def peek_runtime():
    return _runtime


def get_platform():
    return get_runtime().platform


def get_director():
    director = get_runtime().director
    if director is None:
        raise RuntimeError("Ventilastation runtime has no director")
    return director


def clear_runtime():
    global _runtime
    _runtime = None
