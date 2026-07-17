// The WebGL2 half of the emulator renderer. It translates the compact wire
// scene into integer textures and lets scene-shader-core's fragment shader
// write the complete 256-column LED frame into the ring renderer's texture.

import "./scene-shader-core.js?v=20260717a";

const SceneShaderCore = globalThis.VentilastationSceneShaderCore;

if (!SceneShaderCore) {
  throw new Error("Missing VentilastationSceneShaderCore");
}

const { COLUMNS, PIXELS, packDeepspace, packPalette, packSceneLegacy, packSceneVs2,
  packStars, computeStarPositions, packStrips, buildSceneVertexSource,
  buildSceneFragmentSource } = SceneShaderCore;

class LedSceneWebGLCompositor {
  constructor(gl, ledColorTexture) {
    this.gl = gl;
    this.ledColorTexture = ledColorTexture;
    this.available = false;
    this.lastProfile = null;
    this.assetVersion = null;
    this.paletteVersion = null;

    try {
      this.program = this.createProgram(
        buildSceneVertexSource({ es: true }),
        buildSceneFragmentSource({ es: true }),
      );
      this.quadBuffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, this.quadBuffer);
      // One oversized triangle covers the LED frame without an index buffer.
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([
        -1, -1,
        3, -1,
        -1, 3,
      ]), gl.STATIC_DRAW);

