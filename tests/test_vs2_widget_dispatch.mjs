// Generic widget-dispatch tests for the VS2 behaviors inspector panel
// (T12). Plain Node script, no browser -- matching
// tests/test_web_input_v2.mjs's convention of importing the real module
// under test directly rather than reimplementing its logic in the test.
//
//   node tests/test_vs2_widget_dispatch.mjs
//
// The point of this file is T12's headline acceptance bullet: "No
// parameter type is special-cased in the panel; adding one to params.py
// makes it appear with no panel edit." Every one of the ten real type
// names apps/micropython/vs2/params.py's Parameter subclasses emit as
// their `type_name` (Number="number", Angle="angle", Flag="flag",
// Choice="choice", Frames="frames", Sound="sound", Image="image",
// PoolRef="pool", Points="points", Callback="callback" -- read directly
// from params.py, not guessed) is exercised below, alongside one
// completely fictional type name ("vector3") that vs2-widgets.js's
// widgetSpecFor() has never seen. The fictional case is the actual proof:
// if dispatch worked by matching known type strings, an unknown one would
// either throw or silently render nothing. It does neither -- it falls
// through to the same generic shape rule every other untyped value uses.

import { widgetSpecFor, coerceWidgetValue, parseGenericText } from "../web/vs2-widgets.js";

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertEqual(actual, expected, message) {
  const same = JSON.stringify(actual) === JSON.stringify(expected);
  assert(same, `${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

// ---------------------------------------------------------------------------
// The ten real params.py type names, each as vs2beh's documented wire shape
// would carry it.
// ---------------------------------------------------------------------------

function testNumberRendersAsSlider() {
  const spec = widgetSpecFor({ name: "hp", type: "number", value: 1, min: 1, max: 99, step: 1 });
  assertEqual(spec.control, "slider", "Number with min/max/step");
  assertEqual(spec.min, 1, "min carried through");
  assertEqual(spec.max, 99, "max carried through");
}

function testAngleRendersLikeAnyOtherRangedNumber() {
  // Angle is a Number subclass with identical validation (params.py: "class
  // Angle(Number): type_name = 'angle'"); it deliberately gets no special
  // dial widget here -- see the design note in vs2-widgets.js's header --
  // so it takes the exact same shape-driven "slider" path as a plain
  // Number. Proving that is itself part of "no type is special-cased".
  const spec = widgetSpecFor({ name: "speed_x", type: "angle", value: 0, min: -32, max: 32, step: 0.25 });
  assertEqual(spec.control, "slider", "Angle uses the generic ranged-number path");
}

function testFlagRendersAsCheckbox() {
  const spec = widgetSpecFor({ name: "angry", type: "flag", value: false });
  assertEqual(spec.control, "checkbox", "Flag (boolean value)");
}

function testChoiceRendersAsSelect() {
  const spec = widgetSpecFor({ name: "mode", type: "choice", value: "b", options: ["a", "b", "c"] });
  assertEqual(spec.control, "select", "Choice (options present)");
  assertEqual(spec.options, ["a", "b", "c"], "options carried through");
}

function testFramesWithNoOptionsFallsThroughToGeneric() {
  // Frames' own default constructor never populates `options` (see
  // params.py: Frames(default=0, label=None, unit=None) -- no options
  // kwarg at all); a real build might enrich the wire descriptor with the
  // image's frame list, but the bare shape below is what a naive/partial
  // backend would send, and it must still render *something*.
  const spec = widgetSpecFor({ name: "frame", type: "frames", value: 2 });
  assertEqual(spec.control, "number", "Frames with a bare numeric value, no options/range");
}

function testSoundWithOptionsFallsThroughToSelect() {
  const spec = widgetSpecFor({
    name: "hit_sound", type: "sound", value: "boom", options: ["boom", "clang"],
  });
  assertEqual(spec.control, "select", "Sound enriched with options behaves like Choice");
}

function testSoundWithNoOptionsFallsThroughToText() {
  const spec = widgetSpecFor({ name: "hit_sound", type: "sound", value: "boom" });
  assertEqual(spec.control, "text", "Sound with a bare string value, no options");
  assertEqual(spec.value, "boom", "string value passed through unquoted");
}

function testImageFallsThroughToText() {
  const spec = widgetSpecFor({ name: "icon", type: "image", value: "ship.png" });
  assertEqual(spec.control, "text", "Image with a bare string value");
}

function testPoolRefMatchesTheDocumentedSampleExactly() {
  // Straight from docs/vs2-behaviors-proposal.md's "## The live-tune
  // loop" sample: {"name":"explosion","type":"pool","value":"explosions"}
  // -- no min/max/options at all.
  const spec = widgetSpecFor({ name: "explosion", type: "pool", value: "explosions" });
  assertEqual(spec.control, "text", "PoolRef with only a value, matching the spec's own example");
  assertEqual(spec.value, "explosions", "value passed through");
}

function testPointsFallsThroughToGenericJsonText() {
  const spec = widgetSpecFor({ name: "path", type: "points", value: [[0, 0], [10, 20]] });
  assertEqual(spec.control, "text", "Points (an array value, no options/range/boolean)");
  assertEqual(JSON.parse(spec.value), [[0, 0], [10, 20]], "array round-trips through JSON text");
}

function testCallbackFallsThroughToText() {
  const spec = widgetSpecFor({ name: "on_death", type: "callback", value: null });
  assertEqual(spec.control, "text", "Callback with no bound handler");
}

// ---------------------------------------------------------------------------
// The actual proof: a type name invented only for this test.
// ---------------------------------------------------------------------------

function testFictionalTypeFallsThroughToGenericTextWithNoCodeChange() {
  // "vector3" appears nowhere in vs2-widgets.js. If dispatch worked by
  // matching type-name strings this would have to special-case it (or
  // fail); instead it falls through the same shape rules real types do:
  // no options, not a boolean, no numeric range -- so it becomes the
  // generic text control, exactly like the untyped Points/PoolRef cases
  // above.
  const fictionalDescriptor = {
    name: "spin", type: "vector3", value: { x: 1, y: 2, z: 3 },
  };
  const spec = widgetSpecFor(fictionalDescriptor);
  assert(spec.control === "text", "an unknown type name renders as the generic fallback control");
  assertEqual(JSON.parse(spec.value), { x: 1, y: 2, z: 3 }, "its value survives the fallback JSON encoding");

  // And a fictional *ranged* type (shape says "slider", not "text") --
  // proving the fallback isn't itself special-cased to "text is the only
  // possible unknown-type outcome". Dispatch reads shape, and a numeric
  // range is a shape, regardless of what the type is called.
  const fictionalRanged = { name: "warp_factor", type: "quaternion_boost", value: 3, min: 0, max: 9, step: 1 };
  const rangedSpec = widgetSpecFor(fictionalRanged);
  assertEqual(rangedSpec.control, "slider", "a fictional type with a numeric range still gets a slider");
}

function testFictionalBooleanShapedTypeFallsThroughToCheckbox() {
  const spec = widgetSpecFor({ name: "shielded", type: "some_future_flag_type", value: true });
  assertEqual(spec.control, "checkbox", "a fictional type with a boolean value still gets a checkbox");
}

// ---------------------------------------------------------------------------
// dispatch never reads `param.type` to decide -- verified structurally: a
// descriptor with type deleted entirely must dispatch identically to one
// that carries a (possibly wrong) type string, since only shape matters.
// ---------------------------------------------------------------------------

function testDispatchIgnoresTheTypeFieldEntirely() {
  const withType = widgetSpecFor({ name: "hp", type: "totally_wrong_type_name", value: 1, min: 1, max: 99 });
  const withoutType = widgetSpecFor({ name: "hp", value: 1, min: 1, max: 99 });
  assertEqual(withType.control, withoutType.control, "control choice is unaffected by `type`");
  assertEqual(withType.min, withoutType.min, "min is unaffected by `type`");
}

// ---------------------------------------------------------------------------
// coerceWidgetValue(): the DOM-facing inverse, unit tested without a DOM.
// ---------------------------------------------------------------------------

function testCoerceWidgetValueRoundTrips() {
  const numberSpec = widgetSpecFor({ name: "hp", value: 1, min: 1, max: 99, step: 1 });
  assertEqual(coerceWidgetValue(numberSpec, "42"), 42, "slider control coerces a string to a number");

  const checkboxSpec = widgetSpecFor({ name: "angry", value: false });
  assertEqual(coerceWidgetValue(checkboxSpec, true), true, "checkbox control passes booleans through");

  const selectSpec = widgetSpecFor({ name: "mode", value: "b", options: ["a", "b", "c"] });
  assertEqual(coerceWidgetValue(selectSpec, "c"), "c", "select control passes the chosen option through");

  const textSpec = widgetSpecFor({ name: "explosion", value: "explosions" });
  assertEqual(coerceWidgetValue(textSpec, "other_pool"), "other_pool", "text control passes a bare string through");
  assertEqual(coerceWidgetValue(textSpec, "[1,2,3]"), [1, 2, 3], "text control parses JSON-looking input");
}

function testParseGenericTextFallsBackToRawStringOnInvalidJson() {
  assertEqual(parseGenericText("not json at all"), "not json at all", "invalid JSON stays a raw string");
  assertEqual(parseGenericText("42"), 42, "valid JSON number parses");
  assertEqual(parseGenericText('"quoted"'), "quoted", "valid JSON string parses");
}

const tests = [
  testNumberRendersAsSlider,
  testAngleRendersLikeAnyOtherRangedNumber,
  testFlagRendersAsCheckbox,
  testChoiceRendersAsSelect,
  testFramesWithNoOptionsFallsThroughToGeneric,
  testSoundWithOptionsFallsThroughToSelect,
  testSoundWithNoOptionsFallsThroughToText,
  testImageFallsThroughToText,
  testPoolRefMatchesTheDocumentedSampleExactly,
  testPointsFallsThroughToGenericJsonText,
  testCallbackFallsThroughToText,
  testFictionalTypeFallsThroughToGenericTextWithNoCodeChange,
  testFictionalBooleanShapedTypeFallsThroughToCheckbox,
  testDispatchIgnoresTheTypeFieldEntirely,
  testCoerceWidgetValueRoundTrips,
  testParseGenericTextFallsBackToRawStringOnInvalidJson,
];

for (const test of tests) {
  test();
  console.log("ok", test.name);
}
console.log(`vs2 widget dispatch: ${tests.length} checks passed`);
