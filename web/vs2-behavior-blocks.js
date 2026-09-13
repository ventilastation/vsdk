/**
 * T17 Phase 1: the Blockly-for-Behaviors palette (tier 5, generated from
 * parameter declarations) plus the two-zone tick skeleton, over the exact
 * vocabulary tools/vs2_behavior_gen/model.py validates.
 *
 * Spec: docs/vs2-behaviors-proposal.md, "## The block editor" -- "Only
 * tier 5 is generated from parameter declarations ... a new Action appears
 * in palette, panel, protocol and reference docs at once" -- and "### The
 * tick skeleton makes the fast shape unavoidable": "Uniform work physically
 * cannot land inside the per-sprite loop, so generated code is right by
 * construction."
 *
 * **The Action blocks below are built at runtime from
 * ./vs2-behavior-catalog.json**, not hand-typed the way T16's event-sheet
 * BLOCK_JSON is (see vs2-event-sheet.js) -- one field per declared
 * vs2.params.Parameter, in the same "type -> Blockly field" mapping every
 * other consumer of that introspection uses (the property panel,
 * apps/micropython/ventilastation/behavior_control.py's wire protocol).
 * See buildActionFieldSpecs() for the mapping, and catalog.py's own
 * docstring for the one real gap in it: Collide's targets/radius/space and
 * Animate's field are plain constructor keywords, not declared parameters,
 * so the catalog's own "extra_fields" list (not "params") is what supplies
 * them here -- rendered exactly the same way, because a block author does
 * not need to know or care which list a field came from.
 *
 * **Structural enforcement of the two-zone rule.** Every "apply to all"
 * Action block declares previousStatement/nextStatement type
 * "vs2beh_uniform_action"; the hat block's own "apply to all" statement
 * input is the *only* input anywhere in this file with a matching check.
 * Every per-sprite statement (including the Collide-as-condition block and
 * its own nested "do" stack) declares "vs2beh_sprite_statement" instead,
 * and the hat's "for each sprite" input is the only place that connects.
 * Blockly's own connection-checking refuses a mismatched drag outright --
 * this is not a generator-side check that runs after the fact; see this
 * task's report for how that was verified in a live browser (drag a Move
 * block toward the per-sprite zone and watch it fail to snap in).
 *
 * **Why only Collide gets an "if" (condition) flavor, not all four
 * Actions.** A first draft generated one uniformly for every catalog
 * Action ("if <Action> found something, do..."), matching Move/MoveTo/
 * Animate/Collide with no special-casing. That is wrong for three of the
 * four: run_one()'s "found something" result is a *sprite* only for
 * Collide -- MoveTo/Animate report vs2.DONE (a sentinel, not a sprite) on
 * arrival/cycle-end, and Move never returns anything at all. A generic
 * "despawn what it found" block plugged under a MoveTo-flavored condition
 * would call `.despawn()` on vs2.DONE and crash. So this module builds the
 * condition flavor only for Collide, where "the thing it found" really is
 * a sprite worth despawning -- a deliberate narrowing from "no Action is
 * special-cased" for real-correctness reasons, not an oversight. A future
 * phase adding an Action whose run_one() returns another sprite (a
 * TileUnder-like probe, say) would get the same treatment; one that
 * returns vs2.DONE would not.
 *
 * **What is NOT generic here, and why.** Per-sprite `despawn_hit` is not
 * restricted, via Blockly's own connection types, to only ever sit inside
 * a Collide-condition's own "do" stack -- it shares the plain
 * "vs2beh_sprite_statement" type with every other per-sprite statement, so
 * it *can* be dragged into the general "for each sprite" zone directly.
 * Doing so generates code that raises `GeneratorError` at generate time
 * (tools/vs2_behavior_gen/generator.py's `_render_per_sprite_node`) rather
 * than being structurally unreachable in blocks. This is a deliberate,
 * narrower scope than the one required restriction (apply-to-all vs.
 * per-sprite): the proposal's own words for exactly this situation --
 * "Where prevention cannot reach ... the editor warns in place" -- and
 * "the block tier prevents errors; the Python tier reports them" already
 * anticipates a tier that reports rather than a block tier that prevents
 * every possible misuse. The one restriction the T17 dispatch explicitly
 * requires (apply-to-all cannot land in the per-sprite zone) *is* fully
 * Blockly-enforced; this finer one is not, and is flagged here rather than
 * silently assumed equivalent.
 *
 * **T17 Phase 3: every Action-declaration and per-sprite-node block's own
 * ``.id`` rides along as ``block_id`` in the serialized model**, the same
 * addition ``vs2-event-sheet.js`` makes for T16's schema -- see that
 * module's own docstring for why (``tools/vs2_behavior_gen/generator.py``
 * emits a trailing ``# block: <id>`` comment on the line(s) each block
 * produced, so a captured traceback resolves back to the exact block --
 * ``linemap.py``). Not every node kind in this schema has a Blockly block
 * yet (state-hat-only kinds -- ``hold``/``goto_state``/``set_state``/
 * ``call_callback``/``spawn``/``play_sound`` -- have no palette entry in
 * this file at all, a pre-existing Phase 1/2 scope gap this task does not
 * fill, see this task's report), so only the kinds this module actually
 * serializes carry a real ``block_id``; the rest simply validate with
 * none, exactly as the model schema's own "optional everywhere" design
 * allows.
 */

