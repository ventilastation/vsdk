import assert from "node:assert/strict";

globalThis.window = {location: {href: "http://localhost/emulator/"}};
globalThis.VentilastationLedRenderCore = {};
const { KeyboardHelp } = await import("../web/keyboard-help.js");
const listeners = new Map();
const button = {addEventListener() {}, setAttribute() {}};
const dialog = {
  open: false,
  addEventListener(name, callback) { listeners.set(name, callback); },
  querySelector() { return button; },
  showModal() { this.open = true; },
  close() { this.open = false; listeners.get("close")(); },
};
let resets = 0;
let focusReturns = 0;
globalThis.document = {querySelector: () => ({focus() { focusReturns += 1; }})};
const help = new KeyboardHelp(dialog, button, () => { resets += 1; return resets === 1 ? ["KeyW"] : []; });
help.loading = Promise.resolve(); // Fetch/render is exercised in the browser.
const classes = new Set();
help.keycaps.set("Space", {classList: {add: name => classes.add(name), remove: name => classes.delete(name)}});
const event = (code, repeat = false) => ({code, repeat, prevented: false, preventDefault() {this.prevented = true;}});

assert.equal(help.keydown(event("F1")), true);
assert.equal(dialog.open, true);
help.keydown(event("F1", true));
assert.equal(dialog.open, true, "F1 autorepeat must not close help");
assert.equal(help.keydown(event("KeyW")), true, "keys held before opening are quarantined");
help.keyup(event("KeyW"));
const space = event("Space");
assert.equal(help.keydown(space), true);
assert.equal(space.prevented, true);
assert.equal(classes.has("is-held"), true);
assert.equal(help.keydown(event("F1")), true);
assert.equal(dialog.open, false);
assert.equal(help.keydown(event("Space", true)), true, "held preview key must not leak after close");
assert.equal(help.keyup(event("Space")), true);
assert.equal(help.keydown(event("Space")), false, "released key can control the game again");
assert.equal(focusReturns, 1);

help.keydown(event("F1"));
help.keydown(event("Escape"));
assert.equal(dialog.open, false);
assert.equal(help.keydown(event("Escape", true)), true, "closing help must not also exit the game");
help.keyup(event("Escape"));
assert.equal(help.keydown(event("Escape")), false);
help.blocked.add("KeyW");
help.releaseAll();
assert.equal(help.blocked.size, 0);
assert.equal(help.held.size, 0);
console.log("Keyboard help consumes F1/Esc, quarantines held keys and returns focus to play");
