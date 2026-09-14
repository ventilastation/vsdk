// `vs2beh` protocol client tests (T12), against a fake in-memory
// transport. Plain Node script, no browser, no MicroPython process --
// this only exercises wire encode/decode and tree-flattening logic. The
// real, running-MicroPython version of this is
// tests/test_vs2beh_live_tune_e2e.mjs.
//
//   node tests/test_vs2beh_client.mjs

import {
  VS2BehClient,
  buildSetCommand,
  buildResetCommand,
  buildListCommand,
  parseListReply,
  parseSetReply,
  flattenSubjects,
} from "../web/vs2beh-client.js";

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertEqual(actual, expected, message) {
  const same = JSON.stringify(actual) === JSON.stringify(expected);
  assert(same, `${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

// The exact sample from docs/vs2-behaviors-proposal.md's "## The live-tune
// loop", verbatim.
const SAMPLE_LIST_REPLY = JSON.stringify({
  subjects: [
    {
      name: "enemies", kind: "pool", count: 6,
      vars: [{ name: "kind", type: "number", value: 0, min: 0, max: 2 }],
      behaviors: [
        {
          name: "damageable", class: "Damageable",
          params: [
            { name: "hp", type: "number", value: 1, min: 1, max: 99, step: 1 },
            { name: "score", type: "number", value: 40, min: 0, max: 9999 },
            { name: "explosion", type: "pool", value: "explosions" },
          ],
          actions: [
            {
              name: "blink", class: "Blink",
              params: [{ name: "on_ticks", type: "number", value: 2, min: 1, max: 60 }],
            },
          ],
        },
      ],
    },
  ],
});

// ---------------------------------------------------------------------------
// Wire command building: matches the spec's own examples byte for byte.
// ---------------------------------------------------------------------------

function testBuildListCommandMatchesSpec() {
  assertEqual(buildListCommand(), "vs2beh list", "list command text");
}

function testBuildSetCommandMatchesSpecExactly() {
  assertEqual(buildSetCommand("enemies.damageable.hp", 2), "vs2beh set enemies.damageable.hp 2",
    "set command matches 'vs2beh set enemies.damageable.hp 2' verbatim");
  assertEqual(buildSetCommand("enemies.damageable.blink.on_ticks", 4),
    "vs2beh set enemies.damageable.blink.on_ticks 4", "nested action-param path");
}

function testBuildSetCommandEncodesNonNumericValues() {
  assertEqual(buildSetCommand("enemies.damageable.explosion", "explosions"),
    "vs2beh set enemies.damageable.explosion explosions", "a bare string value is not JSON-quoted");
  assertEqual(buildSetCommand("enemies.angry_flag", true), "vs2beh set enemies.angry_flag true",
    "a boolean value encodes as a bare token");
}

function testBuildSetCommandRejectsValuesThatWouldBreakTheLineParser() {
  // The device parses with cmd_line.split() (director.py's
  // _dispatch_control()); a value containing whitespace would silently
  // become extra positional arguments, so this must fail loudly on the
  // client instead of sending a line the device can't parse as intended.
  let threw = false;
  try {
    buildSetCommand("enemies.damageable.explosion", "two words");
  } catch (err) {
    threw = true;
  }
  assert(threw, "a value containing whitespace is rejected before it reaches the wire");
}

function testBuildResetCommand() {
  assertEqual(buildResetCommand("enemies.damageable.hp"), "vs2beh reset enemies.damageable.hp",
    "reset command text");
}

// ---------------------------------------------------------------------------
// Reply parsing.
// ---------------------------------------------------------------------------

function testParseListReplyParsesTheSpecSampleVerbatim() {
  const parsed = parseListReply(SAMPLE_LIST_REPLY);
  assertEqual(parsed.subjects.length, 1, "one subject in the sample");
  assertEqual(parsed.subjects[0].name, "enemies", "subject name");
  assertEqual(parsed.subjects[0].behaviors[0].params.length, 3, "three behavior params");
}

function testParseListReplyRejectsMalformedJson() {
  let threw = false;
  try {
    parseListReply("{not json");
  } catch (err) {
    threw = true;
  }
  assert(threw, "malformed JSON raises rather than returning something half-parsed");
}

function testParseListReplyRejectsMissingSubjectsArray() {
  let threw = false;
  try {
    parseListReply(JSON.stringify({ oops: true }));
  } catch (err) {
    threw = true;
  }
  assert(threw, "JSON missing a subjects array is rejected");
}

function testParseSetReplyOk() {
  const parsed = parseSetReply("vs2beh_ok enemies.damageable.hp=2");
  assertEqual(parsed, { ok: true, path: "enemies.damageable.hp", value: "2" }, "ok reply parses path and value");
}

function testParseSetReplyError() {
  const parsed = parseSetReply("vs2beh_error unknown path 'enemies.damageable.hpp'; closest: hp");
  assert(parsed.ok === false, "error reply is not ok");
  assert(parsed.error.includes("closest: hp"), "error message is carried through, naming the closest valid path");
}

function testParseSetReplyRejectsUnrecognisedLines() {
  let threw = false;
  try {
    parseSetReply("garbage line the device should never actually send");
  } catch (err) {
    threw = true;
  }
  assert(threw, "an unrecognised reply line raises rather than being silently accepted");
}

// ---------------------------------------------------------------------------
// Tree flattening: every var/param/action-param gets its correct dotted
// vs2beh path, matching the two-level subject/behavior tree.
// ---------------------------------------------------------------------------

function testFlattenSubjectsProducesCorrectPaths() {
  const listResult = parseListReply(SAMPLE_LIST_REPLY);
  const leaves = flattenSubjects(listResult);
  const paths = leaves.map((leaf) => leaf.path);
  assertEqual(paths, [
    "enemies.kind",
    "enemies.damageable.hp",
    "enemies.damageable.score",
    "enemies.damageable.explosion",
    "enemies.damageable.blink.on_ticks",
  ], "every leaf's path matches what buildSetCommand() would need to address it");

  const kindLeaf = leaves.find((leaf) => leaf.path === "enemies.kind");
  assertEqual(kindLeaf.kind, "var", "the pool var is tagged as a var leaf");

  const hpLeaf = leaves.find((leaf) => leaf.path === "enemies.damageable.hp");
  assertEqual(hpLeaf.kind, "param", "a behavior parameter is tagged as a param leaf");
  assertEqual(hpLeaf.groupName, "damageable", "grouped under its behavior's name");
  assertEqual(hpLeaf.groupClass, "Damageable", "carries the behavior's class name too");

  const blinkLeaf = leaves.find((leaf) => leaf.path === "enemies.damageable.blink.on_ticks");
  assertEqual(blinkLeaf.kind, "action-param", "an action's own parameter is tagged distinctly");
  assertEqual(blinkLeaf.actionName, "blink", "carries which action it belongs to");
}

// ---------------------------------------------------------------------------
// VS2BehClient against a fake transport (no real process involved -- this
// only proves the client drives *a* transport correctly; the real-process
// version is the E2E test).
// ---------------------------------------------------------------------------

function fakeTransport(script) {
  const calls = [];
  return {
    calls,
    async sendLine(text) {
      calls.push(text);
      if (!(text in script)) {
        throw new Error(`fake transport has no scripted reply for: ${text}`);
      }
      return script[text];
    },
  };
}

async function testClientListParsesThroughTheTransport() {
  const transport = fakeTransport({ "vs2beh list": SAMPLE_LIST_REPLY });
  const client = new VS2BehClient(transport);
  const result = await client.list();
  assertEqual(result.subjects[0].name, "enemies", "client.list() returns the parsed subjects tree");
  assertEqual(transport.calls, ["vs2beh list"], "exactly one list command was sent");
}

async function testClientSetSendsTheCorrectLineAndResolves() {
  const transport = fakeTransport({
    "vs2beh set enemies.damageable.hp 2": "vs2beh_ok enemies.damageable.hp=2",
  });
  const client = new VS2BehClient(transport);
  const result = await client.set("enemies.damageable.hp", 2);
  assertEqual(result, { ok: true, path: "enemies.damageable.hp", value: "2" }, "set() resolves with the parsed ok reply");
}

async function testClientSetRejectsOnDeviceError() {
  const transport = fakeTransport({
    "vs2beh set enemies.damageable.zzz 2": "vs2beh_error unknown path 'enemies.damageable.zzz'; closest: hp",
  });
  const client = new VS2BehClient(transport);
  let threw = false;
  try {
    await client.set("enemies.damageable.zzz", 2);
  } catch (err) {
    threw = err.message.includes("closest: hp");
  }
  assert(threw, "client.set() rejects when the device reports an error, surfacing its message");
}

const syncTests = [
  testBuildListCommandMatchesSpec,
  testBuildSetCommandMatchesSpecExactly,
  testBuildSetCommandEncodesNonNumericValues,
  testBuildSetCommandRejectsValuesThatWouldBreakTheLineParser,
  testBuildResetCommand,
  testParseListReplyParsesTheSpecSampleVerbatim,
  testParseListReplyRejectsMalformedJson,
  testParseListReplyRejectsMissingSubjectsArray,
  testParseSetReplyOk,
  testParseSetReplyError,
  testParseSetReplyRejectsUnrecognisedLines,
  testFlattenSubjectsProducesCorrectPaths,
];

const asyncTests = [
  testClientListParsesThroughTheTransport,
  testClientSetSendsTheCorrectLineAndResolves,
  testClientSetRejectsOnDeviceError,
];

for (const test of syncTests) {
  test();
  console.log("ok", test.name);
}

for (const test of asyncTests) {
  await test();
  console.log("ok", test.name);
}

console.log(`vs2beh client: ${syncTests.length + asyncTests.length} checks passed`);