import { loadBlockly } from "./vs2-event-sheet.js?v=20260913b";

const CATALOG_URL = "./vs2-behavior-catalog.json";

let catalogPromise = null;

/** Fetch and cache ./vs2-behavior-catalog.json (see
 * tools/vs2_behavior_gen/generate_catalog.py -- this is the committed,
 * build-time-generated file, fetched over plain HTTP with no server
 * logic, exactly like web/runtime-manifest.json). */
export function loadCatalog() {
  if (!catalogPromise) {
    catalogPromise = fetch(CATALOG_URL).then((response) => {
      if (!response.ok) {
        throw new Error(`Failed to fetch ${CATALOG_URL}: ${response.status}`);
      }
      return response.json();
    });
  }
  return catalogPromise;
}

// ---------------------------------------------------------------------------
// Action classes this Phase-1 palette gives an "if" (condition) flavor to,
// beyond the "do" (uniform) flavor every catalog Action gets -- see this
// module's docstring for why the set is {"Collide"} and not all four.
// ---------------------------------------------------------------------------
const CONDITION_FLAVOR_ACTIONS = new Set(["Collide"]);

function upperFieldName(name) {
  return name.toUpperCase();
}

/** One catalog action entry (params ++ extra_fields, both already
 * name-sorted by catalog.py) -> the ordered list of Blockly field specs
 * this module renders for it. Each spec is
 * {name, argName, kind: "value"|"dropdown"|"checkbox"|"text", type,
 *  options}. `kind` "value" means an input_value socket (check
 * "vs2beh_expr") -- a literal or a "param NAME" expression block plugs in
 * there; every other kind is a plain literal Blockly field.
 */
function fieldSpecsForAction(actionEntry) {
  const specs = [];
  const allFields = [...actionEntry.params, ...actionEntry.extra_fields];
  for (const field of allFields) {
    const argName = upperFieldName(field.name);
    if (field.type === "choice") {
      specs.push({
        name: field.name, argName, kind: "dropdown", type: field.type,
        options: (field.options || []).map((opt) => [String(opt), String(opt)]),
        default: field.default,
      });
    } else if (field.type === "flag") {
      specs.push({ name: field.name, argName, kind: "checkbox", type: field.type,
        default: !!field.default });
    } else if (field.type === "string") {
      specs.push({ name: field.name, argName, kind: "text", type: field.type,
        default: field.default ?? "" });
    } else {
      // number, angle, frames, pool, sound, image, points, callback:
      // rendered as a value socket. A pool-typed socket only makes sense
      // fed by a "param NAME" expression (there is no literal pool), but
      // that is a matter for the author to get right, not something this
      // minimal palette enforces with a second, pool-only expression
      // block -- see this module's docstring on scope.
      specs.push({ name: field.name, argName, kind: "value", type: field.type });
    }
  }
  return specs;
}

/** Build a Blockly JSON block definition for one catalog Action, in either
 * flavor. `flavor` "do" -> a plain statement block for the apply-to-all
 * zone (check "vs2beh_uniform_action"); "if" -> a condition-with-do-stack
 * block for the per-sprite zone (check "vs2beh_sprite_statement", its own
 * nested "do" stack also "vs2beh_sprite_statement"). */
function buildActionBlockJson(actionEntry, flavor) {
  const specs = fieldSpecsForAction(actionEntry);
  const blockType = flavor === "if"
    ? `vs2beh_if_${actionEntry.name.toLowerCase()}`
    : `vs2beh_action_${actionEntry.name.toLowerCase()}`;

  const args0 = [];
  const messageParts = [flavor === "if" ? `if ${actionEntry.name}` : actionEntry.name];
  let argIndex = 1;
  for (const spec of specs) {
    messageParts.push(`${spec.name} %${argIndex}`);
    argIndex += 1;
    if (spec.kind === "value") {
      args0.push({ type: "input_value", name: spec.argName, check: "vs2beh_expr" });
    } else if (spec.kind === "dropdown") {
      args0.push({
        type: "field_dropdown", name: spec.argName,
        options: spec.options.length ? spec.options : [["", ""]],
      });
    } else if (spec.kind === "checkbox") {
      args0.push({ type: "field_checkbox", name: spec.argName, checked: spec.default });
    } else {
      args0.push({ type: "field_input", name: spec.argName, text: String(spec.default) });
    }
  }

  const json = {
    type: blockType,
    message0: messageParts.join(" "),
    args0,
    inputsInline: false,
    colour: flavor === "if" ? 45 : 20,
    tooltip: actionEntry.doc,
  };

  if (flavor === "if") {
    json.message1 = "found a hit, do %1";
    json.args1 = [{ type: "input_statement", name: "DO", check: "vs2beh_sprite_statement" }];
    json.previousStatement = "vs2beh_sprite_statement";
    json.nextStatement = "vs2beh_sprite_statement";
  } else {
    json.previousStatement = "vs2beh_uniform_action";
    json.nextStatement = "vs2beh_uniform_action";
  }

  return { json, specs, blockType, actionName: actionEntry.name, flavor };
}

