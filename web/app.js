// Web emulator host application. Rendering, audio and shared helpers live
// in led-ring-renderers.js, audio-host.js and app-support.js.

import {
  BUTTONS,
  INPUT_EXTRA,
  keyboardInputForCode,
  keyboardInputForCodes,
  EXIT_KEY_CODES,
  mapGamepadInput,
  computeLedFramePixels,
  computeLedFramePixelsFromRgb,
  FORCE_2D_STORAGE_KEY,
  INVERT_GAMEPAD_Y_STORAGE_KEY,
  INSPECTOR_OPEN_STORAGE_KEY,
  EDITOR_OPEN_STORAGE_KEY,
  RENDERER_PROFILING_STORAGE_KEY,
  WEBGL_RESOLUTION_SCALE_STORAGE_KEY,
  SCENE_RENDERER_STORAGE_KEY,
  SCENE_STEP_MS,
  MAX_CATCH_UP_STEPS,
  MAX_TICK_BACKLOG_MS,
  TOUCH_STICK_DEAD_ZONE,
  FPS_DISPLAY_INTERVAL_MS,
  RENDER_PROFILE_SAMPLE_LIMIT,
  MEMORY_SNAPSHOT_HISTORY_LIMIT,
  TRACE_FLAGS,
  WEBGL_RESOLUTION_SCALE_AUTO,
  DEFAULT_WEBGL_RESOLUTION_SCALE,
  WEBGL_RESOLUTION_SCALES,
  WEBGL_AUTO_SCALE_MIN_FPS,
  WEBGL_AUTO_SCALE_WAIT_MS,
  MEMORY_FRAME_REFRESH_STORAGE_KEY,
  isEditableEventTarget,
  formatProfileMs,
  formatBytes,
  buildRenderProfileSnapshot,
  decodeSpriteStateBuffer,
  decodeVs2SceneBuffer,
  decodeImageStripPayload,
} from "./app-support.js?v=20260717b";

import { BrowserAudioHost } from "./audio-host.js?v=20260709a";
import { LedRingWebGLRenderer, LedRingCanvasRenderer } from "./led-ring-renderers.js?v=20260720g";
import { RemoteWorkbenchAdapter, isRemoteMode } from "./remote-adapter.js?v=20260722a";


class FailedRuntimeAdapter {
  constructor() {
    this.name = "Runtime unavailable";
    this.usesWorkerFrameStream = false;
  }

  setButtons(_buttons) {
    return;
  }

  setInput(_joy1, _joy2, _extra, _exit) {
    return;
  }
}

class BrowserHostApp {
  constructor(runtime) {
    this.adapter = runtime.adapter;
    this.runtime = runtime;
    this.executionError = this.extractProminentError(runtime.error);
    this.currentButtons = 0;
    this.keyboardInput = { joy1: 0, joy2: 0, extra: 0 };
    this.keyboardCodes = new Set();
    this.touchButtons = 0;
    this.touchInput = { joy1: 0, joy2: 0, extra: 0 };
    this.gamepadInput = { joy1: 0, joy2: 0, extra: 0, exit: false };
    this.currentInput = { joy1: 0, joy2: 0, extra: 0 };
    this.keyboardExitPressed = false;
    this.exitPressed = false;
    this.activeGamepadIndex = null;
    this.connectedGamepadCount = 0;
    this.assetIndex = new Map();
    this.assetVersion = 0;
    this.assetRenderCache = new Map();
    this.visibleStripSlots = [];
    this.palette = null;
    this.paletteVersion = 0;
    this.paletteUploadVersion = 0;
    this.paletteLoadedBytes = 0;
    this.lastFrame = null;
    this.lastFrameShape = null;
    this.lastMemorySnapshot = null;
    this.lastCollectedMemorySnapshot = null;
    this.lastMemorySnapshotAt = 0;
    this.memorySnapshotHistory = [];
    this.lastMemoryScene = null;
    this.memorySnapshotPending = null;
    this.traceFlags = 0;
    this.lastRenderedLedPixels = null;
    this.lastRenderAt = null;
    this.displayedFps = null;
    this.pendingMinFps = null;
    this.lastFpsDisplayUpdateAt = null;
    this.renderProfileSamples = [];
    this.fullscreenRenderProfileSamples = [];
    this.lastFullscreenRenderProfile = null;
    this.baseControl = { rgb: [0, 0, 0], servo: 0, mask: 0, blinkMs: 0 };
    this.lastCanvasClientSize = null;
    this.lastAppliedCanvasClientSize = null;
    this.canvasDisplaySize = { width: 0, height: 0 };
    this.fallbackCanvasDisplaySize = { width: 0, height: 0 };
    this.isFullscreen = false;
    this.lowFpsSinceAt = null;
    this.diagnostics = [];
    this.audio = new BrowserAudioHost({
      readProjectFile: (path, encoding = "utf8") => this.readProjectFile(path, encoding),
    });
    // Remote H.264 frames are decoded straight into the WebGL LED texture;
    // there is intentionally no JS readback path for the 2D renderer.
    this.force2dFallback = runtime.source === "remote" ? false : this.readForce2dPreference();
    this.invertGamepadY = this.readInvertGamepadYPreference();
    this.rendererProfiling = this.readRendererProfilingPreference();
    this.sceneRendererMode = this.readSceneRendererPreference();
    this.lastRendererComparison = null;
    this.rendererComparisonRunning = false;
    this.webglResolutionScalePreference = this.readWebglResolutionScalePreference();
    this.webglResolutionScale = this.webglResolutionScalePreference === WEBGL_RESOLUTION_SCALE_AUTO
      ? DEFAULT_WEBGL_RESOLUTION_SCALE
      : this.webglResolutionScalePreference;
    this.inspectorOpen = this.readInspectorPreference();
    this.editorOpen = this.readEditorPreference();
    this.lastSceneTickAt = null;
    this.pollRequestId = null;
    this.pollingHalted = false;
    this.touchStickPointerId = null;
    this.unsubscribeWorkerFrame = null;
    this.unsubscribeWorkerRuntimeError = null;
    this.canvasResizeObserver = null;
    this.mobileLayoutQuery = typeof window.matchMedia === "function"
      ? window.matchMedia("(max-width: 980px) and (pointer: coarse)")
      : null;
    this.appShell = document.querySelector(".app-shell");
    this.stagePanel = document.querySelector(".stage-panel");
    this.editorPanelShell = document.querySelector("#editor-panel-shell");
    this.canvas = document.querySelector("#frame-canvas-gl");
    this.fallbackCanvas = document.querySelector("#frame-canvas-2d");
    this.renderer = new LedRingWebGLRenderer(this.canvas);
    this.renderer.resolutionScale = this.webglResolutionScale;
    this.fallbackRenderer = new LedRingCanvasRenderer(this.fallbackCanvas, this.renderer.geometry);
    this.elements = {
      adapterName: document.querySelector("#adapter-name"),
      adapterSource: document.querySelector("#adapter-source"),
      frameCounter: document.querySelector("#frame-counter"),
      buttonMask: document.querySelector("#button-mask"),
      gamepadStatus: document.querySelector("#gamepad-status"),
      webglScaleStatus: document.querySelector("#webgl-scale-status"),
      sceneErrorBanner: document.querySelector("#scene-error-banner"),
      sceneErrorTitle: document.querySelector("#scene-error-title"),
      sceneErrorMessage: document.querySelector("#scene-error-message"),
      sceneErrorDebugButton: document.querySelector("#scene-error-debug-button"),
      toggleFullscreenButton: document.querySelector("#toggle-fullscreen-button"),
      toggleEditorButton: document.querySelector("#toggle-editor-button"),
      touchStick: document.querySelector("#touch-stick"),
      touchStickKnob: document.querySelector("#touch-stick-knob"),
      touchButtons: Array.from(document.querySelectorAll("[data-touch-channel], [data-touch-button]")),
      runtimeBanner: document.querySelector("#runtime-banner"),
      runtimeMessage: document.querySelector("#runtime-message"),
      inspectorPanel: document.querySelector("#inspector-panel"),
      toggleInspectorButton: document.querySelector("#toggle-inspector-button"),
      remoteConnectButton: document.querySelector("#remote-connect-button"),
      remoteControlButton: document.querySelector("#remote-control-button"),
      remoteResetButton: document.querySelector("#remote-reset-button"),
      remoteRpmControl: document.querySelector("#remote-rpm-control"),
      remoteRpm: document.querySelector("#remote-rpm"),
      remoteStatus: document.querySelector("#remote-status"),
      copyDiagnostics: document.querySelector("#copy-diagnostics"),
      copyDiagnosticsButton: document.querySelector("#copy-diagnostics-button"),
      copyDiagnosticsStatus: document.querySelector("#copy-diagnostics-status"),
      runtimeSummary: document.querySelector("#runtime-summary"),
      memorySummary: document.querySelector("#memory-summary"),
      collectMemoryButton: document.querySelector("#collect-memory-button"),
      refreshMemoryEveryFrame: document.querySelector("#refresh-memory-every-frame"),
      force2dFallback: document.querySelector("#force-2d-fallback"),
      invertGamepadY: document.querySelector("#invert-gamepad-y"),
      enableRendererProfiling: document.querySelector("#enable-renderer-profiling"),
      sceneRendererMode: document.querySelector("#scene-renderer-mode"),
      sceneRendererStatus: document.querySelector("#scene-renderer-status"),
      runRendererComparison: document.querySelector("#run-renderer-comparison"),
      rendererComparison: document.querySelector("#renderer-comparison"),
      webglResolutionScale: document.querySelector("#webgl-resolution-scale"),
      basePreviewStrip: document.querySelector("#base-preview-strip"),
      basePreviewDial: document.querySelector("#base-preview-dial"),
      basePreviewServo: document.querySelector("#base-preview-servo i"),
      basePreviewButton1: document.querySelector("#base-preview-button-1"),
      basePreviewButton2: document.querySelector("#base-preview-button-2"),
      traceFlagControls: Array.from(document.querySelectorAll("[data-trace-flag]")),
    };
    this.copyStatusTimer = null;
    this.refreshMemoryEveryFrame = this.readBooleanPreference(MEMORY_FRAME_REFRESH_STORAGE_KEY, false);
    this.refreshCopyDiagnostics();
  }

  extractProminentError(error) {
    if (!error) {
      return null;
    }

    const sourceText = String(error.message || error.stack || error).trim();
    if (!sourceText) {
      return null;
    }

    const isSceneLifecycleError =
      sourceText.startsWith("Scene lifecycle error") ||
      /Scene\.(step|on_enter|on_exit) failed/u.test(sourceText);
    if (!isSceneLifecycleError) {
      return null;
    }

    return {
      title: "Scene lifecycle error",
      message: sourceText.replace(/^Scene lifecycle error\s*/u, "").trim(),
      isSceneLifecycleError: true,
    };
  }

  usesEventStreamProtocol(frame) {
    return Array.isArray(frame?.events) && frame.events.some((event) => (
      event &&
      typeof event === "object" &&
      (event.command === "palette" || event.command === "imagestrip" ||
        event.command === "sprites" || event.command === "vs2_scene" ||
        event.command === "frame_rgb")
    ));
  }

  processFrameEvents(frame) {
    if (!Array.isArray(frame.events) || !frame.events.length) {
      if (!Array.isArray(frame.sprites)) {
        frame.sprites = [];
      }
      if (!Array.isArray(frame.assets)) {
        frame.assets = [];
      }
      return;
    }

    let decodedSprites = null;
    let decodedVs2Scene = null;
    let legacySceneBytes = null;
    let vs2SceneBytes = null;
    const remainingEvents = [];

    for (const event of frame.events) {
      if (!event || typeof event !== "object") {
        continue;
      }
      if (event.command === "sound") {
        this.audio.playSound((event.args || []).join(" "));
        continue;
      }
      if (event.command === "music") {
        // "music <track> [loop]" — the optional loop flag repeats the track.
        const args = event.args || [];
        this.audio.playMusic(args[0] || "off", args.includes("loop"));
        continue;
      }
      if (event.command === "musicstop") {
        this.audio.playMusic("off", false);
        continue;
      }
      if (event.command === "notes") {
        const folder = event.args?.[0] || "";
        const notes = event.args?.[1] || "";
        this.audio.playNotes(folder, notes);
        continue;
      }
      if (event.command === "base") {
        this.applyBaseControl(event.args || []);
        continue;
      }
      if (event.command === "palette" && event.data instanceof Uint8Array) {
        this.palette = event.data;
        this.paletteLoadedBytes = event.data.length;
        this.paletteVersion += 1;
        this.paletteUploadVersion += 1;
        this.assetRenderCache.clear();
        continue;
      }
      if (event.command === "imagestrip" && event.data instanceof Uint8Array) {
        const slot = Number(event.args?.[0] ?? -1);
        const asset = decodeImageStripPayload(slot, event.data);
        if (asset) {
          this.assetIndex.set(slot, asset);
          this.assetVersion += 1;
          this.assetRenderCache.delete(slot);
        }
        continue;
      }
      if (event.command === "sprites" && event.data instanceof Uint8Array) {
        if (decodedVs2Scene === null) {
          decodedSprites = decodeSpriteStateBuffer(event.data);
          legacySceneBytes = event.data;
        }
        continue;
      }
      if (event.command === "vs2_scene" && event.data instanceof Uint8Array) {
        decodedVs2Scene = decodeVs2SceneBuffer(event.data);
        decodedSprites = decodedVs2Scene.sprites;
        vs2SceneBytes = event.data;
        legacySceneBytes = null;
        continue;
      }
      if (event.command === "frame_rgb" && event.data instanceof Uint8Array) {
        // Raw polar framebuffer (Super Ventilagon / Voom): drawn directly, no sprites.
        frame.povFrameRgb = event.data;
        continue;
      }
      remainingEvents.push(event);
    }

    frame.sprites = decodedSprites || [];
    frame.tilemaps = decodedVs2Scene ? decodedVs2Scene.tilemaps : [];
    frame.vs2Scene = decodedVs2Scene;
    frame.sceneKind = vs2SceneBytes ? "vs2" : legacySceneBytes ? "legacy" : null;
    frame.sceneBytes = vs2SceneBytes || legacySceneBytes;
    frame.assets = [];
    frame.events = remainingEvents;
  }

