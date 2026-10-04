// End-to-end live-tune test for the VS2 behaviors inspector panel (T12):
// drives the REAL browser-side protocol client (web/vs2beh-client.js) and
// the REAL generic widget dispatch (web/vs2-widgets.js) against a REAL
// headless `micropython` process running the real vs2/params.py,
// vs2/behaviors.py and vs2/__init__.py (Waves 1-4, already landed).
//
//   node tests/test_vs2beh_live_tune_e2e.mjs
//
// SKIPs (exit 0, printing why) if no `micropython` unix binary is on
// PATH, matching tests/run_tests.py's own convention for optional
// interpreters.
//
// ## What this actually proves, and what it deliberately does not
//
// docs/vs2-behaviors-proposal.md's "## The live-tune loop" describes:
// "Drag a slider in the panel -> `vs2beh set` -> the running game changes
// on the next tick, with no restart." This test proves every step of that
// chain except the literal DOM `<input type="range">` and the literal
// USB/UART wire hop to physical hardware:
//
//   1. A real Behavior (Damageable, hand-written for this test) with a
//      real vs2.params.Number parameter (`hp`) is attached to a real
//      SpritePool in a real vs2.Scene, running inside a real `micropython`
//      subprocess (tests/fixtures/vs2beh_stub_scene.py).
//   2. This test's ChildProcessLineTransport talks to that subprocess over
//      its actual stdin/stdout pipes -- a real, separate OS process, not
//      an in-memory mock -- using the exact same line-in/line-out Transport
//      contract WebSerialTransport (web/vs2-behavior-panel.js) implements
//      for a real board's USB serial port. Swapping one Transport for the
//      other is the only thing standing between this test and physical
//      hardware; nothing in VS2BehClient or the widget-dispatch logic
//      changes.
//   3. The REAL web/vs2beh-client.js#VS2BehClient.list() call parses the
//      subprocess's real `vs2beh list` JSON reply.
//   4. The REAL web/vs2-widgets.js#widgetSpecFor() decides `hp` renders as
//      a slider (it has min/max/step) -- proving the dispatch that would
//      pick the DOM control a user actually drags is exercised against
//      live data, not a fixture literal.
//   5. This test simulates "the user drags the slider to a new position"
//      by doing exactly what web/vs2-behavior-panel.js's slider `input`
//      listener does: `coerceWidgetValue(spec, newRawValue)` then
//      `client.set(path, coercedValue)` -- both real functions, not
//      reimplemented here.
//   6. The REAL VS2BehClient.set() sends the REAL `vs2beh set
//      enemies.damageable.hp <n>` line to the subprocess and parses its
//      reply.
//   7. The subprocess is told to run one more real `scene_step()` (via the
//      fixture's own `tick` debug command -- not part of the vs2beh
//      protocol, just this test's way of advancing the scene), and this
//      test reads back `hp_log` -- an array the real `Damageable.step()`
//      appended `self.hp` to on every tick -- and confirms the new value
//      appears on the very next tick, with no restart. This is the literal
//      "the actual attribute changed on a running scene object" the task
//      brief asks for, checked by reading the object's own state, not by
//      trusting the wire reply alone.
//
// What is NOT proven here, and is genuinely hardware-only:
//   - That a real `<input type="range">` drag event fires with the DOM
//     event listeners web/vs2-behavior-panel.js registers (no DOM/jsdom is
//     available in this repo's Node test environment -- see this file's
//     companion tests/test_vs2_widget_dispatch.mjs and
//     tests/test_vs2beh_client.mjs for what those pure-logic pieces cover
//     without a browser).
//   - That WebSerialTransport's byte framing survives a real USB CDC link
//     to physical hardware, or that T11's real
//     apps/micropython/ventilastation/behavior_control.py (which does not
//     exist in this worktree) parses `vs2beh` lines exactly like this
//     test's stand-in fixture. The wire *shape* matches the documented
//     contract, but T11's own file is unverified here by design (T12 must
//     not create it).

import { spawn } from "node:child_process";
import { once } from "node:events";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { VS2BehClient } from "../web/vs2beh-client.js";
import { widgetSpecFor, coerceWidgetValue } from "../web/vs2-widgets.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..");
const FIXTURE = path.join("tests", "fixtures", "vs2beh_stub_scene.py");

function checkMicropythonAvailable() {
  return new Promise((resolve) => {
    const probe = spawn("micropython", ["-c", "print('ok')"]);
    probe.on("error", () => resolve(false));
    probe.on("exit", (code) => resolve(code === 0));
  });
}

/**
 * A Transport (matching VS2BehClient's `{sendLine(text) -> Promise<string>}`
 * contract exactly) talking to a real child process over its stdin/stdout
 * pipes -- the same contract web/vs2-behavior-panel.js's WebSerialTransport
 * implements for a real board's USB serial port. One line out, one line
 * back.
 */