// ---------------------------------------------------------------------------
// Hand-authored blocks: the tick skeleton itself, parameter declarations,
// expressions, and the small per-sprite decision vocabulary Projectile
// needs. None of these come from vs2.params.introspect() -- they are new
// editor infrastructure this phase had to invent to make the skeleton
// authorable at all (declaring a Behavior's own parameters, referencing
// per-sprite state) -- see model.py's module docstring for the schema they
// serialize to.
// ---------------------------------------------------------------------------

const STATIC_BLOCK_JSON = [
  {
    type: "vs2beh_when_ticks",
    message0: "when %1 ( %2 ) ticks",
    args0: [
      { type: "field_input", name: "CLASS_NAME", text: "MyBehavior" },
      { type: "field_dropdown", name: "SUBJECT_KIND",
        options: [["pool", "pool"], ["sprite", "sprite"]] },
    ],
    message1: "parameters %1",
    args1: [{ type: "input_statement", name: "PARAMS", check: "vs2beh_param_decl" }],
    message2: "apply to all %1",
    args2: [{ type: "input_statement", name: "APPLY_ALL", check: "vs2beh_uniform_action" }],
    message3: "for each sprite %1",
    args3: [{ type: "input_statement", name: "PER_SPRITE", check: "vs2beh_sprite_statement" }],
    colour: 160,
    tooltip: "The two-zone tick skeleton: uniform work applied to every "
      + "sprite at once, then per-sprite decisions -- see the proposal's "
      + "'The tick skeleton makes the fast shape unavoidable'.",
  },
  // -- Parameter declarations: one block per type Phase 1's proving case
  // (Projectile) actually needs. Extending to the remaining vs2.params
  // types (Flag, Choice, Frames, Sound, Image, Points, Callback) is the
  // same mechanical shape -- not built here, see this file's own report.
  {
    type: "vs2beh_declare_number",
    message0: "number %1 default %2 min %3 max %4 step %5 label %6 unit %7",
    args0: [
      { type: "field_input", name: "NAME", text: "speed" },
      { type: "field_number", name: "DEFAULT", value: 0 },
      { type: "field_number", name: "MIN", value: -32 },
      { type: "field_number", name: "MAX", value: 32 },
      { type: "field_number", name: "STEP", value: 0.25 },
      { type: "field_input", name: "LABEL", text: "" },
      { type: "field_input", name: "UNIT", text: "" },
    ],
    previousStatement: "vs2beh_param_decl",
    nextStatement: "vs2beh_param_decl",
    colour: 300,
  },
  {
    type: "vs2beh_declare_angle",
    message0: "angle %1 default %2 min %3 max %4 step %5 label %6 unit %7",
    args0: [
      { type: "field_input", name: "NAME", text: "speed_x" },
      { type: "field_number", name: "DEFAULT", value: 0 },
      { type: "field_number", name: "MIN", value: -32 },
      { type: "field_number", name: "MAX", value: 32 },
      { type: "field_number", name: "STEP", value: 0.25 },
      { type: "field_input", name: "LABEL", text: "" },
      { type: "field_input", name: "UNIT", text: "" },
    ],
    previousStatement: "vs2beh_param_decl",
    nextStatement: "vs2beh_param_decl",
    colour: 300,
  },
  {
    type: "vs2beh_declare_pool",
    message0: "pool %1 label %2",
    args0: [
      { type: "field_input", name: "NAME", text: "hits" },
      { type: "field_input", name: "LABEL", text: "" },
    ],
    previousStatement: "vs2beh_param_decl",
    nextStatement: "vs2beh_param_decl",
    colour: 300,
  },
  // -- Per-sprite decisions --
  {
    type: "vs2beh_accumulate",
    message0: "add %1 to state %2",
    args0: [
      { type: "input_value", name: "AMOUNT", check: "vs2beh_expr" },
      { type: "field_input", name: "STATE", text: "shot_flown" },
    ],
    inputsInline: true,
    previousStatement: "vs2beh_sprite_statement",
    nextStatement: "vs2beh_sprite_statement",
    colour: 65,
  },
  {
    type: "vs2beh_if_else",
    message0: "if %1 %2 %3",
    args0: [
      { type: "input_value", name: "LEFT", check: "vs2beh_expr" },
      { type: "field_dropdown", name: "OP",
        options: [["==", "=="], ["!=", "!="], ["<", "<"], [">", ">"],
                  ["<=", "<="], [">=", ">="]] },
      { type: "input_value", name: "RIGHT", check: "vs2beh_expr" },
    ],
    message1: "do %1",
    args1: [{ type: "input_statement", name: "THEN", check: "vs2beh_sprite_statement" }],
    message2: "else %1",
    args2: [{ type: "input_statement", name: "ELSE", check: "vs2beh_sprite_statement" }],
    inputsInline: true,
    previousStatement: "vs2beh_sprite_statement",
    nextStatement: "vs2beh_sprite_statement",
    colour: 65,
  },
  {
    type: "vs2beh_despawn",
    message0: "despawn this sprite",
    previousStatement: "vs2beh_sprite_statement",
    nextStatement: "vs2beh_sprite_statement",
    colour: 0,
  },
  {
    type: "vs2beh_despawn_hit",
    message0: "despawn the sprite found",
    previousStatement: "vs2beh_sprite_statement",
    nextStatement: "vs2beh_sprite_statement",
    colour: 0,
    tooltip: "Only meaningful inside a Collide condition block's own "
      + "'do' stack -- see this file's module docstring on why this is "
      + "checked at generate time, not by Blockly's connection types.",
  },
  // -- Expressions --
  {
    type: "vs2beh_expr_literal_number",
    message0: "%1",
    args0: [{ type: "field_number", name: "VALUE", value: 0 }],
    output: "vs2beh_expr",
    colour: 300,
  },
  {
    type: "vs2beh_expr_param",
    message0: "param %1",
    args0: [{ type: "field_input", name: "NAME", text: "speed_y" }],
    output: "vs2beh_expr",
    colour: 300,
  },
  {
    type: "vs2beh_expr_state",
    message0: "state %1",
    args0: [{ type: "field_input", name: "NAME", text: "shot_flown" }],
    output: "vs2beh_expr",
    colour: 300,
  },
];