  applyBaseControl(args) {
    const values = args.map((value) => Number(value));
    if (args[0] === "leds" && values.length === 4 && values.slice(1).every((value) => Number.isInteger(value) && value >= 0 && value <= 255)) {
      this.baseControl.rgb = values.slice(1);
    } else if (args[0] === "servo" && values.length === 2 && Number.isInteger(values[1]) && values[1] >= 0 && values[1] <= 255) {
      this.baseControl.servo = values[1];
    } else if (args[0] === "buttons" && values.length === 3 && Number.isInteger(values[1]) && values[1] >= 0 && values[1] <= 3 && Number.isInteger(values[2]) && values[2] >= 0 && values[2] <= 10000) {
      this.baseControl.mask = values[1];
      this.baseControl.blinkMs = values[2] ? Math.max(100, values[2]) : 0;
    } else {
      return;
    }
    this.renderBasePreview();
  }

  renderBasePreview() {
    const [red, green, blue] = this.baseControl.rgb.map((value) => Math.round(255 * (value / 255) ** 2.2));
    const dialRgb = [red, green, blue].map((value) => Math.round(34 + value * 221 / 255));
    if (this.elements.basePreviewStrip) {
      this.elements.basePreviewStrip.style.backgroundColor = `rgb(${red}, ${green}, ${blue})`;
      this.elements.basePreviewStrip.style.boxShadow = `0 0 11px rgba(${red}, ${green}, ${blue}, .8)`;
    }
    if (this.elements.basePreviewDial) {
      this.elements.basePreviewDial.style.setProperty("--base-dial-color", `rgb(${dialRgb.join(", ")})`);
      this.elements.basePreviewDial.style.setProperty("--base-dial-glow", `rgba(${dialRgb.join(", ")}, .72)`);
      this.elements.basePreviewDial.style.setProperty("--base-dial-text-glow", `rgb(${dialRgb.join(", ")})`);
    }
    if (this.elements.basePreviewServo) {
      // Preview orientation: 0 = left, midpoint = top, 255 = right.
      this.elements.basePreviewServo.style.transform = `rotate(${220 + (this.baseControl.servo * 100 / 255)}deg)`;
    }
    const phase = !this.baseControl.blinkMs || (Date.now() % this.baseControl.blinkMs) < this.baseControl.blinkMs / 2;
    this.elements.basePreviewButton1?.classList.toggle("is-lit", Boolean(this.baseControl.mask & 1) && phase);
    this.elements.basePreviewButton2?.classList.toggle("is-lit", Boolean(this.baseControl.mask & 2) && phase);
  }

  refreshCanvasDisplayMetrics() {
    const webglWidth = this.canvas?.clientWidth || 0;
    const webglHeight = this.canvas?.clientHeight || 0;
    const fallbackWidth = this.fallbackCanvas?.clientWidth || 0;
    const fallbackHeight = this.fallbackCanvas?.clientHeight || 0;

    this.canvasDisplaySize = { width: webglWidth, height: webglHeight };
    this.fallbackCanvasDisplaySize = { width: fallbackWidth, height: fallbackHeight };
    this.lastCanvasClientSize = `${webglWidth}x${webglHeight}`;

    this.renderer?.setDisplaySize(webglWidth, webglHeight);
    this.fallbackRenderer?.setDisplaySize(fallbackWidth, fallbackHeight);
  }

  bindCanvasResizeObserver() {
    this.refreshCanvasDisplayMetrics();

    const handleResize = () => {
      this.refreshCanvasDisplayMetrics();
    };

    if (typeof ResizeObserver === "function") {
      this.canvasResizeObserver = new ResizeObserver(() => {
        handleResize();
      });
      if (this.canvas) {
        this.canvasResizeObserver.observe(this.canvas);
      }
      if (this.fallbackCanvas) {
        this.canvasResizeObserver.observe(this.fallbackCanvas);
      }
    }

    window.addEventListener("resize", handleResize);
  }

  start() {
    window.VentilastationWebEmulator = this.createIntegrationApi();
    window.dispatchEvent(new CustomEvent("ventilastation:ready", {
      detail: {
        api: window.VentilastationWebEmulator,
      },
    }));
    this.applyEditorLayout();
    this.syncFullscreenState();
    this.elements.adapterName.textContent = this.adapter.name;
    this.elements.adapterSource.textContent = this.runtime.source;
    this.addDiagnostic("adapter.start", {
      name: this.adapter.name,
      source: this.runtime.source,
      hasTick: typeof this.adapter.tick === "function",
      hasExportFrame: typeof this.adapter.exportFrame === "function",
      hasMemorySnapshot: typeof this.adapter.memorySnapshot === "function",
      hasWebGL: this.renderer.available,
      hasSceneShader: this.renderer.sceneAvailable,
    });
    this.renderRuntimeStatus();
    this.bindInput();
    this.bindRemoteControls();
    this.bindVisibility();
    this.bindCopyDiagnostics();
    this.bindDebugControls();
    this.renderRendererComparison();
    this.bindFullscreenControls();
    this.bindEditorToggle();
    this.bindInspectorToggle();
    this.bindMemoryControls();
    this.bindSceneErrorControls();
    this.bindResponsiveLayout();
    this.bindCanvasResizeObserver();
    this.syncResponsiveLayout();
    this.renderFullscreenToggle();
    this.renderEditorToggle();
    this.renderInspectorVisibility();
    this.renderCanvasVisibility();
    this.renderSceneError();
    this.renderMemorySummary();
    if (this.runtime.source === "remote" && typeof this.adapter.onStatus === "function") {
      this.unsubscribeRemoteStatus = this.adapter.onStatus((status) => this.renderRemoteStatus(status));
      this.renderRemoteStatus({ state: "connected" });
    }
    if (this.runtime.source === "remote" && typeof this.adapter.onHostEvent === "function") {
      this.unsubscribeRemoteHostEvent = this.adapter.onHostEvent((event) => this.handleRemoteHostEvent(event));
    }
    if (this.runtime.source === "error") {
      return;
    }
    if (this.adapter.usesWorkerFrameStream && typeof this.adapter.onFrame === "function") {
      this.unsubscribeWorkerFrame = this.adapter.onFrame((frame) => {
        this.handleWorkerFrame(frame);
      });
      this.unsubscribeWorkerRuntimeError = this.adapter.onRuntimeError?.((error) => {
        if (!error) {
          return;
        }
        const normalizedError = new Error(error.message || String(error));
        normalizedError.stack = error.stack || normalizedError.stack;
        this.executionError = this.extractProminentError(normalizedError);
        this.runtime.error = this.executionError ? null : normalizedError;
        this.pollingHalted = Boolean(this.executionError?.isSceneLifecycleError);
        this.renderSceneError();
        this.renderRuntimeStatus();
      }) || null;
      void this.adapter.startLoop({ full: true });
    } else {
      this.schedulePoll(true);
    }
  }

  bindRemoteControls() {
    const connectButton = this.elements.remoteConnectButton;
    const controlButton = this.elements.remoteControlButton;
    if (connectButton) {
      connectButton.addEventListener("click", async () => {
        if (this.runtime.source === "remote") {
          this.adapter.close?.();
          const next = new URL(window.location.href);
          next.searchParams.delete("remote");
          window.location.assign(next.toString());
          return;
        }
        try {
          connectButton.disabled = true;
          await RemoteWorkbenchAdapter.requestTicket();
          const next = new URL(window.location.href);
          next.searchParams.set("remote", "1");
          window.location.assign(next.toString());
        } catch (error) {
          this.runtime.error = error;
          this.renderRuntimeStatus();
        } finally {
          connectButton.disabled = false;
        }
      });
    }
    if (controlButton) {
      controlButton.addEventListener("click", () => {
        if (this.runtime.source !== "remote") {
          return;
        }
        if (this.adapter.leaseGeneration === null) {
          this.adapter.requestControl?.();
        } else {
          this.adapter.releaseControl?.();
        }
      });
    }
    this.elements.remoteResetButton?.addEventListener("click", () => this.adapter.resetBoard?.());
    this.elements.remoteRpm?.addEventListener("change", () => this.adapter.setRpm?.(this.elements.remoteRpm.value));
  }

  renderRemoteStatus(status = {}) {
    const connectButton = this.elements.remoteConnectButton;
    const controlButton = this.elements.remoteControlButton;
    const statusNode = this.elements.remoteStatus;
    if (this.runtime.source !== "remote") {
      if (connectButton) {
        connectButton.textContent = "Connect board";
      }
      if (controlButton) {
        controlButton.hidden = true;
      }
      if (statusNode) {
        statusNode.textContent = "Local emulator";
      }
      return;
    }
    if (connectButton) {
      connectButton.textContent = "Disconnect board";
    }
    const controllerEligible = this.adapter.connected && ["controller", "operator", "admin"].includes(this.adapter.role);
    const operatorActive = this.adapter.connected && ["operator", "admin"].includes(this.adapter.role) && this.adapter.leaseGeneration !== null;
    if (controlButton) {
      controlButton.hidden = !controllerEligible;
      controlButton.textContent = this.adapter.leaseGeneration === null ? "Request control" : "Release control";
    }
    if (this.elements.remoteResetButton) {
      this.elements.remoteResetButton.hidden = !operatorActive;
    }
    if (this.elements.remoteRpmControl) {
      this.elements.remoteRpmControl.hidden = !operatorActive;
    }
    if (statusNode) {
      if (status.state === "disconnected") {
        statusNode.textContent = "Board disconnected";
      } else if (this.adapter.boardConnected === false) {
        statusNode.textContent = "Synthetic display — board unplugged";
      } else if (this.adapter.leaseGeneration !== null) {
        statusNode.textContent = `Controlling board as ${this.adapter.role}`;
      } else if (status.holder) {
        statusNode.textContent = `Viewing — ${status.holder} controls`;
      } else {
        statusNode.textContent = `Viewing board as ${this.adapter.role || "user"}`;
      }
    }
  }

  createIntegrationApi() {
    return {
      listProjectFiles: (path = ".") => this.listProjectFiles(path),
      readProjectFile: (path, encoding = "utf8") => this.readProjectFile(path, encoding),
      writeProjectFile: (path, content, encoding = "utf8") => this.writeProjectFile(path, content, encoding),
      deleteProjectFile: (path) => this.deleteProjectFile(path),
      applyProjectSnapshot: (files = []) => this.applyProjectSnapshot(files),
      restartRuntime: (options = {}) => this.restartRuntime(options),
      getRuntimeInfo: () => ({
        adapterName: this.adapter?.name || null,
        adapterSource: this.runtime?.source || null,
        editorOpen: this.editorOpen,
        pollingHalted: this.pollingHalted,
        currentButtons: this.currentButtons,
        currentInput: this.currentInput,
      }),
    };
  }

  listProjectFiles(path = ".") {
    if (typeof this.adapter.listWorkspaceFiles !== "function") {
      return Promise.reject(new Error("Workspace file API unavailable"));
    }
    return this.adapter.listWorkspaceFiles(path);
  }

  readProjectFile(path, encoding = "utf8") {
    if (typeof this.adapter.readWorkspaceFile !== "function") {
      return Promise.reject(new Error("Workspace file API unavailable"));
    }
    return this.adapter.readWorkspaceFile(path, encoding);
  }

  writeProjectFile(path, content, encoding = "utf8") {
    if (typeof this.adapter.writeWorkspaceFile !== "function") {
      return Promise.reject(new Error("Workspace file API unavailable"));
    }
    return this.adapter.writeWorkspaceFile(path, content, encoding);
  }

  deleteProjectFile(path) {
    if (typeof this.adapter.deleteWorkspaceFile !== "function") {
      return Promise.reject(new Error("Workspace file API unavailable"));
    }
    return this.adapter.deleteWorkspaceFile(path);
  }

  applyProjectSnapshot(files = []) {
    if (typeof this.adapter.applyWorkspaceSnapshot !== "function") {
      return Promise.reject(new Error("Workspace file API unavailable"));
    }
    return this.adapter.applyWorkspaceSnapshot(files);
  }

