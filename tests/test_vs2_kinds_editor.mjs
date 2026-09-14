// `kinds` table editor tests for the VS2 behaviors inspector panel (T12).
// Plain Node script, no browser.
//
//   node tests/test_vs2_kinds_editor.mjs
//
// Spec: docs/vs2-behaviors-proposal.md, "### Kinds: per-type defaults as a
// table". SpritePool.kinds() (apps/micropython/vs2/__init__.py) declares
// named rows over a pool's var()s, each row a plain positional tuple in
// var() declaration order -- SpritePool._kind_fields is the column order,
// SpritePool._kind_rows is `{kind_name: row}`.
//
// T12's literal acceptance bullet: "The kinds editor round-trips a table
// without reordering rows." The tests below edit an interior row's value
// and confirm every other row's identity/position is untouched, then
// separately confirm that a *display* reorder (sorting for presentation,
// or reordering columns) never touches the canonical row storage at all.

import {
  kindsTableFromWire,
  kindsTableToWire,
  setKindsCell,
  displayRowOrder,
  displayFieldOrder,
} from "../web/vs2-widgets.js";

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertEqual(actual, expected, message) {
  const same = JSON.stringify(actual) === JSON.stringify(expected);
  assert(same, `${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

// A five-row table, matching the shape SpritePool.kinds() declares:
// self.enemies.var("hp", 1); self.enemies.var("score", 40);
// self.enemies.kinds(driller=(3, 75), chiller=(1, 40), ...).
function sampleWireTable() {
  return {
    fields: ["hp", "score"],
    rows: [
      { name: "driller", values: [3, 75] },
      { name: "chiller", values: [1, 40] },
      { name: "tank", values: [9, 120] },
      { name: "scout", values: [1, 10] },
      { name: "boss", values: [50, 999] },
    ],
  };
}

// ---------------------------------------------------------------------------
// The literal acceptance bullet: edit an interior row, confirm every other
// row's identity/position is untouched.
// ---------------------------------------------------------------------------

function testEditingAnInteriorRowLeavesEveryOtherRowUntouched() {
  const wire = sampleWireTable();
  const table = kindsTableFromWire(wire);
  const originalNamesInOrder = table.rows.map((row) => row.name);
  assertEqual(originalNamesInOrder, ["driller", "chiller", "tank", "scout", "boss"], "sanity: original order");

  // Edit "tank" (index 2, an interior row) -- change its "score" column
  // (index 1) from 120 to 999999.
  const edited = setKindsCell(table, 2, 1, 999999);

  assertEqual(edited.rows.length, table.rows.length, "row count is unchanged");
  assertEqual(edited.rows.map((row) => row.name), originalNamesInOrder,
    "row order (which kind name is in which position) is unchanged");

  edited.rows.forEach((row, index) => {
    if (index === 2) {
      assertEqual(row.name, "tank", "the edited row is still named tank");
      assertEqual(row.values, [9, 999999], "only the edited cell changed on that row");
    } else {
      assertEqual(row, table.rows[index], "every other row is untouched (deep-equal, same content)");
      assert(row === table.rows[index], "every other row is the very same object reference, not a copy");
    }
  });

  // The original table itself must not have been mutated (tank's original
  // score was 120, not 999999).
  assertEqual(table.rows[2].values, [9, 120], "setKindsCell() does not mutate its input table");
}

function testEditingTheFirstAndLastRowsAlsoPreservesEveryoneElse() {
  const table = kindsTableFromWire(sampleWireTable());

  const editedFirst = setKindsCell(table, 0, 0, 4);
  assertEqual(editedFirst.rows.map((r) => r.name), ["driller", "chiller", "tank", "scout", "boss"],
    "editing row 0 preserves full row order");
  assertEqual(editedFirst.rows[0].values, [4, 75], "row 0's edited cell took effect");

  const editedLast = setKindsCell(table, 4, 1, 1000);
  assertEqual(editedLast.rows.map((r) => r.name), ["driller", "chiller", "tank", "scout", "boss"],
    "editing the last row preserves full row order");
  assertEqual(editedLast.rows[4].values, [50, 1000], "last row's edited cell took effect");
}

function testOutOfRangeIndicesRaiseRatherThanSilentlyCorrupting() {
  const table = kindsTableFromWire(sampleWireTable());
  let threw = false;
  try {
    setKindsCell(table, 99, 0, 1);
  } catch (err) {
    threw = err instanceof RangeError;
  }
  assert(threw, "an out-of-range row index raises RangeError instead of writing somewhere wrong");
}

// ---------------------------------------------------------------------------
// Round-trip through the wire shape: unaffected by intervening edits.
// ---------------------------------------------------------------------------

function testWireRoundTripPreservesOrderAfterAnEdit() {
  const wire = sampleWireTable();
  const table = kindsTableFromWire(wire);
  const edited = setKindsCell(table, 1, 0, 2); // chiller.hp: 1 -> 2
  const wireOut = kindsTableToWire(edited);

  assertEqual(wireOut.fields, wire.fields, "fields round-trip unchanged");
  assertEqual(wireOut.rows.map((r) => r.name), wire.rows.map((r) => r.name),
    "row name order round-trips exactly, unchanged from the original wire order");
  assertEqual(wireOut.rows[1].values, [2, 40], "the edited row's new value is present in the round trip");
  assertEqual(wireOut.rows[0].values, wire.rows[0].values, "driller (untouched) is unchanged");
  assertEqual(wireOut.rows[2].values, wire.rows[2].values, "tank (untouched) is unchanged");
}

// ---------------------------------------------------------------------------
// "even if editing reorders columns or you resort the display": a display
// sort/column-reorder must never touch canonical row storage order.
// ---------------------------------------------------------------------------

function testSortingForDisplayNeverMutatesCanonicalRowOrder() {
  const table = kindsTableFromWire(sampleWireTable());
  const canonicalNamesBefore = table.rows.map((r) => r.name);

  // Sort for display by descending "hp" (field index 0): boss(50), tank(9),
  // driller(3), scout(1)==chiller(1) tie broken by stable original order.
  const sortedIndices = displayRowOrder(table, (a, b) => b.values[0] - a.values[0]);
  const displayNames = sortedIndices.map((index) => table.rows[index].name);
  assertEqual(displayNames, ["boss", "tank", "driller", "chiller", "scout"], "display order reflects the sort");

  // Canonical storage is untouched by having computed a display order.
  assertEqual(table.rows.map((r) => r.name), canonicalNamesBefore, "canonical row order is unchanged by sorting");

  // Now edit via a *canonical* index obtained by looking up the row the
  // user clicked on in sorted position 1 ("tank", canonical index 2), and
  // confirm the edit still targets canonical storage correctly and every
  // other row is untouched -- proving a sorted display never confuses which
  // physical row an edit lands on.
  const clickedDisplayPosition = 1; // "tank" in the sorted view
  const canonicalIndex = sortedIndices[clickedDisplayPosition];
  assertEqual(table.rows[canonicalIndex].name, "tank", "sorted display position 1 maps back to tank");
  const edited = setKindsCell(table, canonicalIndex, 1, 7777);
  assertEqual(edited.rows.map((r) => r.name), canonicalNamesBefore,
    "editing through a display-sorted lookup still preserves canonical row order");
  assertEqual(edited.rows[canonicalIndex].values, [9, 7777], "the correct physical row was edited");
}

function testReorderingColumnsForDisplayNeverMutatesFieldStorage() {
  const table = kindsTableFromWire(sampleWireTable());
  const fieldsBefore = [...table.fields];

  const displayOrder = displayFieldOrder(table, ["score", "hp"]); // user dragged "score" first
  assertEqual(displayOrder, [1, 0], "display column order maps to canonical field indices");

  // Canonical field storage (and therefore every row's `values` array
  // layout) is unaffected by having computed a display order.
  assertEqual(table.fields, fieldsBefore, "canonical field order is unchanged by a display reorder");

  // An edit addressed by canonical field index still lands correctly
  // after the display was reordered.
  const canonicalScoreIndex = displayOrder[0]; // "score" is field index 1
  const edited = setKindsCell(table, 0, canonicalScoreIndex, 500);
  assertEqual(edited.rows[0].values, [3, 500], "editing via the canonical index is unaffected by column display order");
  assertEqual(edited.rows.map((r) => r.name), table.rows.map((r) => r.name), "row order still preserved");
}

function testUnknownDisplayFieldNameRaises() {
  const table = kindsTableFromWire(sampleWireTable());
  let threw = false;
  try {
    displayFieldOrder(table, ["hp", "not_a_real_field"]);
  } catch (err) {
    threw = err instanceof RangeError;
  }
  assert(threw, "an unknown field name in a display order request raises");
}

const tests = [
  testEditingAnInteriorRowLeavesEveryOtherRowUntouched,
  testEditingTheFirstAndLastRowsAlsoPreservesEveryoneElse,
  testOutOfRangeIndicesRaiseRatherThanSilentlyCorrupting,
  testWireRoundTripPreservesOrderAfterAnEdit,
  testSortingForDisplayNeverMutatesCanonicalRowOrder,
  testReorderingColumnsForDisplayNeverMutatesFieldStorage,
  testUnknownDisplayFieldNameRaises,
];

for (const test of tests) {
  test();
  console.log("ok", test.name);
}
console.log(`vs2 kinds editor: ${tests.length} checks passed`);
