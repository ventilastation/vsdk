/**
 * T17 Phase 3: browser-side counterpart of
 * tools/vs2_event_gen/linemap.py and tools/vs2_behavior_gen/linemap.py --
 * re-derive a generated file's own ``{line: block_id}`` map from its
 * trailing ``# block: <id>`` comments, and resolve a captured Python
 * traceback against it.
 *
 * **Why this exists as a small JS port, not left CPython-only.** The
 * task's own bar allows a JS port of the resolver as a stretch goal, not
 * a hard requirement -- but the algorithm itself (regex over `File "...",
 * line N` plus a line-number lookup into a re-parsed comment map) is a
 * handful of lines, not a real "port" of anything complicated, and having
 * it here is what lets web/app.js's own scene-error banner
 * (`renderSceneError()`) show *something real* -- which generated file and
 * block a captured traceback actually names -- instead of stopping at
 * "the banner already shows the raw traceback text, nothing more was
 * wired in." See app.js's own `resolveSceneErrorBlocks()` for where this
 * is used, and this task's report for exactly how far the UI integration
 * goes from there (extending the banner's own text; not opening/
 * highlighting the Blockly workspace itself -- a further stretch goal
 * this pass did not reach).
 *
 * Deliberately kept a pure, dependency-free module (no Blockly, no
 * app.js-specific state) so it can be unit-tested on its own -- see
 * tests/test_vs2beh_linemap_js.mjs.
 */

export const BLOCK_COMMENT_RE = /  # block: (\S+)$/;
export const TRACEBACK_FRAME_RE = /File "([^"]*)", line (\d+)/g;

/** ``sourceText`` (a generated file's full text) -> ``Map<lineNumber,
 * blockId>`` for every line carrying a trailing ``# block: <id>``
 * comment. 1-indexed, matching a Python traceback frame's own line
 * number -- see the two ``linemap.py`` modules this mirrors. */
export function buildLineMap(sourceText) {
  const lineMap = new Map();
  const lines = sourceText.split("\n");
  for (let i = 0; i < lines.length; i += 1) {
    const match = BLOCK_COMMENT_RE.exec(lines[i]);
    if (match) {
      lineMap.set(i + 1, match[1]);
    }
  }
  return lineMap;
}

/** Every ``{file, line}`` traceback frame in ``tracebackText``, in the
 * order they appear (outermost call first, matching a real traceback's
 * own top-to-bottom order). */
export function extractTracebackFrames(tracebackText) {
  const frames = [];
  const re = new RegExp(TRACEBACK_FRAME_RE.source, "g");
  let match;
  while ((match = re.exec(tracebackText)) !== null) {
    frames.push({ file: match[1], line: Number(match[2]) });
  }
  return frames;
}

function frameMatches(frameFile, filename) {
  if (frameFile === filename) {
    return true;
  }
  return frameFile.split("/").pop() === filename.split("/").pop();
}

/** ``tracebackText`` + ``filename`` (the generated file believed
 * implicated) + that file's own ``sourceText`` -> a list of ``{line,
 * blockId}`` objects, one per traceback frame naming ``filename``
 * (matched by basename fallback, see :func:`frameMatches`) whose line
 * carries a block-id comment -- the exact contract
 * ``linemap.py``'s ``resolve_traceback_blocks`` documents, applied here
 * in JS. */
export function resolveTracebackBlocks(tracebackText, filename, sourceText) {
  const lineMap = buildLineMap(sourceText);
  const results = [];
  for (const frame of extractTracebackFrames(tracebackText)) {
    if (!frameMatches(frame.file, filename)) {
      continue;
    }
    const blockId = lineMap.get(frame.line);
    if (blockId) {
      results.push({ line: frame.line, blockId, file: frame.file });
    }
  }
  return results;
}

/**
 * The end-to-end helper `renderSceneError()` actually calls: given a raw
 * traceback string and a `readProjectFile(path, encoding)` function (the
 * same bridge the Save/Load buttons already use --
 * `window.VentilastationWebEmulator.readProjectFile`), fetch every
 * distinct file the traceback names and resolve each of its frames
 * against that file's own line map. A frame naming a file the project
 * file API cannot read (not every traceback frame names a
 * generator-managed file under the project root -- some name framework
 * modules) is skipped silently rather than surfaced as an error: this
 * feature only ever *adds* information to the banner when it can, and
 * changes nothing when it can't.
 */
export async function resolveTracebackBlocksFromProject(tracebackText, readProjectFile) {
  const results = [];
  const seenFiles = new Set();
  for (const frame of extractTracebackFrames(tracebackText)) {
    if (seenFiles.has(frame.file)) {
      continue;
    }
    seenFiles.add(frame.file);
    let sourceText;
    try {
      const fileResult = await readProjectFile(frame.file, "utf8");
      sourceText = typeof fileResult === "string" ? fileResult : fileResult?.content;
    } catch {
      continue; // not a project file this bridge can read -- skip, not an error
    }
    if (typeof sourceText !== "string") {
      continue;
    }
    results.push(...resolveTracebackBlocks(tracebackText, frame.file, sourceText));
  }
  return results;
}
