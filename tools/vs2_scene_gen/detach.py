"""``Detach``: the one-way door out of generation.

Spec: "``Detach`` strips the blob; the file becomes ordinary Python
forever. Explicit, one-way, so nobody is trapped in blocks."

This strips **both** the trailing blob comment and the banner's
"generated, do not edit" language (the proposal leaves the exact scope of
"strips the blob" to the implementer here: "and, your call, the 'GENERATED
do not edit' banner language too"). Judgment call: leaving the banner
behind while removing the blob would produce a file that still *claims*
to be generated (and still names a now-meaningless checksum) but can
never actually be regenerated again -- a confusing, half-true state.
Stripping both leaves exactly the body: ordinary Python, indistinguishable
from a file that was always hand-written.

One-way in the literal sense used elsewhere in this package:
:func:`checksum.split_generated_file` returns ``None`` for detached text
(no banner, no blob), which is exactly the signal
:func:`generator.write_scene_file` reads as ``"detached"`` and refuses to
touch. There is no flag, marker or registry recording "this file used to
be generated" -- the file's own shape *is* the record, and once the shape
is gone, it is gone.
"""

from . import checksum


class DetachError(ValueError):
    """Raised when asked to detach text that is not generator-managed in
    the first place (no banner+blob found) -- there is nothing to strip,
    and silently no-op-ing would hide a caller's mistaken path."""


def is_generated(text):
    """``True`` if ``text`` has the banner+blob shape :mod:`checksum`
    documents (regardless of whether its checksum currently matches --
    see :func:`checksum.is_hand_edited` for that distinction). ``False``
    for plain Python, including already-detached text."""
    return checksum.split_generated_file(text) is not None


def detach(text):
    """Strip the banner and the blob, one-way. Returns the plain body
    text (ending in exactly one trailing newline) -- ordinary Python that
    :func:`is_generated` will report ``False`` for, and that
    :mod:`generator`'s write path will thereafter treat as
    ``"detached"`` (skip, never overwrite) for any model/output pairing
    that used to target this file.

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