class ChildProcessLineTransport {
  constructor(child) {
    this.child = child;
    this.buffer = "";
    this.pendingResolvers = [];
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk) => {
      this.buffer += chunk;
      this._drain();
    });
  }

  _drain() {
    let newlineIndex;
    while ((newlineIndex = this.buffer.indexOf("\n")) !== -1 && this.pendingResolvers.length) {
      const line = this.buffer.slice(0, newlineIndex);
      this.buffer = this.buffer.slice(newlineIndex + 1);
      const resolve = this.pendingResolvers.shift();
      resolve(line);
    }
  }

  sendLine(text) {
    const replyPromise = new Promise((resolve) => {
      this.pendingResolvers.push(resolve);
    });
    this.child.stdin.write(`${text}\n`);
    return replyPromise;
  }

  /** Non-protocol helper: this fixture's own debug commands (not part of
   * the vs2beh wire contract), used only to advance the scene and read
   * back what a real Step observed. */
  sendDebugLine(text) {
    return this.sendLine(text);
  }
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertEqual(actual, expected, message) {
  const same = JSON.stringify(actual) === JSON.stringify(expected);
  assert(same, `${message}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
}

async function main() {
  const available = await checkMicropythonAvailable();
  if (!available) {
    console.log("SKIP vs2beh live-tune E2E (micropython not on PATH)");
    return;
  }

  const child = spawn("micropython", [FIXTURE], { cwd: REPO_ROOT });
  const stderrChunks = [];
  child.stderr.setEncoding("utf8");
  child.stderr.on("data", (chunk) => stderrChunks.push(chunk));

  const transport = new ChildProcessLineTransport(child);
  const client = new VS2BehClient(transport);

  try {
    // Step 1: advance one tick before touching anything, and read the
    // Behavior's own live value -- this is the real Damageable.hp default
    // (1), read from a real running scene object, before any tuning.
    await transport.sendDebugLine("tick");
    const beforeLog = JSON.parse(await transport.sendDebugLine("hp_log"));
    assertEqual(beforeLog, [1], "hp starts at its declared default (1) before any live-tune set");

    // Step 3: list() through the REAL client against the REAL subprocess.
    const listResult = await client.list();
    const enemies = listResult.subjects.find((s) => s.name === "enemies");
    assert(enemies, "the real subprocess reports the 'enemies' pool");
    const hpParam = enemies.behaviors
      .find((b) => b.name === "damageable")
      .params.find((p) => p.name === "hp");
    assertEqual(hpParam.value, 1, "list() reports the real live hp value (1) before tuning");

    // Step 4: REAL widget dispatch decides this renders as a slider,
    // because it has min/max/step -- exactly what a user would actually
    // see and drag in the panel.
    const spec = widgetSpecFor(hpParam);
    assertEqual(spec.control, "slider", "hp (min/max/step present) dispatches to a slider, for real");

    // Step 5+6: simulate "the user dragged the slider to 42" the same way
    // web/vs2-behavior-panel.js's own slider `input` listener does --
    // coerce the raw control value, then client.set() the real path.
    const draggedRawValue = "42";
    const newValue = coerceWidgetValue(spec, draggedRawValue);
    assertEqual(newValue, 42, "coerceWidgetValue() turns the dragged raw string into a real number");
    const setResult = await client.set("enemies.damageable.hp", newValue);
    assertEqual(setResult, { ok: true, path: "enemies.damageable.hp", value: "42" },
      "the real subprocess acknowledges the set over the real transport");

    // Step 7: the actual attribute changed on a running scene object --
    // checked by reading the object's own state on the very next tick,
    // with no restart of the subprocess in between.
    await transport.sendDebugLine("tick");
    const afterLog = JSON.parse(await transport.sendDebugLine("hp_log"));
    assertEqual(afterLog, [1, 42],
      "Damageable.step() observed the OLD value on tick 1 and the NEW value on tick 2, " +
      "with no restart -- this is 'dragging a slider changes the running game' end to end, " +
      "against a real headless MicroPython process");

    // And a second list() confirms the same value is now reported back --
    // the full round trip a real panel's "Refresh" button would show.
    const listAfter = await client.list();
    const hpParamAfter = listAfter.subjects[0].behaviors[0].params.find((p) => p.name === "hp");
    assertEqual(hpParamAfter.value, 42, "list() reflects the tuned value after the set");

    console.log("ok: live-tune round trip against a real headless MicroPython process");
    console.log("vs2beh live-tune E2E: 1 check passed");
  } finally {
    child.stdin.end();
    child.kill();
    await once(child, "exit").catch(() => {});
    if (stderrChunks.length) {
      const stderrText = stderrChunks.join("");
      if (stderrText.trim()) {
        console.error("--- micropython stderr ---");
        console.error(stderrText);
      }
    }
  }
}

await main();
