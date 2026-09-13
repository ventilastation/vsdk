/**
 * T16 event-sheet Blockly panel: a real, working Blockly workspace over the
 * exact minimal vocabulary tools/vs2_event_gen/model.py validates --
 * two events (on_start, on_tick), two conditions (compare, timer_elapsed),
 * three expressions (literal, var, random), three actions (set_variable,
 * goto_scene, set_label_text). Nothing else: no arithmetic, no sprite/pool
 * Action blocks (T17's job), no state hats.
 *
 * Blockly vendors as web/vendor/blockly (blockly_compressed.js + msg/en.js,
 * fetched from unpkg's published 13.3.0 dist -- the same plain-<script>-tag
 * UMD build Blockly has shipped since well before its ESM rewrite), lazily
 * loaded the way web/monaco-ide.js's loadMonaco() loads Monaco: inject a
 * <script> tag on first use, cache the load promise, never bundle.
 *
 * **This module does not use Blockly's own code generator.** Blockly's
 * built-in serialization (workspace JSON/XML) is a different shape than
 * tools/vs2_event_gen/model.py's schema, and Blockly.JavaScript-style
 * generators emit source text, not a JSON model this task's CPython
 * generator can validate and re-render deterministically. Instead,
 * :func:`serializeWorkspaceToModel` hand-walks the block tree (exactly the
 * task brief's instruction: "do this serialization by hand-walking the
 * block tree ... you're mapping one into the other, don't conflate them")
 * and :func:`loadModelIntoWorkspace` is its inverse, used both to edit an
 * existing event sheet and to prove the round-trip (see this task's
 * report for how that was actually exercised in a browser).
 *
 * **T17 Phase 3: every event/action block's own ``.id`` rides along as
 * ``block_id`` in the serialized model.** Blockly assigns every block a
 * unique opaque id the moment it is created; this module previously threw
 * that away entirely (nothing here ever read `.id`). Threading it through
 * lets tools/vs2_event_gen/generator.py emit a trailing ``# block: <id>``
 * comment on the line(s) each block produced (see that package's own
 * ``linemap.py``), so a captured traceback can be resolved back to the
 * exact offending block -- docs/vs2-behaviors-proposal.md's "###
 * Debugging generated code". :func:`loadModelIntoWorkspace` restores the
 * same ids on re-creation (``workspace.newBlock(type, id)``), so
 * save -> load -> save is not just model-identical but block-id-identical
 * too.
 */

const BLOCKLY_BASE_URL = "./vendor/blockly";

