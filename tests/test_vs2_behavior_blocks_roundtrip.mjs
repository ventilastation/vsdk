// T17: round-trip tests for web/vs2-behavior-blocks.js -- the Blockly
// palette's own model <-> workspace hand-walk, with the state-hat shape
// (vs2beh_state_machine / vs2beh_state / hold / goto_state / set_state /
// call_callback / spawn / play_sound) and the binary_op expression block.
//
//   node tests/test_vs2_behavior_blocks_roundtrip.mjs
//
// **No browser, no jsdom, no new dependency.** Blockly's vendored
// blockly_compressed.js is a UMD bundle with a real Node.js branch, and
// Blockly's *data model* (Blockly.Workspace, Blockly.Block, connections,
// fields) is entirely DOM-independent -- only the rendered half
// (Blockly.inject, WorkspaceSvg, BlockSvg.initSvg/render) needs a document.
// This file therefore loads the vendored bundle straight into Node, hands
// it to the module as `window.Blockly`, stubs `fetch` to read
// web/vs2-behavior-catalog.json off disk, and drives
// loadModelIntoWorkspace/serializeWorkspaceToModel against a plain
// `new Blockly.Workspace()`. (newRenderedBlock() feature-tests initSvg for
// exactly this reason -- see its own comment.) The half that genuinely
// cannot run here -- does the toolbox render, does a drag actually refuse
// to snap -- is browser work, checked live; see this task's report.
//
// The primary acceptance target is the real, hand-authored reference
// program games/vs2_examples/vasura_states_demo/code/enemy_states.vs2behavior.json,
// read here strictly as a fixture (never written to -- see
// docs/vs2-behaviors-implementation.md's "Never edit anything under
// games/").

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const WEB = path.join(ROOT, "web");
const REFERENCE_MODEL_PATH = path.join(
  ROOT, "games/vs2_examples/vasura_states_demo/code/enemy_states.vs2behavior.json");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertEqual(actual, expected, message) {
  const same = JSON.stringify(actual) === JSON.stringify(expected);
  assert(same, `${message}:\n  expected ${JSON.stringify(expected)}\n  got      ${JSON.stringify(actual)}`);
}

function assertThrows(fn, fragment, message) {
  let threw = null;
  try {
    fn();
  } catch (err) {
    threw = err;
  }
  assert(threw, `${message}: expected a throw, got none`);
  assert(threw.message.includes(fragment),
    `${message}: expected message containing ${JSON.stringify(fragment)}, got ${JSON.stringify(threw.message)}`);
}

// ---------------------------------------------------------------------------
// Headless Blockly + module bootstrap.
// ---------------------------------------------------------------------------

function loadVendoredBlockly() {
  const src = fs.readFileSync(path.join(WEB, "vendor/blockly/blockly_compressed.js"), "utf8");
  const mod = { exports: {} };
  // The bundle's UMD wrapper takes its `typeof exports === "object"` branch
  // and assigns the namespace to module.exports; nothing in that path
  // touches document or window.
  new Function("module", "exports", "require", src)(mod, mod.exports, () => {
    throw new Error("vendored Blockly should not require() anything");
  });
  assert(mod.exports.Workspace, "vendored Blockly exposes Workspace");
  return mod.exports;
}

const Blockly = loadVendoredBlockly();