      this.textures = {
        strips: this.createTexture(),
        stripMeta: this.createTexture(),
        palette: this.createTexture(),
        scene: this.createTexture(),
        cells: this.createTexture(),
        stars: this.createTexture(),
        deepspace: this.createTexture(),
      };
      this.framebuffer = gl.createFramebuffer();
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.framebuffer);
      gl.framebufferTexture2D(
        gl.FRAMEBUFFER,
        gl.COLOR_ATTACHMENT0,
        gl.TEXTURE_2D,
        this.ledColorTexture,
        0,
      );
      if (gl.checkFramebufferStatus(gl.FRAMEBUFFER) !== gl.FRAMEBUFFER_COMPLETE) {
        throw new Error("Scene render target is incomplete");
      }
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);

      this.uniforms = {
        strips: gl.getUniformLocation(this.program, "u_strips"),
        stripMeta: gl.getUniformLocation(this.program, "u_strip_meta"),
        palette: gl.getUniformLocation(this.program, "u_palette"),
        scene: gl.getUniformLocation(this.program, "u_scene"),
        cells: gl.getUniformLocation(this.program, "u_cells"),
        stars: gl.getUniformLocation(this.program, "u_stars"),
        deepspace: gl.getUniformLocation(this.program, "u_deepspace"),
        spriteCount: gl.getUniformLocation(this.program, "u_sprite_count"),
        tilemapCount: gl.getUniformLocation(this.program, "u_tilemap_count"),
        starCount: gl.getUniformLocation(this.program, "u_star_count"),
        columnOffset: gl.getUniformLocation(this.program, "u_column_offset"),
        ledAxis: gl.getUniformLocation(this.program, "u_led_axis"),
      };
      this.uploadIntegerTexture(
        this.textures.deepspace,
        packDeepspace(),
        gl.R32UI,
        gl.RED_INTEGER,
        gl.UNSIGNED_INT,
      );
      this.available = true;
    } catch (error) {
      this.error = error;
      console.warn("GPU scene compositor unavailable", error);
    }
  }

  createTexture() {
    const gl = this.gl;
    const texture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    return texture;
  }

  createShader(type, source) {
    const gl = this.gl;
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(shader) || "Scene shader compilation failed");
    }
    return shader;
  }

  createProgram(vertexSource, fragmentSource) {
    const gl = this.gl;
    const program = gl.createProgram();
    gl.attachShader(program, this.createShader(gl.VERTEX_SHADER, vertexSource));
    gl.attachShader(program, this.createShader(gl.FRAGMENT_SHADER, fragmentSource));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program) || "Scene shader link failed");
    }
    return program;
  }

  uploadIntegerTexture(texture, packed, internalFormat, format, type) {
    const gl = this.gl;
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.texImage2D(
      gl.TEXTURE_2D,
      0,
      internalFormat,
      packed.width,
      packed.height,
      0,
      format,
      type,
      packed.data || packed.atlas || packed.meta || packed.scene || packed.cells,
    );
  }

  uploadAssets(input) {
    if (this.assetVersion === input.assetVersion) {
      return;
    }
    const gl = this.gl;
    const strips = packStrips(input.assetIndex || new Map());
    this.uploadIntegerTexture(this.textures.strips, {
      width: strips.width,
      height: strips.height,
      data: strips.atlas,
    }, gl.R8UI, gl.RED_INTEGER, gl.UNSIGNED_BYTE);
    this.uploadIntegerTexture(this.textures.stripMeta, {
      width: 256,
      height: 1,
      data: strips.meta,
    }, gl.RGBA32UI, gl.RGBA_INTEGER, gl.UNSIGNED_INT);
    this.assetVersion = input.assetVersion;
  }

  uploadPalette(input) {
    if (this.paletteVersion === input.paletteVersion) {
      return;
    }
    const gl = this.gl;
    const palette = packPalette(input.palette);
    gl.bindTexture(gl.TEXTURE_2D, this.textures.palette);
    gl.texImage2D(
      gl.TEXTURE_2D,
      0,
      gl.RGBA8,
      palette.width,
      palette.height,
      0,
      gl.RGBA,
      gl.UNSIGNED_BYTE,
      palette.data,
    );
    this.paletteVersion = input.paletteVersion;
  }

  bindTexture(unit, texture, uniform) {
    const gl = this.gl;
    gl.activeTexture(gl.TEXTURE0 + unit);
    gl.bindTexture(gl.TEXTURE_2D, texture);
    gl.uniform1i(uniform, unit);
  }

  render(input) {
    if (!this.available || !input?.sceneBytes) {
      this.lastProfile = null;
      return false;
    }
    const gl = this.gl;
    const startedAt = performance.now();
    this.uploadAssets(input);
    this.uploadPalette(input);
    const afterStaticUploadAt = performance.now();

    const scene = input.sceneKind === "vs2"
      ? packSceneVs2(input.sceneBytes)
      : packSceneLegacy(input.sceneBytes);
    const stars = packStars(computeStarPositions(input.frameNumber));
    const afterPackAt = performance.now();
    this.uploadIntegerTexture(this.textures.scene, {
      width: scene.sceneWidth,
      height: scene.sceneHeight,
      data: scene.scene,
    }, gl.RGBA32UI, gl.RGBA_INTEGER, gl.UNSIGNED_INT);
    this.uploadIntegerTexture(this.textures.cells, {
      width: scene.cellsWidth,
      height: scene.cellsHeight,
      data: scene.cells,
    }, gl.R8UI, gl.RED_INTEGER, gl.UNSIGNED_BYTE);
    this.uploadIntegerTexture(this.textures.stars, stars, gl.R32UI, gl.RED_INTEGER, gl.UNSIGNED_INT);
    const afterDynamicUploadAt = performance.now();

    gl.bindFramebuffer(gl.FRAMEBUFFER, this.framebuffer);
    gl.viewport(0, 0, PIXELS, COLUMNS);
    gl.disable(gl.BLEND);
    gl.useProgram(this.program);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quadBuffer);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    this.bindTexture(0, this.textures.strips, this.uniforms.strips);
    this.bindTexture(1, this.textures.stripMeta, this.uniforms.stripMeta);
    this.bindTexture(2, this.textures.palette, this.uniforms.palette);
    this.bindTexture(3, this.textures.scene, this.uniforms.scene);
    this.bindTexture(4, this.textures.cells, this.uniforms.cells);
    this.bindTexture(5, this.textures.stars, this.uniforms.stars);
    this.bindTexture(6, this.textures.deepspace, this.uniforms.deepspace);
    gl.uniform1i(this.uniforms.spriteCount, scene.spriteCount);
    gl.uniform1i(this.uniforms.tilemapCount, scene.tilemapCount);
    gl.uniform1i(this.uniforms.starCount, stars.count);
    gl.uniform1i(this.uniforms.columnOffset, Number(input.columnOffset || 0) & 255);
    gl.uniform1i(this.uniforms.ledAxis, 0);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    const finishedAt = performance.now();
    this.lastProfile = {
      staticUploadMs: afterStaticUploadAt - startedAt,
      packMs: afterPackAt - afterStaticUploadAt,
      dynamicUploadMs: afterDynamicUploadAt - afterPackAt,
      drawSubmitMs: finishedAt - afterDynamicUploadAt,
      totalMs: finishedAt - startedAt,
      sceneKind: input.sceneKind,
      spriteCount: scene.spriteCount,
      tilemapCount: scene.tilemapCount,
      sceneBytes: input.sceneBytes.length,
    };
    return true;
  }

  readPixels() {
    if (!this.available) {
      return null;
    }
    const gl = this.gl;
    const pixels = new Uint8Array(PIXELS * COLUMNS * 4);
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.framebuffer);
    gl.readPixels(0, 0, PIXELS, COLUMNS, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return pixels;
  }

  readPaletteEntry(paletteIndex, colorIndex) {
    if (!this.available) {
      return null;
    }
    const gl = this.gl;
    const pixel = new Uint8Array(4);
    gl.bindFramebuffer(gl.FRAMEBUFFER, this.framebuffer);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.textures.palette, 0);
    gl.readPixels(colorIndex, paletteIndex, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, pixel);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, this.ledColorTexture, 0);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return pixel;
  }
}

export { LedSceneWebGLCompositor };
