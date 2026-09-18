"""T17 Phase 3: re-deriving the ``{line: block_id}`` map from a generated
file's own trailing ``# block: <id>`` comments, and resolving a real
traceback against it.

Spec: ``docs/vs2-behaviors-proposal.md``, "### Debugging generated code" --
"The generator emits block IDs as trailing comments and keeps a line map
beside the workspace blob, so the editor highlights the offending block
when a traceback names a generated line."

**Why the line map is re-derived, not stored as a second structure
alongside the blob.** :mod:`generator` already writes ``# block: <id>`` as
a trailing comment on every line a model node with a ``block_id`` produced
(see its own ``_with_block_comment``). The full ``{line: block_id}`` map a
debugger needs is therefore already present, verbatim, in the generated
file's own text -- there is nothing to keep in sync with a second copy, no
extra thing to survive `git mv`/packaging/hand-editing differently than the
code itself does, and no risk of the map silently drifting from the code
if only one of the two were ever updated. The cost is a linear re-scan of
the file's own lines whenever a traceback actually needs resolving, which
is exactly how often this needs to happen (interactively, from a UI
action, or once per captured traceback in a test) and cheap at the file
sizes this generator produces. The alternative the proposal itself allows
("or embedded as a separate structure alongside the existing blob") would
save that re-scan at the cost of a second representation of the same
information; not worth it here.

**Comment format:** ``  # block: <id>`` (two spaces, then the comment),
appended to the end of a rendered line, matching this repo's own
PEP 8-ish "two spaces before an inline comment" convention. The prefix
``# block: `` (singular) does not collide with any of the three existing
``# scene-model:``/``# blocks:``/``# behavior-blocks:`` *blob-line*
prefixes (see ``checksum.py``'s own docstring on that naming history) --
this is a different kind of comment (per-line, not the one trailing blob
line) and deliberately spelled differently so the two are never confused
by a human skimming a generated file.
"""

import re

#: Matches a trailing block-id comment at the end of a line. Anchored to
#: the end of the line (``$``) so it never matches a coincidental
#: occurrence of the same text earlier in a line (block ids are opaque
#: Blockly-assigned strings, but this guards against that anyway).
BLOCK_COMMENT_RE = re.compile(r"  # block: (?P<id>\S+)$")

#: Matches one traceback frame's file+line, exactly the shape both CPython
#: and MicroPython emit: ``File "<path>", line <N>``. ``finditer`` over a
#: full traceback string yields every frame, outermost call first, in the
#: same top-to-bottom order the traceback itself prints them.
TRACEBACK_FRAME_RE = re.compile(r'File "(?P<file>[^"]*)", line (?P<line>\d+)')


def build_line_map(source_text):
    """``source_text`` (a generated file's full text, exactly as
    :func:`tools.vs2_event_gen.generator.generate_source` produced it) ->
    ``{line_number: block_id}`` for every line carrying a trailing
    ``# block: <id>`` comment. 1-indexed, matching a Python traceback
    frame's own ``line`` field."""
    line_map = {}
    for index, line in enumerate(source_text.splitlines(), start=1):
        match = BLOCK_COMMENT_RE.search(line)
        if match:
            line_map[index] = match.group("id")
    return line_map


def _frame_matches(frame_file, filename):
    """True if a traceback frame's own recorded file (whatever the running
    interpreter chose: a full path, a module-relative path, or just a
    basename -- CPython's and MicroPython's own conventions for
    ``__file__``/frame filenames differ, and neither is under this
    module's control) names the same file as ``filename``. Matched by
    exact equality first (the common case), falling back to basename
    equality so e.g. a frame recorded as
    ``games/vs2_examples/x/code/generated_projectile.py`` still matches a
    caller that only knows the bare ``generated_projectile.py``, or vice
    versa."""
    if frame_file == filename:
        return True
    return frame_file.rsplit("/", 1)[-1] == filename.rsplit("/", 1)[-1]


def resolve_traceback_blocks(traceback_text, filename, source_text):
    """``traceback_text`` (a real Python traceback string -- e.g. one
    captured from ``director.report_traceback`` over comms, see
    ``apps/micropython/ventilastation/director.py``'s own
    ``report_traceback``/``tools/pov_profile_report.py``'s ``WireReader``,
    both of which already carry this exact text end to end) + ``filename``
    (the generated file believed implicated) + that file's own
    ``source_text`` -> a list of ``{"line": N, "block_id": id}`` dicts, one
    per traceback frame naming ``filename`` (matched by
    :func:`_frame_matches`) whose line carries a block-id comment, in the
    order the frames appear in ``traceback_text`` (outermost call first).
    A frame naming ``filename`` whose line has no block-id comment
    (framework boilerplate the generator emitted with no originating
    block, e.g. a bare ``super().update()``) is skipped rather than
    reported as a false match."""
    line_map = build_line_map(source_text)
    results = []
    for match in TRACEBACK_FRAME_RE.finditer(traceback_text):
        frame_file = match.group("file")
        if not _frame_matches(frame_file, filename):
            continue
        line_no = int(match.group("line"))
        block_id = line_map.get(line_no)
        if block_id is not None:
            results.append({"line": line_no, "block_id": block_id})
    return results
