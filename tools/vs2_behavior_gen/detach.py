"""``Detach``: the one-way door out of generation.

Identical in shape and intent to ``tools/vs2_scene_gen/detach.py`` and
``tools/vs2_event_gen/detach.py`` (see either's docstring for the full
rationale): strips the trailing ``# behavior-blocks: ...`` blob comment and
the banner's "generated, do not edit" language, leaving exactly the body --
a plain ``Behavior`` subclass indistinguishable from one that was always
hand-written. One-way: this module's ``checksum`` uses its own
``# behavior-blocks:``-shaped :data:`checksum.BLOB_RE`, so
:func:`is_generated` (and therefore :mod:`generator`'s write path) reports
``False`` for detached text, and there is no flag or registry recording
"this file used to be generated" -- the file's own shape is the only
record.
"""

from . import checksum


class DetachError(ValueError):
    """Raised when asked to detach text that is not generator-managed in
    the first place (no banner+blob found) -- there is nothing to strip."""


def is_generated(text):
    """``True`` if ``text`` has the banner+blob shape :mod:`checksum`
    documents (regardless of whether its checksum currently matches).
    ``False`` for plain Python, including already-detached text."""
    return checksum.split_generated_file(text) is not None


def detach(text):
    """Strip the banner and the blob, one-way. Returns the plain body text
    (ending in exactly one trailing newline).

    Raises:
        DetachError: If ``text`` does not have the generator-managed
            banner+blob shape to begin with.
    """
    parsed = checksum.split_generated_file(text)
    if parsed is None:
        raise DetachError(
            "not a generator-managed file (no banner+blob found); nothing to detach")
    _banner_line, body, _blob_line = parsed
    return body + "\n"


def detach_file(path):
    """Detach the file at ``path`` in place. Returns the new text (see
    :func:`detach`)."""
    text = path.read_text()
    new_text = detach(text)
    path.write_text(new_text)
    return new_text