let blocksDefined = false;
let actionBlockSpecsByType = new Map();

function defineStaticBlocks(Blockly) {
  Blockly.defineBlocksWithJsonArray(STATIC_BLOCK_JSON);
}

function defineActionBlocks(Blockly, catalogData) {
  const specs = new Map();
  const jsonDefs = [];
  for (const actionEntry of catalogData.actions) {
    const doFlavor = buildActionBlockJson(actionEntry, "do");
    jsonDefs.push(doFlavor.json);
    specs.set(doFlavor.blockType, doFlavor);
    if (CONDITION_FLAVOR_ACTIONS.has(actionEntry.name)) {
      const ifFlavor = buildActionBlockJson(actionEntry, "if");
      jsonDefs.push(ifFlavor.json);
      specs.set(ifFlavor.blockType, ifFlavor);
    }
  }
  Blockly.defineBlocksWithJsonArray(jsonDefs);
  actionBlockSpecsByType = specs;
}

/** Load Blockly (reusing vs2-event-sheet.js's loader -- see this module's
 * docstring) and define every block this palette needs, fetching the
 * catalog first. Safe to call more than once; blocks are defined exactly
 * once. */
export async function ensureBlocksDefined() {
  const Blockly = await loadBlockly();
  const catalogData = await loadCatalog();
  if (!blocksDefined) {
    defineStaticBlocks(Blockly);
    defineActionBlocks(Blockly, catalogData);
    blocksDefined = true;
  }
  return { Blockly, catalog: catalogData };
}

/** Toolbox XML, built once the catalog is known. */
export function buildToolboxXml(catalogData) {
  const actionBlocks = [];
  for (const actionEntry of catalogData.actions) {
    actionBlocks.push(`<block type="vs2beh_action_${actionEntry.name.toLowerCase()}"></block>`);
    if (CONDITION_FLAVOR_ACTIONS.has(actionEntry.name)) {
      actionBlocks.push(`<block type="vs2beh_if_${actionEntry.name.toLowerCase()}"></block>`);
    }
  }
  return `
<xml xmlns="https://developers.google.com/blockly/xml">
  <category name="Skeleton" colour="160">
    <block type="vs2beh_when_ticks"></block>
  </category>
  <category name="Parameters" colour="300">
    <block type="vs2beh_declare_number"></block>
    <block type="vs2beh_declare_angle"></block>
    <block type="vs2beh_declare_pool"></block>
  </category>
  <category name="Actions" colour="20">
    ${actionBlocks.join("\n    ")}
  </category>
  <category name="Decisions" colour="65">
    <block type="vs2beh_accumulate"></block>
    <block type="vs2beh_if_else"></block>
    <block type="vs2beh_despawn"></block>
    <block type="vs2beh_despawn_hit"></block>
  </category>
  <category name="Expressions" colour="300">
    <block type="vs2beh_expr_literal_number"></block>
    <block type="vs2beh_expr_param"></block>
    <block type="vs2beh_expr_state"></block>
  </category>
</xml>`;
}

/** Inject a real Blockly workspace into `container` (call
 * ensureBlocksDefined() first). */
