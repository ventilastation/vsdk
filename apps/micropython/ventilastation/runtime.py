try:
    import ujson as json
except ImportError:
    import json


class FileStorage:
    def read_json(self, filename):
        with open(filename, "r") as handle:
            return json.load(handle)

    def write_json(self, filename, data):
        with open(filename, "w") as handle:
            json.dump(data, handle)


class MemoryStorage:
    def __init__(self):
        self.files = {}

    def read_json(self, filename):
        if filename not in self.files:
            raise OSError(filename)
        return self.files[filename]

    def write_json(self, filename, data):
        self.files[filename] = data


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
