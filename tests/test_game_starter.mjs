import assert from "node:assert/strict";
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { spawnSync } from "node:child_process";

const source = readFileSync(new URL("../web/game-starter.js", import.meta.url), "utf8");
const { createGameFiles } = await import(
  "data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const files = createGameFiles({ key: "games/newdev/my_game", slug: "my_game" }, "MyGame");
const meta = JSON.parse(files["games/newdev/my_game/meta.json"]);
assert.deepEqual(meta, { api: "vs2", api_revision: 2, title: "my_game" });
assert.ok(files["games/newdev/my_game/images/__images__.yaml"]);
const code = files["games/newdev/my_game/code/my_game.py"];
const temp = mkdtempSync(join(tmpdir(), "vsdk-new-game-"));
try {
  const path = join(temp, "my_game.py");
  writeFileSync(path, code);
  // Compile what a visitor actually receives, not a handwritten copy of it.
  const result = spawnSync("mpy-cross", [path], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr || String(result.error));
  assert.match(code, /class MyGame\(vs2.Scene\)/u);
  assert.match(code, /def build\(self\)/u);
  assert.match(code, /def update\(self\)/u);
  assert.doesNotMatch(code, /ventilastation\.scene|stripes_rom|def step/u);
} finally {
  rmSync(temp, { recursive: true, force: true });
}
console.log("Browser New Game produces compilable VS2 revision-2 code and metadata.");