  async restartRuntime({ full = true, autostartSlug = null } = {}) {
    if (typeof this.adapter.restartRuntime !== "function") {
      throw new Error("Runtime restart unavailable");
    }
    this.addDiagnostic("runtime.restart.begin", { full, autostartSlug });
    this.pollingHalted = false;
    this.executionError = null;
    this.runtime.error = null;
    this.lastSceneTickAt = null;
    this.lastFrame = null;
    this.lastFrameShape = null;
    this.lastRenderedLedPixels = null;
    this.assetIndex.clear();
    this.assetVersion += 1;
    this.assetRenderCache.clear();
    this.audio.resetCache();
    this.visibleStripSlots = [];
    this.palette = null;
    this.paletteVersion = 0;
    this.paletteLoadedBytes = 0;
    if (this.pollRequestId !== null) {
      window.cancelAnimationFrame(this.pollRequestId);
      this.pollRequestId = null;
    }
    if (this.adapter.usesWorkerFrameStream && typeof this.adapter.stopLoop === "function") {
      await this.adapter.stopLoop();
    }
    const result = await this.adapter.restartRuntime({ autostartSlug });
    this.runtime.source = "wasm";
    this.elements.adapterSource.textContent = this.runtime.source;
    this.syncButtons();
    await this.syncTraceFlags();
    this.renderRuntimeStatus();
    this.renderSceneError();
    this.renderMemorySummary();
    this.addDiagnostic("runtime.restart.complete", {
      full,
      result,
    });
    if (this.adapter.usesWorkerFrameStream && typeof this.adapter.startLoop === "function") {
      await this.adapter.startLoop({ full });
    } else {
      this.schedulePoll(full);
    }
    return result;
  }

  schedulePoll(full = false) {
    if (this.pollRequestId !== null || this.pollingHalted) {
      return;
    }
    this.pollRequestId = window.requestAnimationFrame(() => {
      this.pollRequestId = null;
      this.pollFrame(full);
    });
  }

  bindInput() {
    window.addEventListener("pointerdown", () => {
      this.audio.enable();
    }, { once: true });

    window.addEventListener("keydown", (event) => {
      if (isEditableEventTarget(event.target)) {
        return;
      }
      this.audio.enable();
      if (EXIT_KEY_CODES.has(event.code)) {
        event.preventDefault();
        this.keyboardExitPressed = true;
        this.syncButtons();
        this.addDiagnostic("input.exit.keydown", { code: event.code });
        this.renderStatus();
        return;
      }
      const input = keyboardInputForCode(event.code);
      if (!input) {
        return;
      }
      event.preventDefault();
      this.setKeyboardCode(event.code, true);
      this.syncButtons();
      this.addDiagnostic("input.keydown", { code: event.code, buttons: this.currentButtons });
      this.renderStatus();
    });

    window.addEventListener("keyup", (event) => {
      if (EXIT_KEY_CODES.has(event.code)) {
        const wasPressed = this.keyboardExitPressed;
        this.keyboardExitPressed = false;
        if (wasPressed) {
          this.syncButtons();
          this.addDiagnostic("input.exit.keyup", { code: event.code });
          this.renderStatus();
        }
        if (!isEditableEventTarget(event.target)) {
          event.preventDefault();
        }
        return;
      }
      const input = keyboardInputForCode(event.code);
      if (!input) {
        return;
      }
      const wasPressed = this.keyboardCodes.has(event.code);
      if (wasPressed) {
        this.setKeyboardCode(event.code, false);
        this.syncButtons();
        this.addDiagnostic("input.keyup", { code: event.code, buttons: this.currentButtons });
        this.renderStatus();
      }
      if (isEditableEventTarget(event.target)) {
        return;
      }
      event.preventDefault();
    });

    window.addEventListener("blur", () => {
      this.keyboardInput = { joy1: 0, joy2: 0, extra: 0 };
      this.keyboardCodes.clear();
      this.touchButtons = 0;
      this.touchInput = { joy1: 0, joy2: 0, extra: 0 };
      this.gamepadInput = { joy1: 0, joy2: 0, extra: 0, exit: false };
      this.keyboardExitPressed = false;
      this.touchStickPointerId = null;
      this.syncButtons();
      this.addDiagnostic("input.blur", { buttons: 0 });
      this.renderStatus();
    });

    this.bindGamepadControls();
    this.bindTouchControls();
  }

  bindGamepadControls() {
    window.addEventListener("gamepadconnected", (event) => {
      const gamepad = event.gamepad;
      this.selectActiveGamepad();
      this.addDiagnostic("input.gamepad.connected", {
        index: gamepad.index,
        id: gamepad.id,
        mapping: gamepad.mapping || "unknown",
      });
      this.renderStatus();
    });

    window.addEventListener("gamepaddisconnected", (event) => {
      const gamepad = event.gamepad;
      const wasActive = gamepad.index === this.activeGamepadIndex;
      if (wasActive) {
        this.activeGamepadIndex = null;
        this.gamepadInput = { joy1: 0, joy2: 0, extra: 0, exit: false };
      }
      this.selectActiveGamepad();
      this.addDiagnostic("input.gamepad.disconnected", {
        index: gamepad.index,
        id: gamepad.id,
        wasActive,
      });
      this.syncButtons();
      this.renderStatus();
    });

    this.selectActiveGamepad();
  }

  getConnectedGamepads() {
    if (typeof navigator.getGamepads !== "function") {
      this.connectedGamepadCount = 0;
      return [];
    }
    const gamepads = Array.from(navigator.getGamepads()).filter(Boolean);
    this.connectedGamepadCount = gamepads.length;
    return gamepads;
  }

  selectActiveGamepad(gamepads = this.getConnectedGamepads()) {
    const activeGamepad = gamepads.find((gamepad) => gamepad.index === this.activeGamepadIndex);
    if (activeGamepad) {
      return activeGamepad;
    }
    const nextGamepad = gamepads[0] || null;
    const previousIndex = this.activeGamepadIndex;
    this.activeGamepadIndex = nextGamepad ? nextGamepad.index : null;
    if (previousIndex !== this.activeGamepadIndex) {
      this.addDiagnostic("input.gamepad.active", {
        index: this.activeGamepadIndex,
        id: nextGamepad?.id || null,
      });
    }
    return nextGamepad;
  }

  readGamepadInput() {
    const gamepads = this.getConnectedGamepads();
    const primary = this.selectActiveGamepad(gamepads);
    const secondary = gamepads.find((gamepad) => gamepad.index !== primary?.index) || null;
    return mapGamepadInput(primary, secondary, this.invertGamepadY);
  }

  updateGamepadInput() {
    const nextInput = this.readGamepadInput();
    const previous = this.gamepadInput;
    if (nextInput.joy1 === previous.joy1 &&
        nextInput.joy2 === previous.joy2 &&
        nextInput.extra === previous.extra &&
        nextInput.exit === previous.exit) {
      return false;
    }
    if (nextInput.joy1 || nextInput.joy2 || nextInput.extra || nextInput.exit) {
      this.audio.enable();
    }
    this.gamepadInput = nextInput;
    this.syncButtons();
    this.addDiagnostic("input.gamepad.state", {
      activeIndex: this.activeGamepadIndex,
      connected: this.connectedGamepadCount,
      joy1: nextInput.joy1,
      joy2: nextInput.joy2,
      extra: nextInput.extra,
      exit: nextInput.exit,
    });
    return true;
  }

  bindTouchControls() {
    this.bindTouchStick();
    this.bindTouchButtons();
  }

  bindTouchStick() {
    const stick = this.elements.touchStick;
    if (!stick) {
      return;
    }
    stick.addEventListener("pointerdown", (event) => {
      event.preventDefault();
      this.audio.enable();
      this.touchStickPointerId = event.pointerId;
      stick.setPointerCapture(event.pointerId);
      this.updateTouchStickFromPoint(event.clientX, event.clientY);
    });
    stick.addEventListener("pointermove", (event) => {
      if (event.pointerId !== this.touchStickPointerId) {
        return;
      }
      event.preventDefault();
      this.updateTouchStickFromPoint(event.clientX, event.clientY);
    });
    const releaseStick = (event) => {
      if (event.pointerId !== this.touchStickPointerId) {
        return;
      }
      event.preventDefault();
      this.touchStickPointerId = null;
      this.setTouchDirection(0, 0, 0);
    };
    stick.addEventListener("pointerup", releaseStick);
    stick.addEventListener("pointercancel", releaseStick);
  }

