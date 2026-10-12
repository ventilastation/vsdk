import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const source = readFileSync(new URL("../web/launch-options.js", import.meta.url), "utf8");
const { launchConfiguration } = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));
const base = "https://example.org/preview/emulator/";
assert.deepEqual(await launchConfiguration(base), {});
assert.deepEqual(await launchConfiguration(base + "?game=demos.dream_garden"), {autostartSlug: "demos.dream_garden"});
let requested;
const config = await launchConfiguration(base + "?game=demos.dream_garden&checkpoint=01-steering", async (url) => {
  requested = url.href;
  return {ok: true, text: async () => "def main(): pass"};
});
assert.equal(requested, base + "games/demos/dream_garden/code/checkpoints/01-steering.py");
assert.deepEqual(config.workspaceFiles, [{path: "games/demos/dream_garden/code/dream_garden.py", content: "def main(): pass", encoding: "utf8"}]);
for (const query of ["?checkpoint=01-steering", "?game=../foo", "?game=demos.dream_garden&checkpoint=../evil", "?game=demos.dream_garden&checkpoint=https://evil.org/code"]) {
  await assert.rejects(launchConfiguration(base + query, () => {throw new Error("must not fetch")}), /Invalid/);
}
await assert.rejects(launchConfiguration(base + "?game=demos.dream_garden&checkpoint=missing", async () => ({ok:false,status:404})), /could not be loaded \(404\)/);
console.log("Game links and checkpoints stay in the published emulator tree; invalid or missing code fails clearly.");
