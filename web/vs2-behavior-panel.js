// VS2 behaviors inspector panel (T12): mounts the two-level subject/
// behavior tree and the `kinds` table editor into the DOM, and wires
// widget edits to a running game over the `vs2beh` protocol (T11).
//
// This file is deliberately the *only* one of the three T12 modules that
// touches the DOM. vs2-widgets.js (widget dispatch, kinds table transforms)
// and vs2beh-client.js (protocol encode/decode) are plain logic, unit
// tested under Node with no browser -- see tests/test_vs2_widget_dispatch.mjs,
// tests/test_vs2_kinds_editor.mjs, tests/test_vs2beh_client.mjs, and the
// live-tune end-to-end test tests/test_vs2beh_live_tune_e2e.mjs, which
// drives the *same* client module against a real headless `micropython`
// process. This module is the thin, intentionally-untested-under-Node
// remainder: create elements, attach listeners, call the pure functions.
//
// ## Transport: how a browser reaches a running game
//
// docs/vs2-behaviors-proposal.md's "The live-tune loop" is explicit that
// the panel talks to *a running game* "over USB serial -- the only place
// some of these numbers can honestly be judged". Investigating this
// repo's existing browser<->MicroPython paths (micropython-bridge.js,
// wasm-adapter.js, web/remote-adapter.js) turned up no existing channel
// that already carries an arbitrary text control line the way real
// hardware's UART does for `povcal`/`povperf`/`hallfilter`:
//   - the in-browser WASM worker bridge (micropython-bridge.js +
//     wasm-adapter.js) exposes `call(module, function, ...args)` into the
//     worker's MicroPython, and BrowserComms.next_command() (see
//     apps/micropython/ventilastation/platforms/browser.py) only ever
//     surfaces the "exit" button as a control command -- there is no
//     `post_control_line`-shaped entry point today.
//   - the remote workbench WebSocket (remote-adapter.js) forwards INPUT,
//     LEASE and a small whitelisted OPERATOR_COMMAND set (reset/rpm); it
//     does not relay arbitrary text lines either.
// Wiring either of those the rest of the way is a Python-side change (to
// apps/micropython/ventilastation/platforms/browser.py or the workbench
// gateway), outside `web/` and outside T12's owned files.
//
// So WebSerialTransport below talks directly to a real board's USB CDC
// serial port via the standard Web Serial API, bypassing both of the
// above entirely -- this needs no companion change anywhere else, and is
// ready the moment T11 adds its `elif cmd == "vs2beh":` branch to
// director.py's `_dispatch_control()`, since the device-side protocol is
// the same plain newline-terminated text `povcal`/`hallfilter` already
// use. It cannot be exercised in this repo's automated tests (no browser,
// no physical board) -- see tests/test_vs2beh_live_tune_e2e.mjs's header
// comment for what *is* verified there instead: the identical
// VS2BehClient / Transport contract, driven against a real headless
// MicroPython process instead of real hardware.

import { VS2BehClient, flattenSubjects } from "./vs2beh-client.js?v=20260911a";
import {
  widgetSpecFor,
  coerceWidgetValue,
  kindsTableFromWire,
  kindsTableToWire,
  setKindsCell,
  displayRowOrder,
  diffOneKindsCell,
} from "./vs2-widgets.js?v=20260913a";

/**
 * A Transport talking to a real board over the Web Serial API
 * (https://developer.mozilla.org/en-US/docs/Web/API/Web_Serial_API).
 * One line out, one line back, matching `_dispatch_control()`'s
 * `cmd_line.split()` parser on the device (apps/micropython/ventilastation/
 * director.py) -- the same shape povcal/povperf/hallfilter already use
 * over the same UART.
 */
export class WebSerialTransport {
  constructor(port) {
    this.port = port;
    this.writer = null;
    this.reader = null;
    this.lineBuffer = "";
  }

  static isSupported() {
    return typeof navigator !== "undefined" && "serial" in navigator;
  }

  static async requestPort(options = {}) {
    if (!WebSerialTransport.isSupported()) {
      throw new Error("Web Serial API not available in this browser");
    }
    const port = await navigator.serial.requestPort(options);
    return new WebSerialTransport(port);
  }

