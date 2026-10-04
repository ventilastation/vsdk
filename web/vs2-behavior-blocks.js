/**
 * T17: the Blockly-for-Behaviors palette (tier 5, generated from parameter
 * declarations) over the exact vocabulary tools/vs2_behavior_gen/model.py
 * validates -- both of the shapes that schema accepts: Phase 1's two-zone
 * tick skeleton and Phase 2's state hats (see "State hats" below).
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
 * ``linemap.py``). Every node kind this palette can build carries one;
 * expression blocks deliberately do not, because ``model.py``'s
 * ``_check_expr`` does not accept a ``block_id`` key on an expression at
 * all (an expression never occupies a line of its own in the generated
 * source, so there would be nothing for ``linemap.py`` to point at).
 *
 * **State hats: the second top-level shape.** ``model.py``'s Phase-2
 * ``state_machine`` key -- one method per declared state, no flat
 * ``apply_to_all``/``per_sprite`` zones at all -- now has its own hat
 * block, ``vs2beh_state_machine``, holding a stack of ``vs2beh_state``
 * blocks, each with its own ``on enter`` / ``step`` / ``on exit`` body.
 * A workspace carries *exactly one* top-level hat, either kind, never
 * both: :func:`serializeWorkspaceToModel` refuses a workspace holding
 * both rather than silently picking one, because ``validate_model`` would
 * reject the merged result anyway ("Why apply_to_all/per_sprite are
 * mutually exclusive with state_machine") and a silent pick is the worse
 * failure mode.
 *
 * **Connection-type discipline across the two shapes.** ``model.py``'s
 * own vocabulary split is the authority here:
 * ``PER_SPRITE_KINDS`` (``accumulate``/``if_else``/``if_action``/
 * ``despawn``/``despawn_hit``/``set_state``/``call_callback``/``spawn``/
 * ``play_sound``) are legal in *either* shape, while
 * ``STATE_BODY_EXTRA_KINDS`` (``goto_state``/``hold``) are legal *only*
 * inside a state's own body -- ``self.hold(...)`` exists only on
 * :class:`~vs2.behaviors.StateMachine`, and "return the next state's
 * name" means nothing outside a per-state method. So:
 *
 * - every shared statement block declares the two-element check
 *   ``["vs2beh_sprite_statement", "vs2beh_state_body_statement"]`` on its
 *   previous/next connections (and on any statement input of its own, so
 *   a nested ``do``/``then``/``else`` stack stays equally dual-shaped);
 * - ``vs2beh_hold``/``vs2beh_goto_state`` declare
 *   ``"vs2beh_state_body_statement"`` *only*, so Blockly itself refuses
 *   to drop either into ``vs2beh_when_ticks``'s flat "for each sprite"
 *   zone.
 *
 * That last refusal is only structural at the *top* of the flat zone.
 * Dropping a ``goto_state`` into an ``if_else`` that itself sits in the
 * flat per-sprite zone still connects, because Blockly's connection
 * checks are purely local -- an input cannot ask "which hat am I
 * ultimately under?". This is *exactly* the ``despawn_hit`` situation
 * documented above, with exactly the same already-shipped safety net:
 * ``validate_model`` walks the flat ``per_sprite`` list with
 * ``allowed_kinds=PER_SPRITE_KINDS`` and rejects both kinds by name at
 * generate time (its own
 * ``test_goto_state_rejected_outside_a_state_body`` /
 * ``test_hold_rejected_outside_a_state_body``). Per the proposal's "the
 * block tier prevents errors; the Python tier reports them", that is a
 * deliberate division of labour, not an unguarded hole -- and it is
 * flagged here rather than silently assumed equivalent to full
 * prevention.
 *
 * **``call_callback`` is built zero-arity on purpose.** ``model.py``'s
 * node carries ``"args"``, a plain list of expressions, but the one real
 * caller in the tree --
 * ``games/vs2_examples/vasura_states_demo/code/enemy_states.vs2behavior.json``'s
 * ``on_death`` hook -- passes ``"args": []``, and nothing in the shipped
 * catalog passes anything else. So this block has a name field and no arg
 * sockets, and always serializes ``"args": []``; a model *loaded* with a
 * non-empty ``args`` list is refused loudly by
 * :func:`perSpriteNodeToBlock` rather than silently losing the arguments
 * on the next save. Building a variadic-args mutator UI nobody has proven
 * a need for is the same over-build this file already declines for the
 * remaining ``vs2.params`` types (see ``vs2beh_declare_number``'s own
 * comment) -- when a real caller needs arguments, the sockets get added
 * then, against a concrete shape.
 *
 * **Which ``vs2.params`` types have a declaration block.** ``number``,
 * ``angle``, ``pool``, ``sound`` and ``callback`` -- Phase 1's own three
 * plus the two the ``vasura_states_demo`` state-hat reference program
 * needs (``play_sound`` names a ``Sound`` parameter, ``call_callback`` a
 * ``Callback`` one, and a model that cannot *declare* those two cannot
 * round-trip through this editor at all). ``flag``/``choice``/``frames``/
 * ``image``/``points`` remain unbuilt: same mechanical shape, no proving
 * case yet.
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

// ---------------------------------------------------------------------------
// Connection-type vocabulary, mirroring tools/vs2_behavior_gen/model.py's own
// PER_SPRITE_KINDS / STATE_BODY_EXTRA_KINDS split -- see this module's
// docstring, "Connection-type discipline across the two shapes", for why the
// shared set gets a two-element check array rather than one type each.
// ---------------------------------------------------------------------------

/** Blockly's own connection check for a statement legal in *either* shape:
 * the flat `vs2beh_when_ticks` "for each sprite" zone, or a `vs2beh_state`
 * body. Blockly connects two connections whose check lists intersect, so a
 * block carrying both names still snaps into an input checking only
 * "vs2beh_sprite_statement" (the flat hat's own zone) and equally into one
 * checking only "vs2beh_state_body_statement". Fresh array per use --
 * Blockly stores the list it is handed, and sharing one array across every
 * block definition would make a future in-place edit leak everywhere. */
