// Exercise the shipped interpreter and worker, including the real game ROM.
// A small native stack reproduces the startup overflow seen on Android.
import assert from "node:assert/strict";
import { readFileSync, writeFileSync, mkdtempSync, rmSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { spawnSync } from "node:child_process";

const root = fileURLToPath(new URL("../", import.meta.url));
const gameDir = join(root, "games/demos/dream_garden/code");
const checkpoint = process.argv[2];

if (!checkpoint) {
  const build = spawnSync(process.env.VSDK_TEST_PYTHON || "python3",
    ["tools/generate_web_runtime_bundle.py"], { cwd: root, encoding: "utf8" });
  assert.equal(build.status, 0, build.stderr || String(build.error));
  for (const stage of ["finished", ...readdirSync(join(gameDir, "checkpoints")).filter(name => name.endsWith(".py"))]) {
    const result = spawnSync(process.execPath,
      ["--stack-size=256", fileURLToPath(import.meta.url), stage],
      { cwd: root, encoding: "utf8", timeout: 30_000 });
    assert.equal(result.status, 0, `${stage}: ${result.stdout}\n${result.stderr || result.error || ""}`);
    console.log(result.stdout.trim());
  }
} else {
  globalThis.self = {
    location: { href: "https://fixture.invalid/emulator/wasm-worker.js" },
    addEventListener() {},
    postMessage() {},
  };
  globalThis.fetch = async input => {
    const url = new URL(String(input), self.location.href);
    assert.equal(url.origin, "https://fixture.invalid");
    const data = readFileSync(resolve(root, "web", url.pathname.replace(/^\/emulator\//u, "")));
    return { ok: true, json: async () => JSON.parse(data.toString()) };
  };
  const temp = mkdtempSync(join(tmpdir(), "vsdk-wasm-startup-"));
  try {
    // A file import avoids spending the constrained stack decoding a data URL.
    const vendor = pathToFileURL(join(root, "web/vendor/micropython/micropython.mjs")).href;
    const source = readFileSync(join(root, "web/wasm-worker.js"), "utf8")
      .replace(/from "\.\/vendor\/micropython\/micropython\.mjs[^"]*"/u, `from ${JSON.stringify(vendor)}`)
      .replace('"./ventilagon-native.js"', JSON.stringify(pathToFileURL(join(root, "web/ventilagon-native.js")).href));
    const fixture = join(temp, "worker.mjs");
    writeFileSync(fixture, `${source}\nexport { MicroPythonRuntime, workerHostState };\n`);
    const { MicroPythonRuntime, workerHostState } = await import(pathToFileURL(fixture).href);
    const runtime = new MicroPythonRuntime({
      fsRoot: "/games", pystack: 32 * 1024, heapsize: 8 * 1024 * 1024,
      micropythonWasmUrl: join(root, "web/vendor/micropython/micropython.wasm"),
      ventilagonModuleUrl: pathToFileURL(join(root, "web/vendor/ventilagon/ventilagon.mjs")).href,
      ventilagonWasmUrl: join(root, "web/vendor/ventilagon/ventilagon.wasm"),
      runtimeManifestUrl: "./runtime-manifest.json", runtimeBundleUrl: "./runtime-bundle.json",
      autostartSlug: "demos.dream_garden",
      workspaceFiles: checkpoint === "finished" ? [] : [{
        path: "games/demos/dream_garden/code/dream_garden.py",
        content: readFileSync(join(gameDir, "checkpoints", checkpoint), "utf8"),
      }],
    });
    await runtime.initialize();
    await runtime.step(1);
    const snapshot = () => runtime.call("ventilastation.browser", "memory_snapshot", [true]);
    let memory = await snapshot();
    assert.equal(memory.runtime.platform, "browser");
    assert.ok(["Title", "Game"].includes(memory.runtime.currentScene), JSON.stringify(memory));
    if (memory.runtime.currentScene === "Title") {
      workerHostState.joy1 = 0x10; // A enters the game, not just its title screen.
      await runtime.step(1);
      workerHostState.joy1 = 0;
      await runtime.step(1);
    }
    memory = await snapshot();
    const expectedScene = ["finished", "10-shared.py", "11-audio.py"].includes(checkpoint) ? "Garden" : "Game";
    assert.equal(memory.runtime.currentScene, expectedScene);
    const frame = await runtime.call("ventilastation.browser", "export_frame", [true]);
    assert.ok(frame.vs2_scene instanceof Uint8Array);
    assert.ok(frame.vs2_scene.byteLength > 0);
    workerHostState.joy1 = 0x01; // Run gameplay and sprite updates under the same limit.
    await runtime.step(120);
    await runtime.exec(`
import sys
__vs_trace_calls = 0
def __vs_trace(frame, event, arg):
    global __vs_trace_calls
    if event == "call":
        __vs_trace_calls += 1
    return __vs_trace
def __vs_nested(n):
    if n == 0:
        return 0
    return 1 + __vs_nested(n - 1)
def __vs_raise(n):
    if n == 0:
        raise ValueError("trace-unwind")
    return __vs_raise(n - 1)
sys.settrace(__vs_trace)
assert __vs_nested(8) == 8
try:
    __vs_raise(8)
except ValueError:
    pass
else:
    raise AssertionError("nested exception was lost")
assert __vs_nested(8) == 8
sys.settrace(None)
assert __vs_trace_calls >= 8
`);
    await runtime.step(1);
    assert.ok((await snapshot()).gc.allocBytes > 0);
    console.log(`WASM small-stack startup and gameplay: ${checkpoint}`);
  } finally {
    rmSync(temp, { recursive: true, force: true });
  }
}