  async open(options = { baudRate: 115200 }) {
    await this.port.open(options);
    const encoder = new TextEncoderStream();
    encoder.readable.pipeTo(this.port.writable);
    this.writer = encoder.writable.getWriter();

    const decoder = new TextDecoderStream();
    this.port.readable.pipeTo(decoder.writable);
    this.reader = decoder.readable.getReader();
  }

  async close() {
    if (this.reader) {
      await this.reader.cancel().catch(() => {});
      this.reader = null;
    }
    if (this.writer) {
      await this.writer.close().catch(() => {});
      this.writer = null;
    }
    await this.port.close().catch(() => {});
  }

  async _readLine() {
    while (!this.lineBuffer.includes("\n")) {
      const { value, done } = await this.reader.read();
      if (done) {
        throw new Error("serial port closed while waiting for a reply");
      }
      this.lineBuffer += value;
    }
    const newlineIndex = this.lineBuffer.indexOf("\n");
    const line = this.lineBuffer.slice(0, newlineIndex).replace(/\r$/, "");
    this.lineBuffer = this.lineBuffer.slice(newlineIndex + 1);
    return line;
  }

  async sendLine(text) {
    await this.writer.write(`${text}\n`);
    return this._readLine();
  }
}

// ---------------------------------------------------------------------------
// DOM mounting.
// ---------------------------------------------------------------------------

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "className") {
      node.className = value;
    } else if (key.startsWith("on") && typeof value === "function") {
      node.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value !== undefined && value !== null) {
      node.setAttribute(key, value);
    }
  }
  for (const child of children) {
    if (child === null || child === undefined) {
      continue;
    }
    node.append(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

/**
 * Render one generic parameter widget: dispatches purely through
 * widgetSpecFor() (vs2-widgets.js) -- this function itself never reads
 * `param.type`. Calls `onChange(newValue)` with an already-coerced value.
 */
function mountParamWidget(param, onChange) {
  const spec = widgetSpecFor(param);
  let input;

  switch (spec.control) {
    case "checkbox": {
      input = el("input", {
        type: "checkbox",
        className: "vs2beh-widget-checkbox",
      });
      input.checked = Boolean(spec.value);
      input.addEventListener("change", () => {
        onChange(coerceWidgetValue(spec, input.checked));
      });
      break;
    }
    case "select": {
      input = el(
        "select",
        { className: "vs2beh-widget-select" },
        spec.options.map((option) => {
          const optionEl = el("option", { value: String(option) }, [String(option)]);
          if (option === spec.value) {
            optionEl.selected = true;
          }
          return optionEl;
        })
      );
      input.addEventListener("change", () => {
        onChange(coerceWidgetValue(spec, input.value));
      });
      break;
    }
    case "slider": {
      const slider = el("input", {
        type: "range",
        className: "vs2beh-widget-slider",
        min: spec.min ?? undefined,
        max: spec.max ?? undefined,
        step: spec.step ?? "any",
      });
      slider.value = spec.value;
      const numberEcho = el("input", {
        type: "number",
        className: "vs2beh-widget-number-echo",
        min: spec.min ?? undefined,
        max: spec.max ?? undefined,
        step: spec.step ?? "any",
      });
      numberEcho.value = spec.value;
      const emit = (rawValue) => onChange(coerceWidgetValue(spec, rawValue));
      slider.addEventListener("input", () => {
        numberEcho.value = slider.value;
        emit(slider.value);
      });
      numberEcho.addEventListener("change", () => {
        slider.value = numberEcho.value;
        emit(numberEcho.value);
      });
      input = el("span", { className: "vs2beh-widget-slider-group" }, [slider, numberEcho]);
      break;
    }
    case "number": {
      input = el("input", { type: "number", className: "vs2beh-widget-number" });
      input.value = spec.value;
      input.addEventListener("change", () => {
        onChange(coerceWidgetValue(spec, input.value));
      });
      break;
    }
    case "text":
    default: {
      input = el("input", { type: "text", className: "vs2beh-widget-text" });
      input.value = typeof spec.value === "string" ? spec.value : String(spec.value);
      input.addEventListener("change", () => {
        onChange(coerceWidgetValue(spec, input.value));
      });
      break;
    }
  }

  return el("label", { className: `vs2beh-param vs2beh-param-${spec.control}` }, [
    el("span", { className: "vs2beh-param-label" }, [
      spec.label + (spec.unit ? ` (${spec.unit})` : ""),
    ]),
    input,
  ]);
}

/**
 * Build the two-level tree: subjects at the top, each subject's vars and
 * behaviors (with their params, and a behavior's actions' params) nested
 * underneath as a collapsible group. Every leaf widget is produced by
 * mountParamWidget() above, so no branch here ever names a parameter type.
 */
export function mountSubjectTree(container, listResult, client, options = {}) {
  container.replaceChildren();
  const onDirty = options.onDirty || (() => {});

  for (const subject of listResult.subjects) {
    const subjectDetails = el("details", { className: "vs2beh-subject", open: "" }, [
      el("summary", {}, [`${subject.name}  (${subject.kind}${
        typeof subject.count === "number" ? `, ${subject.count}` : ""
      })`]),
    ]);

    if (subject.vars && subject.vars.length) {
      const varsGroup = el("div", { className: "vs2beh-group vs2beh-vars-group" }, [
        el("h4", {}, ["vars"]),
      ]);
      for (const v of subject.vars) {
        const path = `${subject.name}.${v.name}`;
        varsGroup.append(
          mountParamWidget(v, (value) => {
            client.set(path, value).then(() => onDirty(path, value));
          })
        );
      }
      subjectDetails.append(varsGroup);
    }

    if (subject.kinds) {
      const kindsGroup = el("div", { className: "vs2beh-group vs2beh-kinds-group" }, [
        el("h4", {}, ["kinds"]),
      ]);
      const kindsContainer = el("div", { className: "vs2beh-kinds-container" });
      kindsGroup.append(kindsContainer);
      subjectDetails.append(kindsGroup);
      // mountKindsEditor's own onChange hands back the *whole* wire table
      // after exactly one cell changed (its own docstring: "editing a
      // cell only ever calls setKindsCell()"). The wire protocol
      // (ventilastation.behavior_control's _register_kind_cells)
      // addresses one cell at a time, at
      // `<subject>.kinds.<kind_name>.<field_name>` -- the same set/reset
      // verb every other param already uses -- so diff against the
      // table this closure already has to find exactly that one cell
      // rather than re-sending the whole table.
      let previousTable = subject.kinds;
      mountKindsEditor(kindsContainer, previousTable, (nextTable) => {
        const changed = diffOneKindsCell(previousTable, nextTable);
        previousTable = nextTable;
        if (!changed) {
          return;
        }
        const path = `${subject.name}.kinds.${changed.kindName}.${changed.fieldName}`;
        client.set(path, changed.value).then(() => onDirty(path, changed.value));
      });
    }

    for (const behavior of subject.behaviors || []) {
      const behaviorBlock = el("details", { className: "vs2beh-behavior", open: "" }, [
        el("summary", {}, [`${behavior.name}  (${behavior.class})`]),
      ]);
      for (const p of behavior.params || []) {
        const path = `${subject.name}.${behavior.name}.${p.name}`;
        behaviorBlock.append(
          mountParamWidget(p, (value) => {
            client.set(path, value).then(() => onDirty(path, value));
          })
        );
      }
      for (const action of behavior.actions || []) {
        const actionBlock = el("div", { className: "vs2beh-action" }, [
          el("h5", {}, [action.name]),
        ]);
        for (const p of action.params || []) {
          const path = `${subject.name}.${behavior.name}.${action.name}.${p.name}`;
          actionBlock.append(
            mountParamWidget(p, (value) => {
              client.set(path, value).then(() => onDirty(path, value));
            })
          );
        }
        behaviorBlock.append(actionBlock);
      }
      subjectDetails.append(behaviorBlock);
    }

    container.append(subjectDetails);
  }

  // The flattened leaf list drives nothing in the DOM directly, but is
  // exposed for callers that want a flat readout (e.g. "Copy Diagnostics").
  return flattenSubjects(listResult);
}

/**
 * Mount the `kinds` table editor: a plain HTML <table>, one row per kind,
 * one column per declared var(), editing a cell only ever calls
 * setKindsCell() (vs2-widgets.js) -- which never reorders `table.rows` --
 * and reports the whole updated table back via `onChange`.
 *
 * @param {HTMLElement} container
 * @param {{fields: string[], rows: {name: string, values: Array}[]}} wireTable
 * @param {(nextWireTable: Object) => void} onChange
 */
export function mountKindsEditor(container, wireTable, onChange) {
  container.replaceChildren();
  let table = kindsTableFromWire(wireTable);

  const renderRows = () => {
    const rowIndices = displayRowOrder(table); // canonical order; no sort applied.
    const headRow = el("tr", {}, [
      el("th", {}, ["kind"]),
      ...table.fields.map((field) => el("th", {}, [field])),
    ]);
    const bodyRows = rowIndices.map((rowIndex) => {
      const row = table.rows[rowIndex];
      return el("tr", { "data-kind-name": row.name }, [
        el("td", { className: "vs2beh-kind-name" }, [row.name]),
        ...row.values.map((value, fieldIndex) => {
          const cellInput = el("input", { type: "text", className: "vs2beh-kind-cell" });
          cellInput.value = String(value);
          cellInput.addEventListener("change", () => {
            table = setKindsCell(table, rowIndex, fieldIndex, coerceCellValue(cellInput.value, value));
            onChange(kindsTableToWire(table));
          });
          return el("td", {}, [cellInput]);
        }),
      ]);
    });
    tableEl.replaceChildren(el("thead", {}, [headRow]), el("tbody", {}, bodyRows));
  };

  const tableEl = el("table", { className: "vs2beh-kinds-table" });
  container.append(tableEl);
  renderRows();
}

function coerceCellValue(text, previousValue) {
  if (typeof previousValue === "number") {
    const parsed = Number(text);
    return Number.isNaN(parsed) ? previousValue : parsed;
  }
  if (typeof previousValue === "boolean") {
    return text === "true" || text === "1";
  }
  return text;
}

/**
 * Top-level bootstrap: wires the panel's own toggle button, a "Connect
 * serial" button (feature-detected -- hidden entirely where Web Serial is
 * unavailable, e.g. Firefox and Safari), and a "Refresh" button that calls
 * `client.list()` and re-renders the tree.
 */
export function createVS2BehaviorPanel({
  container,
  panelElement,
  toggleButton,
  connectButton,
  refreshButton,
  statusElement,
}) {
  let client = null;
  // `panelElement` is the section shown/hidden by `toggleButton` (toolbar
  // and tree together); `container` is only the tree-mounting target
  // inside it. They may be the same element for a caller with no separate
  // toolbar chrome.
  const toggleTarget = panelElement || container;

  const setStatus = (text) => {
    if (statusElement) {
      statusElement.textContent = text;
    }
  };

  const refresh = async () => {
    if (!client) {
      setStatus("Not connected");
      return;
    }
    try {
      const listResult = await client.list();
      mountSubjectTree(container, listResult, client, {
        onDirty: (path, value) => setStatus(`${path} = ${JSON.stringify(value)}`),
      });
      setStatus("Connected");
    } catch (err) {
      setStatus(`list failed: ${err.message}`);
    }
  };

  if (toggleButton && toggleTarget) {
    toggleButton.addEventListener("click", () => {
      const nextHidden = !toggleTarget.hidden;
      toggleTarget.hidden = nextHidden;
      toggleButton.setAttribute("aria-expanded", nextHidden ? "false" : "true");
    });
  }

  if (connectButton) {
    if (!WebSerialTransport.isSupported()) {
      connectButton.hidden = true;
    } else {
      connectButton.addEventListener("click", async () => {
        try {
          const transport = await WebSerialTransport.requestPort();
          await transport.open();
          client = new VS2BehClient(transport);
          await refresh();
        } catch (err) {
          setStatus(`connect failed: ${err.message}`);
        }
      });
    }
  }

  if (refreshButton) {
    refreshButton.addEventListener("click", refresh);
  }

  return {
    /** Wire an already-constructed client (e.g. a non-serial transport). */
    setClient(newClient) {
      client = newClient;
      return refresh();
    },
    refresh,
  };
}
