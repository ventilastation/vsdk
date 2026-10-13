// Production native/WASM replay parity plus the real MicroPython worker bridge.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import { loadVentilagon } from '../web/ventilagon-native.js';

const root = fileURLToPath(new URL('../', import.meta.url));
const nativeModule = pathToFileURL(join(root, 'web/vendor/ventilagon/ventilagon.mjs')).href;
const nativeWasm = join(root, 'web/vendor/ventilagon/ventilagon.wasm');
const native = await loadVentilagon(nativeModule, nativeWasm);
const drain = () => { const lines = []; native.drainCommands(line => lines.push(line)); return lines; };
const reference = spawnSync(process.env.VSDK_TEST_PYTHON || 'python3',
  ['tests/test_ventilagon_parity.py', '--trace'], { cwd: root, encoding: 'utf8' });
assert.equal(reference.status, 0, reference.stderr);
const expected = JSON.parse(reference.stdout);
function replay() {
  native.enter(123);
  const records = [{ commands: drain() }];
  for (let step = 0; step < 200; step++) {
    const pixels = native.update(30000, Math.floor(step / 20) % 2 ? 2 : 1);
    const commands = drain();
    if (step % 20 === 0 || commands.length || step === 199) records.push({
      step, commands, idle: native.isIdle(), frame: createHash('sha256').update(pixels).digest('hex'),
    });
  }
  native.exit();
  records.push({ commands: drain(), idle: native.isIdle() });
  return records;
}
assert.deepEqual(replay(), expected);
assert.deepEqual(replay(), expected, 'seeded re-entry must reset WASM globals');
console.log('Ventilagon desktop/WASM frames, input, lifecycle and audio match');

const messages = [];
globalThis.self = {
  location: { href: 'https://fixture.invalid/emulator/wasm-worker.js' },
  addEventListener() {}, postMessage(message) { messages.push(message); },
};
globalThis.fetch = async input => {
  const url = new URL(String(input), self.location.href);
  assert.equal(url.origin, 'https://fixture.invalid');
  const data = readFileSync(resolve(root, 'web', url.pathname.replace(/^\/emulator\//u, '')));
  return { ok: true, json: async () => JSON.parse(data.toString()) };
};
const temp = mkdtempSync(join(tmpdir(), 'vsdk-ventilagon-worker-'));
try {
  const source = readFileSync(join(root, 'web/wasm-worker.js'), 'utf8')
    .replace(/from "\.\/vendor\/micropython\/micropython\.mjs[^"]*"/u,
      `from ${JSON.stringify(pathToFileURL(join(root, 'web/vendor/micropython/micropython.mjs')).href)}`)
    .replace('"./ventilagon-native.js"', JSON.stringify(pathToFileURL(join(root, 'web/ventilagon-native.js')).href));
  writeFileSync(join(temp, 'worker.mjs'), source + '\nexport { MicroPythonRuntime, workerHostState };\n');
  const { MicroPythonRuntime, workerHostState } = await import(pathToFileURL(join(temp, 'worker.mjs')).href);
  const runtime = new MicroPythonRuntime({
    fsRoot: '/games', pystack: 32 * 1024, heapsize: 8 * 1024 * 1024,
    micropythonWasmUrl: join(root, 'web/vendor/micropython/micropython.wasm'),
    ventilagonModuleUrl: nativeModule, ventilagonWasmUrl: nativeWasm,
    runtimeManifestUrl: './runtime-manifest.json', runtimeBundleUrl: './runtime-bundle.json',
    autostartSlug: 'alecu.ventilagon_game',
  });
  await runtime.initialize();
  const lastFrame = () => messages.filter(m => m.type === 'frame').at(-1)?.frame;
  const snapshot = () => runtime.call('ventilastation.browser', 'memory_snapshot', [true]);
  async function enterGame() {
    workerHostState.joy1 = 0;
    await runtime.step(1);
    workerHostState.joy1 = 16;
    await runtime.step(1);
    workerHostState.joy1 = 2;
    await runtime.step(1);
    assert.equal((await snapshot()).runtime.currentScene, 'VentilagonGame');
    const rgb = lastFrame().events.find(e => e.command === 'frame_rgb');
    assert.equal(rgb.data.length, 256 * 54 * 3);
    assert.ok(rgb.data.some(value => value !== 0));
    assert.ok(!lastFrame().events.some(e => e.command === 'sprites' || e.command === 'vs2_scene'));
  }
  async function exitGame() {
    workerHostState.joy1 = 0;
    workerHostState.extra = 1; // Joy1 Y (BUTTON_D)
    await runtime.step(1);
    workerHostState.extra = 0;
    await runtime.step(1);
    assert.equal((await snapshot()).runtime.currentScene, 'VentilagonIdle');
    assert.ok(lastFrame().events.some(e => e.command === 'sprites'));
    assert.ok(!lastFrame().events.some(e => e.command === 'frame_rgb'));
  }
  await enterGame();
  await runtime.step(100);
  messages.length = 0;
  const before = (await snapshot()).gc.allocBytes;
  const start = performance.now();
  for (let batch = 0; batch < 20; batch++) {
    await runtime.step(100);
    messages.length = 0;
  }
  const stepMs = (performance.now() - start) / 2000;
  const after = (await snapshot()).gc.allocBytes;
  // Cross-language frame traffic must not retain new Python objects each step.
  assert.ok(after - before < 4096, `post-GC heap grew ${after - before} bytes`);
  await exitGame();
  const exited = (await snapshot()).gc.allocBytes;
  for (let i = 0; i < 5; i++) {
    await enterGame();
    await runtime.step(20);
    await exitGame();
    messages.length = 0;
  }
  const reentered = (await snapshot()).gc.allocBytes;
  assert.ok(reentered - exited < 4096, `entry/exit leaked ${reentered - exited} bytes`);
  console.log(`Ventilagon real worker: ${stepMs.toFixed(2)} ms/step; heap delta ${after - before} B; entry/exit delta ${reentered - exited} B`);
  if (process.argv.includes('--soak')) {
    const baseline = (await snapshot()).gc.allocBytes;
    for (let window = 0; window < 2; window++) {
      const until = performance.now() + 30000;
      while (performance.now() < until) {
        // Keep the idle scene from switching to Gallery after 45 seconds.
        // Gallery intentionally loads another asset bank, not a heap leak.
        workerHostState.joy1 = Math.floor(performance.now() / 1000) % 2 ? 1 : 2;
        await runtime.step(1);
        messages.length = 0;
        await new Promise(resolve => setTimeout(resolve, 30));
      }
      const memory = await snapshot();
      assert.equal(memory.runtime.currentScene, 'VentilagonIdle');
      const used = memory.gc.allocBytes;
      assert.ok(used - baseline < 4096, `idle soak heap grew ${used - baseline} bytes`);
      console.log(`Ventilagon 30-second idle soak ${window + 1}: post-GC heap delta ${used - baseline} B`);
    }
  }
} finally {
  rmSync(temp, { recursive: true, force: true });
}