export function injectWorkspace(container, catalogData) {
  return window.Blockly.inject(container, {
    toolbox: buildToolboxXml(catalogData),
    trashcan: true,
    scrollbars: true,
  });
}

// ---------------------------------------------------------------------------
// Hand-walk serialization: Blockly block tree ->
// tools/vs2_behavior_gen/model.py JSON shape. See vs2-event-sheet.js's own
// module docstring for why this is a hand-walk rather than Blockly's own
// serializer: the two shapes (a Blockly workspace vs. this task's
// generator-facing model) are not the same thing and must not be
// conflated.
// ---------------------------------------------------------------------------

function blockToExpr(block) {
  if (!block) {
    throw new Error("expression socket is empty");
  }
  switch (block.type) {
    case "vs2beh_expr_literal_number":
      return { kind: "literal", value: Number(block.getFieldValue("VALUE")) };
    case "vs2beh_expr_param":
      return { kind: "param", name: String(block.getFieldValue("NAME")) };
    case "vs2beh_expr_state":
      return { kind: "state", name: String(block.getFieldValue("NAME")) };
    default:
      throw new Error(`not an expression block: ${block.type}`);
  }
}

function collectStack(firstBlock) {
  const blocks = [];
  let block = firstBlock;
  while (block) {
    blocks.push(block);
    block = block.getNextBlock();
  }
  return blocks;
}

/** A fresh, deterministic bind name for an Action placed directly in the
 * workspace (an author never types this -- it is invented at
 * serialization time, the same way tools/vs2_event_gen's model needs no
 * author-chosen name for things it can derive on its own). */
function makeBindAllocator() {
  const counts = new Map();
  return (actionName) => {
    const base = actionName.toLowerCase();
    const seen = counts.get(base) || 0;
    counts.set(base, seen + 1);
    return seen === 0 ? base : `${base}_${seen + 1}`;
  };
}

function actionArgsFromBlock(block, spec) {
  const args = {};
  for (const fieldSpec of spec.specs) {
    if (fieldSpec.kind === "value") {
      const target = block.getInputTargetBlock(fieldSpec.argName);
      if (!target) {
        continue; // socket left empty: field omitted, generator/class default applies
      }
      args[fieldSpec.name] = blockToExpr(target);
    } else if (fieldSpec.kind === "checkbox") {
      args[fieldSpec.name] = { kind: "literal", value: block.getFieldValue(fieldSpec.argName) === "TRUE" };
    } else {
      args[fieldSpec.name] = { kind: "literal", value: block.getFieldValue(fieldSpec.argName) };
    }
  }
  return args;
}

/** Walk the "apply to all" stack: each block is a catalog Action's "do"
 * flavor. Returns `{actions, applyToAll}` -- `actions` entries to append
 * to the model's own `actions` list, `applyToAll` the bind names in
 * stack order. */
function serializeApplyToAll(firstBlock, allocateBind) {
  const actions = [];
  const applyToAll = [];
  for (const block of collectStack(firstBlock)) {
    const spec = actionBlockSpecsByType.get(block.type);
    if (!spec) {
      throw new Error(`not an apply-to-all action block: ${block.type}`);
    }
    const bind = allocateBind(spec.actionName);
    actions.push({
      bind, action_class: spec.actionName, args: actionArgsFromBlock(block, spec),
      block_id: block.id,
    });
    applyToAll.push(bind);
  }
  return { actions, applyToAll };
}

/** Walk one per-sprite statement stack recursively. Returns `{nodes,
 * actions}` -- `nodes` the model's own per_sprite node list, `actions`
 * any Collide-condition actions discovered along the way (appended to the
 * model's `actions` list exactly like an apply-to-all Action is). */
function serializePerSpriteStack(firstBlock, allocateBind) {
  const nodes = [];
  const actions = [];
  for (const block of collectStack(firstBlock)) {
    if (block.type === "vs2beh_accumulate") {
      nodes.push({
        kind: "accumulate",
        state: String(block.getFieldValue("STATE")),
        amount: blockToExpr(block.getInputTargetBlock("AMOUNT")),
        block_id: block.id,
      });
    } else if (block.type === "vs2beh_if_else") {
      const thenResult = serializePerSpriteStack(
        block.getInputTargetBlock("THEN"), allocateBind);
      const elseResult = serializePerSpriteStack(
        block.getInputTargetBlock("ELSE"), allocateBind);
      actions.push(...thenResult.actions, ...elseResult.actions);
      nodes.push({
        kind: "if_else",
        condition: {
          kind: "compare",
          op: block.getFieldValue("OP"),
          left: blockToExpr(block.getInputTargetBlock("LEFT")),
          right: blockToExpr(block.getInputTargetBlock("RIGHT")),
        },
        then: thenResult.nodes,
        else: elseResult.nodes,
        block_id: block.id,
      });
    } else if (block.type === "vs2beh_despawn") {
      nodes.push({ kind: "despawn", block_id: block.id });
    } else if (block.type === "vs2beh_despawn_hit") {
      nodes.push({ kind: "despawn_hit", block_id: block.id });
    } else {
      const spec = actionBlockSpecsByType.get(block.type);
      if (!spec || spec.flavor !== "if") {
        throw new Error(`not a per-sprite statement block: ${block.type}`);
      }
      const bind = allocateBind(spec.actionName);
      actions.push({
        bind, action_class: spec.actionName, args: actionArgsFromBlock(block, spec),
        block_id: block.id,
      });
      const doResult = serializePerSpriteStack(block.getInputTargetBlock("DO"), allocateBind);
      actions.push(...doResult.actions);
      nodes.push({ kind: "if_action", bind, then: doResult.nodes, else: [], block_id: block.id });
    }
  }
  return { nodes, actions };
}

