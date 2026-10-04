// T17 Phase 3: tests for web/vs2-debug-linemap.js -- the browser-side
// counterpart of tools/vs2_event_gen/linemap.py and
// tools/vs2_behavior_gen/linemap.py (block-id trailing comments -> a
// {line: block_id} map -> resolving a captured traceback against it).
// Plain Node script, no browser needed for these pure-function checks --
// the "does the banner actually change in a real page" half is covered
// manually (see this task's report).
//
//   node tests/test_vs2_debug_linemap_js.mjs

import {
  buildLineMap,
  extractTracebackFrames,
  resolveTracebackBlocks,
  resolveTracebackBlocksFromProject,
} from "../web/vs2-debug-linemap.js";

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertEqual(actual, expected, message) {
  const same = JSON.stringify(actual) === JSON.stringify(expected);
  assert(same, `${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

// A tiny stand-in for a real generated file's body -- shaped exactly like
// tools/vs2_behavior_gen/generator.py's own output, block-id comments
// included, so this test does not need to actually run the CPython
// generator to exercise the JS side.
const SAMPLE_SOURCE = [
  "from vs2.behaviors import Behavior",
  "",
  "",
  "class GeneratedProjectile(Behavior):",
  "    def step(self, sprites):",
  "        live = sprites._live",
  "        index = len(live) - 1",
  "        while index >= 0:",
  "            sprite = live[index]",
  "            sprite.shot_flown += self.speed_y  # block: BLK_ACC",
  "            index -= 1",
].join("\n");

function testBuildLineMapFindsExactlyTheCommentedLines() {
  const map = buildLineMap(SAMPLE_SOURCE);
  assertEqual(map.size, 1, "exactly one commented line");
  assertEqual(map.get(10), "BLK_ACC", "line 10 (1-indexed) carries BLK_ACC");
}

function testExtractTracebackFramesParsesEveryFrameInOrder() {
  const tb = [
    "Traceback (most recent call last):",
    '  File "games/x/code/game.py", line 3, in <module>',
    '  File "games/x/code/generated_projectile.py", line 10, in step',
    "AttributeError: 'FakeSprite' object has no attribute 'shot_flown'",
  ].join("\n");
  const frames = extractTracebackFrames(tb);
  assertEqual(frames, [
    { file: "games/x/code/game.py", line: 3 },
    { file: "games/x/code/generated_projectile.py", line: 10 },
  ], "frames in top-to-bottom order");
}

function testResolveTracebackBlocksMatchesByExactFilename() {
  const tb = 'File "generated_projectile.py", line 10, in step';
  const result = resolveTracebackBlocks(tb, "generated_projectile.py", SAMPLE_SOURCE);
  assertEqual(result, [{ line: 10, blockId: "BLK_ACC", file: "generated_projectile.py" }],
    "resolves the exact matching frame");
}

function testResolveTracebackBlocksMatchesByBasenameFallback() {
  // The frame's own recorded path is longer than what the caller passed
  // in (a real interpreter's own __file__ convention vs. a bare basename
  // the caller happens to know) -- still resolves via basename fallback.
  const tb = 'File "games/x/code/generated_projectile.py", line 10, in step';
  const result = resolveTracebackBlocks(tb, "generated_projectile.py", SAMPLE_SOURCE);
  assertEqual(result, [
    { line: 10, blockId: "BLK_ACC", file: "games/x/code/generated_projectile.py" },
  ], "resolves via basename fallback");
}

function testResolveTracebackBlocksSkipsFramesWithNoBlockComment() {
  const tb = 'File "generated_projectile.py", line 6, in step';
  const result = resolveTracebackBlocks(tb, "generated_projectile.py", SAMPLE_SOURCE);
  assertEqual(result, [], "a framework line with no block-id comment resolves to nothing");
}

function testResolveTracebackBlocksIgnoresFramesForOtherFiles() {
  const tb = [
    'File "some_other_file.py", line 10, in whatever',
  ].join("\n");
  const result = resolveTracebackBlocks(tb, "generated_projectile.py", SAMPLE_SOURCE);
  assertEqual(result, [], "a frame naming a different file is not matched");
}

async function testResolveTracebackBlocksFromProjectFetchesEachNamedFileOnce() {
  const tb = [
    'Traceback (most recent call last):',
    '  File "generated_projectile.py", line 10, in step',
    '  File "generated_projectile.py", line 10, in step',
  ].join("\n");
  const reads = [];
  const readProjectFile = async (path, encoding) => {
    reads.push([path, encoding]);
    return { content: SAMPLE_SOURCE };
  };
  const result = await resolveTracebackBlocksFromProject(tb, readProjectFile);
  assertEqual(reads.length, 1, "fetches each distinct named file exactly once");
  assertEqual(result, [
    { line: 10, blockId: "BLK_ACC", file: "generated_projectile.py" },
    { line: 10, blockId: "BLK_ACC", file: "generated_projectile.py" },
  ], "resolves both frames from the one fetched file");
}

async function testResolveTracebackBlocksFromProjectSkipsUnreadableFiles() {
  const tb = 'File "not_a_real_file.py", line 1, in x';
  const readProjectFile = async () => {
    throw new Error("no such file");
  };
  const result = await resolveTracebackBlocksFromProject(tb, readProjectFile);
  assertEqual(result, [], "an unreadable frame file is skipped, not thrown");
}

const syncTests = [
  testBuildLineMapFindsExactlyTheCommentedLines,
  testExtractTracebackFramesParsesEveryFrameInOrder,
  testResolveTracebackBlocksMatchesByExactFilename,
  testResolveTracebackBlocksMatchesByBasenameFallback,
  testResolveTracebackBlocksSkipsFramesWithNoBlockComment,
  testResolveTracebackBlocksIgnoresFramesForOtherFiles,
];

const asyncTests = [
  testResolveTracebackBlocksFromProjectFetchesEachNamedFileOnce,
  testResolveTracebackBlocksFromProjectSkipsUnreadableFiles,
];

for (const test of syncTests) {
  test();
  console.log("ok", test.name);
}

for (const test of asyncTests) {
  await test();
  console.log("ok", test.name);
}

console.log(`vs2 debug linemap (js): ${syncTests.length + asyncTests.length} checks passed`);
