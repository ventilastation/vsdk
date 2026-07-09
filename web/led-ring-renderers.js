// LED ring renderers for the web emulator: WebGL and 2D-canvas fallback
// (split out of app.js).

import {
  COLUMNS,
  PIXELS,
  createLedRingGeometry,
  DEFAULT_WEBGL_RESOLUTION_SCALE,
  fillRepeatedLedColors,
} from "./app-support.js?v=20260709a";


class LedRingWebGLRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.geometry = createLedRingGeometry();
    this.lastProfile = null;
    this.resolutionScale = DEFAULT_WEBGL_RESOLUTION_SCALE;
    this.displayWidth = canvas.clientWidth || 0;
    this.displayHeight = canvas.clientHeight || 0;
    this.lastDevicePixelRatio = null;
    this.gl = canvas.getContext("webgl", {
      alpha: true,
      antialias: false,
      premultipliedAlpha: false,
    });
    this.available = Boolean(this.gl);
    if (!this.available) {
      this.fallbackCtx = canvas.getContext("2d");
      return;
    }

    const gl = this.gl;
    this.blendMinMax = gl.getExtension("EXT_blend_minmax");
    this.program = this.createProgram(
      `
        attribute vec2 a_position;
        attribute vec2 a_texCoord;
        attribute vec4 a_color;
        uniform vec2 u_resolution;
        uniform vec2 u_center;
        uniform float u_scale;
        varying vec2 v_texCoord;
        varying vec4 v_color;

        void main() {
          vec2 pos = u_center + (a_position * vec2(1.0, -1.0) * u_scale);
          vec2 zeroToOne = pos / u_resolution;
          vec2 clip = zeroToOne * 2.0 - 1.0;
          gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
          v_texCoord = a_texCoord;
          v_color = a_color;
        }
      `,
      `
        precision mediump float;
        varying vec2 v_texCoord;
        varying vec4 v_color;

        void main() {
          vec2 center = vec2(0.5, 0.5);
          vec2 p = v_texCoord - center;
          float width = 0.1;
          float height = 0.05;
          float radius = height;
          vec2 q = abs(p) - vec2(width - radius, height - radius);
          float dist = length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - radius;
          float pill = smoothstep(0.01, -0.01, dist);
          float glow = exp(-dist * dist * 10.0) * 0.3;
          gl_FragColor = v_color * (pill + glow);
        }
      `
    );

    this.positionBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.positionBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, this.geometry.positions, gl.STATIC_DRAW);

    this.texCoordBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.texCoordBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, this.geometry.texCoords, gl.STATIC_DRAW);

    this.colorBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.colorBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, this.geometry.vertexCount * 4, gl.DYNAMIC_DRAW);
    this.colorBytes = new Uint8Array(this.geometry.vertexCount * 4);
    this.colorWords = new Uint32Array(this.colorBytes.buffer);

    this.attribs = {
      position: gl.getAttribLocation(this.program, "a_position"),
      texCoord: gl.getAttribLocation(this.program, "a_texCoord"),
      color: gl.getAttribLocation(this.program, "a_color"),
    };
    this.uniforms = {
      resolution: gl.getUniformLocation(this.program, "u_resolution"),
      center: gl.getUniformLocation(this.program, "u_center"),
      scale: gl.getUniformLocation(this.program, "u_scale"),
    };

    gl.enable(gl.BLEND);
    if (this.blendMinMax) {
      gl.blendFunc(gl.SRC_COLOR, gl.SRC_COLOR);
      gl.blendEquation(this.blendMinMax.MAX_EXT);
    } else {
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
    }
  }

  setDisplaySize(width, height) {
    this.displayWidth = Math.max(0, Number(width) || 0);
    this.displayHeight = Math.max(0, Number(height) || 0);
  }

  createShader(type, source) {
    const gl = this.gl;
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      throw new Error(gl.getShaderInfoLog(shader) || "WebGL shader compile failed");
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
      throw new Error(gl.getProgramInfoLog(program) || "WebGL program link failed");
    }
    return program;
  }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const scale = Number.isFinite(this.resolutionScale) && this.resolutionScale > 0
      ? this.resolutionScale
      : DEFAULT_WEBGL_RESOLUTION_SCALE;
    const width = Math.max(1, Math.round(this.displayWidth * dpr * scale));
    const height = Math.max(1, Math.round(this.displayHeight * dpr * scale));
    if (this.canvas.width !== width || this.canvas.height !== height || this.lastDevicePixelRatio !== dpr) {
      this.canvas.width = width;
      this.canvas.height = height;
      this.lastDevicePixelRatio = dpr;
    }
    if (this.gl) {
      this.gl.viewport(0, 0, width, height);
    }
    return { width, height, scale };
  }

  clear() {
    if (!this.gl) {
      return;
    }
    this.gl.clearColor(0.02, 0.03, 0.05, 1.0);
    this.gl.clear(this.gl.COLOR_BUFFER_BIT);
  }

  render(ledPixels) {
    if (!this.available) {
      this.lastProfile = null;
      return false;
    }

    const startedAt = performance.now();
    const { width, height, scale } = this.resize();
    const afterResizeAt = performance.now();
    const gl = this.gl;
    this.clear();
    const afterClearAt = performance.now();
    gl.useProgram(this.program);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.positionBuffer);
    gl.enableVertexAttribArray(this.attribs.position);
    gl.vertexAttribPointer(this.attribs.position, 2, gl.FLOAT, false, 0, 0);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.texCoordBuffer);
    gl.enableVertexAttribArray(this.attribs.texCoord);
    gl.vertexAttribPointer(this.attribs.texCoord, 2, gl.FLOAT, false, 0, 0);

    gl.bindBuffer(gl.ARRAY_BUFFER, this.colorBuffer);
    fillRepeatedLedColors(ledPixels, this.colorWords, 6);
    const afterColorExpandAt = performance.now();
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, this.colorBytes);
    const afterUploadAt = performance.now();
    gl.enableVertexAttribArray(this.attribs.color);
    gl.vertexAttribPointer(this.attribs.color, 4, gl.UNSIGNED_BYTE, true, 0, 0);

    gl.uniform2f(this.uniforms.resolution, width, height);
    gl.uniform2f(this.uniforms.center, width * 0.5, height * 0.5);
    gl.uniform1f(this.uniforms.scale, Math.min(width, height) / 200);
    gl.drawArrays(gl.TRIANGLES, 0, this.geometry.vertexCount);
    const finishedAt = performance.now();
    this.lastProfile = {
      resizeMs: afterResizeAt - startedAt,
      clearMs: afterClearAt - afterResizeAt,
      colorExpandMs: afterColorExpandAt - afterClearAt,
      uploadMs: afterUploadAt - afterColorExpandAt,
      drawSubmitMs: finishedAt - afterUploadAt,
      totalMs: finishedAt - startedAt,
      resolutionScale: scale,
      vertexCount: this.geometry.vertexCount,
      colorBytes: this.colorBytes.length,
    };
    return true;
  }
}