/** Every state name this per_sprite node tree reads or writes, collected
 * the same way tools/vs2_event_gen/generator.py's `_collect_declared_vars`
 * collects project-variable names from usage -- a state field needs no
 * separate "declare" block, exactly like that precedent. */
function collectStateNames(nodes, into) {
  for (const node of nodes) {
    if (node.kind === "accumulate") {
      into.add(node.state);
      collectExprStateNames(node.amount, into);
    } else if (node.kind === "if_else") {
      collectExprStateNames(node.condition.left, into);
      collectExprStateNames(node.condition.right, into);
      collectStateNames(node.then, into);
      collectStateNames(node.else, into);
    } else if (node.kind === "if_action") {
      collectStateNames(node.then, into);
      collectStateNames(node.else, into);
    }
  }
}

function collectExprStateNames(expr, into) {
  if (expr && expr.kind === "state") {
    into.add(expr.name);
  }
}

/** Walk the "parameters" stack into the model's own `params` list. */
function serializeParams(firstBlock) {
  const params = [];
  for (const block of collectStack(firstBlock)) {
    if (block.type === "vs2beh_declare_number" || block.type === "vs2beh_declare_angle") {
      const entry = {
        name: String(block.getFieldValue("NAME")),
        type: block.type === "vs2beh_declare_angle" ? "angle" : "number",
        default: Number(block.getFieldValue("DEFAULT")),
        min: Number(block.getFieldValue("MIN")),
        max: Number(block.getFieldValue("MAX")),
        step: Number(block.getFieldValue("STEP")),
      };
      const label = block.getFieldValue("LABEL");
      const unit = block.getFieldValue("UNIT");
      if (label) entry.label = label;
      if (unit) entry.unit = unit;
      params.push(entry);
    } else if (block.type === "vs2beh_declare_pool") {
      const entry = { name: String(block.getFieldValue("NAME")), type: "pool", default: null };
      const label = block.getFieldValue("LABEL");
      if (label) entry.label = label;
      params.push(entry);
    } else {
      throw new Error(`not a parameter declaration block: ${block.type}`);
    }
  }
  return params;
}

/** Serialize the single top-level `vs2beh_when_ticks` hat block (there
 * should be exactly one -- this palette models one Behavior per
 * workspace, matching "code/behaviors/chasing.py ... One file per custom
 * behavior" in the proposal's own project layout) into the full model
 * dict tools/vs2_behavior_gen/model.validate_model accepts. */
export function serializeWorkspaceToModel(workspace) {
  const hatBlock = workspace.getTopBlocks(true)
    .find((block) => block.type === "vs2beh_when_ticks");
  if (!hatBlock) {
    throw new Error("no 'when ... ticks' block in the workspace");
  }
  const allocateBind = makeBindAllocator();

  const params = serializeParams(hatBlock.getInputTargetBlock("PARAMS"));
  const applyToAllResult = serializeApplyToAll(
    hatBlock.getInputTargetBlock("APPLY_ALL"), allocateBind);
  const perSpriteResult = serializePerSpriteStack(
    hatBlock.getInputTargetBlock("PER_SPRITE"), allocateBind);

  const stateNames = new Set();
  collectStateNames(perSpriteResult.nodes, stateNames);

  return {
    version: 1,
    class_name: String(hatBlock.getFieldValue("CLASS_NAME")),
    subject_kind: String(hatBlock.getFieldValue("SUBJECT_KIND")),
    params,
    state: [...stateNames].sort(),
    actions: [...applyToAllResult.actions, ...perSpriteResult.actions],
    apply_to_all: applyToAllResult.applyToAll,
    per_sprite: perSpriteResult.nodes,
  };
}

// ---------------------------------------------------------------------------
// Inverse: model JSON -> a real, connected block tree. Used to load an
// existing behavior-block program for editing, and to prove the round
// trip visually in a live browser (see this task's report).
// ---------------------------------------------------------------------------

function newRenderedBlock(workspace, type, id) {
  const block = workspace.newBlock(type, id);
  block.initSvg();
  block.render();
  return block;
}

function connectValueInput(parentBlock, inputName, childBlock) {
  parentBlock.getInput(inputName).connection.connect(childBlock.outputConnection);
}

