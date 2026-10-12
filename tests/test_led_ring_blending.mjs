// WebGL2 exposes MAX in core even when EXT_blend_minmax is unavailable.
// Exercise renderer initialization with each supported context capability.
import assert from "node:assert/strict";
import { copyFileSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

globalThis.window = { location: { href: "http://localhost/emulator/" } };
createRequire(import.meta.url)("../web/led-render-core.js");
const directory = mkdtempSync(join(tmpdir(), "vsdk-ring-blending-"));
try {
  // Load the browser ES modules unchanged, including their versioned imports.
  writeFileSync(join(directory, "package.json"), '{"type":"module"}');
  for (const name of ["led-ring-renderers.js", "app-support.js",
    "scene-webgl-compositor.js", "scene-shader-core.js"]) {
    copyFileSync(new URL(`../web/${name}`, import.meta.url), join(directory, name));
  }
  const { LedRingWebGLRenderer } = await import(
    pathToFileURL(join(directory, "led-ring-renderers.js")).href);
  // Shader compilation is covered separately; this check observes GL state.
  LedRingWebGLRenderer.prototype.createProgram = () => ({});

  class Context {
    BLEND = 0x0BE2;
    MAX = 0x8008;
    SRC_COLOR = 0x0300;
    SRC_ALPHA = 0x0302;
    ONE = 1;
    equation = 0x8006; // Default FUNC_ADD.
    constructor(extension) { this.extension = extension; }
    getExtension(name) {
      assert.equal(name, "EXT_blend_minmax");
      return this.extension;
    }
    createBuffer() { return {}; }
    bindBuffer() {}
    bufferData() {}
    createTexture() { return {}; }
    bindTexture() {}
    texParameteri() {}
    texImage2D() {}
    getAttribLocation() { return 0; }
    getUniformLocation() { return {}; }
    enable(value) { assert.equal(value, this.BLEND); }
    blendFunc(source, destination) { this.factors = [source, destination]; }
    blendEquation(value) { this.equation = value; }
  }
  class Context2 extends Context {}
  globalThis.WebGL2RenderingContext = Context2;

  for (const [webgl2, extension] of [
    [true, null], [true, { MAX_EXT: 0x8008 }],
    [false, { MAX_EXT: 0x8008 }], [false, null],
  ]) {
    const gl = webgl2 ? new Context2(extension) : new Context(extension);
    const renderer = new LedRingWebGLRenderer({
      clientWidth: 320, clientHeight: 320,
      getContext: (kind) => kind === (webgl2 ? "webgl2" : "webgl") ? gl : null,
    });
    assert.equal(renderer.available, true);
    assert.equal(renderer.isWebGL2, webgl2);
    const maxSupported = webgl2 || Boolean(extension);
    assert.equal(gl.equation, maxSupported ? gl.MAX : 0x8006);
    assert.deepEqual(gl.factors, maxSupported
      ? [gl.SRC_COLOR, gl.SRC_COLOR] : [gl.SRC_ALPHA, gl.ONE]);
  }
  console.log("LED ring blending tests passed");
} finally {
  rmSync(directory, { recursive: true, force: true });
}