// vs2-behavior-blocks.js reaches loadBlockly() -> `window.Blockly?.Workspace`
// and short-circuits when it is already there, and loadCatalog() -> fetch().
// Both are satisfied without a browser.
globalThis.window = { Blockly };
globalThis.fetch = async (url) => {
  const filePath = path.join(WEB, String(url).replace(/^\.\//, ""));
  return {
    ok: true,
    status: 200,
    json: async () => JSON.parse(fs.readFileSync(filePath, "utf8")),
  };
};

const blocksModule = await import(path.join(WEB, "vs2-behavior-blocks.js"));
const { ensureBlocksDefined, loadModelIntoWorkspace, serializeWorkspaceToModel,
  buildToolboxXml } = blocksModule;
const { catalog } = await ensureBlocksDefined();

function newWorkspace() {
  return new Blockly.Workspace();
}

function roundTrip(model) {
  const workspace = newWorkspace();
  loadModelIntoWorkspace(workspace, model);
  return serializeWorkspaceToModel(workspace);
}

// ---------------------------------------------------------------------------
// Semantic equivalence: the three representational differences a
// model -> blocks -> model trip is *expected* to introduce, each absorbed
// by one explicit normalization rule so nothing else can hide behind them.
// ---------------------------------------------------------------------------

/** Every catalog field that is rendered as a plain Blockly field (dropdown,
 * checkbox, text) rather than a value socket, mapped to its declared
 * default. Such a field always has *some* value on a block -- there is no
 * "unset" state for a dropdown -- so a model that omitted it comes back
 * carrying the default explicitly. Only that exact case is normalized
 * away; any other added arg, or any changed value, still fails. */
function catalogDefaultLiterals(actionClass) {
  const entry = catalog.actions.find((action) => action.name === actionClass);
  assert(entry, `catalog has an entry for ${actionClass}`);
  const defaults = new Map();
  for (const field of [...entry.params, ...entry.extra_fields]) {
    if (field.type === "choice" || field.type === "flag" || field.type === "string") {
      defaults.set(field.name, field.default);
    }
  }
  return defaults;
}

function normalizeActionArgs(actionClass, args, originalArgs) {
  const defaults = catalogDefaultLiterals(actionClass);
  const out = {};
  for (const [name, expr] of Object.entries(args)) {
    const addedByTheEditor = originalArgs && !(name in originalArgs)
      && defaults.has(name) && expr.kind === "literal" && expr.value === defaults.get(name);
    if (!addedByTheEditor) {
      out[name] = expr;
    }
  }
  return out;
}

/** Strip `block_id` recursively. Fresh blocks get fresh Blockly ids
 * wherever the source model carried none (the hand-authored reference file
 * carries none at all), so ids are never comparable across a reload. */
function stripBlockIds(value) {
  if (Array.isArray(value)) {
    return value.map(stripBlockIds);
  }
  if (value && typeof value === "object") {
    const out = {};
    for (const [key, entry] of Object.entries(value)) {
      if (key !== "block_id") {
        out[key] = stripBlockIds(entry);
      }
    }
    return out;
  }
  return value;
}

/** Replace every `if_action` node's `bind` with the *content* of the action
 * it names, and replace the model's own `actions` list with the distinct
 * set of those contents.
 *
 * Two expected differences collapse here at once. (1) Bind names are
 * invented at serialization time (makeBindAllocator -- "an author never
 * types this"), so the reference file's hand-chosen `hit` comes back as
 * `collide`. (2) One shared action declaration referenced from three
 * `if_action` nodes comes back as three identical declarations, because an
 * `if_action` renders as a self-contained block with the Action's fields
 * inline. Inlining makes both invisible while keeping every *meaningful*
 * difference -- which Action class, with which arguments, tested at which
 * point in which state body -- fully compared. */
function inlineActions(model) {
  const byBind = new Map((model.actions || []).map((action) => [action.bind, action]));
  const distinct = [];
  const seen = new Set();

  const inlineOne = (bind, originalArgsFor) => {
    const decl = byBind.get(bind);
    assert(decl, `if_action bind ${JSON.stringify(bind)} names a declared action`);
    const inlined = {
      action_class: decl.action_class,
      args: normalizeActionArgs(decl.action_class, decl.args, originalArgsFor),
    };
    const key = JSON.stringify(inlined);
    if (!seen.has(key)) {
      seen.add(key);
      distinct.push(inlined);
    }
    return inlined;
  };

  const walkNodes = (nodes) => nodes.map((node) => {
    if (node.kind === "if_action") {
      const { bind, ...rest } = node;
      return { ...rest, action: inlineOne(bind), then: walkNodes(node.then),
        else: walkNodes(node.else || []) };
    }
    if (node.kind === "if_else") {
      return { ...node, then: walkNodes(node.then), else: walkNodes(node.else || []) };
    }
    return node;
  });

  const out = { ...model, per_sprite: walkNodes(model.per_sprite || []) };
  if (model.state_machine) {
    const bodies = {};
    for (const [name, body] of Object.entries(model.state_machine.bodies)) {
      const outBody = {};
      for (const hook of ["enter", "step", "exit"]) {
        if (hook in body) {
          outBody[hook] = walkNodes(body[hook]);
        }
      }
      bodies[name] = outBody;
    }
    out.state_machine = { ...model.state_machine, bodies };
  }
  // apply_to_all binds stay as-is: their *order* is the meaning, and the
  // flat path's own tests below compare them directly.
  out.actions = distinct;
  return out;
}

/** Canonical JSON: object keys sorted, so key *insertion* order (which the
 * model schema attaches no meaning to, and which a hand-authored file
 * spells however a formatter left it) never fails a comparison, while list
 * order (which the schema very much does attach meaning to -- statement
 * order, state declaration order) is preserved exactly. */
function canonical(value) {
  if (Array.isArray(value)) {
    return value.map(canonical);
  }
  if (value && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value).sort()) {
      out[key] = canonical(value[key]);
    }
    return out;
  }
  return value;
}