function connectStatementInput(parentBlock, inputName, firstBlock) {
  if (firstBlock) {
    parentBlock.getInput(inputName).connection.connect(firstBlock.previousConnection);
  }
}

function connectStack(blocks) {
  for (let i = 0; i < blocks.length - 1; i += 1) {
    blocks[i].nextConnection.connect(blocks[i + 1].previousConnection);
  }
  return blocks.length ? blocks[0] : null;
}

function exprToBlock(workspace, expr) {
  if (expr.kind === "literal") {
    const block = newRenderedBlock(workspace, "vs2beh_expr_literal_number");
    block.setFieldValue(String(expr.value), "VALUE");
    return block;
  }
  if (expr.kind === "param") {
    const block = newRenderedBlock(workspace, "vs2beh_expr_param");
    block.setFieldValue(expr.name, "NAME");
    return block;
  }
  // kind === "state"
  const block = newRenderedBlock(workspace, "vs2beh_expr_state");
  block.setFieldValue(expr.name, "NAME");
  return block;
}

function findActionSpec(actionClass, flavor) {
  const blockType = flavor === "if"
    ? `vs2beh_if_${actionClass.toLowerCase()}`
    : `vs2beh_action_${actionClass.toLowerCase()}`;
  const spec = actionBlockSpecsByType.get(blockType);
  if (!spec) {
    throw new Error(`no palette block for ${actionClass} (${flavor} flavor)`);
  }
  return spec;
}

function actionBlockFromDecl(workspace, actionDecl, flavor) {
  const spec = findActionSpec(actionDecl.action_class, flavor);
  const block = newRenderedBlock(workspace, spec.blockType, actionDecl.block_id);
  for (const fieldSpec of spec.specs) {
    const value = actionDecl.args[fieldSpec.name];
    if (value === undefined) {
      continue;
    }
    if (fieldSpec.kind === "value") {
      connectValueInput(block, fieldSpec.argName, exprToBlock(workspace, value));
    } else if (fieldSpec.kind === "checkbox") {
      block.setFieldValue(value.value ? "TRUE" : "FALSE", fieldSpec.argName);
    } else {
      block.setFieldValue(String(value.value), fieldSpec.argName);
    }
  }
  return block;
}

function perSpriteNodeToBlock(workspace, node, actionsByBind) {
  if (node.kind === "accumulate") {
    const block = newRenderedBlock(workspace, "vs2beh_accumulate", node.block_id);
    block.setFieldValue(node.state, "STATE");
    connectValueInput(block, "AMOUNT", exprToBlock(workspace, node.amount));
    return block;
  }
  if (node.kind === "if_else") {
    const block = newRenderedBlock(workspace, "vs2beh_if_else", node.block_id);
    connectValueInput(block, "LEFT", exprToBlock(workspace, node.condition.left));
    block.setFieldValue(node.condition.op, "OP");
    connectValueInput(block, "RIGHT", exprToBlock(workspace, node.condition.right));
    connectStatementInput(block, "THEN",
      connectStack(node.then.map((n) => perSpriteNodeToBlock(workspace, n, actionsByBind))));
    connectStatementInput(block, "ELSE",
      connectStack(node.else.map((n) => perSpriteNodeToBlock(workspace, n, actionsByBind))));
    return block;
  }
  if (node.kind === "despawn") {
    return newRenderedBlock(workspace, "vs2beh_despawn", node.block_id);
  }
  if (node.kind === "despawn_hit") {
    return newRenderedBlock(workspace, "vs2beh_despawn_hit", node.block_id);
  }
  // kind === "if_action"
  const actionDecl = actionsByBind.get(node.bind);
  const block = actionBlockFromDecl(workspace, actionDecl, "if");
  connectStatementInput(block, "DO",
    connectStack(node.then.map((n) => perSpriteNodeToBlock(workspace, n, actionsByBind))));
  return block;
}

function paramDeclToBlock(workspace, param) {
  if (param.type === "pool") {
    const block = newRenderedBlock(workspace, "vs2beh_declare_pool");
    block.setFieldValue(param.name, "NAME");
    block.setFieldValue(param.label || "", "LABEL");
    return block;
  }
  const block = newRenderedBlock(
    workspace, param.type === "angle" ? "vs2beh_declare_angle" : "vs2beh_declare_number");
  block.setFieldValue(param.name, "NAME");
  block.setFieldValue(String(param.default), "DEFAULT");
  block.setFieldValue(String(param.min ?? 0), "MIN");
  block.setFieldValue(String(param.max ?? 0), "MAX");
  block.setFieldValue(String(param.step ?? 1), "STEP");
  block.setFieldValue(param.label || "", "LABEL");
  block.setFieldValue(param.unit || "", "UNIT");
  return block;
}

/** Clear `workspace` and rebuild it from `model` (the same JSON shape
 * serializeWorkspaceToModel() produces). */
