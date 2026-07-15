// The editor's dependency-free zip writer (web/package-builder.js buildZip)
// must produce archives CPython's zipfile — and therefore the base's
// package_manager and the board's vszip — can read. Node runs the writer,
// CPython re-reads the archive and reports every member back.

import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { buildZip } from "../web/package-builder.js";

const PYTHON_READER = `
import json, sys, zipfile
archive = zipfile.ZipFile(sys.argv[1])
archive.testzip()  # verifies every member's CRC
members = []
for info in archive.infolist():
    members.append({
        "name": info.filename,
        "method": info.compress_type,
        "data_b64": __import__("base64").b64encode(archive.read(info)).decode(),
    })
print(json.dumps(members))
`;

function assert(condition, message) {
  if (!condition) {
    console.error(`FAIL: ${message}`);
    process.exit(1);
  }
}

const binary = new Uint8Array(20000);
for (let i = 0; i < binary.length; i += 1) {
  binary[i] = (i * 7 + 13) & 0xff;
}
const members = [
  { name: "meta.json", data: new TextEncoder().encode('{"title": "Test"}') },
  { name: "code/game.py", data: new TextEncoder().encode("def main():\n    return None\n") },
  { name: "roms/alecu.test.rom", data: binary },
  { name: "sounds/blip.mp3", data: new TextEncoder().encode("ID3 fake mp3"), store: true },
];

const zipBytes = await buildZip(members);

const python = ["python3", "python"].find(
  (name) => spawnSync(name, ["--version"]).status === 0);
if (!python) {
  console.log("SKIP: no python available to cross-check the archive");
  process.exit(0);
}

const dir = mkdtempSync(join(tmpdir(), "vszip-"));
try {
  const zipPath = join(dir, "package.vs2");
  writeFileSync(zipPath, zipBytes);
  const result = spawnSync(python, ["-c", PYTHON_READER, zipPath], { encoding: "utf8" });
  assert(result.status === 0, `python zipfile rejected the archive: ${result.stderr}`);
  const readBack = JSON.parse(result.stdout);

  assert(readBack.length === members.length, "member count mismatch");
  for (let i = 0; i < members.length; i += 1) {
    const expected = members[i];
    const actual = readBack[i];
    assert(actual.name === expected.name, `name mismatch: ${actual.name}`);
    const expectedMethod = expected.store ? 0 : 8;
    assert(actual.method === expectedMethod,
      `${actual.name}: method ${actual.method} != ${expectedMethod}`);
    const data = Buffer.from(actual.data_b64, "base64");
    assert(Buffer.from(expected.data).equals(data),
      `${actual.name}: content mismatch`);
  }
  console.log(`zip writer: ${members.length} members verified by ${python} zipfile`);
} finally {
  rmSync(dir, { recursive: true, force: true });
}
