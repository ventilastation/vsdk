"""The banner/body/blob grammar and the ``body-sha`` checksum.

Spec (``## The block editor`` -> ``### Round-trip...``): "Banner and body
checksum at the top. If the body no longer matches, the editor reports the
file as hand-edited and refuses to overwrite silently."

**File shape, exactly.** A generator-managed file is three parts joined
like this (see :func:`join_generated_file`/:func:`split_generated_file`,
which are exact inverses of each other -- this is the one place the
boundary is defined; everything else in this package calls one of these
two)::

    <banner line>\\n
    <body>\\n
    \\n
    <blob line>\\n

- **banner** -- one line, ``# {basename}  -- generated, do not edit.
  body-sha: {8 hex digits}``.
- **body** -- everything else: imports, the class, ``build()``, the
  ``on_build_N`` stubs. No leading or trailing blank line of its own --
  the blank line that visually separates it from the blob (matching the
  proposal's own worked example) is part of the join, not the body.
- **blob** -- one line, ``# scene-model: {base64(zlib(canonical json))}``.

**Why sha256 truncated to 8 hex digits, not a "real" hash.** This is a
change-detection tripwire, not a security boundary -- collision
resistance is irrelevant to "did a human edit this file since it was
generated" -- and 8 hex digits is what the proposal's own worked example
shows (``body-sha: 8f3a1c02``), so matching it keeps a real generated file
looking exactly like the spec's illustration.
"""

import hashlib
import re

BANNER_RE = re.compile(
    r"^# (?P<basename>.+)  -- generated, do not edit\. body-sha: (?P<sha>[0-9a-f]{8})$")
BLOB_RE = re.compile(r"^# scene-model: (?P<data>\S+)$")


def body_sha(body):
    """The 8-hex-digit checksum recorded in the banner, computed over
    ``body`` exactly as :func:`split_generated_file` would hand it back --
    UTF-8 bytes, sha256, first 8 hex digits."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:8]


def make_banner(basename, sha):
    return "# %s  -- generated, do not edit. body-sha: %s" % (basename, sha)


def make_blob_line(blob_text):
    return "# scene-model: %s" % (blob_text,)


def join_generated_file(banner_line, body, blob_line):
    """Inverse of :func:`split_generated_file`. ``body`` must carry no
    leading/trailing blank line of its own (see this module's docstring)."""
    return "\n".join((banner_line, body, "", blob_line)) + "\n"


def split_generated_file(text):
    """``(banner_line, body, blob_line)`` if ``text`` has the generator-
    managed shape this module documents, else ``None`` -- the one
    predicate every caller in this package uses to decide "is this file
    ours to regenerate" (see :mod:`generator`, :mod:`detach`,
    :mod:`regenerate`). Deliberately permissive about *content* (a banner
    with a stale checksum still splits fine -- that is the hand-edited
    case, told apart by comparing the recorded and actual checksums, not
    by failing to split at all) and strict about *shape* (missing banner,
    missing blob, or a missing blank-line separator all return ``None`` --
    the shape ``Detach`` produces, and the shape any file that was never
    generated at all has).
    """
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
        raise ValueError("not a scene-model blob line: %r" % (blob_line,))
    return match.group("data")


def is_hand_edited(text):
    """``True`` if ``text`` has the generator-managed shape but its
    recorded checksum no longer matches its actual body -- the "someone
    hand-edited a generated file" case. ``False`` for a byte-perfect
    generated file *and* for a file that is not generator-managed at all
    (not generated, or already ``Detach``-ed) -- callers that need to
    treat "not managed" and "hand-edited" differently should call
    :func:`split_generated_file` themselves; this is the convenience
    single-question form.
    """
    parsed = split_generated_file(text)
    if parsed is None:
        return False
    banner_line, body, _blob_line = parsed
    return recorded_sha(banner_line) != body_sha(body)