/** The `normalizeActionArgs` pass above needs to know which args the
 * *original* carried, to tell "the editor filled in a dropdown default"
 * from "the editor invented an argument". Applied to the round-tripped
 * model only, against the original's own per-class arg sets. */
function withOriginalArgsKnown(roundTripped, original) {
  const originalArgsByClass = new Map();
  for (const action of original.actions || []) {
    originalArgsByClass.set(action.action_class, action.args);
  }
  const out = JSON.parse(JSON.stringify(roundTripped));
  for (const action of out.actions || []) {
    action.args = normalizeActionArgs(
      action.action_class, action.args, originalArgsByClass.get(action.action_class));
  }
  return out;
}

function assertSemanticallyEqual(roundTripped, original, message) {
  const left = canonical(inlineActions(stripBlockIds(
    withOriginalArgsKnown(roundTripped, original))));
  const right = canonical(inlineActions(stripBlockIds(original)));
  assertEqual(left, right, message);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

function testReferenceStateHatProgramRoundTrips() {
  const original = JSON.parse(fs.readFileSync(REFERENCE_MODEL_PATH, "utf8"));
  const again = roundTrip(original);
  assertSemanticallyEqual(again, original,
    "the vasura_states_demo state-hat reference program survives model -> blocks -> model");
}

function testReferenceProgramKeepsTheStateHatShapeExactly() {
  const original = JSON.parse(fs.readFileSync(REFERENCE_MODEL_PATH, "utf8"));
  const again = roundTrip(original);

  assertEqual(again.state_machine.states, original.state_machine.states,
    "state declaration order is preserved");
  assertEqual(again.state_machine.initial, "orbiting", "initial state is preserved");
  assertEqual(again.apply_to_all, [], "a state-hat model emits an empty apply_to_all");
  assertEqual(again.per_sprite, [], "a state-hat model emits an empty per_sprite");
  assertEqual(again.subject_kind, "pool", "subject kind is preserved");
  assertEqual(again.class_name, "EnemyStates", "class name is preserved");

  // The hook-omission convention, checked directly rather than only through
  // the deep compare: `step` is always there, enter/exit only when used.
  for (const [name, body] of Object.entries(again.state_machine.bodies)) {
    assert("step" in body, `state ${name} always carries a 'step' body`);
    for (const hook of ["enter", "exit"]) {
      assert(!(hook in body) || body[hook].length > 0,
        `state ${name} only carries '${hook}' when it is non-empty`);
    }
  }
  assert(!("exit" in again.state_machine.bodies.orbiting),
    "orbiting declares no 'exit' hook, so none is emitted");
  assert(!("enter" in again.state_machine.bodies.falling),
    "falling declares no 'enter' hook, so none is emitted");

  // The built-in sprite fields must not leak into the declared state list:
  // "falling" accumulates straight into sprite.y, and declaring `y` would
  // make the generator shadow the real field.
  assertEqual(again.state, [], "x/y/visible are never collected as declared state fields");
}

function testEveryPhase2NodeKindSurvivesTheTrip() {
  // Every kind at once, in the two places each is legal, including a
  // nested binary_op -- the reference program exercises most of these but
  // not set_state, and not arithmetic at all.
  const model = {
    version: 1,
    class_name: "Everything",
    subject_kind: "pool",
    params: [
      { name: "speed", type: "number", default: 1, min: 0, max: 8, step: 0.25,
        label: "Speed", unit: "led/tick" },
      { name: "debris", type: "pool", default: null, label: "Debris" },
      { name: "boom", type: "sound", default: null, label: "Boom" },
      { name: "notify", type: "callback", default: null, label: "Notify" },
    ],
    state: ["ticks_left"],
    actions: [],
    apply_to_all: [],
    per_sprite: [],
    state_machine: {
      states: ["waiting", "dying"],
      initial: "waiting",
      bodies: {
        waiting: {
          enter: [
            { kind: "hold", ticks: { kind: "literal", value: 30 }, then: "dying" },
            { kind: "set_state", state: "ticks_left",
              value: { kind: "binary_op", op: "max",
                left: { kind: "literal", value: 0 },
                right: { kind: "binary_op", op: "-",
                  left: { kind: "state", name: "y" },
                  right: { kind: "param", name: "speed" } } } },
          ],
          step: [
            { kind: "accumulate", state: "ticks_left",
              amount: { kind: "binary_op", op: "*",
                left: { kind: "param", name: "speed" },
                right: { kind: "literal", value: 2 } } },
            { kind: "if_else",
              condition: { kind: "compare", op: "<=",
                left: { kind: "state", name: "ticks_left" },
                right: { kind: "literal", value: 0 } },
              then: [{ kind: "goto_state", name: "dying" }],
              else: [] },
          ],
          // `visible` is one of model.py's BUILTIN_SPRITE_FIELDS, and 0/1
          // is how this palette writes it: the literal block is a
          // field_number, so a genuine `false` is refused rather than
          // coerced (see exprToBlock) and is covered separately below.
          exit: [{ kind: "set_state", state: "visible",
            value: { kind: "literal", value: 0 } }],
        },
        dying: {
          enter: [
            { kind: "play_sound", name: "boom" },
            { kind: "spawn", pool: "debris",
              x: { kind: "state", name: "x" }, y: { kind: "state", name: "y" } },
            { kind: "call_callback", name: "notify", args: [] },
          ],
          step: [{ kind: "despawn" }],
        },
      },
    },
  };
  const again = roundTrip(model);
  assertSemanticallyEqual(again, model, "every Phase-2 node kind survives the trip");
  assertEqual(again.state, ["ticks_left"],
    "only the genuinely declared state field is collected back");
}

function testFlatTwoZoneProgramStillRoundTripsUnchanged() {
  // The Phase-1 shape must be untouched by all of the above -- including
  // its own connection types still being accepted by the flat hat's zones.
  const model = {
    version: 1,
    class_name: "GeneratedProjectile",
    subject_kind: "pool",
    params: [
      { name: "speed_y", type: "number", default: 8, min: -32, max: 32, step: 0.25 },
      { name: "range", type: "number", default: 180, min: 1, max: 255, step: 1 },
      { name: "hits", type: "pool", default: null, label: "Hits what" },
    ],
    state: ["shot_flown"],
    actions: [
      { bind: "move", action_class: "Move",
        args: { speed_y: { kind: "param", name: "speed_y" } } },
      { bind: "hit", action_class: "Collide",
        args: { targets: { kind: "param", name: "hits" } } },
    ],
    apply_to_all: ["move"],
    per_sprite: [
      { kind: "accumulate", state: "shot_flown",
        amount: { kind: "param", name: "speed_y" } },
      { kind: "if_else",
        condition: { kind: "compare", op: ">",
          left: { kind: "state", name: "shot_flown" },
          right: { kind: "param", name: "range" } },
        then: [{ kind: "despawn" }],
        else: [{ kind: "if_action", bind: "hit",
          then: [{ kind: "despawn_hit" }, { kind: "despawn" }], else: [] }] },
    ],
  };
  const again = roundTrip(model);
  assert(!("state_machine" in again), "a flat program gains no state_machine key");
  assertEqual(again.apply_to_all.length, 1, "the apply-to-all zone still serializes");
  assertSemanticallyEqual(again, model, "the Phase-1 flat shape is unchanged");
}

function testHoldAndGotoStateCannotEnterTheFlatPerSpriteZone() {
  // The one restriction Blockly itself enforces (see the module docstring):
  // a state-body-only block's previousStatement type has no overlap with
  // the flat hat's "for each sprite" input check, so the connection is
  // refused outright -- not reported later.
  const workspace = newWorkspace();
  const flatHat = workspace.newBlock("vs2beh_when_ticks");
  const stateHat = workspace.newBlock("vs2beh_state_machine");
  const stateBlock = workspace.newBlock("vs2beh_state");
  // Blockly's own checker -- the very object a real drag consults -- so
  // this asserts the shipped behaviour, not a re-implementation of it.
  const checker = workspace.connectionChecker;
  const connects = (input, block) => checker.canConnect(
    input.connection, block.previousConnection, false);

  for (const type of ["vs2beh_hold", "vs2beh_goto_state"]) {
    const block = workspace.newBlock(type);
    assert(!connects(flatHat.getInput("PER_SPRITE"), block),
      `${type} is refused by the flat 'for each sprite' zone`);
    assert(connects(stateBlock.getInput("STEP"), block),
      `${type} is accepted by a state's own step body`);
    assert(connects(stateBlock.getInput("ENTER"), block),
      `${type} is accepted by a state's own enter body`);
  }

  // ...while every shared PER_SPRITE_KINDS block connects in both.
  for (const type of ["vs2beh_accumulate", "vs2beh_set_state", "vs2beh_if_else",
    "vs2beh_despawn", "vs2beh_despawn_hit", "vs2beh_spawn", "vs2beh_play_sound",
    "vs2beh_call_callback", "vs2beh_if_collide"]) {
    const block = workspace.newBlock(type);
    assert(connects(flatHat.getInput("PER_SPRITE"), block),
      `${type} connects in the flat per-sprite zone`);
    assert(connects(stateBlock.getInput("STEP"), block),
      `${type} connects in a state body`);
  }

  // A nested "do"/"then" stack keeps the same dual shape, so a goto_state
  // can sit inside an if_else inside a state body (exactly what the
  // reference program's "falling" state does).
  const ifElse = workspace.newBlock("vs2beh_if_else");
  const ifCollide = workspace.newBlock("vs2beh_if_collide");
  const goto1 = workspace.newBlock("vs2beh_goto_state");
  assert(connects(ifElse.getInput("THEN"), goto1),
    "goto_state nests inside an if_else's 'do' stack");
  assert(connects(ifCollide.getInput("DO"), goto1),
    "goto_state nests inside a Collide condition's 'do' stack");

  // An apply-to-all Action still cannot reach any per-sprite zone -- the
  // one restriction Phase 1 made fully structural must survive all of the
  // above.
  const uniformMove = workspace.newBlock("vs2beh_action_move");
  assert(!connects(flatHat.getInput("PER_SPRITE"), uniformMove),
    "an apply-to-all Action is still refused by the per-sprite zone");
  assert(!connects(stateBlock.getInput("STEP"), uniformMove),
    "an apply-to-all Action is refused by a state body too");

  // A state declaration belongs to the state hat and nowhere else.
  const anotherState = workspace.newBlock("vs2beh_state");
  assert(connects(stateHat.getInput("STATES"), anotherState),
    "a state block connects to the state hat");
  assert(!connects(flatHat.getInput("PER_SPRITE"), anotherState),
    "a state block is refused by the flat zone");
}

function testANonNumericLiteralIsRefusedRatherThanCoerced() {
  const model = JSON.parse(fs.readFileSync(REFERENCE_MODEL_PATH, "utf8"));
  model.state_machine.bodies.falling.step[0].amount = { kind: "literal", value: false };
  assertThrows(() => roundTrip(model), "not a number",
    "a bool literal is refused, not silently rendered as 0");
}

function testTwoHatsInOneWorkspaceIsRefused() {
  const workspace = newWorkspace();
  const flatHat = workspace.newBlock("vs2beh_when_ticks");
  flatHat.setFieldValue("A", "CLASS_NAME");
  const stateHat = workspace.newBlock("vs2beh_state_machine");
  stateHat.setFieldValue("B", "CLASS_NAME");
  assertThrows(() => serializeWorkspaceToModel(workspace), "one or the other",
    "a workspace holding both hats is refused rather than half-serialized");
}

function testEmptyWorkspaceIsRefused() {
  assertThrows(() => serializeWorkspaceToModel(newWorkspace()), "no 'when ... ticks'",
    "an empty workspace is refused");
}

function testCallCallbackWithArgumentsIsRefusedRatherThanSilentlyTruncated() {
  const model = JSON.parse(fs.readFileSync(REFERENCE_MODEL_PATH, "utf8"));
  model.state_machine.bodies.exploding.enter[2].args = [{ kind: "literal", value: 1 }];
  assertThrows(() => roundTrip(model), "zero-arity",
    "a callback with arguments is refused by the zero-arity block");
}

function testUnbuiltParameterTypeIsRefusedRatherThanRetyped() {
  const model = JSON.parse(fs.readFileSync(REFERENCE_MODEL_PATH, "utf8"));
  model.params.push({ name: "blink", type: "flag", default: true, label: "Blink" });
  assertThrows(() => roundTrip(model), "no parameter-declaration block for type 'flag'",
    "an unbuilt parameter type is refused, not silently rendered as a number");
}

function testToolboxOffersEveryNewBlock() {
  const xml = buildToolboxXml(catalog);
  for (const type of ["vs2beh_state_machine", "vs2beh_state", "vs2beh_hold",
    "vs2beh_goto_state", "vs2beh_set_state", "vs2beh_call_callback", "vs2beh_spawn",
    "vs2beh_play_sound", "vs2beh_expr_binary_op", "vs2beh_declare_sound",
    "vs2beh_declare_callback"]) {
    assert(xml.includes(`<block type="${type}">`), `the toolbox offers ${type}`);
  }
  assert(xml.includes('<category name="States"'), "the toolbox has a States category");
}

/** The strongest check available here: hand the round-tripped model to the
 * real tools/vs2_behavior_gen/model.validate_model, which is the only
 * authority on whether this JSON is acceptable at all (every field name,
 * every required/optional distinction). Skipped with a warning if python3
 * is absent -- though tests/run_tests.py is itself python3, so under the
 * repo's own runner it always runs. */
function testRoundTrippedModelsPassTheRealValidator() {
  const models = {
    reference: roundTrip(JSON.parse(fs.readFileSync(REFERENCE_MODEL_PATH, "utf8"))),
  };
  const script = [
    "import json, sys",
    "sys.path.insert(0, sys.argv[1])",
    "from tools.vs2_behavior_gen.model import validate_model",
    "for name, model in json.load(sys.stdin).items():",
    "    validate_model(model)",
    "print('ok')",
  ].join("\n");
  const result = spawnSync("python3", ["-c", script, ROOT], {
    input: JSON.stringify(models), encoding: "utf8",
  });
  if (result.error && result.error.code === "ENOENT") {
    console.log("SKIP validate_model check (python3 not on PATH)");
    return;
  }
  assert(result.status === 0,
    `validate_model rejected a round-tripped model:\n${result.stderr || result.stdout}`);
}

const TESTS = [
  testReferenceStateHatProgramRoundTrips,
  testReferenceProgramKeepsTheStateHatShapeExactly,
  testEveryPhase2NodeKindSurvivesTheTrip,
  testFlatTwoZoneProgramStillRoundTripsUnchanged,
  testHoldAndGotoStateCannotEnterTheFlatPerSpriteZone,
  testTwoHatsInOneWorkspaceIsRefused,
  testEmptyWorkspaceIsRefused,
  testCallCallbackWithArgumentsIsRefusedRatherThanSilentlyTruncated,
  testUnbuiltParameterTypeIsRefusedRatherThanRetyped,
  testANonNumericLiteralIsRefusedRatherThanCoerced,
  testToolboxOffersEveryNewBlock,
  testRoundTrippedModelsPassTheRealValidator,
];

let failures = 0;
for (const test of TESTS) {
  try {
    test();
    console.log(`PASS ${test.name}`);
  } catch (err) {
    failures += 1;
    console.error(`FAIL ${test.name}: ${err.message}`);
  }
}
if (failures) {
  console.error(`${failures} failure(s)`);
  process.exit(1);
}
console.log("all vs2-behavior-blocks round-trip tests passed");