let blocklyLoadPromise = null;

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load script: ${src}`));
    document.head.appendChild(script);
  });
}

/**
 * Load a UMD script that only checks `typeof define === "function" &&
 * define.amd` (Blockly's compressed builds do exactly this) while this
 * page's Monaco loader (web/monaco-ide.js) has already installed a global
 * AMD `define`. Left alone, Blockly's UMD wrapper takes the AMD branch
 * instead of the plain-`<script>` branch, registers itself as an anonymous
 * RequireJS module nobody asks for, and never sets `window.Blockly` at
 * all -- silently, no thrown error, just a missing global. Monaco's own
 * AMD loader additionally rejects a *second* anonymous `define()` outright
 * ("Can only have one anonymous define call per script file"), which is
 * how this was actually caught (see this task's report). The fix used
 * throughout this repo's own vendor scripts for exactly this shape of
 * conflict: hide `define` for the duration of the load so the UMD wrapper
 * falls through to `root.Blockly = factory()`, then restore it.
 */
async function loadUmdScriptWithoutAmd(src) {
  const hadDefine = Object.prototype.hasOwnProperty.call(window, "define");
  const savedDefine = window.define;
  try {
    delete window.define;
  } catch {
    window.define = undefined;
  }
  try {
    await loadScript(src);
  } finally {
    if (hadDefine) {
      window.define = savedDefine;
    }
  }
}

/** Lazily load Blockly core + English messages, define this module's
 * blocks exactly once, and resolve with the global `Blockly` namespace. */
export function loadBlockly() {
  if (window.Blockly?.Workspace) {
    defineBlocks(window.Blockly);
    return Promise.resolve(window.Blockly);
  }
  if (blocklyLoadPromise) {
    return blocklyLoadPromise;
  }
  blocklyLoadPromise = (async () => {
    await loadUmdScriptWithoutAmd(`${BLOCKLY_BASE_URL}/blockly_compressed.js`);
    await loadUmdScriptWithoutAmd(`${BLOCKLY_BASE_URL}/msg/en.js`);
    if (!window.Blockly?.Workspace) {
      throw new Error("Blockly failed to install window.Blockly");
    }
    defineBlocks(window.Blockly);
    return window.Blockly;
  })();
  return blocklyLoadPromise;
}

// ---------------------------------------------------------------------------
// Block definitions: exactly the T16 vocabulary, nothing more.
// ---------------------------------------------------------------------------

const COMPARE_OPS = [
  ["==", "=="], ["!=", "!="], ["<", "<"], [">", ">"], ["<=", "<="], [">=", ">="],
];

const BLOCK_JSON = [
  {
    type: "vs2_event_on_start",
    message0: "on start",
    message1: "conditions %1",
    args1: [{ type: "input_statement", name: "CONDITIONS", check: "vs2_condition" }],
    message2: "do %1",
    args2: [{ type: "input_statement", name: "ACTIONS", check: "vs2_action" }],
    colour: 210,
    tooltip: "Fires once, on scene entry (maps to on_enter()).",
  },
  {
    type: "vs2_event_on_tick",
    message0: "on tick",
    message1: "conditions %1",
    args1: [{ type: "input_statement", name: "CONDITIONS", check: "vs2_condition" }],
    message2: "do %1",
    args2: [{ type: "input_statement", name: "ACTIONS", check: "vs2_action" }],
    colour: 210,
    tooltip: "Fires every update() call.",
  },
  {
    type: "vs2_condition_compare",
    message0: "%1 %2 %3",
    args0: [
      { type: "input_value", name: "LEFT", check: "vs2_expr" },
      { type: "field_dropdown", name: "OP", options: COMPARE_OPS },
      { type: "input_value", name: "RIGHT", check: "vs2_expr" },
    ],
    inputsInline: true,
    previousStatement: "vs2_condition",
    nextStatement: "vs2_condition",
    colour: 65,
  },
  {
    type: "vs2_condition_timer_elapsed",
    message0: "timer elapsed %1 ticks since scene entry",
    args0: [{ type: "field_number", name: "TICKS", value: 1, min: 1, precision: 1 }],
    previousStatement: "vs2_condition",
    nextStatement: "vs2_condition",
    colour: 65,
  },
  {
    type: "vs2_expr_literal_number",
    message0: "%1",
    args0: [{ type: "field_number", name: "VALUE", value: 0 }],
    output: "vs2_expr",
    colour: 300,
  },
  {
    type: "vs2_expr_literal_string",
    message0: "“ %1 ”",
    args0: [{ type: "field_input", name: "VALUE", text: "" }],
    output: "vs2_expr",
    colour: 300,
  },
  {
    type: "vs2_expr_var",
    message0: "var %1",
    args0: [{ type: "field_input", name: "NAME", text: "score" }],
    output: "vs2_expr",
    colour: 300,
  },
  {
    type: "vs2_expr_random",
    message0: "random %1 to %2",
    args0: [
      { type: "input_value", name: "A", check: "vs2_expr" },
      { type: "input_value", name: "B", check: "vs2_expr" },
    ],
    inputsInline: true,
    output: "vs2_expr",
    colour: 300,
  },
  {
    type: "vs2_action_set_variable",
    message0: "set variable %1 to %2",
    args0: [
      { type: "field_input", name: "NAME", text: "score" },
      { type: "input_value", name: "VALUE", check: "vs2_expr" },
    ],
    inputsInline: true,
    previousStatement: "vs2_action",
    nextStatement: "vs2_action",
    colour: 20,
  },
  {
    type: "vs2_action_goto_scene",
    message0: "go to scene module %1 class %2",
    args0: [
      { type: "field_input", name: "MODULE", text: "games.pkg.code.other_scene" },
      { type: "field_input", name: "CLASS_NAME", text: "OtherScene" },
    ],
    previousStatement: "vs2_action",
    nextStatement: "vs2_action",
    colour: 20,
  },
  {
    type: "vs2_action_set_label_text",
    message0: "set label %1 text %2",
    args0: [
      { type: "field_input", name: "LABEL_ATTR", text: "title_label" },
      { type: "input_value", name: "TEXT", check: "vs2_expr" },
    ],
    inputsInline: true,
    previousStatement: "vs2_action",
    nextStatement: "vs2_action",
    colour: 20,
  },
];

let blocksDefined = false;

function defineBlocks(Blockly) {
  if (blocksDefined) {
    return;
  }
  Blockly.defineBlocksWithJsonArray(BLOCK_JSON);
  blocksDefined = true;
}

/** Toolbox XML: one category per tier (events / conditions / expressions /
 * actions), exactly this task's five-tier proposal collapsed to the four
 * tiers this minimal pass builds (tier 5, sprite Actions, is T17's). */
export const TOOLBOX_XML = `
<xml xmlns="https://developers.google.com/blockly/xml">
  <category name="Events" colour="210">
    <block type="vs2_event_on_start"></block>
    <block type="vs2_event_on_tick"></block>
  </category>
  <category name="Conditions" colour="65">
    <block type="vs2_condition_compare"></block>
    <block type="vs2_condition_timer_elapsed"></block>
  </category>
  <category name="Expressions" colour="300">
    <block type="vs2_expr_literal_number"></block>
    <block type="vs2_expr_literal_string"></block>
    <block type="vs2_expr_var"></block>
    <block type="vs2_expr_random"></block>
  </category>
  <category name="Actions" colour="20">
    <block type="vs2_action_set_variable"></block>
    <block type="vs2_action_goto_scene"></block>
    <block type="vs2_action_set_label_text"></block>
  </category>
