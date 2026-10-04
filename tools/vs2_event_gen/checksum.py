"""The banner/body/blob grammar and the ``body-sha`` checksum.

A small parallel of ``tools/vs2_scene_gen/checksum.py``, identical in every
mechanic (banner shape, body-sha, the join/split/detect functions) except
one deliberate difference: **the blob line's prefix is ``# blocks: ``, not
``# scene-model: ``.** ``vs2_scene_gen.blob``'s own docstring reserves that
prefix for exactly this package's Blockly-workspace-shaped blob (a JSON
*event sheet*, :mod:`model`, not a scene graph), so a generated file's
trailing comment says at a glance which of the two generators produced it --
and a scene file that carries both a ``# scene-model:`` blob (T15) and, once
this module's output is wired in, its own separate ``# blocks:``-carrying
companion file, is unambiguous either way.

``vs2_scene_gen.checksum.BLOB_RE`` hardcodes the other prefix, so it cannot
be reused here; everything else below is deliberately copy-shaped so the two
packages read as the same convention applied to two different blob kinds.
See ``vs2_scene_gen/checksum.py`` for the full rationale (sha256-truncated-
to-8-hex-digits as a change-detection tripwire, not a security boundary; the
banner/body/blob join being the one place the file's three-part shape is
defined).
"""

import hashlib
import re

BANNER_RE = re.compile(
    r"^# (?P<basename>.+)  -- generated, do not edit\. body-sha: (?P<sha>[0-9a-f]{8})$")
BLOB_RE = re.compile(r"^# blocks: (?P<data>\S+)$")


def body_sha(body):
    """The 8-hex-digit checksum recorded in the banner, computed over
    ``body`` exactly as :func:`split_generated_file` would hand it back --
    UTF-8 bytes, sha256, first 8 hex digits."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:8]


def make_banner(basename, sha):
    return "# %s  -- generated, do not edit. body-sha: %s" % (basename, sha)


def make_blob_line(blob_text):
    return "# blocks: %s" % (blob_text,)


def join_generated_file(banner_line, body, blob_line):
    """Inverse of :func:`split_generated_file`. ``body`` must carry no
    leading/trailing blank line of its own."""
    return "\n".join((banner_line, body, "", blob_line)) + "\n"


def split_generated_file(text):
    """``(banner_line, body, blob_line)`` if ``text`` has the generator-
    managed shape this module documents, else ``None``. See
    ``vs2_scene_gen.checksum.split_generated_file`` for the full contract
    this mirrors: permissive about *content* (a stale checksum still
    splits), strict about *shape* (missing banner/blob/separator all
    return ``None``)."""
    if not text.endswith("\n"):
        return None
    lines = text[:-1].split("\n")
    if len(lines) < 4:
        return None
    banner_line = lines[0]
    blob_line = lines[-1]
    separator = lines[-2]
    if separator != "":
        return None
    if not BANNER_RE.match(banner_line):
        return None
    if not BLOB_RE.match(blob_line):
        return None
    body = "\n".join(lines[1:-2])
    return banner_line, body, blob_line


def recorded_sha(banner_line):
    match = BANNER_RE.match(banner_line)
    if not match:
        raise ValueError("not a generated-file banner line: %r" % (banner_line,))
    return match.group("sha")


def blob_data(blob_line):
    match = BLOB_RE.match(blob_line)
    if not match:
        raise ValueError("not a blocks blob line: %r" % (blob_line,))
    return match.group("data")


def is_hand_edited(text):
    """``True`` if ``text`` has the generator-managed shape but its
    recorded checksum no longer matches its actual body. ``False`` for a
    byte-perfect generated file *and* for a file that is not generator-
    managed at all."""
    parsed = split_generated_file(text)
    if parsed is None:
        return False
    banner_line, body, _blob_line = parsed
    return recorded_sha(banner_line) != body_sha(body)