export function loadModelIntoWorkspace(workspace, model) {
  workspace.clear();
  const actionsByBind = new Map(model.actions.map((a) => [a.bind, a]));
  const applyToAllBinds = new Set(model.apply_to_all);

  const hatBlock = newRenderedBlock(workspace, "vs2beh_when_ticks");
  hatBlock.moveBy(20, 20);
  hatBlock.setFieldValue(model.class_name, "CLASS_NAME");
  hatBlock.setFieldValue(model.subject_kind, "SUBJECT_KIND");

  connectStatementInput(hatBlock, "PARAMS",
    connectStack(model.params.map((p) => paramDeclToBlock(workspace, p))));

  const applyToAllBlocks = model.apply_to_all.map(
    (bind) => actionBlockFromDecl(workspace, actionsByBind.get(bind), "do"));
  connectStatementInput(hatBlock, "APPLY_ALL", connectStack(applyToAllBlocks));

  const perSpriteBlocks = model.per_sprite.map(
    (node) => perSpriteNodeToBlock(workspace, node, actionsByBind));
  connectStatementInput(hatBlock, "PER_SPRITE", connectStack(perSpriteBlocks));

  // Every action bind referenced from apply_to_all is already placed above;
  // any bind referenced only from an if_action node is placed by
  // perSpriteNodeToBlock itself. Nothing here should be orphaned as long as
  // the model came from serializeWorkspaceToModel() or an equivalent
  // hand-authored one -- applyToAllBinds is kept only for this comment's
  // own bookkeeping clarity, not used further.
  void applyToAllBinds;
}

// ---------------------------------------------------------------------------
// Panel bootstrap -- mirrors createVS2EventSheetPanel's shape.
// ---------------------------------------------------------------------------

/**
 * @param container Element the Blockly workspace is injected into.
 * @param panelElement Element shown/hidden by `toggleButton`.
 * @param toggleButton Button that shows/hides `panelElement`.
 * @param pathInput Text input holding the target `.vs2behavior.json` path.
 * @param saveButton Serializes the workspace and writes it to `pathInput`'s
 *   path via `window.VentilastationWebEmulator.writeProjectFile`.
 * @param loadButton Reads `pathInput`'s path back and rebuilds the
 *   workspace from it.
 * @param statusElement Where status/error text is written.
 */
export function createVS2BehaviorBlocksPanel({
  container,
  panelElement,
  toggleButton,
  pathInput,
  saveButton,
  loadButton,
  statusElement,
}) {
  const toggleTarget = panelElement || container;
  let workspace = null;
  let catalogData = null;

  const setStatus = (text) => {
    if (statusElement) {
      statusElement.textContent = text;
    }
  };

  const ensureWorkspace = async () => {
    if (workspace) {
      return workspace;
    }
    const loaded = await ensureBlocksDefined();
    catalogData = loaded.catalog;
    workspace = injectWorkspace(container, catalogData);
    return workspace;
  };

  if (toggleButton && toggleTarget) {
    toggleButton.addEventListener("click", async () => {
      const nextHidden = !toggleTarget.hidden;
      toggleTarget.hidden = nextHidden;
      toggleButton.setAttribute("aria-expanded", nextHidden ? "false" : "true");
      if (!nextHidden) {
        try {
          await ensureWorkspace();
          setStatus("Ready");
        } catch (err) {
          setStatus(`Failed to load: ${err.message}`);
        }
      }
    });
  }

  const getApi = () => window.VentilastationWebEmulator || null;

  if (saveButton) {
    saveButton.addEventListener("click", async () => {
      const api = getApi();
      if (!api) {
        setStatus("Workspace file API unavailable");
        return;
      }
      try {
        const ws = await ensureWorkspace();
        const model = serializeWorkspaceToModel(ws);
        const path = pathInput?.value?.trim();
        if (!path) {
          setStatus("Enter a .vs2behavior.json path first");
          return;
        }
        await api.writeProjectFile(path, JSON.stringify(model, null, 2), "utf8");
        setStatus(`Saved ${path}`);
      } catch (err) {
        setStatus(`Save failed: ${err.message}`);
      }
    });
  }

  if (loadButton) {
    loadButton.addEventListener("click", async () => {
      const api = getApi();
      if (!api) {
        setStatus("Workspace file API unavailable");
        return;
      }
      try {
        const ws = await ensureWorkspace();
        const path = pathInput?.value?.trim();
        if (!path) {
          setStatus("Enter a .vs2behavior.json path first");
          return;
        }
        const file = await api.readProjectFile(path, "utf8");
        const model = JSON.parse(file.content ?? file);
        loadModelIntoWorkspace(ws, model);
        setStatus(`Loaded ${path}`);
      } catch (err) {
        setStatus(`Load failed: ${err.message}`);
      }
    });
  }

  return {
    ensureWorkspace,
    serialize: () => serializeWorkspaceToModel(workspace),
    loadModel: (model) => loadModelIntoWorkspace(workspace, model),
  };
}