  bindTouchButtons() {
    for (const button of this.elements.touchButtons) {
      const buttonName = button.dataset.touchButton;
      const channel = button.dataset.touchChannel || "joy1";
      const bit = Number(button.dataset.touchBit || BUTTONS[buttonName] || 0);
      if (!bit || !Object.prototype.hasOwnProperty.call(this.touchInput, channel)) {
        continue;
      }
      const setPressed = (pressed) => {
        if (pressed) {
          this.touchInput[channel] |= bit;
        } else {
          this.touchInput[channel] &= ~bit;
        }
        this.syncButtons();
        this.renderStatus();
      };
      button.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        this.audio.enable();
        button.setPointerCapture(event.pointerId);
        setPressed(true);
      });
      const release = (event) => {
        event.preventDefault();
        setPressed(false);
      };
      button.addEventListener("pointerup", release);
      button.addEventListener("pointercancel", release);
    }
  }

  updateTouchStickFromPoint(clientX, clientY) {
    const stick = this.elements.touchStick;
    if (!stick) {
      return;
    }
    const rect = stick.getBoundingClientRect();
    const centerX = rect.left + rect.width * 0.5;
    const centerY = rect.top + rect.height * 0.5;
    const dx = clientX - centerX;
    const dy = clientY - centerY;
    const radius = rect.width * 0.34;
    const distance = Math.hypot(dx, dy);
    const clampedDistance = Math.min(distance, radius);
    const angle = distance > 0 ? Math.atan2(dy, dx) : 0;
    const knobX = Math.cos(angle) * clampedDistance;
    const knobY = Math.sin(angle) * clampedDistance;
    this.setTouchDirection(knobX, knobY, radius);
  }

  setTouchDirection(knobX, knobY, radius) {
    const magnitude = radius > 0 ? Math.min(1, Math.hypot(knobX, knobY) / radius) : 0;
    let directionMask = 0;
    if (magnitude >= TOUCH_STICK_DEAD_ZONE) {
      const normalizedX = knobX / radius;
      const normalizedY = knobY / radius;
      if (normalizedX <= -0.35) {
        directionMask |= BUTTONS.JOY_LEFT;
      }
      if (normalizedX >= 0.35) {
        directionMask |= BUTTONS.JOY_RIGHT;
      }
      if (normalizedY <= -0.35) {
        directionMask |= BUTTONS.JOY_UP;
      }
      if (normalizedY >= 0.35) {
        directionMask |= BUTTONS.JOY_DOWN;
      }
    }
    this.touchButtons &= ~(BUTTONS.JOY_LEFT | BUTTONS.JOY_RIGHT | BUTTONS.JOY_UP | BUTTONS.JOY_DOWN);
    this.touchButtons |= directionMask;
    this.renderTouchStick(knobX, knobY);
    this.syncButtons();
    this.renderStatus();
  }

  renderTouchStick(x, y) {
    const knob = this.elements.touchStickKnob;
    if (!knob) {
      return;
    }
    knob.style.setProperty("--stick-x", `${Math.round(x)}px`);
    knob.style.setProperty("--stick-y", `${Math.round(y)}px`);
  }

  renderTouchButtons() {
    for (const button of this.elements.touchButtons) {
      const buttonName = button.dataset.touchButton;
      const channel = button.dataset.touchChannel || "joy1";
      const bit = Number(button.dataset.touchBit || BUTTONS[buttonName] || 0);
      if (!bit || !Object.prototype.hasOwnProperty.call(this.currentInput, channel)) {
        continue;
      }
      button.classList.toggle("is-pressed", Boolean(this.currentInput[channel] & bit));
    }
  }

  renderTouchStickFromButtons() {
    const stick = this.elements.touchStick;
    if (!stick) {
      return;
    }
    let x = 0;
    let y = 0;
    if (this.currentButtons & BUTTONS.JOY_LEFT) {
      x -= 1;
    }
    if (this.currentButtons & BUTTONS.JOY_RIGHT) {
      x += 1;
    }
    if (this.currentButtons & BUTTONS.JOY_UP) {
      y -= 1;
    }
    if (this.currentButtons & BUTTONS.JOY_DOWN) {
      y += 1;
    }
    if (!x && !y) {
      this.renderTouchStick(0, 0);
      return;
    }
    const magnitude = Math.hypot(x, y) || 1;
    const visualRadius = stick.getBoundingClientRect().width * 0.2;
    this.renderTouchStick(
      (x / magnitude) * visualRadius,
      (y / magnitude) * visualRadius,
    );
  }

  setKeyboardCode(code, pressed) {
    if (pressed) {
      this.keyboardCodes.add(code);
    } else {
      this.keyboardCodes.delete(code);
    }
    this.keyboardInput = keyboardInputForCodes(this.keyboardCodes);
  }

  syncButtons() {
    const joy1 = (this.keyboardInput.joy1 | this.touchButtons | this.touchInput.joy1 | this.gamepadInput.joy1) & 0x7f;
    const joy2 = (this.keyboardInput.joy2 | this.touchInput.joy2 | this.gamepadInput.joy2) & 0x7f;
    const extra = (this.keyboardInput.extra | this.touchInput.extra | this.gamepadInput.extra) & 0x7f;
    const exitPressed = this.keyboardExitPressed || this.gamepadInput.exit;
    const exit = exitPressed && !this.exitPressed;
    this.exitPressed = exitPressed;
    this.currentButtons = joy1 | ((extra & INPUT_EXTRA.JOY1_Y) ? BUTTONS.BUTTON_D : 0);
    this.currentInput = { joy1, joy2, extra };
    if (typeof this.adapter.setInput === "function") {
      this.adapter.setInput(joy1, joy2, extra, exit);
    } else {
      this.adapter.setButtons(joy1);
    }
    this.renderTouchButtons();
    this.renderTouchStickFromButtons();
  }

  bindVisibility() {
    document.addEventListener("visibilitychange", () => {
      const now = performance.now();
      if (document.hidden) {
        this.lastSceneTickAt = now;
        this.addDiagnostic("timing.pause", { reason: "hidden" });
        if (this.adapter.usesWorkerFrameStream && typeof this.adapter.stopLoop === "function") {
          void this.adapter.stopLoop();
        }
        return;
      }
      this.lastSceneTickAt = now - SCENE_STEP_MS;
      this.addDiagnostic("timing.resume", { reason: "visible" });
      if (this.adapter.usesWorkerFrameStream && typeof this.adapter.startLoop === "function") {
        void this.adapter.startLoop({ full: false });
      } else {
        this.schedulePoll(false);
      }
    });
  }

  bindCopyDiagnostics() {
    if (!this.elements.copyDiagnosticsButton) {
      return;
    }
    this.elements.copyDiagnosticsButton.addEventListener("click", async () => {
      const text = this.refreshCopyDiagnostics();
      if (!text) {
        this.setCopyDiagnosticsStatus("Empty");
        return;
      }
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(text);
        } else {
          this.copyViaSelection(text);
        }
        this.setCopyDiagnosticsStatus("Copied");
      } catch (error) {
        console.error("Copy diagnostics failed", error);
        this.setCopyDiagnosticsStatus("Copy failed");
      }
    });
  }

  bindDebugControls() {
    if (this.elements.force2dFallback) {
      this.elements.force2dFallback.checked = this.force2dFallback;
      this.elements.force2dFallback.disabled = this.runtime.source === "remote";
      this.elements.force2dFallback.addEventListener("change", () => {
        this.force2dFallback = Boolean(this.elements.force2dFallback.checked);
        this.writeForce2dPreference(this.force2dFallback);
        this.renderProfileSamples = [];
        this.fullscreenRenderProfileSamples = [];
        this.lastFullscreenRenderProfile = null;
        this.addDiagnostic("renderer.mode", {
          forced2d: this.force2dFallback,
          webglAvailable: this.renderer.available,
        });
        this.renderCanvasVisibility();
        this.renderStatus();
        this.renderFrame();
      });
    }

    if (this.elements.invertGamepadY) {
      this.elements.invertGamepadY.checked = this.invertGamepadY;
      this.elements.invertGamepadY.addEventListener("change", () => {
        this.invertGamepadY = Boolean(this.elements.invertGamepadY.checked);
        this.writeInvertGamepadYPreference(this.invertGamepadY);
        this.addDiagnostic("input.gamepad.invert_y", {
          enabled: this.invertGamepadY,
        });
        if (this.updateGamepadInput()) {
          this.renderStatus();
        }
      });
    }

    if (this.elements.enableRendererProfiling) {
      this.elements.enableRendererProfiling.checked = this.rendererProfiling;
      this.elements.enableRendererProfiling.addEventListener("change", () => {
        this.rendererProfiling = Boolean(this.elements.enableRendererProfiling.checked);
        this.writeRendererProfilingPreference(this.rendererProfiling);
        this.renderProfileSamples = [];
        this.fullscreenRenderProfileSamples = [];
        this.lastFullscreenRenderProfile = null;
        this.addDiagnostic("renderer.profiling", {
          enabled: this.rendererProfiling,
        });
        if (this.lastFrame) {
          this.renderInspectors(this.lastFrame);
        } else {
          this.refreshCopyDiagnostics();
        }
      });
    }

    if (this.elements.sceneRendererMode) {
      if (this.sceneRendererMode === "shader" && !this.renderer.sceneAvailable) {
        this.sceneRendererMode = "cpu";
        this.writeSceneRendererPreference(this.sceneRendererMode);
      }
      this.elements.sceneRendererMode.value = this.sceneRendererMode;
      this.elements.sceneRendererMode.addEventListener("change", () => {
        const requestedMode = this.elements.sceneRendererMode.value;
        this.sceneRendererMode = requestedMode === "shader" && this.renderer.sceneAvailable
          ? "shader"
          : "cpu";
        this.elements.sceneRendererMode.value = this.sceneRendererMode;
        this.writeSceneRendererPreference(this.sceneRendererMode);
        this.renderProfileSamples = [];
        this.fullscreenRenderProfileSamples = [];
        this.lastFullscreenRenderProfile = null;
        this.addDiagnostic("renderer.compositor", {
          mode: this.sceneRendererMode,
          shaderAvailable: this.renderer.sceneAvailable,
        });
        if (this.lastFrame) {
          this.renderFrame();
        } else {
          this.renderStatus();
        }
      });
    }

    if (this.elements.runRendererComparison) {
      this.elements.runRendererComparison.addEventListener("click", () => {
        void this.runRendererComparison();
      });
    }

    if (this.elements.webglResolutionScale) {
      this.elements.webglResolutionScale.value = String(this.webglResolutionScalePreference);
      this.elements.webglResolutionScale.addEventListener("change", () => {
        const nextValue = this.elements.webglResolutionScale.value;
        if (nextValue === WEBGL_RESOLUTION_SCALE_AUTO) {
          this.setWebglResolutionScalePreference(WEBGL_RESOLUTION_SCALE_AUTO, { reason: "manual_auto", persist: true });
          this.applyWebglResolutionScale(DEFAULT_WEBGL_RESOLUTION_SCALE, { reason: "manual_auto", persist: false });
        } else {
          const nextScale = Number.parseFloat(nextValue);
          const resolvedScale = Number.isFinite(nextScale) && nextScale > 0
            ? nextScale
            : DEFAULT_WEBGL_RESOLUTION_SCALE;
          this.setWebglResolutionScalePreference(resolvedScale, { reason: "manual_fixed", persist: true });
          this.applyWebglResolutionScale(resolvedScale, { reason: "manual_fixed", persist: false });
        }
        if (this.lastFrame) {
          this.renderFrame();
        } else {
          this.renderStatus();
          this.refreshCopyDiagnostics();
        }
      });
    }

    if (this.elements.traceFlagControls.length) {
      this.elements.traceFlagControls.forEach((control) => {
        control.checked = false;
        control.addEventListener("change", () => {
          void this.syncTraceFlags();
        });
      });
      void this.syncTraceFlags();
    }
  }

  syncTraceFlags() {
    const flags = this.elements.traceFlagControls.reduce((mask, control) => {
      if (!control.checked) {
        return mask;
      }
      return mask | (TRACE_FLAGS[control.dataset.traceFlag] || 0);
    }, 0);
    this.traceFlags = flags;
    if (typeof this.adapter.setTraceFlags !== "function") {
      this.addDiagnostic("trace.flags.unavailable", { flags });
      return Promise.resolve(null);
    }
    return Promise.resolve()
      .then(() => this.adapter.setTraceFlags(flags))
      .then(() => {
        this.addDiagnostic("trace.flags", {
          flags,
          enabled: Object.entries(TRACE_FLAGS)
            .filter(([, bit]) => Boolean(flags & bit))
            .map(([name]) => name),
        });
        this.refreshCopyDiagnostics();
      })
      .catch((error) => {
        this.addDiagnostic("trace.flags.error", {
          flags,
          message: error?.message || String(error),
        });
      });
  }

  applyWebglResolutionScale(scale, { reason = "manual", persist = true } = {}) {
    const resolvedScale = WEBGL_RESOLUTION_SCALES.includes(scale)
      ? scale
      : DEFAULT_WEBGL_RESOLUTION_SCALE;
    this.webglResolutionScale = resolvedScale;
    this.renderer.resolutionScale = resolvedScale;
    this.lowFpsSinceAt = null;
    this.renderProfileSamples = [];
    this.fullscreenRenderProfileSamples = [];
    this.lastFullscreenRenderProfile = null;
    if (persist) {
      this.writeWebglResolutionScalePreference(this.webglResolutionScalePreference);
    }
    if (this.elements.webglResolutionScale) {
      this.elements.webglResolutionScale.value = String(this.webglResolutionScalePreference);
    }
    this.addDiagnostic("renderer.resolution_scale", {
      preference: this.webglResolutionScalePreference,
      scale: resolvedScale,
      reason,
      persist,
    });
  }

  setWebglResolutionScalePreference(value, { reason = "manual", persist = true } = {}) {
    const resolvedPreference = value === WEBGL_RESOLUTION_SCALE_AUTO
      ? WEBGL_RESOLUTION_SCALE_AUTO
      : (WEBGL_RESOLUTION_SCALES.includes(value) ? value : DEFAULT_WEBGL_RESOLUTION_SCALE);
    this.webglResolutionScalePreference = resolvedPreference;
    if (persist) {
      this.writeWebglResolutionScalePreference(resolvedPreference);
    }
    if (this.elements.webglResolutionScale) {
      this.elements.webglResolutionScale.value = String(resolvedPreference);
    }
    this.addDiagnostic("renderer.resolution_scale_preference", {
      preference: resolvedPreference,
      reason,
      persist,
    });
  }

  getNextLowerWebglResolutionScale() {
    const currentIndex = WEBGL_RESOLUTION_SCALES.indexOf(this.webglResolutionScale);
    if (currentIndex === -1) {
      return null;
    }
    return WEBGL_RESOLUTION_SCALES[currentIndex + 1] || null;
  }

  syncAdaptiveWebglResolution(now = performance.now()) {
    if (!this.canvas || this.force2dFallback || !this.renderer.available) {
      this.lowFpsSinceAt = null;
      return;
    }
    if (this.webglResolutionScalePreference !== WEBGL_RESOLUTION_SCALE_AUTO) {
      this.lowFpsSinceAt = null;
      return;
    }

    const currentSize = this.lastCanvasClientSize;
    if (this.lastAppliedCanvasClientSize !== currentSize) {
      this.lastAppliedCanvasClientSize = currentSize;
      this.applyWebglResolutionScale(DEFAULT_WEBGL_RESOLUTION_SCALE, {
        reason: "display_change",
        persist: false,
      });
      return;
    }

    if (this.displayedFps === null || this.displayedFps >= WEBGL_AUTO_SCALE_MIN_FPS) {
      this.lowFpsSinceAt = null;
      return;
    }

    if (this.lowFpsSinceAt === null) {
      this.lowFpsSinceAt = now;
      return;
    }

    if (now - this.lowFpsSinceAt < WEBGL_AUTO_SCALE_WAIT_MS) {
      return;
    }

    const nextScale = this.getNextLowerWebglResolutionScale();
    if (!nextScale) {
      this.lowFpsSinceAt = null;
      return;
    }

    this.applyWebglResolutionScale(nextScale, {
      reason: "auto_low_fps",
      persist: true,
    });
    this.lowFpsSinceAt = now;
  }

  renderCanvasVisibility() {
    if (!this.canvas || !this.fallbackCanvas) {
      return;
    }
    const use2d = this.force2dFallback || !this.renderer.available;
    this.canvas.hidden = use2d;
    this.fallbackCanvas.hidden = !use2d;
  }

  bindFullscreenControls() {
    const button = this.elements.toggleFullscreenButton;
    if (!button || !this.stagePanel || !this.canUseFullscreen()) {
      if (button) {
        button.hidden = true;
      }
      return;
    }

    button.addEventListener("click", () => {
      void this.toggleFullscreen();
    });

    document.addEventListener("fullscreenchange", () => {
      this.syncFullscreenState();
      this.refreshCanvasDisplayMetrics();
      this.renderFullscreenToggle();
      this.renderStatus();
      if (this.lastFrame) {
        this.renderInspectors(this.lastFrame);
      } else {
        this.refreshCopyDiagnostics();
      }
    });
  }

  bindResponsiveLayout() {
    const syncLayout = () => {
      this.syncResponsiveLayout();
    };
    if (this.mobileLayoutQuery && typeof this.mobileLayoutQuery.addEventListener === "function") {
      this.mobileLayoutQuery.addEventListener("change", syncLayout);
    } else if (this.mobileLayoutQuery && typeof this.mobileLayoutQuery.addListener === "function") {
      this.mobileLayoutQuery.addListener(syncLayout);
    }
    window.addEventListener("resize", syncLayout);
  }

  bindInspectorToggle() {
    if (!this.elements.toggleInspectorButton || !this.elements.inspectorPanel) {
      return;
    }
    this.elements.toggleInspectorButton.addEventListener("click", () => {
      this.setInspectorOpen(!this.inspectorOpen);
    });
  }

  bindMemoryControls() {
    const button = this.elements.collectMemoryButton;
    const refreshToggle = this.elements.refreshMemoryEveryFrame;
    if (!button) {
      return;
    }
    if (typeof this.adapter.memorySnapshot !== "function") {
      button.disabled = true;
      if (refreshToggle) {
        refreshToggle.disabled = true;
      }
      return;
    }
    if (refreshToggle) {
      refreshToggle.checked = this.refreshMemoryEveryFrame;
      refreshToggle.addEventListener("change", () => {
        this.refreshMemoryEveryFrame = Boolean(refreshToggle.checked);
        this.writeBooleanPreference(MEMORY_FRAME_REFRESH_STORAGE_KEY, this.refreshMemoryEveryFrame);
      });
    }
    button.addEventListener("click", async () => {
      button.disabled = true;
      button.textContent = "Collecting";
      try {
        await this.requestMemorySnapshot({
          collect: true,
          reason: "manual_collect",
        });
      } finally {
        button.disabled = false;
        button.textContent = "Collect";
      }
    });
  }

  bindEditorToggle() {
    if (!this.elements.toggleEditorButton) {
      return;
    }
    this.elements.toggleEditorButton.addEventListener("click", () => {
      this.setEditorOpen(!this.editorOpen);
    });
  }

  bindSceneErrorControls() {
    if (!this.elements.sceneErrorDebugButton) {
      return;
    }
    this.elements.sceneErrorDebugButton.addEventListener("click", () => {
      this.setInspectorOpen(true);
    });
  }

  setInspectorOpen(open) {
    const nextOpen = Boolean(open);
    if (nextOpen && this.editorOpen) {
      this.editorOpen = false;
      this.writeEditorPreference(false);
    }
    this.inspectorOpen = nextOpen;
    this.writeInspectorPreference(this.inspectorOpen);
    this.applyEditorLayout();
    this.renderEditorToggle();
    this.renderInspectorVisibility();
    this.addDiagnostic("inspector.toggle", {
      open: this.inspectorOpen,
    });
    if (this.inspectorOpen && this.lastFrame) {
      this.renderInspectors(this.lastFrame);
    }
    this.refreshCanvasDisplayMetrics();
    if (this.lastFrame) {
      this.renderFrame();
    } else {
      this.renderStatus();
    }
  }

  setEditorOpen(open) {
    const nextOpen = Boolean(open);
    if (nextOpen && this.inspectorOpen) {
      this.inspectorOpen = false;
      this.writeInspectorPreference(false);
    }
    this.editorOpen = nextOpen;
    this.writeEditorPreference(this.editorOpen);
    this.applyEditorLayout();
    this.renderEditorToggle();
    this.renderInspectorVisibility();
    this.addDiagnostic("editor.toggle", {
      open: this.editorOpen,
    });
    window.dispatchEvent(new CustomEvent("ventilastation:editor-toggle", {
      detail: {
        open: this.editorOpen,
      },
    }));
    this.refreshCanvasDisplayMetrics();
    if (this.lastFrame) {
      this.renderFrame();
    } else {
      this.renderStatus();
    }
  }

  applyEditorLayout() {
    if (this.appShell) {
      this.appShell.classList.toggle("is-editor-open", this.editorOpen);
      this.appShell.classList.toggle("is-inspector-open", this.inspectorOpen);
    }
    if (this.editorPanelShell) {
      this.editorPanelShell.hidden = !this.editorOpen;
    }
    if (this.elements.inspectorPanel) {
      this.elements.inspectorPanel.hidden = !this.inspectorOpen;
    }
  }

  syncFullscreenState() {
    const active = Boolean(this.stagePanel && document.fullscreenElement === this.stagePanel);
    if (this.isFullscreen === active) {
      if (this.stagePanel) {
        this.stagePanel.classList.toggle("is-fullscreen", active);
      }
      return;
    }

    this.isFullscreen = active;
    if (this.stagePanel) {
      this.stagePanel.classList.toggle("is-fullscreen", active);
    }
    this.syncResponsiveLayout();
    if (active) {
      this.fullscreenRenderProfileSamples = [];
      this.lastFullscreenRenderProfile = null;
    } else if (this.fullscreenRenderProfileSamples.length) {
      this.lastFullscreenRenderProfile = buildRenderProfileSnapshot(this.fullscreenRenderProfileSamples);
      this.fullscreenRenderProfileSamples = [];
    }
    this.addDiagnostic("fullscreen.state", {
      active,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
        devicePixelRatio: window.devicePixelRatio || 1,
      },
    });
  }

  isMobileLayout() {
    return Boolean(this.mobileLayoutQuery?.matches);
  }

  syncResponsiveLayout() {
    if (!this.stagePanel) {
      return;
    }
    this.stagePanel.classList.toggle("is-mobile-layout", this.isMobileLayout());
  }

  canUseFullscreen() {
    return Boolean(
      this.stagePanel &&
      document.fullscreenEnabled &&
      typeof this.stagePanel.requestFullscreen === "function",
    );
  }

  async enterFullscreen() {
    if (!this.canUseFullscreen() || this.isFullscreen) {
      return false;
    }
    try {
      await this.stagePanel.requestFullscreen();
      return true;
    } catch (error) {
      this.addDiagnostic("fullscreen.error", {
        message: error?.message || String(error),
      });
      return false;
    }
  }

  async exitFullscreen() {
    if (!document.fullscreenElement) {
      return false;
    }
    try {
      await document.exitFullscreen();
      return true;
    } catch (error) {
      this.addDiagnostic("fullscreen.error", {
        message: error?.message || String(error),
      });
      return false;
    }
  }

  async toggleFullscreen() {
    if (this.isFullscreen) {
      return this.exitFullscreen();
    }
    return this.enterFullscreen();
  }

  renderFullscreenToggle() {
    const button = this.elements.toggleFullscreenButton;
    if (!button) {
      return;
    }
    button.setAttribute("aria-pressed", this.isFullscreen ? "true" : "false");
    button.setAttribute("aria-label", this.isFullscreen ? "Exit fullscreen" : "Enter fullscreen");
    button.title = this.isFullscreen ? "Exit fullscreen" : "Enter fullscreen";
  }

  renderEditorToggle() {
    const button = this.elements.toggleEditorButton;
    if (!button) {
      return;
    }
    button.textContent = "Editor";
    button.setAttribute("aria-pressed", this.editorOpen ? "true" : "false");
  }

  renderInspectorVisibility() {
    if (!this.elements.toggleInspectorButton) {
      return;
    }
    this.elements.toggleInspectorButton.textContent = "Options";
    this.elements.toggleInspectorButton.setAttribute("aria-expanded", this.inspectorOpen ? "true" : "false");
  }

  readBooleanPreference(storageKey, fallback = false) {
    try {
      return localStorage.getItem(storageKey) === "1";
    } catch (_error) {
      return fallback;
    }
  }

  writeBooleanPreference(storageKey, enabled) {
    try {
      if (enabled) {
        localStorage.setItem(storageKey, "1");
      } else {
        localStorage.removeItem(storageKey);
      }
    } catch (_error) {
      return;
    }
  }

  readStoredBooleanPreference(storageKey) {
    try {
      const rawValue = localStorage.getItem(storageKey);
      if (rawValue === null) {
        return null;
      }
      return rawValue === "1";
    } catch (_error) {
      return null;
    }
  }

  readForce2dPreference() {
    const storedPreference = this.readStoredBooleanPreference(FORCE_2D_STORAGE_KEY);
    if (storedPreference !== null) {
      return storedPreference;
    }
    return this.isMobileLayout();
  }

  writeForce2dPreference(enabled) {
    this.writeBooleanPreference(FORCE_2D_STORAGE_KEY, enabled);
  }

  readInvertGamepadYPreference() {
    return this.readBooleanPreference(INVERT_GAMEPAD_Y_STORAGE_KEY, false);
  }

  writeInvertGamepadYPreference(enabled) {
    this.writeBooleanPreference(INVERT_GAMEPAD_Y_STORAGE_KEY, enabled);
  }

  readRendererProfilingPreference() {
    return this.readBooleanPreference(RENDERER_PROFILING_STORAGE_KEY, false);
  }

  writeRendererProfilingPreference(enabled) {
    this.writeBooleanPreference(RENDERER_PROFILING_STORAGE_KEY, enabled);
  }

  readSceneRendererPreference() {
    try {
      return localStorage.getItem(SCENE_RENDERER_STORAGE_KEY) === "shader" ? "shader" : "cpu";
    } catch (_error) {
      return "cpu";
    }
  }

  writeSceneRendererPreference(mode) {
    try {
      localStorage.setItem(SCENE_RENDERER_STORAGE_KEY, mode === "shader" ? "shader" : "cpu");
    } catch (_error) {
      return;
    }
  }

  readWebglResolutionScalePreference() {
    try {
      const rawValue = localStorage.getItem(WEBGL_RESOLUTION_SCALE_STORAGE_KEY);
      if (rawValue === null || rawValue === WEBGL_RESOLUTION_SCALE_AUTO) {
        return WEBGL_RESOLUTION_SCALE_AUTO;
      }
      const parsed = Number.parseFloat(rawValue ?? "");
      return Number.isFinite(parsed) && parsed > 0 ? parsed : WEBGL_RESOLUTION_SCALE_AUTO;
    } catch (_error) {
      return WEBGL_RESOLUTION_SCALE_AUTO;
    }
  }

  writeWebglResolutionScalePreference(scalePreference) {
    try {
      if (scalePreference === WEBGL_RESOLUTION_SCALE_AUTO) {
        localStorage.setItem(WEBGL_RESOLUTION_SCALE_STORAGE_KEY, WEBGL_RESOLUTION_SCALE_AUTO);
      } else {
        localStorage.setItem(WEBGL_RESOLUTION_SCALE_STORAGE_KEY, String(scalePreference));
      }
    } catch (_error) {
      return;
    }
  }

  readInspectorPreference() {
    return this.readBooleanPreference(INSPECTOR_OPEN_STORAGE_KEY, false);
  }

  writeInspectorPreference(enabled) {
    this.writeBooleanPreference(INSPECTOR_OPEN_STORAGE_KEY, enabled);
  }

  readEditorPreference() {
    return this.readBooleanPreference(EDITOR_OPEN_STORAGE_KEY, false);
  }

  writeEditorPreference(enabled) {
    this.writeBooleanPreference(EDITOR_OPEN_STORAGE_KEY, enabled);
  }

  copyViaSelection(text) {
    const textarea = this.elements.copyDiagnostics;
    const previousSelectionStart = textarea.selectionStart;
    const previousSelectionEnd = textarea.selectionEnd;
    textarea.focus();
    textarea.select();
    document.execCommand("copy");
    textarea.setSelectionRange(previousSelectionStart, previousSelectionEnd);
  }

  setCopyDiagnosticsStatus(message) {
    if (!this.elements.copyDiagnosticsStatus) {
      return;
    }
    this.elements.copyDiagnosticsStatus.textContent = message;
    if (this.copyStatusTimer) {
      clearTimeout(this.copyStatusTimer);
    }
    this.copyStatusTimer = window.setTimeout(() => {
      this.elements.copyDiagnosticsStatus.textContent = "";
      this.copyStatusTimer = null;
    }, 1500);
  }

  refreshCopyDiagnostics() {
    const diagnostics = this.diagnostics.slice();
    const frameShape = this.lastFrameShape || this.describeFrame(this.lastFrame || {});
    const text = this.buildDiagnosticBundle(frameShape, diagnostics);
    if (this.elements.copyDiagnostics) {
      this.elements.copyDiagnostics.value = text;
    }
    return text;
  }

  async requestMemorySnapshot({ collect = false, reason = "manual", track = true } = {}) {
    if (typeof this.adapter.memorySnapshot !== "function") {
      return null;
    }
    if (this.memorySnapshotPending) {
      if (!collect) {
        return this.memorySnapshotPending;
      }
      await this.memorySnapshotPending;
    }
    this.memorySnapshotPending = Promise.resolve()
      .then(async () => {
        const [snapshot, proxyRefInfo] = await Promise.all([
          this.adapter.memorySnapshot({ collect }),
          typeof this.adapter.proxyRefInfo === "function"
            ? this.adapter.proxyRefInfo().catch(() => null)
            : Promise.resolve(null),
        ]);
        return { snapshot, proxyRefInfo };
      })
      .then(({ snapshot, proxyRefInfo }) => {
        const stampedSnapshot = {
          ...snapshot,
          proxyRefInfo,
          sampledAt: new Date().toISOString(),
          reason,
        };
        this.lastMemorySnapshot = stampedSnapshot;
        if (collect) {
          this.lastCollectedMemorySnapshot = stampedSnapshot;
        }
        this.lastMemorySnapshotAt = performance.now();
        if (track) {
          this.recordMemorySnapshot(stampedSnapshot, { collect, reason });
          this.addDiagnostic("memory.snapshot", {
            reason,
            collect,
            gc: stampedSnapshot.gc || null,
            runtime: stampedSnapshot.runtime || null,
            display: stampedSnapshot.display || null,
            proxyRefInfo: stampedSnapshot.proxyRefInfo || null,
            jsHistoryLength: this.memorySnapshotHistory.length,
            traceFlags: this.traceFlags,
          });
        }
        this.renderMemorySummary();
        if (track && this.inspectorOpen && this.lastFrame) {
          this.renderInspectors(this.lastFrame);
        } else if (track) {
          this.refreshCopyDiagnostics();
        }
        return stampedSnapshot;
      })
      .catch((error) => {
        this.lastMemorySnapshotAt = performance.now();
        this.addDiagnostic("memory.snapshot.error", {
          reason,
          message: error.message || String(error),
        });
        this.renderMemorySummary(error);
        return null;
      })
      .finally(() => {
        this.memorySnapshotPending = null;
      });
    return this.memorySnapshotPending;
  }

  recordMemorySnapshot(snapshot, { collect = false, reason = "manual" } = {}) {
    const currentScene = snapshot?.runtime?.currentScene || null;
    const sceneChanged = currentScene !== this.lastMemoryScene;
    const entry = {
      sampledAt: snapshot.sampledAt,
      reason,
      collect,
      sceneChanged,
      previousScene: this.lastMemoryScene,
      currentScene,
      frame: snapshot?.runtime?.frame ?? null,
      allocBytes: snapshot?.gc?.allocBytes ?? null,
      freeBytes: snapshot?.gc?.freeBytes ?? null,
      assetBytes: snapshot?.display?.assetBytes ?? null,
      assetCount: snapshot?.display?.assetCount ?? null,
      pendingCalls: snapshot?.runtime?.pendingCalls ?? null,
      sceneStackDepth: snapshot?.runtime?.sceneStackDepth ?? null,
    };
    this.lastMemoryScene = currentScene;
    this.memorySnapshotHistory.push(entry);
    if (this.memorySnapshotHistory.length > MEMORY_SNAPSHOT_HISTORY_LIMIT) {
      this.memorySnapshotHistory.shift();
    }
  }

  refreshFrameMemorySummary() {
    if (!(this.traceFlags & TRACE_FLAGS.auto_gc_frame) && !this.refreshMemoryEveryFrame) {
      return;
    }
    void this.requestMemorySnapshot({
      collect: false,
      reason: "frame",
      track: false,
    });
  }

  applyFrame(frame) {
    if (!frame || typeof frame !== "object") {
      throw new Error(`Invalid frame payload: ${String(frame)}`);
    }
    if (this.usesEventStreamProtocol(frame)) {
      this.processFrameEvents(frame);
    } else if (!Array.isArray(frame.sprites)) {
      frame.sprites = [];
    }
    this.renderBasePreview();
    if (
      frame.palette instanceof Uint8Array &&
      (
        !(this.palette instanceof Uint8Array) ||
        Boolean(frame.palette_dirty) ||
        Number(frame.palette_version || 0) !== this.paletteVersion
      )
    ) {
      this.palette = frame.palette;
      this.paletteVersion = Number(frame.palette_version || 0);
      this.paletteUploadVersion += 1;
      this.paletteLoadedBytes = frame.palette.length;
      this.assetRenderCache.clear();
    }
    if (Array.isArray(frame.assets) && frame.assets.length) {
      for (const asset of frame.assets) {
        this.assetIndex.set(asset.slot, {
          ...asset,
          dataLength: asset.data?.length ?? 0,
          loadedBytes: asset.data?.length ?? 0,
          data: asset.data ?? null,
        });
        this.assetVersion += 1;
      }
    }
    this.runtime.error = null;
    if (this.executionError && this.runtime.source === "wasm") {
      this.executionError = null;
      this.pollingHalted = false;
      this.renderSceneError();
      this.renderRuntimeStatus();
    }
    this.lastFrame = frame;
    this.visibleStripSlots = [...new Set([
      ...(Array.isArray(frame.sprites) ? frame.sprites.map((sprite) => sprite.image_strip) : []),
      ...(Array.isArray(frame.tilemaps) ? frame.tilemaps.map((tilemap) => tilemap.image_strip) : []),
    ].filter((slot) => Number.isInteger(slot) && slot >= 0))];
    this.addDiagnostic("frame.ok", {
      frame: frame.frame,
      sprites: Array.isArray(frame.sprites) ? frame.sprites.length : -1,
      assets: this.assetIndex.size,
      hasPalette: this.palette instanceof Uint8Array,
    });
  }

  handleWorkerFrame(frame) {
    try {
      const gamepadChanged = this.updateGamepadInput();
      this.applyFrame(frame);
      this.renderFrame();
      this.refreshFrameMemorySummary();
      if (gamepadChanged) {
        this.renderStatus();
      }
    } catch (error) {
      this.executionError = this.extractProminentError(error);
      this.runtime.error = this.executionError ? null : error;
      this.pollingHalted = Boolean(this.executionError?.isSceneLifecycleError);
      this.addDiagnostic("frame.error", {
        message: error.message || String(error),
        stack: error.stack || null,
      });
      this.renderSceneError();
      this.renderRuntimeStatus();
      console.error("Worker frame handling failed", error);
    }
  }

  handleRemoteHostEvent(event) {
    try {
      this.processFrameEvents({ events: [event] });
      this.renderBasePreview();
    } catch (error) {
      this.addDiagnostic("remote.host-event.error", {
        message: error.message || String(error),
      });
      console.error("Remote host event failed", error);
    }
  }

  async pollFrame(full = false) {
    try {
      const gamepadChanged = this.updateGamepadInput();
      const now = performance.now();
      let stepsDue = 0;
      if (this.lastSceneTickAt === null) {
        this.lastSceneTickAt = now;
        stepsDue = 1;
      } else {
        const elapsed = now - this.lastSceneTickAt;
        if (elapsed > MAX_TICK_BACKLOG_MS) {
          this.addDiagnostic("timing.resync", {
            elapsedMs: Math.round(elapsed),
            maxBacklogMs: MAX_TICK_BACKLOG_MS,
          });
          this.lastSceneTickAt = now - SCENE_STEP_MS;
          stepsDue = 1;
        } else {
          stepsDue = Math.floor(elapsed / SCENE_STEP_MS);
        }
      }

      if (stepsDue > MAX_CATCH_UP_STEPS) {
        this.addDiagnostic("timing.catchup", {
          requestedSteps: stepsDue,
          appliedSteps: MAX_CATCH_UP_STEPS,
        });
        stepsDue = MAX_CATCH_UP_STEPS;
      }

      if (stepsDue > 0 && typeof this.adapter.tick === "function") {
        await Promise.resolve(this.adapter.tick(stepsDue));
        this.lastSceneTickAt += stepsDue * SCENE_STEP_MS;
      }

      if (!full && stepsDue === 0 && this.lastFrame) {
        this.renderFrame();
        if (gamepadChanged) {
          this.renderStatus();
        }
        return;
      }

      const frame = await Promise.resolve(this.adapter.exportFrame({ full }));
      this.applyFrame(frame);
      this.renderFrame();
      this.refreshFrameMemorySummary();
    } catch (error) {
      this.executionError = this.extractProminentError(error);
      this.runtime.error = this.executionError ? null : error;
      this.pollingHalted = Boolean(this.executionError?.isSceneLifecycleError);
      this.addDiagnostic("frame.error", {
        message: error.message || String(error),
        stack: error.stack || null,
      });
      this.renderSceneError();
      this.renderRuntimeStatus();
      console.error("Frame polling failed", error);
    } finally {
      if (!this.pollingHalted) {
        this.schedulePoll(false);
      }
    }
  }

  renderFrame() {
    const frame = this.lastFrame;
    if (!frame) {
      return;
    }

    this.updateDisplayedFps();
    this.syncAdaptiveWebglResolution();
    const startedAt = this.rendererProfiling ? performance.now() : 0;

    const hasPendingVisibleAsset = this.visibleStripSlots.some((slot) => {
      const asset = this.assetIndex.get(slot);
      return !asset || !(asset.data instanceof Uint8Array) || asset.loadedBytes < asset.dataLength;
    });
    const sceneInput = this.getSceneRenderInput(frame);
    const videoFrame = frame.povVideoFrame || null;
    const useSceneShader = this.sceneRendererMode === "shader" &&
      !this.force2dFallback &&
      !videoFrame &&
      !hasPendingVisibleAsset &&
      Boolean(sceneInput) &&
      this.renderer.sceneAvailable;
    const beforePixelsAt = this.rendererProfiling ? performance.now() : 0;
    let ledPixels = null;
    if (!useSceneShader && !videoFrame) {
      if (frame.povFrameRgb instanceof Uint8Array) {
        // Raw polar framebuffer path (Super Ventilagon / Voom): bypass sprite compositing.
        ledPixels = computeLedFramePixelsFromRgb(frame.povFrameRgb);
      } else if (hasPendingVisibleAsset && this.lastRenderedLedPixels) {
        ledPixels = this.lastRenderedLedPixels;
      } else {
        ledPixels = computeLedFramePixels(frame, this.assetIndex, this.palette);
      }
    }
    const afterPixelsAt = this.rendererProfiling ? performance.now() : 0;
    if (ledPixels && !hasPendingVisibleAsset) {
      this.lastRenderedLedPixels = ledPixels;
    }
    this.renderCanvasVisibility();
    const beforeRendererAt = this.rendererProfiling ? performance.now() : 0;
    let composition = videoFrame ? "video-h264" : useSceneShader ? "shader" : "cpu";
    let rendered = videoFrame
      ? !this.force2dFallback && this.renderer.renderVideoFrame(videoFrame)
      : useSceneShader
        ? this.renderer.renderScene(sceneInput)
        : !this.force2dFallback && this.renderer.render(ledPixels);
    if (videoFrame && !rendered) {
      throw new Error("H.264 remote video requires WebGL and a decoded 162x256 RGB-luma frame");
    }
    if (!rendered && useSceneShader) {
      composition = "cpu";
      ledPixels = computeLedFramePixels(frame, this.assetIndex, this.palette);
      this.lastRenderedLedPixels = ledPixels;
      rendered = !this.force2dFallback && this.renderer.render(ledPixels);
    }
    if (!videoFrame && (!rendered || this.force2dFallback) && this.fallbackRenderer) {
      this.fallbackRenderer.render(ledPixels || this.lastRenderedLedPixels || computeLedFramePixels(frame, this.assetIndex, this.palette));
    }
    const afterRendererAt = this.rendererProfiling ? performance.now() : 0;
    if (this.rendererProfiling) {
      this.recordRenderProfile({
        renderer: rendered && !this.force2dFallback
          ? composition === "shader" ? "scene-webgl" : "webgl"
          : "canvas",
        composition,
        totalMs: afterRendererAt - startedAt,
        computePixelsMs: afterPixelsAt - beforePixelsAt,
        rendererMs: afterRendererAt - beforeRendererAt,
        rendererDetail: rendered && !this.force2dFallback
          ? this.renderer.lastProfile
          : this.fallbackRenderer?.lastProfile || null,
      });
    }
    this.renderStatus();
    this.renderInspectors(frame);
  }

  getSceneRenderInput(frame) {
    if (!frame?.sceneBytes || !frame.sceneKind || frame.povFrameRgb instanceof Uint8Array || frame.povVideoFrame) {
      return null;
    }
    return {
      sceneKind: frame.sceneKind,
      sceneBytes: frame.sceneBytes,
      assetIndex: this.assetIndex,
      assetVersion: this.assetVersion,
      palette: this.palette,
      paletteVersion: this.paletteUploadVersion,
      frameNumber: frame.frame || 0,
      columnOffset: frame.column_offset || 0,
    };
  }

  async runRendererComparison() {
    if (this.rendererComparisonRunning) {
      return;
    }
    const frame = this.lastFrame;
    const sceneInput = this.getSceneRenderInput(frame);
    if (!frame || !sceneInput || !this.renderer.sceneAvailable || this.force2dFallback) {
      this.lastRendererComparison = {
        error: this.force2dFallback
          ? "Switch off the 2D renderer to compare GPU composition."
          : "This frame has no legacy-sprite or VS2 scene payload for the shader.",
      };
      this.renderRendererComparison();
      return;
    }
    const hasPendingVisibleAsset = this.visibleStripSlots.some((slot) => {
      const asset = this.assetIndex.get(slot);
      return !asset || !(asset.data instanceof Uint8Array) || asset.loadedBytes < asset.dataLength;
    });
    if (hasPendingVisibleAsset) {
      this.lastRendererComparison = { error: "Waiting for the visible image strips to load." };
      this.renderRendererComparison();
      return;
    }

    this.rendererComparisonRunning = true;
    this.lastRendererComparison = { running: true };
    this.renderRendererComparison();
    await new Promise((resolve) => window.requestAnimationFrame(resolve));
    const samples = 24;
    const cpuTotals = [];
    const cpuCompose = [];
    const shaderTotals = [];
    try {
      // Warm both pipelines so lazy program/texture allocation is not part of
      // the result. gl.finish is deliberately used only in this explicit
      // benchmark; normal-frame profiling remains asynchronous.
      this.renderer.render(computeLedFramePixels(frame, this.assetIndex, this.palette));
      this.renderer.finish();
      this.renderer.renderScene(sceneInput);
      this.renderer.finish();
      const expectedPixels = computeLedFramePixels(frame, this.assetIndex, this.palette);
      const shaderPixels = this.renderer.readScenePixels();
      const shaderCore = globalThis.VentilastationSceneShaderCore;
      const packedScene = sceneInput.sceneKind === "vs2"
        ? shaderCore.packSceneVs2(sceneInput.sceneBytes)
        : shaderCore.packSceneLegacy(sceneInput.sceneBytes);
      const softwarePixels = shaderCore.renderSceneSoftware({
        strips: shaderCore.packStrips(this.assetIndex),
        palette: shaderCore.packPalette(this.palette),
        sceneData: packedScene,
        stars: shaderCore.packStars(shaderCore.computeStarPositions(sceneInput.frameNumber)),
        deepspace: shaderCore.packDeepspace(),
        columnOffset: sceneInput.columnOffset,
      });
      let parityMismatches = 0;
      let firstParityMismatch = null;
      let softwareParityMismatches = 0;
      if (!shaderPixels || shaderPixels.length !== expectedPixels.length) {
        parityMismatches = -1;
      } else {
        for (let index = 0; index < expectedPixels.length; index += 1) {
          if (shaderPixels[index] !== expectedPixels[index]) {
            parityMismatches += 1;
            if (!firstParityMismatch) {
              firstParityMismatch = {
                column: Math.floor(index / 4 / 54),
                led: Math.floor(index / 4) % 54,
                channel: index % 4,
                expected: Array.from(expectedPixels.subarray(index - (index % 4), index - (index % 4) + 4)),
                shader: Array.from(shaderPixels.subarray(index - (index % 4), index - (index % 4) + 4)),
              };
            }
          }
        }
      }
      for (let index = 0; index < expectedPixels.length; index += 1) {
        if (softwarePixels[index] !== expectedPixels[index]) {
          softwareParityMismatches += 1;
        }
      }
      if (firstParityMismatch && this.palette instanceof Uint8Array) {
        const findPaletteMatches = (rgba) => {
          const matches = [];
          for (let paletteIndex = 0; paletteIndex * 1024 + 1024 <= this.palette.length; paletteIndex += 1) {
            for (let colorIndex = 0; colorIndex < 256; colorIndex += 1) {
              const base = (paletteIndex * 256 + colorIndex) * 4;
              if (this.palette[base + 3] === rgba[0] &&
                  this.palette[base + 2] === rgba[1] &&
                  this.palette[base + 1] === rgba[2]) {
                matches.push([paletteIndex, colorIndex]);
              }
            }
          }
          return matches;
        };
        firstParityMismatch.expectedPaletteMatches = findPaletteMatches(firstParityMismatch.expected);
        firstParityMismatch.shaderPaletteMatches = findPaletteMatches(firstParityMismatch.shader);
        const expectedPaletteEntry = firstParityMismatch.expectedPaletteMatches[0];
        if (expectedPaletteEntry) {
          firstParityMismatch.gpuPaletteTexel = Array.from(
            this.renderer.readScenePaletteEntry(expectedPaletteEntry[0], expectedPaletteEntry[1]) || [],
          );
        }
      }

      for (let index = 0; index < samples; index += 1) {
        const startedAt = performance.now();
        const ledPixels = computeLedFramePixels(frame, this.assetIndex, this.palette);
        const afterComposeAt = performance.now();
        this.renderer.render(ledPixels);
        this.renderer.finish();
        cpuCompose.push(afterComposeAt - startedAt);
        cpuTotals.push(performance.now() - startedAt);
      }
      for (let index = 0; index < samples; index += 1) {
        const startedAt = performance.now();
        this.renderer.renderScene(sceneInput);
        this.renderer.finish();
        shaderTotals.push(performance.now() - startedAt);
      }
      const average = (values) => values.reduce((sum, value) => sum + value, 0) / values.length;
      const cpuTotalMs = average(cpuTotals);
      const shaderTotalMs = average(shaderTotals);
      this.lastRendererComparison = {
        samples,
        sceneKind: sceneInput.sceneKind,
        cpuTotalMs,
        cpuComposeMs: average(cpuCompose),
        shaderTotalMs,
        speedup: shaderTotalMs > 0 ? cpuTotalMs / shaderTotalMs : null,
        parityMismatches,
        firstParityMismatch,
        softwareParityMismatches,
      };
      this.addDiagnostic("renderer.comparison", this.lastRendererComparison);
    } catch (error) {
      this.lastRendererComparison = { error: error?.message || String(error) };
    } finally {
      this.rendererComparisonRunning = false;
      this.renderRendererComparison();
      if (this.lastFrame) {
        this.renderFrame();
      }
    }
  }

  renderRendererComparison() {
    const element = this.elements.rendererComparison;
    const button = this.elements.runRendererComparison;
    if (button) {
      button.disabled = this.rendererComparisonRunning;
    }
    if (!element) {
      return;
    }
    const result = this.lastRendererComparison;
    if (!result) {
      element.textContent = "Runs 24 synchronized frames through both full rendering paths on this device.";
    } else if (result.running) {
      element.textContent = "Comparing CPU and shader paths…";
    } else if (result.error) {
      element.textContent = result.error;
    } else {
      const parity = result.parityMismatches === 0
        ? "pixel parity pass"
        : result.parityMismatches < 0
          ? "parity readback unavailable"
          : `${result.parityMismatches} mismatched channels`;
      element.textContent = `${result.sceneKind.toUpperCase()} · CPU ${formatProfileMs(result.cpuTotalMs)} frame (${formatProfileMs(result.cpuComposeMs)} compositor) · Shader ${formatProfileMs(result.shaderTotalMs)} frame · ${result.speedup?.toFixed(2) || "--"}× · ${parity}`;
    }
  }

  updateDisplayedFps() {
    const now = performance.now();
    if (this.lastRenderAt !== null) {
      const elapsedMs = now - this.lastRenderAt;
      if (elapsedMs > 0) {
        const instantaneousFps = 1000 / elapsedMs;
        this.pendingMinFps = this.pendingMinFps === null
          ? instantaneousFps
          : Math.min(this.pendingMinFps, instantaneousFps);
      }
    }

    if (this.lastFpsDisplayUpdateAt === null) {
      this.lastFpsDisplayUpdateAt = now;
    }

    if (this.displayedFps === null && this.pendingMinFps !== null) {
      this.displayedFps = this.pendingMinFps;
      this.pendingMinFps = null;
      this.lastFpsDisplayUpdateAt = now;
    } else if (this.pendingMinFps !== null && now - this.lastFpsDisplayUpdateAt >= FPS_DISPLAY_INTERVAL_MS) {
      this.displayedFps = this.pendingMinFps;
      this.pendingMinFps = null;
      this.lastFpsDisplayUpdateAt = now;
    }

    if (now < this.lastFpsDisplayUpdateAt) {
      this.lastFpsDisplayUpdateAt = now;
      this.pendingMinFps = null;
    }

    this.lastRenderAt = now;
  }

  recordRenderProfile(sample) {
    const stampedSample = {
      at: performance.now(),
      isFullscreen: this.isFullscreen,
      viewport: {
        width: window.innerWidth,
        height: window.innerHeight,
        devicePixelRatio: window.devicePixelRatio || 1,
      },
      ...sample,
    };
    this.renderProfileSamples.push(stampedSample);
    if (this.renderProfileSamples.length > RENDER_PROFILE_SAMPLE_LIMIT) {
      this.renderProfileSamples.shift();
    }
    if (this.isFullscreen) {
      this.fullscreenRenderProfileSamples.push(stampedSample);
      if (this.fullscreenRenderProfileSamples.length > RENDER_PROFILE_SAMPLE_LIMIT) {
        this.fullscreenRenderProfileSamples.shift();
      }
    }
  }

  getRenderProfileSnapshot() {
    if (!this.rendererProfiling) {
      return null;
    }
    return buildRenderProfileSnapshot(this.renderProfileSamples);
  }

  getFullscreenRenderProfileSnapshot() {
    if (!this.rendererProfiling) {
      return null;
    }
    if (this.isFullscreen) {
      return buildRenderProfileSnapshot(this.fullscreenRenderProfileSamples);
    }
    return this.lastFullscreenRenderProfile;
  }

  getAssetFrameImage(asset, frameNumber) {
    if (!asset || !(asset.data instanceof Uint8Array) || asset.loadedBytes < asset.dataLength || !(this.palette instanceof Uint8Array)) {
      return null;
    }

    const cached = this.assetRenderCache.get(asset.slot);
    if (cached && cached.asset === asset && cached.paletteVersion === this.paletteVersion) {
      return cached.frames[frameNumber % cached.frames.length] || null;
    }

    const frames = this.decodeAssetFrames(asset);
    this.assetRenderCache.set(asset.slot, {
      asset,
      frames,
      paletteVersion: this.paletteVersion,
    });
    return frames[frameNumber % frames.length] || null;
  }

  decodeAssetFrames(asset) {
    const frames = [];
    const totalFrames = Math.max(asset.frames || 1, 1);
    const bytesPerFrame = asset.width * asset.height;
    const paletteBase = (asset.palette || 0) * 256 * 4;

    for (let frameIndex = 0; frameIndex < totalFrames; frameIndex += 1) {
      const canvas = document.createElement("canvas");
      canvas.width = asset.width;
      canvas.height = asset.height;
      const context = canvas.getContext("2d");
      const imageData = context.createImageData(asset.width, asset.height);
      const frameOffset = frameIndex * bytesPerFrame;

      for (let x = 0; x < asset.width; x += 1) {
        for (let y = 0; y < asset.height; y += 1) {
          const colorIndex = asset.data[frameOffset + x * asset.height + y];
          const dest = (y * asset.width + x) * 4;
          if (colorIndex === 255) {
            imageData.data[dest + 3] = 0;
            continue;
          }
          const paletteOffset = paletteBase + colorIndex * 4;
          imageData.data[dest] = this.palette[paletteOffset + 3] || 0;
          imageData.data[dest + 1] = this.palette[paletteOffset + 2] || 0;
          imageData.data[dest + 2] = this.palette[paletteOffset + 1] || 0;
          imageData.data[dest + 3] = 255;
        }
      }

      context.putImageData(imageData, 0, 0);
      frames.push(canvas);
    }

    return frames;
  }

  renderStatus() {
    this.elements.buttonMask.textContent =
      `J1 0x${this.currentInput.joy1.toString(16).padStart(2, "0")} ` +
      `J2 0x${this.currentInput.joy2.toString(16).padStart(2, "0")} ` +
      `X 0x${this.currentInput.extra.toString(16).padStart(2, "0")}`;
    if (this.elements.gamepadStatus) {
      this.elements.gamepadStatus.textContent = this.activeGamepadIndex === null
        ? "Gamepad none"
        : this.connectedGamepadCount > 1
          ? `Gamepads ${this.connectedGamepadCount} (primary ${this.activeGamepadIndex + 1})`
          : `Gamepad ${this.activeGamepadIndex + 1}`;
    }
    if (this.elements.webglScaleStatus) {
      this.elements.webglScaleStatus.textContent = this.webglResolutionScalePreference === WEBGL_RESOLUTION_SCALE_AUTO
        ? `Scale Auto ${Math.round(this.webglResolutionScale * 100)}%`
        : `Scale ${Math.round(this.webglResolutionScale * 100)}%`;
    }
    if (this.elements.sceneRendererStatus) {
      this.elements.sceneRendererStatus.textContent = this.sceneRendererMode === "shader"
        ? this.renderer.sceneAvailable ? "Compositor shader" : "Compositor CPU fallback"
        : "Compositor CPU";
    }
    if (this.elements.frameCounter) {
      this.elements.frameCounter.textContent = this.displayedFps === null
        ? "FPS --"
        : `FPS ${this.displayedFps.toFixed(1)}`;
    }
  }

  renderRuntimeStatus() {
    const { runtimeBanner, runtimeMessage } = this.elements;
    runtimeBanner.classList.remove("is-error", "is-warning");

    if (this.executionError) {
      runtimeBanner.hidden = false;
      runtimeBanner.classList.add("is-error");
      runtimeMessage.textContent = `${this.executionError.title}\n\n${this.executionError.message}`;
      return;
    }

    if (this.runtime.error) {
      runtimeBanner.hidden = false;
      runtimeBanner.classList.add("is-error");
      runtimeMessage.textContent = this.runtime.source === "error"
        ? `Runtime initialization failed.\n\n${this.runtime.error.stack || this.runtime.error.message || String(this.runtime.error)}`
        : (this.runtime.error.stack || this.runtime.error.message || String(this.runtime.error));
      return;
    }

    runtimeBanner.hidden = true;
    runtimeMessage.textContent = "";
  }

  renderSceneError() {
    const { sceneErrorBanner, sceneErrorTitle, sceneErrorMessage } = this.elements;
    if (!sceneErrorBanner || !sceneErrorTitle || !sceneErrorMessage) {
      return;
    }

    if (!this.executionError) {
      sceneErrorBanner.hidden = true;
      sceneErrorTitle.textContent = "Scene lifecycle error";
      sceneErrorMessage.textContent = "";
      return;
    }

    sceneErrorBanner.hidden = false;
    sceneErrorTitle.textContent = this.executionError.title;
    sceneErrorMessage.textContent = this.executionError.message;
  }

  renderMemorySummary(error = null) {
    if (!this.elements.memorySummary) {
      return;
    }
    const memory = this.lastMemorySnapshot;
    let summary;
    if (memory) {
      const usedPercent = typeof memory.gc?.usedPercent === "number"
        ? `${memory.gc.usedPercent.toFixed(1)}%`
        : "--";
      summary = [
        ["Heap Used", `${formatBytes(memory.gc?.allocBytes)} / ${usedPercent}`],
        ["Heap Free", formatBytes(memory.gc?.freeBytes)],
      ];
      if (memory.proxyRefInfo) {
        summary.push([
          "Proxy Refs",
          `${memory.proxyRefInfo.usedSlots ?? "--"}/${memory.proxyRefInfo.totalSlots ?? "--"} next ${memory.proxyRefInfo.nextSlot ?? "--"}`,
        ]);
      }
    } else if (error) {
      summary = [["Heap", "Snapshot failed"]];
    } else if (typeof this.adapter.memorySnapshot === "function") {
      summary = [["Heap", "Not sampled"]];
    } else {
      summary = [["Heap", "Unavailable"]];
    }
    this.elements.memorySummary.innerHTML = summary.map(([label, value]) => `
      <div class="summary-card">
        <strong>${label}</strong>
        <span>${value}</span>
      </div>
    `).join("");
  }

  renderInspectors(frame) {
    if (!this.inspectorOpen) {
      return;
    }
    const profile = this.getRenderProfileSnapshot();
    const fullscreenProfile = this.getFullscreenRenderProfileSnapshot();
    const summary = [
      ["Sprites", frame.sprites.length],
      ["Assets", this.assetIndex.size],
      ["Events", frame.events.length],
      ["Column Offset", frame.column_offset],
      ["Gamma", frame.gamma_mode],
      // RGB-only remote frames do not carry the local-runtime button field.
      // Show the browser's canonical input state in that case.
      ["Buttons", `0x${(Number.isInteger(frame.buttons) ? frame.buttons : this.currentButtons).toString(16).padStart(2, "0")}`],
      ["Gamepad", this.activeGamepadIndex === null
        ? "None"
        : this.connectedGamepadCount > 1
          ? `${this.connectedGamepadCount} controllers (primary ${this.activeGamepadIndex + 1})`
          : `Controller ${this.activeGamepadIndex + 1}`],
      ["Renderer", this.force2dFallback ? "2D fallback" : this.renderer.available ? "WebGL" : "2D fallback"],
      ["Compositor", this.sceneRendererMode === "shader"
        ? this.renderer.sceneAvailable ? "GPU shader" : "CPU fallback"
        : "CPU (existing)"],
      ["Fullscreen", this.isFullscreen ? "Active" : "Windowed"],
      ["WebGL Scale", this.webglResolutionScalePreference === WEBGL_RESOLUTION_SCALE_AUTO
        ? `Auto (${Math.round(this.webglResolutionScale * 100)}%)`
        : `${Math.round(this.webglResolutionScale * 100)}%`],
    ];
    if (frame.videoMetadata) {
      summary.push(
        ["Remote Video", `${frame.videoMetadata.codec || "H264"} ${frame.videoMetadata.width}x${frame.videoMetadata.height}`],
        ["Decoded FPS", this.adapter.videoStats?.framesPerSecond || "--"],
        ["Video Bytes", formatBytes(this.adapter.videoStats?.bytesReceived)],
        ["Video Drops", this.adapter.videoStats?.framesDropped ?? "--"],
      );
    }
    if (profile) {
      summary.push(
        ["Profile Samples", profile.sampleCount],
        ["Frame Total", `${formatProfileMs(profile.totalMs?.avg)} avg / ${formatProfileMs(profile.totalMs?.max)} max`],
        ["Pixels", `${formatProfileMs(profile.computePixelsMs?.avg)} avg / ${formatProfileMs(profile.computePixelsMs?.max)} max`],
        ["Renderer Cost", `${formatProfileMs(profile.rendererMs?.avg)} avg / ${formatProfileMs(profile.rendererMs?.max)} max`],
      );
      if (profile.renderer === "webgl") {
        summary.push(
          ["Color Expand", `${formatProfileMs(profile.detail.colorExpandMs?.avg)} avg / ${formatProfileMs(profile.detail.colorExpandMs?.max)} max`],
          ["Upload", `${formatProfileMs(profile.detail.uploadMs?.avg)} avg / ${formatProfileMs(profile.detail.uploadMs?.max)} max`],
          ["Draw Submit", `${formatProfileMs(profile.detail.drawSubmitMs?.avg)} avg / ${formatProfileMs(profile.detail.drawSubmitMs?.max)} max`],
        );
      } else if (profile.renderer === "scene-webgl") {
        summary.push(
          ["GPU Scene", `${formatProfileMs(profile.detail.sceneMs?.avg)} avg / ${formatProfileMs(profile.detail.sceneMs?.max)} max`],
          ["Scene Pack", `${formatProfileMs(profile.detail.scenePackMs?.avg)} avg / ${formatProfileMs(profile.detail.scenePackMs?.max)} max`],
          ["Scene Upload", `${formatProfileMs(profile.detail.sceneDynamicUploadMs?.avg)} avg / ${formatProfileMs(profile.detail.sceneDynamicUploadMs?.max)} max`],
          ["Scene Submit", `${formatProfileMs(profile.detail.sceneDrawSubmitMs?.avg)} avg / ${formatProfileMs(profile.detail.sceneDrawSubmitMs?.max)} max`],
          ["Ring Submit", `${formatProfileMs(profile.detail.ringDrawSubmitMs?.avg)} avg / ${formatProfileMs(profile.detail.ringDrawSubmitMs?.max)} max`],
        );
      } else {
        summary.push([
          "Canvas Draw",
          `${formatProfileMs(profile.detail.drawMs?.avg)} avg / ${formatProfileMs(profile.detail.drawMs?.max)} max`,
        ]);
      }
    }
    if (fullscreenProfile) {
      summary.push(
        ["FS Samples", fullscreenProfile.sampleCount],
        ["FS Frame Total", `${formatProfileMs(fullscreenProfile.totalMs?.avg)} avg / ${formatProfileMs(fullscreenProfile.totalMs?.max)} max`],
        ["FS Renderer", `${formatProfileMs(fullscreenProfile.rendererMs?.avg)} avg / ${formatProfileMs(fullscreenProfile.rendererMs?.max)} max`],
      );
      if (fullscreenProfile.renderer === "webgl") {
        summary.push(
          ["FS Upload", `${formatProfileMs(fullscreenProfile.detail.uploadMs?.avg)} avg / ${formatProfileMs(fullscreenProfile.detail.uploadMs?.max)} max`],
          ["FS Draw Submit", `${formatProfileMs(fullscreenProfile.detail.drawSubmitMs?.avg)} avg / ${formatProfileMs(fullscreenProfile.detail.drawSubmitMs?.max)} max`],
        );
      } else if (fullscreenProfile.renderer === "scene-webgl") {
        summary.push(
          ["FS GPU Scene", `${formatProfileMs(fullscreenProfile.detail.sceneMs?.avg)} avg / ${formatProfileMs(fullscreenProfile.detail.sceneMs?.max)} max`],
          ["FS Scene Pack", `${formatProfileMs(fullscreenProfile.detail.scenePackMs?.avg)} avg / ${formatProfileMs(fullscreenProfile.detail.scenePackMs?.max)} max`],
        );
      } else {
        summary.push([
          "FS Canvas Draw",
          `${formatProfileMs(fullscreenProfile.detail.drawMs?.avg)} avg / ${formatProfileMs(fullscreenProfile.detail.drawMs?.max)} max`,
        ]);
      }
    }
    this.elements.runtimeSummary.innerHTML = summary.map(([label, value]) => `
      <div class="summary-card">
        <strong>${label}</strong>
        <span>${value}</span>
      </div>
    `).join("");

    const frameShape = this.describeFrame(frame);
    this.lastFrameShape = frameShape;
    this.refreshCopyDiagnostics();
  }

  describeFrame(frame) {
    const firstAsset = this.assetIndex.size ? this.assetIndex.values().next().value : null;
    const renderProfile = this.getRenderProfileSnapshot();
    const fullscreenRenderProfile = this.getFullscreenRenderProfileSnapshot();
    const dpr = window.devicePixelRatio || 1;
    return {
      frameType: typeof frame,
      keys: Object.keys(frame || {}),
      paletteType: frame.palette?.constructor?.name,
      paletteLength: frame.palette_length ?? this.palette?.length,
      paletteVersion: frame.palette_version ?? this.paletteVersion,
      paletteLoadedBytes: this.paletteLoadedBytes,
      sceneRenderer: {
        mode: this.sceneRendererMode,
        available: this.renderer.sceneAvailable,
        sceneKind: frame.sceneKind || null,
        sceneBytes: frame.sceneBytes?.length ?? null,
        comparison: this.lastRendererComparison,
      },
      spriteCount: Array.isArray(frame.sprites) ? frame.sprites.length : null,
      assetCount: this.assetIndex.size,
      eventCount: Array.isArray(frame.events) ? frame.events.length : null,
      remoteVideo: frame.videoMetadata ? {
        ...frame.videoMetadata,
        stats: this.adapter.videoStats || null,
      } : null,
      firstSprite: Array.isArray(frame.sprites) && frame.sprites.length ? frame.sprites[0] : null,
      firstAsset: firstAsset ? {
        ...firstAsset,
        data: `[${firstAsset.data?.length ?? 0} bytes]`,
      } : null,
      viewport: {
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
        devicePixelRatio: dpr,
        isFullscreen: this.isFullscreen,
      },
      webglResolutionScalePreference: this.webglResolutionScalePreference,
      webglResolutionScale: this.webglResolutionScale,
      webglCanvas: this.canvas ? {
        clientWidth: this.canvasDisplaySize.width,
        clientHeight: this.canvasDisplaySize.height,
        width: this.canvas.width,
        height: this.canvas.height,
      } : null,
      fallbackCanvas: this.fallbackCanvas ? {
        clientWidth: this.fallbackCanvasDisplaySize.width,
        clientHeight: this.fallbackCanvasDisplaySize.height,
        width: this.fallbackCanvas.width,
        height: this.fallbackCanvas.height,
      } : null,
      renderProfile,
      fullscreenRenderProfile,
      memorySnapshot: this.lastMemorySnapshot,
      collectedMemorySnapshot: this.lastCollectedMemorySnapshot,
      memorySnapshotHistory: this.memorySnapshotHistory.slice(),
      traceFlags: this.traceFlags,
    };
  }

  addDiagnostic(type, payload) {
    this.diagnostics.push({
      at: new Date().toISOString(),
      type,
      payload,
    });
    if (this.diagnostics.length > 30) {
      this.diagnostics.shift();
    }
  }

  buildDiagnosticBundle(frameShape, diagnostics) {
    const exportedDiagnostics = this.rendererProfiling
      ? diagnostics.filter((entry) => (
        entry?.type === "renderer.profiling" ||
        entry?.type === "renderer.mode" ||
        entry?.type === "fullscreen.state" ||
        entry?.type === "fullscreen.error" ||
        entry?.type === "timing.resync" ||
        entry?.type === "timing.catchup" ||
        entry?.type === "frame.error"
      ))
      : diagnostics;
    const bundle = {
      generatedAt: new Date().toISOString(),
      runtimeStatus: this.elements.runtimeMessage.textContent,
      adapterName: this.adapter.name,
      adapterSource: this.runtime.source,
      currentButtons: this.currentButtons,
      currentInput: this.currentInput,
      runtimeError: this.runtime.error ? {
        message: this.runtime.error.message || String(this.runtime.error),
        stack: this.runtime.error.stack || null,
      } : null,
      executionError: this.executionError ? {
        title: this.executionError.title,
        message: this.executionError.message,
        isSceneLifecycleError: this.executionError.isSceneLifecycleError,
      } : null,
      frameShape,
      memorySnapshot: this.lastMemorySnapshot,
      collectedMemorySnapshot: this.lastCollectedMemorySnapshot,
      memorySnapshotHistory: this.memorySnapshotHistory.slice(),
      traceFlags: this.traceFlags,
      diagnostics: exportedDiagnostics,
    };
    return JSON.stringify(bundle, null, 2);
  }
}

