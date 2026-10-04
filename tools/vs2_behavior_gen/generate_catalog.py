#!/usr/bin/env python3
"""CLI: regenerate ``web/vs2-behavior-catalog.json`` from the real
``vs2.actions``/``vs2.behaviors`` modules.

    python3 tools/vs2_behavior_gen/generate_catalog.py
    python3 tools/vs2_behavior_gen/generate_catalog.py --check   # CI: fail if stale

**Committed, like ``web/runtime-manifest.json``.** This file is checked
into the repo (not generated fresh by the web server, which has no server
logic at all -- see ``tools/generate_web_runtime_bundle.py`` for the
precedent this follows) so the browser panel's ``fetch("./vs2-behavior-
catalog.json")`` works against a plain static file server
(``python3 -m http.server``) with no build step required at page-load
time. ``--check`` exists for a future CI hook the same way
``tools/vs2_scene_gen/regenerate.py`` exists for scene files -- regenerate
into a temp location and diff, rather than trusting a stale commit.
"""

import argparse
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.vs2_behavior_gen import catalog  # noqa: E402

DEFAULT_OUTPUT = REPO_ROOT / "web" / "vs2-behavior-catalog.json"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                         help="where to write the catalog JSON (default: %(default)s)")
    parser.add_argument("--check", action="store_true",
                         help="don't write; exit non-zero if the committed file is stale")
    args = parser.parse_args(argv)

    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "vs2-behavior-catalog.json"
            catalog.write_catalog(tmp_path)
            fresh = tmp_path.read_text()
        current = args.output.read_text() if args.output.exists() else None
        if current != fresh:
            print("STALE: %s does not match the current vs2 catalog; "
                  "re-run without --check to regenerate" % (args.output,), file=sys.stderr)
            return 1
        print("OK: %s is up to date" % (args.output,))
        return 0

    catalog.write_catalog(args.output)
    print("wrote %s" % (args.output,))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
