"""Sphinx configuration for the VS2 game developer documentation.

Built from the sources in this folder plus docstrings pulled straight out of
``apps/micropython/vs2``.  The runtime targets MicroPython on the rotor board,
so a handful of firmware-only modules are shimmed below to let autodoc import
the package on a normal CPython host.
"""

import os
import random
import sys
import time

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_ROOT, "apps", "micropython"))


# ``vs2`` imports these from the firmware.  Shimming beats autodoc_mock_imports
# here: the real modules underneath (display_geometry, api_guard) are plain
# Python, so the reference renders true values -- vs2.display.width really is
# 256 in the built page -- instead of a mock repr.
sys.modules.setdefault("uos", os)
sys.modules.setdefault("urandom", random)

if "utime" not in sys.modules:
    class _Utime:
        @staticmethod
        def ticks_ms():
            return int(time.monotonic() * 1000)

        @staticmethod
        def ticks_add(value, delta):
            return value + delta

        @staticmethod
        def ticks_diff(end, start):
            return end - start

    sys.modules["utime"] = _Utime


project = "Ventilastation VS2"
author = "The Ventilastation project"
copyright = "%s, the Ventilastation project" % time.strftime("%Y")

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

source_suffix = {".md": "markdown", ".rst": "restructuredtext"}

myst_enable_extensions = ["colon_fence", "deflist", "substitution"]
myst_heading_anchors = 3

# Games are written against the board's MicroPython, not CPython.  Linking to
# the CPython docs would send readers to APIs the board does not have.
intersphinx_mapping = {}

autodoc_member_order = "bysource"
autodoc_typehints = "none"
autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_use_rtype = False

html_theme = "furo"
html_title = "Ventilastation VS2"
# No html_static_path or templates_path on purpose: there are no custom assets
# or template overrides yet, and git does not track empty directories -- so
# naming one here builds fine locally and then fails the Read the Docs build
# (which runs with fail_on_warning) on its clean checkout. Add the directory
# and the setting together, in the same commit, if assets are ever needed.
html_theme_options = {
    "source_repository": "https://github.com/ventilastation/vsdk/",
    "source_branch": "main",
    "source_directory": "docs/vs2/",
}

# Every warning is a broken cross-reference or a page missing from a toctree;
# both are silent failures for the reader, so make the build fail instead.
nitpicky = True

# ``vs2.Scene`` subclasses the runtime's V1-facing scene so the director can
# drive it. That base class is firmware internals, deliberately out of scope
# for game-developer docs, so its inheritance link has nothing to point at.
nitpick_ignore = [
    ("py:class", "ventilastation.scene.Scene"),
]
