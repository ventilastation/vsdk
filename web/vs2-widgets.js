// Generic widget dispatch for the VS2 behaviors inspector panel (T12).
//
// Spec: docs/vs2-behaviors-proposal.md, "### Parameters are the schema".
// Work-breakdown card: docs/vs2-behaviors-implementation.md, T12.
//
// The whole point of this module is that it never branches on a parameter's
// *type name* ("number", "angle", "flag", ...) -- vs2/params.py's own
// introspect() emits those strings (see apps/micropython/vs2/params.py,
// Parameter.type_name on each subclass), but a panel that pattern-matches
// them one by one is exactly the thing T12's acceptance list forbids:
// "No parameter type is special-cased in the panel; adding one to
// params.py makes it appear with no panel edit."
//
// So dispatch here reads only the *shape* of the wire descriptor -- whether
// it carries `options`, whether its `value` is a boolean, whether it carries
// a numeric range -- never the `type` string itself. `type` is carried
// through into the returned spec purely as a label/debugging aid; nothing
// in this file inspects it to make a decision. A parameter type this
// module has never heard of (today's ten real ones, or a hypothetical
// eleventh added to params.py tomorrow, or a completely fictional one
// invented only for a test) is handled by the same shape rules as every
// other parameter, falling through to the generic text control when no
// more specific shape matches -- see tests/test_vs2_widget_dispatch.mjs.

/**
 * @typedef {Object} ParamDescriptor
 * @property {string} name
 * @property {string} [type]
 * @property {*} value
 * @property {number|null} [min]
 * @property {number|null} [max]
 * @property {number|null} [step]
 * @property {string|null} [label]
 * @property {string|null} [unit]
 * @property {Array|null} [options]
 */

/**
 * @typedef {Object} WidgetSpec
 * @property {string} control - "select" | "checkbox" | "slider" | "number" | "text"
 * @property {string} label
 * @property {*} value
 * @property {string|undefined} unit
 * @property {number|null|undefined} min
 * @property {number|null|undefined} max
 * @property {number|null|undefined} step
 * @property {Array|undefined} options
 * @property {string} sourceType - the descriptor's own `type` string, carried
 *   through unexamined -- never read by this module to make a decision, kept
 *   only so a caller (e.g. a debug readout) can display it.
 */