</xml>`;

/** Inject a real Blockly workspace into `container` (already-loaded
 * Blockly required -- call :func:`loadBlockly` first). */
export function injectWorkspace(container) {
  return window.Blockly.inject(container, {
    toolbox: TOOLBOX_XML,
    trashcan: true,
    scrollbars: true,
  });
}

// ---------------------------------------------------------------------------
// Hand-walk serialization: Blockly block tree -> tools/vs2_event_gen/model.py
// JSON shape. Deliberately not Blockly's own (workspace-)JSON/XML format --
// see this module's docstring for why the two must not be conflated.
// ---------------------------------------------------------------------------

function blockToExpr(block) {
  if (!block) {
    throw new Error("expression socket is empty");
  }
  switch (block.type) {
    case "vs2_expr_literal_number":
      return { kind: "literal", value: Number(block.getFieldValue("VALUE")) };
    case "vs2_expr_literal_string":
      return { kind: "literal", value: String(block.getFieldValue("VALUE")) };
    case "vs2_expr_var":
      return { kind: "var", name: String(block.getFieldValue("NAME")) };
    case "vs2_expr_random":
      return {
        kind: "random",
        a: blockToExpr(block.getInputTargetBlock("A")),
        b: blockToExpr(block.getInputTargetBlock("B")),
      };
    default:
      throw new Error(`not an expression block: ${block.type}`);
  }
}

function blockToCondition(block) {
  switch (block.type) {
    case "vs2_condition_compare":
      return {
        kind: "compare",
        left: blockToExpr(block.getInputTargetBlock("LEFT")),
        op: block.getFieldValue("OP"),
        right: blockToExpr(block.getInputTargetBlock("RIGHT")),
      };
    case "vs2_condition_timer_elapsed":
      return { kind: "timer_elapsed", ticks: Number(block.getFieldValue("TICKS")) };
    default:
      throw new Error(`not a condition block: ${block.type}`);
  }
}

function blockToAction(block) {
  switch (block.type) {
    case "vs2_action_set_variable":
      return {
        kind: "set_variable",
        name: String(block.getFieldValue("NAME")),
        value: blockToExpr(block.getInputTargetBlock("VALUE")),
        block_id: block.id,
      };
    case "vs2_action_goto_scene":
      return {
        kind: "goto_scene",
        module: String(block.getFieldValue("MODULE")),
        class_name: String(block.getFieldValue("CLASS_NAME")),
        block_id: block.id,
      };
    case "vs2_action_set_label_text":
      return {
        kind: "set_label_text",
        label_attr: String(block.getFieldValue("LABEL_ATTR")),
        text: blockToExpr(block.getInputTargetBlock("TEXT")),
        block_id: block.id,
      };
    default:
      throw new Error(`not an action block: ${block.type}`);
  }
}

function collectStack(firstBlock, mapper) {
  const items = [];
  let block = firstBlock;
  while (block) {
    items.push(mapper(block));
    block = block.getNextBlock();
  }
  return items;
}

function blockToEvent(block) {
  const kind = block.type === "vs2_event_on_start" ? "on_start" : "on_tick";
  return {
    kind,
    block_id: block.id,
    conditions: collectStack(block.getInputTargetBlock("CONDITIONS"), blockToCondition),
    actions: collectStack(block.getInputTargetBlock("ACTIONS"), blockToAction),
  };
}

/** Walk every top-level on_start/on_tick block in `workspace` into the
 * exact JSON shape tools/vs2_event_gen/model.validate_model accepts. */
export function serializeWorkspaceToModel(workspace, className) {
  const events = [];
  for (const block of workspace.getTopBlocks(true)) {
    if (block.type === "vs2_event_on_start" || block.type === "vs2_event_on_tick") {
      events.push(blockToEvent(block));
    }
  }
  return { version: 1, class_name: className, events };
}

// ---------------------------------------------------------------------------
// Inverse: model JSON -> a real, connected block tree in the workspace.
// Used to edit an existing event sheet, and to prove the round trip
// (load a hand-authored .vs2events.json, re-serialize, diff).
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

function exprToBlock(workspace, expr) {
  if (expr.kind === "literal") {
    const isNumber = typeof expr.value === "number";
    const block = newRenderedBlock(
      workspace, isNumber ? "vs2_expr_literal_number" : "vs2_expr_literal_string");
    block.setFieldValue(String(expr.value), "VALUE");
    return block;
  }
  if (expr.kind === "var") {
    const block = newRenderedBlock(workspace, "vs2_expr_var");
    block.setFieldValue(expr.name, "NAME");
    return block;
  }
  if (expr.kind === "random") {
    const block = newRenderedBlock(workspace, "vs2_expr_random");
    connectValueInput(block, "A", exprToBlock(workspace, expr.a));
    connectValueInput(block, "B", exprToBlock(workspace, expr.b));
    return block;
  }
  throw new Error(`unknown expression kind: ${expr.kind}`);
}

function conditionToBlock(workspace, condition) {
  if (condition.kind === "compare") {
    const block = newRenderedBlock(workspace, "vs2_condition_compare");
    connectValueInput(block, "LEFT", exprToBlock(workspace, condition.left));
    block.setFieldValue(condition.op, "OP");
    connectValueInput(block, "RIGHT", exprToBlock(workspace, condition.right));
    return block;
  }
  if (condition.kind === "timer_elapsed") {
    const block = newRenderedBlock(workspace, "vs2_condition_timer_elapsed");
    block.setFieldValue(String(condition.ticks), "TICKS");
    return block;
  }
  throw new Error(`unknown condition kind: ${condition.kind}`);
}

function actionToBlock(workspace, action) {
  if (action.kind === "set_variable") {
    const block = newRenderedBlock(workspace, "vs2_action_set_variable", action.block_id);
    block.setFieldValue(action.name, "NAME");
    connectValueInput(block, "VALUE", exprToBlock(workspace, action.value));
    return block;
  }
  if (action.kind === "goto_scene") {
    const block = newRenderedBlock(workspace, "vs2_action_goto_scene", action.block_id);
    block.setFieldValue(action.module, "MODULE");
    block.setFieldValue(action.class_name, "CLASS_NAME");
    return block;
  }
  if (action.kind === "set_label_text") {
    const block = newRenderedBlock(workspace, "vs2_action_set_label_text", action.block_id);
    block.setFieldValue(action.label_attr, "LABEL_ATTR");
    connectValueInput(block, "TEXT", exprToBlock(workspace, action.text));
    return block;
  }
  throw new Error(`unknown action kind: ${action.kind}`);
}

function connectStack(blocks) {
  for (let i = 0; i < blocks.length - 1; i += 1) {
    blocks[i].nextConnection.connect(blocks[i + 1].previousConnection);
  }
  return blocks.length ? blocks[0] : null;
}

function connectStatementInput(parentBlock, inputName, firstBlock) {
  if (firstBlock) {
    parentBlock.getInput(inputName).connection.connect(firstBlock.previousConnection);
  }
}

/** Clear `workspace` and rebuild it from `model` (the same JSON shape
 * :func:`serializeWorkspaceToModel` produces). Returns nothing; the
 * workspace now holds real, connected blocks. */
export function loadModelIntoWorkspace(workspace, model) {
  workspace.clear();
  let y = 20;
  for (const event of model.events) {
    const eventBlock = newRenderedBlock(
      workspace, event.kind === "on_start" ? "vs2_event_on_start" : "vs2_event_on_tick",
      event.block_id);
    eventBlock.moveBy(20, y);
    y += 160;

    const conditionBlocks = (event.conditions || []).map((c) => conditionToBlock(workspace, c));
    connectStatementInput(eventBlock, "CONDITIONS", connectStack(conditionBlocks));

    const actionBlocks = (event.actions || []).map((a) => actionToBlock(workspace, a));
    connectStatementInput(eventBlock, "ACTIONS", connectStack(actionBlocks));
  }
}

// ---------------------------------------------------------------------------
// Panel bootstrap: mirrors createVS2BehaviorPanel's shape (toggle button,
// status line) plus a Save button that writes the serialized model to disk
// through the same workspace-file bridge monaco-ide.js uses.
// ---------------------------------------------------------------------------

/**
 * @param container Element the Blockly workspace is injected into.
 * @param panelElement Element shown/hidden by `toggleButton` (defaults to
 *   `container` if not given, same convention as createVS2BehaviorPanel).
 * @param toggleButton Button that shows/hides `panelElement`.
 * @param classNameInput Text input holding the model's `class_name`.
 * @param pathInput Text input holding the target `.vs2events.json` path
 *   (workspace-relative), e.g.
 *   "games/vs2_examples/event_sheet_demo/code/title_scene.vs2events.json".
 * @param saveButton Serializes the workspace and writes it to `pathInput`'s
 *   path via `window.VentilastationWebEmulator.writeProjectFile`.
 * @param loadButton Reads `pathInput`'s path back and rebuilds the
 *   workspace from it -- this is the round-trip check's "load it back"
 *   half.
 * @param statusElement Where status/error text is written.
 */
export function createVS2EventSheetPanel({
  container,
  panelElement,
  toggleButton,
  classNameInput,
  pathInput,
  saveButton,
  loadButton,
  statusElement,
}) {
  const toggleTarget = panelElement || container;
  let workspace = null;

  const setStatus = (text) => {
    if (statusElement) {
      statusElement.textContent = text;
    }
  };

  const ensureWorkspace = async () => {
    if (workspace) {
      return workspace;
    }
    await loadBlockly();
    workspace = injectWorkspace(container);
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
          setStatus(`Blockly failed to load: ${err.message}`);
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
        const className = classNameInput?.value?.trim() || "SceneEvents";
        const model = serializeWorkspaceToModel(ws, className);
        const path = pathInput?.value?.trim();
        if (!path) {
          setStatus("Enter a .vs2events.json path first");
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
          setStatus("Enter a .vs2events.json path first");
          return;
        }
        const file = await api.readProjectFile(path, "utf8");
        const model = JSON.parse(file.content ?? file);
        loadModelIntoWorkspace(ws, model);
        if (classNameInput) {
          classNameInput.value = model.class_name;
        }
        setStatus(`Loaded ${path}`);
      } catch (err) {
        setStatus(`Load failed: ${err.message}`);
      }
    });
  }

  return {
    ensureWorkspace,
    serialize: (className) => serializeWorkspaceToModel(workspace, className),
    loadModel: (model) => loadModelIntoWorkspace(workspace, model),
  };
}