class LedRingCanvasRenderer {
  constructor(canvas, geometry) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.geometry = geometry;
    this.ledLayout = this.buildLedLayout();
    this.lastProfile = null;
    this.displayWidth = canvas.clientWidth || 0;
    this.displayHeight = canvas.clientHeight || 0;
    this.lastDevicePixelRatio = null;
  }

  setDisplaySize(width, height) {
    this.displayWidth = Math.max(0, Number(width) || 0);
    this.displayHeight = Math.max(0, Number(height) || 0);
  }

  buildLedLayout() {
    const positions = this.geometry.positions;
    const layout = new Array(COLUMNS * PIXELS);

    for (let column = 0; column < COLUMNS; column += 1) {
      for (let led = 0; led < PIXELS; led += 1) {
        const index = column * PIXELS + led;
        const vertexOffset = index * 12;
        const p0x = positions[vertexOffset];
        const p0y = positions[vertexOffset + 1];
        const p1x = positions[vertexOffset + 2];
        const p1y = positions[vertexOffset + 3];
        const p2x = positions[vertexOffset + 4];
        const p2y = positions[vertexOffset + 5];
        const p3x = positions[vertexOffset + 10];
        const p3y = positions[vertexOffset + 11];

        const centerX = (p0x + p1x + p2x + p3x) * 0.25;
        const centerY = (p0y + p1y + p2y + p3y) * 0.25;
        const angle = Math.atan2(-(p1y - p0y), p1x - p0x);
        const radius = Math.hypot(centerX, centerY);
        const widthWorld = (2 * Math.PI * radius) / COLUMNS;

        let rowSpacingWorld = 0;
        if (led + 1 < PIXELS) {
          const nextIndex = index + 1;
          const nextVertexOffset = nextIndex * 12;
          const np0x = positions[nextVertexOffset];
          const np0y = positions[nextVertexOffset + 1];
          const np1x = positions[nextVertexOffset + 2];
          const np1y = positions[nextVertexOffset + 3];
          const np2x = positions[nextVertexOffset + 4];
          const np2y = positions[nextVertexOffset + 5];
          const np3x = positions[nextVertexOffset + 10];
          const np3y = positions[nextVertexOffset + 11];
          const nextCenterX = (np0x + np1x + np2x + np3x) * 0.25;
          const nextCenterY = (np0y + np1y + np2y + np3y) * 0.25;
          rowSpacingWorld = Math.hypot(nextCenterX - centerX, nextCenterY - centerY);
        } else if (led > 0) {
          const prevIndex = index - 1;
          const prevVertexOffset = prevIndex * 12;
          const pp0x = positions[prevVertexOffset];
          const pp0y = positions[prevVertexOffset + 1];
          const pp1x = positions[prevVertexOffset + 2];
          const pp1y = positions[prevVertexOffset + 3];
          const pp2x = positions[prevVertexOffset + 4];
          const pp2y = positions[prevVertexOffset + 5];
          const pp3x = positions[prevVertexOffset + 10];
          const pp3y = positions[prevVertexOffset + 11];
          const prevCenterX = (pp0x + pp1x + pp2x + pp3x) * 0.25;
          const prevCenterY = (pp0y + pp1y + pp2y + pp3y) * 0.25;
          rowSpacingWorld = Math.hypot(centerX - prevCenterX, centerY - prevCenterY);
        }

        layout[index] = {
          centerX,
          centerY,
          angle,
          widthWorld,
          heightWorld: rowSpacingWorld * (2 / 3),
        };
      }
    }

    return layout;
  }

  resize() {
    const dpr = window.devicePixelRatio || 1;
    const width = Math.max(1, Math.round(this.displayWidth * dpr));
    const height = Math.max(1, Math.round(this.displayHeight * dpr));
    if (this.canvas.width !== width || this.canvas.height !== height || this.lastDevicePixelRatio !== dpr) {
      this.canvas.width = width;
      this.canvas.height = height;
      this.lastDevicePixelRatio = dpr;
    }
    return { width, height };
  }

  render(ledPixels) {
    if (!this.ctx) {
      this.lastProfile = null;
      return;
    }
    const startedAt = performance.now();
    const { width, height } = this.resize();
    const afterResizeAt = performance.now();
    const scale = Math.min(width, height) / 200;
    const ctx = this.ctx;
    ctx.clearRect(0, 0, width, height);
    ctx.fillStyle = "#05070b";
    ctx.fillRect(0, 0, width, height);

    let drawnLedCount = 0;

    for (let index = 0; index < this.ledLayout.length; index += 1) {
      const colorOffset = index * 4;
      const red = ledPixels[colorOffset];
      const green = ledPixels[colorOffset + 1];
      const blue = ledPixels[colorOffset + 2];
      const alpha = ledPixels[colorOffset + 3];
      if (!red && !green && !blue) {
        continue;
      }
      drawnLedCount += 1;

      const layout = this.ledLayout[index];
      const ledWidth = Math.max(0.35, layout.widthWorld * scale);
      const ledHeight = Math.max(0.16, layout.heightWorld * scale);
      const drawX = width * 0.5 + layout.centerX * scale;
      const drawY = height * 0.5 - layout.centerY * scale;

      ctx.save();
      ctx.translate(drawX, drawY);
      ctx.rotate(layout.angle);
      ctx.fillStyle = `rgba(${red}, ${green}, ${blue}, ${Math.max(alpha, 208) / 255})`;
      ctx.fillRect(-ledWidth * 0.5, -ledHeight * 0.5, ledWidth, ledHeight);
      ctx.restore();
    }

    const finishedAt = performance.now();
    this.lastProfile = {
      resizeMs: afterResizeAt - startedAt,
      drawMs: finishedAt - afterResizeAt,
      totalMs: finishedAt - startedAt,
      drawnLedCount,
    };
  }
}

export { LedRingWebGLRenderer, LedRingCanvasRenderer };
