// Browser Gamepad API → Input Protocol v2 mapping tests.
import { readFileSync } from "node:fs";

globalThis.window = { location: { href: "https://example.test/web/index.html" } };
globalThis.VentilastationLedRenderCore = {};

const {
  BUTTONS,
  INPUT_EXTRA,
  keyboardInputForCode,
  keyboardInputForCodes,
  mapGamepadInput,
} = await import(new URL("../web/app-support.js", import.meta.url));

function gamepad({ axes = [], pressed = [], analog = [] } = {}) {
  const buttons = Array.from({ length: 17 }, () => ({ pressed: false, value: 0 }));
  for (const index of pressed) {
    buttons[index] = { pressed: true, value: 1 };
  }
  for (const index of analog) {
    buttons[index] = { pressed: false, value: 1 };
  }
  return { axes, buttons };
}

function testSingleControllerMapping() {
  const primary = gamepad({
    axes: [1, 0, -1, 1],
    pressed: [0, 1, 2, 3, 4, 5, 8, 9, 16],
    analog: [6, 7],
  });
  const input = mapGamepadInput(primary);

  assert(input.joy1 === (BUTTONS.JOY_RIGHT | BUTTONS.BUTTON_A | BUTTONS.BUTTON_B | BUTTONS.BUTTON_C));
  assert(input.joy2 === (BUTTONS.JOY_LEFT | BUTTONS.JOY_DOWN |
    BUTTONS.BUTTON_A | BUTTONS.BUTTON_B | BUTTONS.BUTTON_C));
  assert(input.extra === (INPUT_EXTRA.JOY1_Y | INPUT_EXTRA.JOY2_Y |
    INPUT_EXTRA.JOY1_START | INPUT_EXTRA.JOY1_BACK));
  assert(input.exit === true);
}

function testSecondControllerOwnsJoy2() {
  const primary = gamepad({
    // This right stick must be ignored while a second controller is present.
    axes: [0, 0, 1, 1],
    pressed: [0],
  });
  const secondary = gamepad({
    axes: [0, 0],
    pressed: [0, 1, 2, 3, 8, 9, 12, 14, 16],
  });
  const input = mapGamepadInput(primary, secondary);

  assert(input.joy1 === BUTTONS.BUTTON_A);
  assert(input.joy2 === (BUTTONS.JOY_LEFT | BUTTONS.JOY_UP |
    BUTTONS.BUTTON_A | BUTTONS.BUTTON_B | BUTTONS.BUTTON_C));
  assert(input.extra === (INPUT_EXTRA.JOY2_Y | INPUT_EXTRA.JOY2_START | INPUT_EXTRA.JOY2_BACK));
  assert(input.exit === true);
}

function testInvertedYAxis() {
  const primary = gamepad({ axes: [0, 1, 0, -1] });
  const input = mapGamepadInput(primary, null, true);
  assert(input.joy1 === BUTTONS.JOY_UP);
  assert(input.joy2 === BUTTONS.JOY_DOWN);
}

function testKeyboardMapsAllProtocolV2Controls() {
  const expected = {
    KeyW: [4, 0, 0], KeyS: [8, 0, 0], KeyA: [1, 0, 0], KeyD: [2, 0, 0],
    Space: [16, 0, 0], KeyB: [32, 0, 0], KeyN: [64, 0, 0], KeyM: [0, 0, 1],
    Digit1: [0, 0, 8], Digit2: [0, 0, 4],
    ArrowUp: [0, 4, 0], ArrowDown: [0, 8, 0], ArrowLeft: [0, 1, 0], ArrowRight: [0, 2, 0],
    Numpad0: [0, 16, 0], Numpad1: [0, 32, 0], Numpad2: [0, 64, 0], Numpad3: [0, 0, 2],
    NumpadAdd: [0, 0, 32], NumpadEnter: [0, 0, 16],
  };
  for (const [code, wanted] of Object.entries(expected)) {
    const input = keyboardInputForCodes([code]);
    assert([input.joy1, input.joy2, input.extra].every((value, i) => value === wanted[i]), code);
  }
  const combined = keyboardInputForCodes(Object.keys(expected));
  assert(combined.joy1 === 127 && combined.joy2 === 127 && combined.extra === 63);
  for (const code of ["Enter", "Digit0", "Digit3", "KeyO", "KeyP", "KeyY", "KeyH", "KeyJ",
    "KeyK", "KeyL", "KeyZ", "KeyX", "KeyC", "KeyV", "PageUp", "PageDown", "Home", "End"]) {
    assert(keyboardInputForCode(code) === null, `unassigned main keyboard key: ${code}`);
  }
}

function testHelpDiagramMatchesActualBindings() {
  const layout = JSON.parse(readFileSync(new URL("../web/keyboard-layout.json", import.meta.url)));
  assert(layout.keys.length === 20);
  assert(new Set(layout.keys.map(key => key.code)).size === 20);
  for (const key of layout.keys) {
    const input = keyboardInputForCode(key.code);
    assert(input && input[key.channel] === key.bit, `diagram disagrees with mapping: ${key.code}`);
  }
  for (const cap of [...layout.keys, ...layout.context]) {
    assert(cap.x >= 0 && cap.y >= 0 && cap.x + (cap.w || 1) <= layout.width
      && cap.y + (cap.h || 1) <= layout.height, `cap outside diagram: ${cap.key}`);
  }
}

function assert(value, message = "assertion failed") {
  if (!value) {
    throw new Error(message);
  }
}

const tests = [testSingleControllerMapping, testSecondControllerOwnsJoy2, testInvertedYAxis,
  testKeyboardMapsAllProtocolV2Controls, testHelpDiagramMatchesActualBindings];
for (const test of tests) {
  test();
  console.log("ok", test.name);
}
console.log(`web input v2: ${tests.length} checks passed`);