function dualStatementCheck() {
  return ["vs2beh_sprite_statement", "vs2beh_state_body_statement"];
}

/** Statements legal *only* inside a state's own enter/step/exit body:
 * `hold` and `goto_state`. Naming just this one type is what makes Blockly
 * physically refuse to drop either at the top of the flat per-sprite zone. */
const STATE_BODY_ONLY_CHECK = "vs2beh_state_body_statement";

/** The built-in `vs2.Sprite` fields a "state" expression may read and an
 * `accumulate`/`set_state` node may write *without* the model declaring
 * them -- an exact mirror of model.py's own `BUILTIN_SPRITE_FIELDS`. They
 * are excluded from the `state` list this module derives from usage (see
 * collectStateNames): declaring `y` as a per-sprite state field would make
 * the generator allocate a *second*, shadowing accumulator byte next to the
 * real `sprite.y` the author meant. */
const BUILTIN_SPRITE_FIELDS = new Set(["x", "y", "visible"]);

/** Parameter types whose declaration block is just "name + label" -- the
 * reference-shaped params (`default` is always null: a pool, a sound set or
 * a callback is bound at construction time, never typed into the editor).
 * One entry per type, so the block and its inverse stay a single source of
 * truth. See this module's docstring for which types are deliberately not
 * built yet. */
const REFERENCE_PARAM_BLOCK_TYPES = {
  pool: "vs2beh_declare_pool",
  sound: "vs2beh_declare_sound",
  callback: "vs2beh_declare_callback",
};

