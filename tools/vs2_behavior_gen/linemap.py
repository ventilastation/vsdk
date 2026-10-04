"""T17 Phase 3: re-deriving the ``{line: block_id}`` map from a generated
Behavior file's own trailing ``# block: <id>`` comments, and resolving a
real traceback against it.

A parallel of ``tools/vs2_event_gen/linemap.py`` (same task, same package
convention every other module pair in this effort already follows -- see
e.g. ``checksum.py``'s own "third parallel" docstring), applied to
generated ``Behavior``/``StateMachine`` subclasses instead of scene event
mixins. Everything below is deliberately copy-shaped with that module; see
its docstring for the full rationale (why re-parsed rather than a second
stored structure, why the comment format is what it is, why matching a
traceback frame's file is done by basename fallback).
"""

import re

BLOCK_COMMENT_RE = re.compile(r"  # block: (?P<id>\S+)$")
TRACEBACK_FRAME_RE = re.compile(r'File "(?P<file>[^"]*)", line (?P<line>\d+)')


def build_line_map(source_text):
    """``source_text`` (a generated file's full text, exactly as
    :func:`tools.vs2_behavior_gen.generator.generate_source` produced it)
    -> ``{line_number: block_id}`` for every line carrying a trailing
    ``# block: <id>`` comment. 1-indexed, matching a Python traceback
    frame's own ``line`` field."""
    line_map = {}
    for index, line in enumerate(source_text.splitlines(), start=1):
        match = BLOCK_COMMENT_RE.search(line)
        if match:
            line_map[index] = match.group("id")
    return line_map


def _frame_matches(frame_file, filename):
    if frame_file == filename:
        return True
    return frame_file.rsplit("/", 1)[-1] == filename.rsplit("/", 1)[-1]


def resolve_traceback_blocks(traceback_text, filename, source_text):
    """See ``tools.vs2_event_gen.linemap.resolve_traceback_blocks`` for the
    full contract -- identical here, applied to a generated Behavior
    file's own traceback frames instead of a scene event mixin's."""
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
