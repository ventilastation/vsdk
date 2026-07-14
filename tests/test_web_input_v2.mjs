// Browser Gamepad API → Input Protocol v2 mapping tests.

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
  assert(keyboardInputForCode("PageUp").extra === INPUT_EXTRA.JOY1_START);
  assert(keyboardInputForCode("PageDown").extra === INPUT_EXTRA.JOY1_BACK);
  assert(keyboardInputForCode("KeyH").joy2 === BUTTONS.JOY_LEFT);
  assert(keyboardInputForCode("KeyJ").joy2 === BUTTONS.JOY_DOWN);
  assert(keyboardInputForCode("KeyK").joy2 === BUTTONS.JOY_UP);
  assert(keyboardInputForCode("KeyL").joy2 === BUTTONS.JOY_RIGHT);
  assert(keyboardInputForCode("KeyZ").joy2 === BUTTONS.BUTTON_A);
  assert(keyboardInputForCode("KeyX").joy2 === BUTTONS.BUTTON_B);
  assert(keyboardInputForCode("KeyC").joy2 === BUTTONS.BUTTON_C);
  assert(keyboardInputForCode("KeyV").extra === INPUT_EXTRA.JOY2_Y);
  assert(keyboardInputForCode("Home").extra === INPUT_EXTRA.JOY2_START);
  assert(keyboardInputForCode("End").extra === INPUT_EXTRA.JOY2_BACK);

  const combined = keyboardInputForCodes(["ArrowLeft", "KeyA", "KeyZ", "PageUp"]);
  assert(combined.joy1 === BUTTONS.JOY_LEFT);
  assert(combined.joy2 === BUTTONS.BUTTON_A);
  assert(combined.extra === INPUT_EXTRA.JOY1_START);
}

function assert(value, message = "assertion failed") {
  if (!value) {
    throw new Error(message);
  }
}

const tests = [testSingleControllerMapping, testSecondControllerOwnsJoy2, testInvertedYAxis,
  testKeyboardMapsAllProtocolV2Controls];
for (const test of tests) {
  test();
  console.log("ok", test.name);
}
console.log(`web input v2: ${tests.length} checks passed`);