function isFiniteNumber(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function hasNumericRange(param) {
  return isFiniteNumber(param.min) || isFiniteNumber(param.max) || isFiniteNumber(param.step);
}

function hasOptions(param) {
  return Array.isArray(param.options) && param.options.length > 0;
}

/**
 * Decide which generic control renders a parameter descriptor, purely from
 * its shape. This is the one function every param widget in the panel goes
 * through -- see mountParamWidget() in vs2-behavior-panel.js, which reads
 * `spec.control` and nothing else about the parameter.
 *
 * @param {ParamDescriptor} param
 * @returns {WidgetSpec}
 */
export function widgetSpecFor(param) {
  const label = param.label || param.name;
  const base = {
    label,
    value: param.value,
    unit: param.unit || undefined,
    sourceType: param.type,
  };

  if (hasOptions(param)) {
    return { ...base, control: "select", options: param.options };
  }

  if (typeof param.value === "boolean") {
    return { ...base, control: "checkbox" };
  }

  if (hasNumericRange(param)) {
    return {
      ...base,
      control: "slider",
      min: isFiniteNumber(param.min) ? param.min : null,
      max: isFiniteNumber(param.max) ? param.max : null,
      step: isFiniteNumber(param.step) ? param.step : null,
    };
  }

  if (typeof param.value === "number") {
    return { ...base, control: "number" };
  }

  // Generic fallback: anything this module has no more specific shape rule
  // for -- a pool/image/sound/frames/callback/points reference with no
  // populated `options`, or a parameter type nobody has invented yet.
  // Rendered as an editable text field carrying the value's JSON form, so
  // it is always *something sensible* rather than a silent no-op.
  return { ...base, control: "text", value: stringifyGeneric(param.value) };
}

/**
 * The inverse of the "text" branch above: turn a string typed into the
 * generic fallback control back into a JS value to send over the wire.
 * Tries JSON first (so `[1,2,3]`, `"literal"`, `true`, `42` round-trip
 * exactly); falls back to the raw string for anything that is not valid
 * JSON (a bare pool name like `explosions`, for instance).
 */
export function parseGenericText(text) {
  try {
    return JSON.parse(text);
  } catch (_err) {
    return text;
  }
}

function stringifyGeneric(value) {
  if (typeof value === "string") {
    return value;
  }
  if (value === undefined) {
    return "";
  }
  try {
    return JSON.stringify(value);
  } catch (_err) {
    return String(value);
  }
}

/**
 * Read a raw value back out of a mounted control, coercing it to match
 * `spec.control` -- the DOM-facing counterpart of widgetSpecFor(). Kept
 * here (not in the DOM-mounting module) so it can be unit tested without a
 * browser: callers pass whatever their control produced (a string from an
 * <input>, a boolean from a checkbox, ...).
 */
export function coerceWidgetValue(spec, rawValue) {
  switch (spec.control) {
    case "checkbox":
      return Boolean(rawValue);
    case "slider":
    case "number":
      return typeof rawValue === "number" ? rawValue : Number(rawValue);
    case "select":
      return rawValue;
    case "text":
    default:
      return typeof rawValue === "string" ? parseGenericText(rawValue) : rawValue;
  }
}

// ---------------------------------------------------------------------------
// The `kinds` table editor.
//
// Spec: docs/vs2-behaviors-proposal.md, "### Kinds: per-type defaults as a
// table". SpritePool.kinds() (apps/micropython/vs2/__init__.py) declares
// named rows over a pool's var()s, each row a plain positional tuple
// matching var() declaration order -- see SpritePool._kind_fields (the
// column order) and SpritePool._kind_rows (`{kind_name: row}`).
//
// vs2/__init__.py's own comment on SpritePool._var_order explains why this
// module represents a kinds table as an ORDERED ARRAY of {name, values}
// rows, never a plain object/dict keyed by kind name: "MicroPython's dict
// does not preserve insertion order the way CPython's does ... this list
// is what kinds() reads instead." The same hazard applies to any wire
// format for a kinds table -- a JSON object's key order is not a contract
// either party should rely on -- so this module's KindsTable shape carries
// row order explicitly as array position, which is what "round-trips a
// table without reordering rows" (T12's acceptance bullet) actually means:
// the array's element order is the row order, full stop.
// ---------------------------------------------------------------------------

/**
 * @typedef {Object} KindsRow
 * @property {string} name
 * @property {Array} values
 */

/**
 * @typedef {Object} KindsTable
 * @property {string[]} fields - column names, in var() declaration order.
 * @property {KindsRow[]} rows - in declaration/display order.
 */

/**
 * Build a KindsTable from the wire shape `{fields: [...], rows: [{name,
 * values}, ...]}`, deep-copying so later edits never mutate the caller's
 * object.
 *
 * @param {{fields: string[], rows: {name: string, values: Array}[]}} wire
 * @returns {KindsTable}
 */
export function kindsTableFromWire(wire) {
  return {
    fields: [...wire.fields],
    rows: wire.rows.map((row) => ({ name: row.name, values: [...row.values] })),
  };
}

/** The inverse of kindsTableFromWire(): a plain JSON-serialisable object. */
export function kindsTableToWire(table) {
  return {
    fields: [...table.fields],
    rows: table.rows.map((row) => ({ name: row.name, values: [...row.values] })),
  };
}

/**
 * Return a new KindsTable with exactly one cell changed. Every other row is
 * the same object reference as before (not just deep-equal) -- editing one
 * cell never touches, reorders, or reallocates any other row, which is the
 * literal thing T12's acceptance bullet ("without reordering rows") tests.
 *
 * @param {KindsTable} table
 * @param {number} rowIndex - canonical row index (array position), never a
 *   display/sorted index -- see displayRowOrder() below for that.
 * @param {number} fieldIndex - canonical column index into `table.fields`.
 * @param {*} value
 * @returns {KindsTable}
 */
export function setKindsCell(table, rowIndex, fieldIndex, value) {
  if (rowIndex < 0 || rowIndex >= table.rows.length) {
    throw new RangeError(`row index ${rowIndex} out of range (${table.rows.length} rows)`);
  }
  if (fieldIndex < 0 || fieldIndex >= table.fields.length) {
    throw new RangeError(`field index ${fieldIndex} out of range (${table.fields.length} fields)`);
  }
  const rows = table.rows.map((row, index) => {
    if (index !== rowIndex) {
      return row; // same reference: untouched.
    }
    const values = row.values.slice();
    values[fieldIndex] = value;
    return { name: row.name, values };
  });
  return { fields: table.fields, rows };
}

/**
 * Rename a row's identity is deliberately NOT offered here: the row's
 * `name` is the kind name spawn(kind=...) addresses, so renaming is a
 * structural edit, not a cell edit. This module only ever changes `values`.
 */

/**
 * A *display* order for the table's rows -- e.g. sorted by one column for
 * presentation -- that never mutates `table.rows` itself. Returns an array
 * of canonical row indices; a caller iterates `order.map(i => table.rows[i])`
 * to render sorted, while any edit still addresses the table by its
 * canonical `rowIndex`, not by position in this list.
 *
 * @param {KindsTable} table
 * @param {(a: KindsRow, b: KindsRow) => number} [compareFn] - defaults to
 *   each row's declared (canonical) order, i.e. a no-op sort.
 * @returns {number[]}
 */
export function displayRowOrder(table, compareFn) {
  const indices = table.rows.map((_row, index) => index);
  if (!compareFn) {
    return indices;
  }
  return indices
    .slice()
    .sort((a, b) => compareFn(table.rows[a], table.rows[b]));
}

/**
 * A *display* column order (e.g. the user dragged a column header) as a
 * list of canonical field indices, again without mutating `table.fields`
 * or any row's `values` array.
 *
 * @param {KindsTable} table
 * @param {string[]} displayFieldNames - `table.fields` in the desired
 *   display order.
 * @returns {number[]}
 */
export function displayFieldOrder(table, displayFieldNames) {
  return displayFieldNames.map((name) => {
    const index = table.fields.indexOf(name);
    if (index === -1) {
      throw new RangeError(`unknown field ${JSON.stringify(name)}`);
    }
    return index;
  });
}

/**
 * Compare two *wire*-shaped kinds tables (`{fields, rows: [{name,
 * values}]}` -- the shape `mountKindsEditor`'s `onChange` in
 * vs2-behavior-panel.js hands back, via `kindsTableToWire`) and return the
 * single `{kindName, fieldName, value}` that changed, or `null` if
 * nothing did. `mountKindsEditor` only ever changes one cell per call
 * (its own docstring: "editing a cell only ever calls setKindsCell()"),
 * so this never needs to report more than one -- the panel uses this to
 * turn "the whole table changed" back into the single
 * `<subject>.kinds.<kind_name>.<field_name>` `vs2beh set` every other
 * param already addresses one cell at, rather than inventing a
 * whole-table wire verb.
 */
export function diffOneKindsCell(previousTable, nextTable) {
  const previousByName = new Map(previousTable.rows.map((row) => [row.name, row]));
  for (const row of nextTable.rows) {
    const previousRow = previousByName.get(row.name);
    if (!previousRow) {
      continue;
    }
    for (let fieldIndex = 0; fieldIndex < nextTable.fields.length; fieldIndex += 1) {
      if (row.values[fieldIndex] !== previousRow.values[fieldIndex]) {
        return {
          kindName: row.name,
          fieldName: nextTable.fields[fieldIndex],
          value: row.values[fieldIndex],
        };
      }
    }
  }
  return null;
}