async function resolveRuntime() {
  if (isRemoteMode()) {
    try {
      const remoteAdapter = new RemoteWorkbenchAdapter();
      await remoteAdapter.init();
      return { adapter: remoteAdapter, source: "remote" };
    } catch (error) {
      console.error("Failed to initialize physical workbench adapter", error);
      return { adapter: new FailedRuntimeAdapter(), source: "error", error };
    }
  }
  const adapter = window.VentilastationRuntimeAdapter;
  if (adapter && (typeof adapter.setInput === "function" || typeof adapter.setButtons === "function") &&
      typeof adapter.exportFrame === "function") {
    return { adapter, source: "preloaded" };
  }
  const createWasmAdapter = window.createVentilastationWasmAdapter;
  if (typeof createWasmAdapter === "function") {
    try {
      const wasmAdapter = await createWasmAdapter();
      if (wasmAdapter && (typeof wasmAdapter.setInput === "function" || typeof wasmAdapter.setButtons === "function") &&
          typeof wasmAdapter.exportFrame === "function") {
        return { adapter: wasmAdapter, source: "wasm" };
      }
    } catch (error) {
      console.error("Failed to initialize Ventilastation WASM adapter", error);
      return { adapter: new FailedRuntimeAdapter(), source: "error", error };
    }
  }
  return {
    adapter: new FailedRuntimeAdapter(),
    source: "error",
    error: new Error(
      "No Ventilastation WASM bridge available. " +
      "Expected window.VentilastationWasmBridge or window.createVentilastationWasmBridge()."
    ),
  };
}

resolveRuntime().then((runtime) => {
  new BrowserHostApp(runtime).start();
});