const REFERENCE_PARAM_TYPES_BY_BLOCK = new Map(
  Object.entries(REFERENCE_PARAM_BLOCK_TYPES).map(([type, blockType]) => [blockType, type]));

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
    // `if_action` is one of model.py's PER_SPRITE_KINDS, so it -- and its
    // own nested "do" stack -- is legal in both shapes; see this module's
    // docstring on the two-element check.
    json.message1 = "found a hit, do %1";
    json.args1 = [{ type: "input_statement", name: "DO", check: dualStatementCheck() }];
    json.previousStatement = dualStatementCheck();
    json.nextStatement = dualStatementCheck();
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
  // -- The *other* top-level hat: model.py's Phase-2 "state_machine" shape.
  // A workspace holds one hat or the other, never both (validate_model
  // rejects a model carrying state_machine alongside a non-empty
  // apply_to_all/per_sprite, and serializeWorkspaceToModel refuses the
  // ambiguity outright rather than picking one silently).
  //
  // There is no "apply to all" input here on purpose: the generated class
  // never overrides step()/step_one() (see generator.py), so there is no
  // uniform prologue phase for such a zone to render into. Offering the
  // input and rejecting its contents later would be a worse editor than
  // not offering it at all.
  {
    type: "vs2beh_state_machine",
    message0: "state machine %1 ( %2 ) starting in %3",
    args0: [
      { type: "field_input", name: "CLASS_NAME", text: "MyStateMachine" },
      { type: "field_dropdown", name: "SUBJECT_KIND",
        options: [["pool", "pool"], ["sprite", "sprite"]] },
      { type: "field_input", name: "INITIAL", text: "idle" },
    ],
    // The very same "vs2beh_param_decl" check the flat hat uses: a
    // Behavior's declared parameters mean exactly the same thing in either
    // shape, so the declaration blocks are shared rather than duplicated.
    message1: "parameters %1",
    args1: [{ type: "input_statement", name: "PARAMS", check: "vs2beh_param_decl" }],
    message2: "states %1",
    args2: [{ type: "input_statement", name: "STATES", check: "vs2beh_state_decl" }],
    colour: 160,
    tooltip: "One vs2.behaviors.StateMachine subclass: a stack of named "
      + "states, each with its own optional 'on enter'/'on exit' hooks and "
      + "a required 'step' body. 'starting in' names the initial state.",
  },
  {
    type: "vs2beh_state",
    message0: "in state %1",
    args0: [{ type: "field_input", name: "NAME", text: "idle" }],
    // "in state" rather than plain "state" so this reads unambiguously
    // next to the vs2beh_expr_state block ("state <name>", which *reads a
    // per-sprite field*, an entirely different thing from a named FSM
    // state). The three hooks are named for the methods they generate.
    message1: "on enter %1",
    args1: [{ type: "input_statement", name: "ENTER", check: STATE_BODY_ONLY_CHECK }],
    message2: "step %1",
    args2: [{ type: "input_statement", name: "STEP", check: STATE_BODY_ONLY_CHECK }],
    message3: "on exit %1",
    args3: [{ type: "input_statement", name: "EXIT", check: STATE_BODY_ONLY_CHECK }],
    previousStatement: "vs2beh_state_decl",
    nextStatement: "vs2beh_state_decl",
    colour: 200,
    tooltip: "One declared state. 'step' always generates a method (even "
      + "empty); 'on enter'/'on exit' generate one only when non-empty -- "
      + "the same 'optional hooks, skipped when absent' contract "
      + "vs2.behaviors.StateMachine itself documents.",
  },
  // -- Parameter declarations: one block per type this editor's proving
  // cases actually need -- Phase 1's Projectile (number/angle/pool) plus
  // the vasura_states_demo state-hat reference program (sound/callback).
  // Extending to the remaining vs2.params types (Flag, Choice, Frames,
  // Image, Points) is the same mechanical shape -- not built here, see
  // this module's docstring.
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
  {
    type: "vs2beh_declare_sound",
    message0: "sound %1 label %2",
    args0: [
      { type: "field_input", name: "NAME", text: "sound" },
      { type: "field_input", name: "LABEL", text: "" },
    ],
    previousStatement: "vs2beh_param_decl",
    nextStatement: "vs2beh_param_decl",
    colour: 300,
    tooltip: "A vs2.params.Sound parameter -- what a 'play sound' block "
      + "names. Its actual value (one name, or a tuple picked from at "
      + "random) is bound at construction, never typed here.",
  },
  {
    type: "vs2beh_declare_callback",
    message0: "callback %1 label %2",
    args0: [
      { type: "field_input", name: "NAME", text: "on_death" },
      { type: "field_input", name: "LABEL", text: "" },
    ],
    previousStatement: "vs2beh_param_decl",
    nextStatement: "vs2beh_param_decl",
    colour: 300,
    tooltip: "A vs2.params.Callback parameter -- what a 'call callback' "
      + "block names. The function itself is bound at construction.",
  },
  // -- Per-sprite decisions. Every block below is one of model.py's own
  // PER_SPRITE_KINDS, legal in the flat per-sprite zone *and* inside a
  // state body, hence the two-element connection check throughout --
  // including on each nested statement input, so a "do"/"else" stack
  // inside a state body keeps accepting state-body-only blocks.
  {
    type: "vs2beh_accumulate",
    message0: "add %1 to state %2",
    args0: [
      { type: "input_value", name: "AMOUNT", check: "vs2beh_expr" },
      { type: "field_input", name: "STATE", text: "shot_flown" },
    ],
    inputsInline: true,
    previousStatement: dualStatementCheck(),
    nextStatement: dualStatementCheck(),
    colour: 65,
  },
  {
    type: "vs2beh_set_state",
    message0: "set state %1 to %2",
    args0: [
      { type: "field_input", name: "STATE", text: "shot_flown" },
      { type: "input_value", name: "VALUE", check: "vs2beh_expr" },
    ],
    inputsInline: true,
    previousStatement: dualStatementCheck(),
    nextStatement: dualStatementCheck(),
    colour: 65,
    tooltip: "A plain assignment -- the 'add to state' block's "
      + "non-accumulating sibling. The name may be one of this Behavior's "
      + "own declared state fields or a built-in sprite field (x/y/visible).",
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
    args1: [{ type: "input_statement", name: "THEN", check: dualStatementCheck() }],
    message2: "else %1",
    args2: [{ type: "input_statement", name: "ELSE", check: dualStatementCheck() }],
    inputsInline: true,
    previousStatement: dualStatementCheck(),
    nextStatement: dualStatementCheck(),
    colour: 65,
  },
  {
    type: "vs2beh_despawn",
    message0: "despawn this sprite",
    previousStatement: dualStatementCheck(),
    nextStatement: dualStatementCheck(),
    colour: 0,
  },
  {
    type: "vs2beh_despawn_hit",
    message0: "despawn the sprite found",
    previousStatement: dualStatementCheck(),
    nextStatement: dualStatementCheck(),
    colour: 0,
    tooltip: "Only meaningful inside a Collide condition block's own "
      + "'do' stack -- see this file's module docstring on why this is "
      + "checked at generate time, not by Blockly's connection types.",
  },
  // -- Effects reaching outside this sprite's own bookkeeping. Same
  // PER_SPRITE_KINDS membership as the decisions above (legal in either
  // shape); a separate colour only because "spawn a thing / make a noise /
  // tell the game" is a different kind of act than "adjust my own state".
  {
    type: "vs2beh_spawn",
    message0: "spawn into pool %1 at x %2 y %3",
    args0: [
      { type: "field_input", name: "POOL", text: "explosion" },
      { type: "input_value", name: "X", check: "vs2beh_expr" },
      { type: "input_value", name: "Y", check: "vs2beh_expr" },
    ],
    inputsInline: true,
    previousStatement: dualStatementCheck(),
    nextStatement: dualStatementCheck(),
    colour: 30,
    tooltip: "Spawn into a declared pool parameter. Feed x/y the built-in "
      + "sprite fields (a 'state x' / 'state y' expression) to spawn at "
      + "this sprite's own position.",
  },
  {
    type: "vs2beh_play_sound",
    message0: "play sound %1",
    args0: [{ type: "field_input", name: "NAME", text: "sound" }],
    previousStatement: dualStatementCheck(),
    nextStatement: dualStatementCheck(),
    colour: 30,
    tooltip: "Play a declared sound parameter.",
  },
  {
    type: "vs2beh_call_callback",
    message0: "call callback %1",
    args0: [{ type: "field_input", name: "NAME", text: "on_death" }],
    previousStatement: dualStatementCheck(),
    nextStatement: dualStatementCheck(),
    colour: 30,
    tooltip: "Invoke a declared callback parameter with no arguments -- "
      + "see this file's module docstring on why the args list this "
      + "serializes is deliberately always empty.",
  },
  // -- State-body-only statements. The single-type check here is the whole
  // point: Blockly itself refuses to drop either at the top of the flat
  // 'for each sprite' zone, matching model.py's STATE_BODY_EXTRA_KINDS.
  {
    type: "vs2beh_hold",
    message0: "hold %1 ticks then go to state %2",
    args0: [
      { type: "input_value", name: "TICKS", check: "vs2beh_expr" },
      { type: "field_input", name: "THEN", text: "falling" },
    ],
    inputsInline: true,
    previousStatement: STATE_BODY_ONLY_CHECK,
    nextStatement: STATE_BODY_ONLY_CHECK,
    colour: 200,
    tooltip: "Stay in this state for the given number of ticks, then "
      + "enter the named one (self.hold(...), only on a StateMachine).",
  },
  {
    type: "vs2beh_goto_state",
    message0: "go to state %1",
    args0: [{ type: "field_input", name: "NAME", text: "exploding" }],
    previousStatement: STATE_BODY_ONLY_CHECK,
    nextStatement: STATE_BODY_ONLY_CHECK,
    colour: 200,
    tooltip: "Leave this state for the named one (a per-state method's "
      + "own 'return \"<name>\"').",
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
    // model.py's "literal" kind allows a bool value too (added in Phase 2
    // for Damageable's own "blink" flag comparison) -- this palette had
    // no way to author one until a real file (games/vs2_examples/
    // vyruss_vs2's own BaddieFormation, whose "formed"/"attack_closer"
    // states set formation_done/in_attack_run to a literal true/false)
    // failed to load with "literal expression true is not a number".
    // A separate block rather than overloading the number one: Blockly
    // has no "number or boolean" field type, and a checkbox reads far
    // more honestly as a bool than a text box asking for 0/1 would.
    type: "vs2beh_expr_literal_bool",
    message0: "%1",
    args0: [{ type: "field_checkbox", name: "VALUE", checked: true }],
    output: "vs2beh_expr",
    colour: 300,
    tooltip: "A literal true/false -- model.py's own \"literal\" expression "
      + "kind allows a bool value alongside number/string/null.",
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
  {
    // model.py's own "binary_op" kind. Both sockets and the output all use
    // the one "vs2beh_expr" type, so this block plugs into every existing
    // expression socket in the palette *and* nests inside itself -- which
    // is the whole point: the choreography math this was added for
    // (vyruss_vs2's `max(0, baddie.y - RIM_Y)`) is a nested binary_op, not
    // a flat one. min/max read oddly infix; the tooltip says so rather
    // than splitting the block in two over cosmetics.
    type: "vs2beh_expr_binary_op",
    message0: "%1 %2 %3",
    args0: [
      { type: "input_value", name: "LEFT", check: "vs2beh_expr" },
      { type: "field_dropdown", name: "OP",
        options: [["+", "+"], ["-", "-"], ["*", "*"], ["//", "//"],
                  ["%", "%"], ["min", "min"], ["max", "max"]] },
      { type: "input_value", name: "RIGHT", check: "vs2beh_expr" },
    ],
    inputsInline: true,
    output: "vs2beh_expr",
    colour: 300,
    tooltip: "Arithmetic on two expressions. '+ - * // %' render as plain "
      + "infix Python; 'min'/'max' render as a call on the same two "
      + "operands, so read those as 'min(left, right)'.",
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

/** Toolbox XML, built once the catalog is known.
 *
 * Categories group by *what a block means*, not by which phase added it:
 * both top-level hats sit together under "Skeleton" (picking one is the
 * first thing an author does, and seeing them side by side is what makes
 * the either/or obvious), the four Phase-2 effect blocks sit with their
 * fellow PER_SPRITE_KINDS under "Decisions" because they are legal in
 * exactly the same places, and "States" holds only what is specific to the
 * state-hat shape -- the state declaration and the two
 * STATE_BODY_EXTRA_KINDS that live nowhere else. */
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
    <block type="vs2beh_state_machine"></block>
  </category>
  <category name="Parameters" colour="300">
    <block type="vs2beh_declare_number"></block>
    <block type="vs2beh_declare_angle"></block>
    <block type="vs2beh_declare_pool"></block>
    <block type="vs2beh_declare_sound"></block>
    <block type="vs2beh_declare_callback"></block>
  </category>
  <category name="Actions" colour="20">
    ${actionBlocks.join("\n    ")}
  </category>
  <category name="Decisions" colour="65">
    <block type="vs2beh_accumulate"></block>
    <block type="vs2beh_set_state"></block>
    <block type="vs2beh_if_else"></block>
    <block type="vs2beh_despawn"></block>
    <block type="vs2beh_despawn_hit"></block>
    <block type="vs2beh_spawn"></block>
    <block type="vs2beh_play_sound"></block>
    <block type="vs2beh_call_callback"></block>
  </category>
  <category name="States" colour="200">
    <block type="vs2beh_state"></block>
    <block type="vs2beh_hold"></block>
    <block type="vs2beh_goto_state"></block>
  </category>
  <category name="Expressions" colour="300">
    <block type="vs2beh_expr_literal_number"></block>
    <block type="vs2beh_expr_literal_bool"></block>
    <block type="vs2beh_expr_param"></block>
    <block type="vs2beh_expr_state"></block>
    <block type="vs2beh_expr_binary_op"></block>
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
    case "vs2beh_expr_literal_bool":
      return { kind: "literal", value: block.getFieldValue("VALUE") === "TRUE" };
    case "vs2beh_expr_param":
      return { kind: "param", name: String(block.getFieldValue("NAME")) };
    case "vs2beh_expr_state":
      return { kind: "state", name: String(block.getFieldValue("NAME")) };
    case "vs2beh_expr_binary_op":
      // No block_id here, unlike every statement node: model.py's
      // _check_expr rejects an unknown key on a binary_op outright, and an
      // expression never gets a line of its own in the generated source
      // for linemap.py to point a traceback at anyway.
      return {
        kind: "binary_op",
        op: String(block.getFieldValue("OP")),
        left: blockToExpr(block.getInputTargetBlock("LEFT")),
        right: blockToExpr(block.getInputTargetBlock("RIGHT")),
      };
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

/** Walk one statement stack recursively -- the flat "for each sprite"
 * zone, or one `vs2beh_state` body's enter/step/exit stack, which are the
 * same walk over an overlapping vocabulary. Returns `{nodes, actions}` --
 * `nodes` the model's own node list, `actions` any Collide-condition
 * actions discovered along the way (appended to the model's `actions` list
 * exactly like an apply-to-all Action is).
 *
 * **No `allowed_kinds` parameter here on purpose.** Whether a `hold` or
 * `goto_state` is legal *where it was dropped* is not a question this walk
 * can answer: Blockly has already refused the only placement it can see
 * locally (the top of the flat per-sprite zone -- see this module's
 * docstring), and the placement it cannot see (nested inside an `if_else`
 * that is itself in the flat zone) is precisely what
 * `model.py`'s `validate_model` re-checks with the right `allowed_kinds`
 * for the enclosing shape. So this walk emits whatever block it finds and
 * leaves "is this misplaced" to the Python tier, exactly as this module
 * already does for `despawn_hit`. Dropping a node silently here would turn
 * a loud, path-naming ModelError into vanished work. */
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
    } else if (block.type === "vs2beh_set_state") {
      nodes.push({
        kind: "set_state",
        state: String(block.getFieldValue("STATE")),
        value: blockToExpr(block.getInputTargetBlock("VALUE")),
        block_id: block.id,
      });
    } else if (block.type === "vs2beh_spawn") {
      nodes.push({
        kind: "spawn",
        pool: String(block.getFieldValue("POOL")),
        x: blockToExpr(block.getInputTargetBlock("X")),
        y: blockToExpr(block.getInputTargetBlock("Y")),
        block_id: block.id,
      });
    } else if (block.type === "vs2beh_play_sound") {
      nodes.push({
        kind: "play_sound",
        name: String(block.getFieldValue("NAME")),
        block_id: block.id,
      });
    } else if (block.type === "vs2beh_call_callback") {
      // Always the empty args list -- this block has no arg sockets; see
      // this module's docstring on why that is a scope choice and not an
      // omission.
      nodes.push({
        kind: "call_callback",
        name: String(block.getFieldValue("NAME")),
        args: [],
        block_id: block.id,
      });
    } else if (block.type === "vs2beh_hold") {
      nodes.push({
        kind: "hold",
        ticks: blockToExpr(block.getInputTargetBlock("TICKS")),
        then: String(block.getFieldValue("THEN")),
        block_id: block.id,
      });
    } else if (block.type === "vs2beh_goto_state") {
      nodes.push({
        kind: "goto_state",
        name: String(block.getFieldValue("NAME")),
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

/** Every state name this node tree reads or writes, collected the same way
 * tools/vs2_event_gen/generator.py's `_collect_declared_vars` collects
 * project-variable names from usage -- a state field needs no separate
 * "declare" block, exactly like that precedent. Call it once per statement
 * stack (a state-hat program has one per state body) into a shared set.
 *
 * **The built-in sprite fields are deliberately never collected.**
 * model.py lets a `state` expression read, and an `accumulate`/`set_state`
 * node write, `x`/`y`/`visible` *without* the model declaring them -- they
 * are the real Sprite's own attributes. Adding one to the model's `state`
 * list would make the generator allocate a second, shadowing per-sprite
 * field of the same name, so a state body that accumulates straight into
 * `sprite.y` (exactly what games/vs2_examples/vasura_states_demo's
 * "falling" state does) would silently stop moving the sprite. */
function collectStateNames(nodes, into) {
  for (const node of nodes) {
    if (node.kind === "accumulate") {
      addStateName(node.state, into);
      collectExprStateNames(node.amount, into);
    } else if (node.kind === "set_state") {
      addStateName(node.state, into);
      collectExprStateNames(node.value, into);
    } else if (node.kind === "spawn") {
      collectExprStateNames(node.x, into);
      collectExprStateNames(node.y, into);
    } else if (node.kind === "hold") {
      collectExprStateNames(node.ticks, into);
    } else if (node.kind === "call_callback") {
      for (const arg of node.args) {
        collectExprStateNames(arg, into);
      }
    } else if (node.kind === "if_else") {
      collectExprStateNames(node.condition.left, into);
      collectExprStateNames(node.condition.right, into);
      collectStateNames(node.then, into);
      collectStateNames(node.else, into);
    } else if (node.kind === "if_action") {
      collectStateNames(node.then, into);
      collectStateNames(node.else, into);
    }
    // "despawn"/"despawn_hit"/"goto_state"/"play_sound" name no state and
    // hold no expression -- nothing to collect.
  }
}

function addStateName(name, into) {
  if (!BUILTIN_SPRITE_FIELDS.has(name)) {
    into.add(name);
  }
}

function collectExprStateNames(expr, into) {
  if (!expr) {
    return;
  }
  if (expr.kind === "state") {
    addStateName(expr.name, into);
  } else if (expr.kind === "binary_op") {
    collectExprStateNames(expr.left, into);
    collectExprStateNames(expr.right, into);
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
    } else if (REFERENCE_PARAM_TYPES_BY_BLOCK.has(block.type)) {
      // pool/sound/callback: identical "name + label, value bound at
      // construction" shape, one branch rather than three.
      const entry = {
        name: String(block.getFieldValue("NAME")),
        type: REFERENCE_PARAM_TYPES_BY_BLOCK.get(block.type),
        default: null,
      };
      const label = block.getFieldValue("LABEL");
      if (label) entry.label = label;
      params.push(entry);
    } else {
      throw new Error(`not a parameter declaration block: ${block.type}`);
    }
  }
  return params;
}

/** Walk the `STATES` stack of a `vs2beh_state_machine` hat into
 * model.py's own `state_machine` object, plus everything the surrounding
 * model needs from it. Returns `{stateMachine, actions, stateNames}`.
 *
 * **`enter`/`exit` are omitted entirely when their stack is empty, but
 * `step` is always emitted, even as `[]`.** That is not cosmetic:
 * `validate_model` *requires* a `step` key on every declared state
 * (matching StateMachine's own "every declared state needs its own
 * method, even a no-op one"), while generating an `enter_<state>`/
 * `exit_<state>` method the author never wrote would install a hook the
 * framework then calls on every transition. The hand-authored reference
 * program uses exactly this convention. */
function serializeStateMachine(hatBlock, allocateBind) {
  const states = [];
  const bodies = {};
  const actions = [];
  const stateNames = new Set();

  for (const stateBlock of collectStack(hatBlock.getInputTargetBlock("STATES"))) {
    if (stateBlock.type !== "vs2beh_state") {
      throw new Error(`not a state declaration block: ${stateBlock.type}`);
    }
    const name = String(stateBlock.getFieldValue("NAME"));
    // A duplicate name collapses two bodies into one object key while
    // leaving two entries in `states` -- deliberately left for
    // validate_model's own "duplicate state name" check to report, the
    // same division of labour every other name check in this module
    // follows. It cannot silently succeed either way.
    states.push(name);
    const body = {};
    for (const [hook, inputName] of [["enter", "ENTER"], ["step", "STEP"], ["exit", "EXIT"]]) {
      const result = serializePerSpriteStack(
        stateBlock.getInputTargetBlock(inputName), allocateBind);
      actions.push(...result.actions);
      collectStateNames(result.nodes, stateNames);
      if (hook === "step" || result.nodes.length) {
        body[hook] = result.nodes;
      }
    }
    bodies[name] = body;
  }

  return {
    stateMachine: {
      states,
      initial: String(hatBlock.getFieldValue("INITIAL")),
      bodies,
    },
    actions,
    stateNames,
  };
}

/** Serialize the single top-level hat block (there should be exactly one
 * -- this palette models one Behavior per workspace, matching
 * "code/behaviors/chasing.py ... One file per custom behavior" in the
 * proposal's own project layout) into the full model dict
 * tools/vs2_behavior_gen/model.validate_model accepts.
 *
 * Two hat kinds, two shapes: `vs2beh_when_ticks` produces the flat
 * two-zone model (unchanged since Phase 1), `vs2beh_state_machine`
 * produces the `state_machine` one. Both at once is refused rather than
 * resolved by picking a winner -- validate_model would reject the merged
 * result anyway ("Why apply_to_all/per_sprite are mutually exclusive with
 * state_machine"), and a silent pick would quietly discard half an
 * author's workspace. */
export function serializeWorkspaceToModel(workspace) {
  const topBlocks = workspace.getTopBlocks(true);
  const flatHat = topBlocks.find((block) => block.type === "vs2beh_when_ticks");
  const stateHat = topBlocks.find((block) => block.type === "vs2beh_state_machine");
  if (flatHat && stateHat) {
    throw new Error(
      "workspace holds both a 'when ... ticks' and a 'state machine' hat; "
      + "a behavior is one or the other");
  }
  const hatBlock = flatHat || stateHat;
  if (!hatBlock) {
    throw new Error("no 'when ... ticks' or 'state machine' block in the workspace");
  }
  const allocateBind = makeBindAllocator();

  const params = serializeParams(hatBlock.getInputTargetBlock("PARAMS"));
  const common = {
    version: 1,
    class_name: String(hatBlock.getFieldValue("CLASS_NAME")),
    subject_kind: String(hatBlock.getFieldValue("SUBJECT_KIND")),
    params,
  };

  if (stateHat) {
    const result = serializeStateMachine(stateHat, allocateBind);
    return {
      ...common,
      state: [...result.stateNames].sort(),
      actions: result.actions,
      // Both zones emitted as empty lists rather than omitted: validate_model
      // rejects them only when *non-empty* alongside a state_machine, and
      // the hand-authored reference program spells them out the same way,
      // which keeps a save of a loaded file diff-clean against it.
      apply_to_all: [],
      per_sprite: [],
      state_machine: result.stateMachine,
    };
  }

  const applyToAllResult = serializeApplyToAll(
    hatBlock.getInputTargetBlock("APPLY_ALL"), allocateBind);
  const perSpriteResult = serializePerSpriteStack(
    hatBlock.getInputTargetBlock("PER_SPRITE"), allocateBind);

  const stateNames = new Set();
  collectStateNames(perSpriteResult.nodes, stateNames);

  return {
    ...common,
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

/** Create a block, rendering it if this workspace renders at all.
 *
 * A `Blockly.WorkspaceSvg` (what `injectWorkspace` returns in a real page)
 * hands back a `BlockSvg`, which needs `initSvg()`/`render()` before it is
 * visible. A headless `new Blockly.Workspace()` -- Blockly's own
 * DOM-independent data model, which is how
 * `tests/test_vs2_behavior_blocks_roundtrip.mjs` exercises this module
 * under plain Node with no jsdom and no browser -- hands back a plain
 * `Blockly.Block`, on which neither method exists at all. Feature-testing
 * leaves the browser path byte-for-byte what it was while making the
 * model half of this file testable without one. */
function newRenderedBlock(workspace, type, id) {
  const block = workspace.newBlock(type, id);
  if (typeof block.initSvg === "function") {
    block.initSvg();
    block.render();
  }
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
    // model.py's literal accepts number/string/bool/null. Two blocks now
    // cover number and bool (see vs2beh_expr_literal_bool's own comment --
    // games/vs2_examples/vyruss_vs2's real BaddieFormation model sets
    // formation_done/in_attack_run to a literal true/false through the
    // ordinary per-sprite "value" socket, not just an Action's own
    // dropdown/checkbox arg, so this genuinely needs handling here, not
    // only in actionArgsFromBlock/actionBlockFromDecl). A string or null
    // literal in a real model today still only ever appears as an
    // Action's own field arg (set directly by those two functions), so
    // still refused here rather than silently coerced.
    if (typeof expr.value === "boolean") {
      const block = newRenderedBlock(workspace, "vs2beh_expr_literal_bool");
      block.setFieldValue(expr.value ? "TRUE" : "FALSE", "VALUE");
      return block;
    }
    if (typeof expr.value !== "number") {
      throw new Error(
        `literal expression ${JSON.stringify(expr.value)} is not a number `
        + "or bool; this palette has no block for it");
    }
    const block = newRenderedBlock(workspace, "vs2beh_expr_literal_number");
    block.setFieldValue(String(expr.value), "VALUE");
    return block;
  }
  if (expr.kind === "param") {
    const block = newRenderedBlock(workspace, "vs2beh_expr_param");
    block.setFieldValue(expr.name, "NAME");
    return block;
  }
  if (expr.kind === "binary_op") {
    const block = newRenderedBlock(workspace, "vs2beh_expr_binary_op");
    block.setFieldValue(expr.op, "OP");
    connectValueInput(block, "LEFT", exprToBlock(workspace, expr.left));
    connectValueInput(block, "RIGHT", exprToBlock(workspace, expr.right));
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
  if (node.kind === "set_state") {
    const block = newRenderedBlock(workspace, "vs2beh_set_state", node.block_id);
    block.setFieldValue(node.state, "STATE");
    connectValueInput(block, "VALUE", exprToBlock(workspace, node.value));
    return block;
  }
  if (node.kind === "spawn") {
    const block = newRenderedBlock(workspace, "vs2beh_spawn", node.block_id);
    block.setFieldValue(node.pool, "POOL");
    connectValueInput(block, "X", exprToBlock(workspace, node.x));
    connectValueInput(block, "Y", exprToBlock(workspace, node.y));
    return block;
  }
  if (node.kind === "play_sound") {
    const block = newRenderedBlock(workspace, "vs2beh_play_sound", node.block_id);
    block.setFieldValue(node.name, "NAME");
    return block;
  }
  if (node.kind === "call_callback") {
    // Refuse loudly rather than dropping arguments the zero-arity block
    // cannot show: a silent load would turn into a silent *loss* on the
    // very next save. See this module's docstring on the arity choice.
    if (node.args && node.args.length) {
      throw new Error(
        `call_callback '${node.name}' passes ${node.args.length} argument(s); `
        + "the 'call callback' block is zero-arity and would lose them");
    }
    const block = newRenderedBlock(workspace, "vs2beh_call_callback", node.block_id);
    block.setFieldValue(node.name, "NAME");
    return block;
  }
  if (node.kind === "hold") {
    const block = newRenderedBlock(workspace, "vs2beh_hold", node.block_id);
    connectValueInput(block, "TICKS", exprToBlock(workspace, node.ticks));
    block.setFieldValue(node.then, "THEN");
    return block;
  }
  if (node.kind === "goto_state") {
    const block = newRenderedBlock(workspace, "vs2beh_goto_state", node.block_id);
    block.setFieldValue(node.name, "NAME");
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
  const referenceBlockType = REFERENCE_PARAM_BLOCK_TYPES[param.type];
  if (referenceBlockType) {
    const block = newRenderedBlock(workspace, referenceBlockType);
    block.setFieldValue(param.name, "NAME");
    block.setFieldValue(param.label || "", "LABEL");
    return block;
  }
  if (param.type !== "number" && param.type !== "angle") {
    // flag/choice/frames/image/points have no declaration block yet (see
    // this module's docstring). Refusing here beats quietly rendering one
    // as a number block, which would silently rewrite the parameter's type
    // on the next save.
    throw new Error(
      `no parameter-declaration block for type '${param.type}' (parameter '${param.name}')`);
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

/** Rebuild a `vs2beh_state_machine` hat and its whole state stack from
 * `model.state_machine`. The inverse of serializeStateMachine(): each
 * declared state becomes one `vs2beh_state` block in `states` order (not
 * `bodies` key order -- `states` is the declaration order the author sees
 * and the only one model.py treats as meaningful), with whichever of
 * enter/step/exit the body actually carries.
 *
 * A single action declaration referenced by several `if_action` nodes --
 * the reference program's one `Collide` tested from three different state
 * bodies -- becomes one Collide-condition *block* per reference, because
 * an `if_action` is rendered as a self-contained "if Collide(...) found a
 * hit" block with the Action's own fields inline; blocks have nowhere to
 * share one declaration between them. Re-saving therefore emits N
 * identically-configured actions where the hand-authored file had one.
 * The generated code means the same thing (each `if_action` still tests
 * the same Collide configuration) but constructs N Action objects; noted
 * here because it is the one place this round trip is not byte-identical
 * by design rather than by accident. */
function loadStateMachineIntoWorkspace(workspace, model, actionsByBind) {
  const stateMachine = model.state_machine;
  const hatBlock = newRenderedBlock(workspace, "vs2beh_state_machine");
  hatBlock.moveBy(20, 20);
  hatBlock.setFieldValue(model.class_name, "CLASS_NAME");
  hatBlock.setFieldValue(model.subject_kind, "SUBJECT_KIND");
  hatBlock.setFieldValue(stateMachine.initial, "INITIAL");

  connectStatementInput(hatBlock, "PARAMS",
    connectStack((model.params || []).map((p) => paramDeclToBlock(workspace, p))));

  const stateBlocks = stateMachine.states.map((name) => {
    const stateBlock = newRenderedBlock(workspace, "vs2beh_state");
    stateBlock.setFieldValue(name, "NAME");
    const body = stateMachine.bodies[name] || {};
    for (const [hook, inputName] of [["enter", "ENTER"], ["step", "STEP"], ["exit", "EXIT"]]) {
      connectStatementInput(stateBlock, inputName,
        connectStack((body[hook] || []).map(
          (node) => perSpriteNodeToBlock(workspace, node, actionsByBind))));
    }
    return stateBlock;
  });
  connectStatementInput(hatBlock, "STATES", connectStack(stateBlocks));
}

/** Clear `workspace` and rebuild it from `model` (the same JSON shape
 * serializeWorkspaceToModel() produces), in whichever of the two shapes
 * the model is -- `state_machine` truthiness is the single discriminator,
 * exactly the check model.py and generator.py both make. */
export function loadModelIntoWorkspace(workspace, model) {
  workspace.clear();
  const actionsByBind = new Map((model.actions || []).map((a) => [a.bind, a]));

  if (model.state_machine) {
    loadStateMachineIntoWorkspace(workspace, model, actionsByBind);
    return;
  }

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

  const getApi = () => window.VentilastationWebEmulator || null;

  /** Reads `path` back, falling back to fetching it as a plain static file
   * (and seeding the sandboxed workspace FS with it) when the sandboxed
   * API doesn't know it -- .vs2behavior.json sidecar files are deliberately
   * not part of web-runtime-bundle's manifest (tools/generate_web_
   * runtime_bundle.py only globs *.py/meta.json/roms/assets), so a fresh
   * session's virtual FS has never heard of one until this reads it. */
  const readModelText = async (api, path) => {
    try {
      const file = await api.readProjectFile(path, "utf8");
      return file.content ?? file;
    } catch (_notFoundError) {
      const response = await fetch(path);
      if (!response.ok) {
        throw new Error(`${path}: HTTP ${response.status}`);
      }
      const text = await response.text();
      await api.writeProjectFile(path, text, "utf8");
      return text;
    }
  };

  /** Loads `path` into the workspace -- the shared body behind both the
   * Load button and auto-loading the currently selected game (see the
   * `ventilastation:editor-game-selected` listener below). Assumes
   * `ensureWorkspace()` has already run once if the panel itself isn't
   * visible yet (auto-load only calls this once it has). */
  const loadPath = async (path) => {
    const api = getApi();
    if (!api) {
      setStatus("Workspace file API unavailable");
      return;
    }
    try {
      const ws = await ensureWorkspace();
      const text = await readModelText(api, path);
      const model = JSON.parse(text);
      loadModelIntoWorkspace(ws, model);
      setStatus(`Loaded ${path}`);
    } catch (err) {
      setStatus(`Load failed: ${err.message}`);
    }
  };

  if (toggleButton && toggleTarget) {
    toggleButton.addEventListener("click", async () => {
      const nextHidden = !toggleTarget.hidden;
      toggleTarget.hidden = nextHidden;
      toggleButton.setAttribute("aria-expanded", nextHidden ? "false" : "true");
      if (!nextHidden) {
        const isFirstOpen = !workspace;
        try {
          await ensureWorkspace();
          const path = pathInput?.value?.trim();
          if (isFirstOpen && path) {
            // pathInput was already synced to the selected game by the
            // ventilastation:editor-game-selected listener below, before
            // there was a workspace to load it into -- load it now.
            await loadPath(path);
          } else {
            setStatus("Ready");
          }
        } catch (err) {
          setStatus(`Failed to load: ${err.message}`);
        }
      }
    });
  }

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
    loadButton.addEventListener("click", () => {
      const path = pathInput?.value?.trim();
      if (!path) {
        setStatus("Enter a .vs2behavior.json path first");
        return;
      }
      void loadPath(path);
    });
  }

  /** Finds a game's first file ending in `suffix` (alphabetically, if it
   * has more than one). Tries the sandboxed workspace listing first
   * (covers `suffix`s that are manifest-backed); falls back to the dev
   * server's own directory listing of `<gameKey>/code/` (every
   * .vs2behavior.json in this codebase lives directly there) since
   * sidecar model files aren't in the manifest -- see readModelText's
   * docstring above. Returns null if nothing matches either way (a game
   * with no such file, e.g. event_sheet_demo has no behavior file). */
  const findGameFilePath = async (api, gameKey, suffix) => {
    try {
      const entries = await api.listProjectFiles(`games/${gameKey}`);
      const matches = entries.filter((entry) => entry.endsWith(suffix)).sort((left, right) => left.localeCompare(right));
      if (matches.length) {
        return `games/${matches[0]}`;
      }
    } catch (_error) {
      // Fall through to the directory-listing fallback below.
    }
    const dirPath = `games/${gameKey}/code/`;
    try {
      const response = await fetch(dirPath);
      if (!response.ok) {
        return null;
      }
      const html = await response.text();
      const hrefs = Array.from(new DOMParser().parseFromString(html, "text/html").querySelectorAll("a[href]"))
        .map((anchor) => anchor.getAttribute("href") || "");
      const matches = hrefs
        .map((href) => href.split("/").pop())
        .filter((name) => name && name.endsWith(suffix))
        .sort((left, right) => left.localeCompare(right));
      return matches.length ? `${dirPath}${matches[0]}` : null;
    } catch (_error) {
      return null;
    }
  };

  // Auto-load whichever game the editor (a separate module -- see
  // monaco-ide.js's setCurrentGameKey) has selected: find that game's
  // first .vs2behavior.json (see findGameFilePath), sync pathInput to it,
  // and load it if the workspace already exists (panel previously opened)
  // so an open panel refreshes immediately on a game switch. If the
  // workspace doesn't exist yet, the toggle-open handler above loads this
  // same pathInput value the first time the panel opens.
  window.addEventListener("ventilastation:editor-game-selected", (event) => {
    const gameKey = event.detail?.gameKey;
    if (!gameKey) {
      return;
    }
    void (async () => {
      const api = getApi();
      if (!api) {
        return;
      }
      const path = await findGameFilePath(api, gameKey, ".vs2behavior.json");
      if (pathInput) {
        pathInput.value = path || "";
      }
      if (path) {
        if (workspace) {
          await loadPath(path);
        }
      } else {
        setStatus(`No .vs2behavior.json file found for ${gameKey}`);
      }
    })();
  });

  return {
    ensureWorkspace,
    serialize: () => serializeWorkspaceToModel(workspace),
    loadModel: (model) => loadModelIntoWorkspace(workspace, model),
  };
}
