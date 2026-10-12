"""Keyboard bindings and geometry shared with the browser help diagram."""

import json
from pathlib import Path

LAYOUT = json.loads((Path(__file__).resolve().parent.parent / "web" / "keyboard-layout.json").read_text())
KEYS = LAYOUT["keys"]
