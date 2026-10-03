#!/usr/bin/env python3
"""Write the cache-busting versions into a published copy of web/.

Browsers cache the emulator's modules by URL, so every module URL carries a
?v= version, and a deploy has to change it for each file that changed. Doing
that by hand was easy to forget. Publishing runs this on the copy instead
(never on web/ itself): every ?v= value, and the *_VERSION constants that
build ?v= URLs at run time, become one hash of the published files, so any
change reaches every visitor on their next load.

Usage: python3 tools/stamp_web_versions.py <published web dir>
"""

import argparse
import hashlib
import re
import sys
from pathlib import Path


# Constants the modules interpolate into ?v= URLs, e.g. `?v=${CHIPSYNTH_VERSION}`.
VERSION_CONSTANTS = (
    "CHIPSYNTH_VERSION",
    "MICROPYTHON_WASM_VERSION",
    "WORKER_BUILD_VERSION",
    "WORKER_SCRIPT_VERSION",
)
WEB_SOURCE_DIR = Path(__file__).resolve().parent.parent / "web"
STAMPED_SUFFIXES = {".html", ".js", ".mjs", ".css"}
LITERAL_VERSION = re.compile(r"(\?v=)[A-Za-z0-9._-]+")
INTERPOLATED_VERSION = re.compile(r"\?v=\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def constant_pattern(name):
    return re.compile(r'(\bconst\s+%s\s*=\s*")[^"]*(")' % name)


def tree_version(root):
    """Short hash of every file under root, by path and content."""
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8") + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()[:12]


def stamp(root):
    """Rewrite the versions in root's own pages and modules (vendor/ keeps
    the version strings its libraries ship with). Returns the version."""
    root = Path(root)
    version = tree_version(root)
    stamped_constants = set()
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix not in STAMPED_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        for name in INTERPOLATED_VERSION.findall(text):
            if name not in VERSION_CONSTANTS:
                raise SystemExit(
                    f"stamp_web_versions: {path.name} builds ?v= from {name}, which "
                    "this tool does not stamp; add it to VERSION_CONSTANTS")
        new_text = LITERAL_VERSION.sub(lambda match: match.group(1) + version, text)
        for name in VERSION_CONSTANTS:
            new_text, count = constant_pattern(name).subn(lambda match: match.group(1) + version + match.group(2), new_text)
            if count:
                stamped_constants.add(name)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
    missing = sorted(set(VERSION_CONSTANTS) - stamped_constants)
    if missing:
        raise SystemExit(
            "stamp_web_versions: no string constant named %s in %s; "
            "update VERSION_CONSTANTS" % (", ".join(missing), root))
    return version


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("published_dir", type=Path)
    args = parser.parse_args(argv)
    if args.published_dir.resolve() == WEB_SOURCE_DIR:
        sys.exit("stamp_web_versions: run this on a published copy, not on web/ itself")
    print(f"Stamped ?v={stamp(args.published_dir)} into {args.published_dir}")


if __name__ == "__main__":
    main()
