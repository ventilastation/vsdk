"""The banner/body/blob grammar and the ``body-sha`` checksum.

A third parallel of ``tools/vs2_scene_gen/checksum.py`` (T15) and
``tools/vs2_event_gen/checksum.py`` (T16), identical in every mechanic
(banner shape, body-sha, the join/split/detect functions) except one
deliberate difference: **the blob line's prefix is ``# behavior-blocks: ``,
not ``# scene-model: `` or ``# blocks: ``.**

**A real naming collision, worth recording plainly.** The proposal's own
``## The block editor`` -> ``### Round-trip`` text says "Embed the workspace
as a base64+zlib blob in a trailing comment", and its earlier worked example
(``## Projects, scenes and ownership``) literally shows ``# blocks: eJyV...``
as the comment on a *scene* file -- i.e. the spec's own illustration uses
``# blocks:`` for what ``tools/vs2_scene_gen`` actually built as
``# scene-model:``. Then T16 (this repo's actual event-sheet task) claimed
``# blocks:`` for *its* blob instead -- reasonably, since
``vs2_scene_gen/blob.py``'s own docstring explicitly reserved that prefix
"for a future Blockly workspace blob", and an event sheet is exactly that.
The result: by the time this package (T17, "Blockly for *behaviors*", the
other thing that spec text could plausibly have meant) needs its own blob
prefix, both plausible candidates -- the literal spec string and the
"future Blockly workspace" reservation -- are already taken by two earlier,
unrelated generators. This is not a mistake either earlier task made; it is
the spec's own text being reusable for more than one later task, discovered
only once the second and third claimants actually exist. Flagged here,
exactly like ``docs/vs2-behaviors-handoff.md`` already flags the first half
of this collision, so a fourth generator does not repeat the confusion:
**check this module and its two siblings before inventing yet another
``# ...:`` prefix.**

``vs2_scene_gen.checksum.BLOB_RE`` and ``vs2_event_gen.checksum.BLOB_RE``
each hardcode their own prefix, so neither can be reused here; everything
below is deliberately copy-shaped so all three packages read as the same
convention applied to three different blob kinds. See
``vs2_scene_gen/checksum.py`` for the full rationale (sha256-truncated-to-8-
hex-digits as a change-detection tripwire, not a security boundary; the
banner/body/blob join being the one place the file's three-part shape is
defined).
"""

import hashlib
import re

BANNER_RE = re.compile(
    r"^# (?P<basename>.+)  -- generated, do not edit\. body-sha: (?P<sha>[0-9a-f]{8})$")
BLOB_RE = re.compile(r"^# behavior-blocks: (?P<data>\S+)$")


def body_sha(body):
    """The 8-hex-digit checksum recorded in the banner, computed over
    ``body`` exactly as :func:`split_generated_file` would hand it back --
    UTF-8 bytes, sha256, first 8 hex digits."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:8]


def make_banner(basename, sha):
    return "# %s  -- generated, do not edit. body-sha: %s" % (basename, sha)


def make_blob_line(blob_text):
    return "# behavior-blocks: %s" % (blob_text,)


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
        raise ValueError("not a behavior-blocks blob line: %r" % (blob_line,))
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
