import { EmbeddedPiskelEditor } from "./piskel-embed.js?v=20260622d";
import {
  buildPackageForGame,
  probePackageServer,
  pushPackage,
} from "./package-builder.js";
import {
  findStripedefItemForPath,
  getSerializedSpritePath,
  isSerializedSpritePath,
  isSpriteAssetPath,
  maybeRebuildRomForPath,
} from "./workspace-rom-builder.js";

const MONACO_BASE_URL = "./vendor/monaco/vs";
const WORKSPACE_ROOT_CANDIDATES = ["."];
const WORKSPACE_READY_RETRY_COUNT = 20;
const WORKSPACE_READY_RETRY_DELAY_MS = 150;
const EDITABLE_EXTENSIONS = new Set([
  ".py",
  ".pyi",
  ".md",
  ".txt",
  ".json",
  ".yaml",
  ".yml",
  ".toml",
  ".ini",
  ".cfg",
  ".js",
  ".mjs",
  ".cjs",
  ".css",
  ".html",
  ".xml",
  ".csv",
]);

let monacoLoadPromise = null;
const workerUrlCache = new Map();

function getMonacoBaseUrl() {
  return new URL(`${MONACO_BASE_URL}/`, window.location.href).href.replace(/\/$/u, "");
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function extensionOf(path) {
  const match = /(\.[^.\/]+)$/u.exec(String(path || ""));
  return match ? match[1].toLowerCase() : "";
}

function isEditableTextPath(path) {
  return EDITABLE_EXTENSIONS.has(extensionOf(path));
}

function isVisibleWorkspacePath(path) {
  return !isSerializedSpritePath(path) && (isEditableTextPath(path) || isSpriteAssetPath(path));
}

function inferLanguage(path) {
  const extension = extensionOf(path);
  switch (extension) {
    case ".py":
    case ".pyi":
      return "python";
    case ".md":
      return "markdown";
    case ".json":
      return "json";
    case ".yaml":
    case ".yml":
      return "yaml";
    case ".toml":
    case ".ini":
    case ".cfg":
      return "ini";
    case ".js":
    case ".mjs":
    case ".cjs":
      return "javascript";
    case ".css":
      return "css";
    case ".html":
      return "html";
    case ".xml":
      return "xml";
    default:
      return "plaintext";
  }
}

function inferDisplayLanguage(path) {
  if (isSpriteAssetPath(path)) {
    return "Piskel PNG";
  }
  const language = inferLanguage(path);
  if (language === "python") {
    return "Micropython";
  }
  return language;
}

function trimWorkspaceRoot(path, workspaceRoot = "") {
  const normalized = String(path || "").replace(/^\/+/u, "");
  if (!workspaceRoot || workspaceRoot === ".") {
    return normalized;
  }
  if (normalized === workspaceRoot) {
    return "";
  }
  if (normalized.startsWith(`${workspaceRoot}/`)) {
    return normalized.slice(workspaceRoot.length + 1);
  }
  return normalized;
}

function pathIsWithinWorkspace(path, workspaceRoot = "") {
  const normalized = String(path || "").replace(/^\/+/u, "");
  if (!workspaceRoot || workspaceRoot === ".") {
    return true;
  }
  return normalized === workspaceRoot || normalized.startsWith(`${workspaceRoot}/`);
}

function resolveWorkspaceFilePath(workspaceRoot, relativePath) {
  const normalizedRelativePath = String(relativePath || "").replace(/^\/+/u, "");
  if (!workspaceRoot || workspaceRoot === ".") {
    return normalizedRelativePath;
  }
  return `${workspaceRoot}/${normalizedRelativePath}`;
}

function createMonacoWorkerUrl() {
  if (workerUrlCache.has("default")) {
    return workerUrlCache.get("default");
  }
  const monacoBaseUrl = getMonacoBaseUrl();
  const workerSource = [
    `self.MonacoEnvironment = { baseUrl: ${JSON.stringify(`${monacoBaseUrl}/`)} };`,
    `importScripts(${JSON.stringify(`${monacoBaseUrl}/base/worker/workerMain.js`)});`,
  ].join("\n");
  const url = URL.createObjectURL(new Blob([workerSource], { type: "text/javascript" }));
  workerUrlCache.set("default", url);
  return url;
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error(`Failed to load script: ${src}`));
    document.head.appendChild(script);
  });
}

function loadMonaco() {
  if (window.monaco?.editor) {
    return Promise.resolve(window.monaco);
  }
  if (monacoLoadPromise) {
    return monacoLoadPromise;
  }
  monacoLoadPromise = (async () => {
    if (typeof window.require !== "function") {
      await loadScript(`${MONACO_BASE_URL}/loader.js`);
    }
    window.MonacoEnvironment = {
      getWorkerUrl() {
        return createMonacoWorkerUrl();
      },
    };
    return new Promise((resolve, reject) => {
      window.require.config({
        paths: {
          vs: MONACO_BASE_URL,
        },
      });
      window.require(["vs/editor/editor.main"], () => {
        resolve(window.monaco);
      }, reject);
    });
  })();
  return monacoLoadPromise;
}

function fileTypeForPath(path) {
  return isSpriteAssetPath(path) ? "sprite" : "text";
}

function makeSpriteMetaLabel(spriteState) {
  if (spriteState?.manifestItem?.frames > 1) {
    return `${spriteState.manifestItem.frames} frames`;
  }
  return "1 frame";
}

function normalizeWorkspacePath(path) {
  return String(path || "")
    .replace(/\\/g, "/")
    .replace(/^\/+/u, "")
    .replace(/\/{2,}/gu, "/")
    .replace(/\/$/u, "");
}

function getPathSegments(path) {
  return normalizeWorkspacePath(path).split("/").filter(Boolean);
}

function getGameKeyFromPath(path) {
  const parts = getPathSegments(path);
  if (parts.length < 2) {
    return null;
  }
  return `${parts[0]}/${parts[1]}`;
}

function getGameInfoFromKey(gameKey) {
  const parts = getPathSegments(gameKey);
  if (parts.length < 2) {
    return null;
  }
  return {
    key: `${parts[0]}/${parts[1]}`,
    group: parts[0],
    slug: parts[1],
  };
}

function gameKeyToSlug(gameKey) {
  const info = getGameInfoFromKey(gameKey);
  if (!info) {
    return null;
  }
  return `${info.group}.${info.slug}`;
}

function trimGameRoot(path, gameKey) {
  const normalizedPath = normalizeWorkspacePath(path);
  const normalizedRoot = normalizeWorkspacePath(gameKey);
  if (!normalizedRoot || normalizedPath === normalizedRoot) {
    return normalizedPath;
  }
  if (normalizedPath.startsWith(`${normalizedRoot}/`)) {
    return normalizedPath.slice(normalizedRoot.length + 1);
  }
  return normalizedPath;
}

function slugToIdentifier(slug) {
  const cleaned = String(slug || "")
    .replace(/[^a-zA-Z0-9]+/g, " ")
    .trim();
  if (!cleaned) {
    return "NewGame";
  }
  return cleaned
    .split(/\s+/u)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
}

function ensurePyModuleName(name, fallback = "new_file.py") {
  const trimmed = String(name || "").trim().replace(/^\/+/u, "");
  if (!trimmed) {
    return fallback;
  }
  return trimmed.endsWith(".py") ? trimmed : `${trimmed}.py`;
}

function ensurePngName(name, fallback = "new_strip.png") {
  const trimmed = String(name || "").trim().replace(/^\/+/u, "");
  if (!trimmed) {
    return fallback;
  }
  return trimmed.endsWith(".png") ? trimmed : `${trimmed}.png`;
}

const EMPTY_STRIPE_PNG_BASE64 =
  "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAAEElEQVR4nGNgYGD4DwABBAEAff8GJwAAAABJRU5ErkJggg==";

function imageDataUrlFromBase64(base64) {
  return `data:image/png;base64,${base64}`;
}

function delay(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function isTransientWorkspaceError(error) {
  const message = String(error?.message || error || "");
  return (
    message.includes("WASM worker not initialized") ||
    message.includes("Workspace file API unavailable") ||
    message.includes("Worker restarted")
  );
}

const GAME_MENU_PREVIEW_MAP = new Map();

class WorkspaceIde {
  constructor(api) {
    this.api = api;
    this.workspaceRoot = "";
    this.fileEntries = [];
    this.currentGameKey = null;
    this.textFileStates = new Map();
    this.spriteFileStates = new Map();
    this.spritePreviewUrls = new Map();
    this.gamePreviewUrls = new Map();
    this.currentPath = null;
    this.currentMode = null;
    this.editor = null;
    this.monaco = null;
    this.isApplyingModel = false;
    this.activeDrawer = null;
    this.actionInFlight = false;
    this.activeActionLabel = "";
    this.root = document.querySelector("#editor-panel-shell");
    if (!this.root) {
      return;
    }
    this.elements = {
      gamesList: document.querySelector("#editor-games-list"),
      fileList: document.querySelector("#editor-file-list"),
      surface: document.querySelector("#editor-surface"),
      message: document.querySelector("#editor-message"),
      activeFile: document.querySelector("#editor-active-file"),
      activeMeta: document.querySelector("#editor-active-meta"),
      toggleGamesButton: document.querySelector("#editor-toggle-games-button"),
      toggleFilesButton: document.querySelector("#editor-toggle-files-button"),
      toggleNewButton: document.querySelector("#editor-toggle-new-button"),
      gamesDrawer: document.querySelector("#editor-games-drawer"),
      filesDrawer: document.querySelector("#editor-files-drawer"),
      newDrawer: document.querySelector("#editor-new-drawer"),
      saveButton: document.querySelector("#editor-save-button"),
      runButton: document.querySelector("#editor-run-button"),
      pushButton: document.querySelector("#editor-push-button"),
      newGameButton: document.querySelector("#editor-new-game-button"),
      newSourceButton: document.querySelector("#editor-new-source-button"),
      newStripeButton: document.querySelector("#editor-new-stripe-button"),
      createHelp: document.querySelector("#editor-create-help"),
      createDialog: document.querySelector("#editor-create-dialog"),
      createForm: document.querySelector("#editor-create-form"),
      createTitle: document.querySelector("#editor-create-title"),
      createDescription: document.querySelector("#editor-create-description"),
      createLabel: document.querySelector("#editor-create-label"),
      createInput: document.querySelector("#editor-create-input"),
      createHint: document.querySelector("#editor-create-hint"),
      createCancel: document.querySelector("#editor-create-cancel"),
      createSubmit: document.querySelector("#editor-create-submit"),
    };
    this.textSurface = document.createElement("div");
    this.textSurface.className = "editor-text-surface";
    this.textSurface.hidden = true;
    this.spriteSurface = document.createElement("div");
    this.spriteSurface.className = "editor-sprite-surface";
    this.spriteSurface.hidden = true;
    this.elements.surface?.append(this.textSurface, this.spriteSurface);
    this.piskel = new EmbeddedPiskelEditor(this.spriteSurface, {
      onDirtyChange: (dirty) => this.onSpriteDirtyChange(dirty),
    });
    this.pendingCreateDialogResolver = null;
  }

  async start() {
    if (!this.root) {
      return;
    }
    this.bindUi();
    this.setStatus("Opening workspace");
    this.setMessage("Opening workspace…");
    try {
      await this.refreshFiles({ openDefault: true });
      this.setStatus("Ready");
      if (!this.currentPath) {
        this.setMessage("Select a game, code file, or sprite sheet to start editing.", { ready: false });
      }
    } catch (error) {
      this.setStatus("Workspace failed");
      this.setMessage(
        `The workspace could not be opened. ${error.message || String(error)}`,
        { error: true },
      );
      console.error("Workspace refresh failed", error);
    }
  }

  bindUi() {
    this.elements.toggleGamesButton?.addEventListener("click", () => {
      this.toggleDrawer("games");
    });
    this.elements.toggleFilesButton?.addEventListener("click", () => {
      this.toggleDrawer("files");
    });
    this.elements.toggleNewButton?.addEventListener("click", () => {
      this.toggleDrawer("new");
    });
    this.elements.saveButton?.addEventListener("click", () => {
      void this.runAction("Save failed", () => this.saveCurrentFile());
    });
    this.elements.runButton?.addEventListener("click", () => {
      void this.runAction("Run failed", () => this.saveAndRun());
    });
    this.elements.pushButton?.addEventListener("click", () => {
      void this.runAction("Push failed", () => this.pushToConsole());
    });
    // The push button only appears when this page is served by a
    // Ventilastation base (same origin as the package endpoints).
    this.packageServerAvailable = false;
    void probePackageServer().then((available) => {
      this.packageServerAvailable = available;
      this.updateActionState();
    });
    this.elements.newGameButton?.addEventListener("click", () => {
      void this.runAction("Create game failed", () => this.createNewGame());
    });
    this.elements.newSourceButton?.addEventListener("click", () => {
      void this.runAction("Create source file failed", () => this.createSourceFile());
    });
    this.elements.newStripeButton?.addEventListener("click", () => {
      void this.runAction("Create image stripe failed", () => this.createImageStripe());
    });
    this.elements.createCancel?.addEventListener("click", () => {
      this.closeCreateDialog(null);
    });
    this.elements.createDialog?.addEventListener("cancel", (event) => {
      event.preventDefault();
      this.closeCreateDialog(null);
    });
    this.elements.createForm?.addEventListener("submit", (event) => {
      event.preventDefault();
      this.closeCreateDialog(this.elements.createInput?.value || "");
    });
    window.addEventListener("ventilastation:editor-toggle", (event) => {
      if (!event.detail?.open) {
        return;
      }
      this.editor?.layout();
      if (this.currentMode === "sprite") {
        void this.piskel.focus().catch(() => {});
      }
    });
    document.addEventListener("pointerdown", (event) => {
      if (!this.activeDrawer || !this.root) {
        return;
      }
      const target = event.target;
      const activeToggle = this.getDrawerToggleButton(this.activeDrawer);
      const activeDrawer = this.getDrawerElement(this.activeDrawer);
      if ((activeToggle && activeToggle.contains(target)) || (activeDrawer && activeDrawer.contains(target))) {
        return;
      }
      this.toggleDrawer(this.activeDrawer);
    });
  }

  async runAction(failureLabel, action) {
    if (this.actionInFlight) {
      return;
    }
    this.actionInFlight = true;
    this.activeActionLabel = failureLabel;
    this.updateActionState();
    try {
      await action();
    } catch (error) {
      this.handleError(failureLabel, error);
    } finally {
      this.actionInFlight = false;
      this.activeActionLabel = "";
      this.updateActionState();
    }
  }

  handleError(label, error) {
    console.error(label, error);
    this.setStatus(label);
    this.setMessage(`${label}. ${error.message || String(error)}`, { error: true });
  }

  getDrawerElement(name) {
    if (name === "games") {
      return this.elements.gamesDrawer;
    }
    if (name === "files") {
      return this.elements.filesDrawer;
    }
    if (name === "new") {
      return this.elements.newDrawer;
    }
    return null;
  }

  getDrawerToggleButton(name) {
    if (name === "games") {
      return this.elements.toggleGamesButton;
    }
    if (name === "files") {
      return this.elements.toggleFilesButton;
    }
    if (name === "new") {
      return this.elements.toggleNewButton;
    }
    return null;
  }

  async ensureMonacoLoaded() {
    if (this.editor) {
      return;
    }
    this.setStatus("Loading Monaco");
    this.monaco = await loadMonaco();
    this.editor = this.monaco.editor.create(this.textSurface, {
      value: "",
      language: "python",
      theme: "vs-dark",
      automaticLayout: true,
      minimap: { enabled: false },
      fontSize: 13,
      lineNumbersMinChars: 3,
      padding: { top: 14, bottom: 14 },
      roundedSelection: false,
      scrollBeyondLastLine: false,
      smoothScrolling: true,
      tabSize: 2,
      insertSpaces: true,
    });
    this.editor.onDidChangeModelContent(() => {
      if (this.isApplyingModel || !this.currentPath || this.currentMode !== "text") {
        return;
      }
      const state = this.textFileStates.get(this.currentPath);
      if (!state) {
        return;
      }
      state.dirty = state.model.getValue() !== state.savedContent;
      this.renderFileList();
      this.renderActiveFileState();
      this.updateActionState();
      this.setStatus(state.dirty ? "Unsaved changes" : "Ready");
    });
  }

  async resolveWorkspaceRoot() {
    if (this.workspaceRoot) {
      return this.workspaceRoot;
    }
    let lastError = null;
    for (let attempt = 0; attempt < WORKSPACE_READY_RETRY_COUNT; attempt += 1) {
      for (const candidate of WORKSPACE_ROOT_CANDIDATES) {
        try {
          await this.api.listProjectFiles(candidate);
          this.workspaceRoot = candidate;
          return candidate;
        } catch (error) {
          lastError = error;
          if (!isTransientWorkspaceError(error)) {
            break;
          }
        }
      }
      if (!isTransientWorkspaceError(lastError)) {
        break;
      }
      await delay(WORKSPACE_READY_RETRY_DELAY_MS);
    }
    if (lastError && !isTransientWorkspaceError(lastError)) {
      throw lastError;
    }
    throw new Error(
      `Unable to locate an editable workspace root. Tried: ${WORKSPACE_ROOT_CANDIDATES.join(", ")}`
    );
  }

  async refreshFiles({ openDefault = false } = {}) {
    this.setStatus("Refreshing files");
    const workspaceRoot = await this.resolveWorkspaceRoot();
    const paths = await this.api.listProjectFiles(workspaceRoot);
    this.fileEntries = paths
      .filter((path) => pathIsWithinWorkspace(path, workspaceRoot) && isVisibleWorkspacePath(path))
      .sort((left, right) => left.localeCompare(right));
    if (this.currentGameKey && !this.getGameEntries().some((entry) => entry.key === this.currentGameKey)) {
      this.currentGameKey = null;
    }
    if (!this.currentGameKey) {
      this.currentGameKey = this.pickDefaultGameKey();
    }
    this.renderGamesList();
    this.renderFileList();
    this.renderCreateState();
    if (openDefault) {
      const preferredPath = this.pickDefaultFile();
      if (preferredPath) {
        await this.openFile(preferredPath);
      }
    } else if (this.currentPath && this.fileEntries.includes(this.currentPath)) {
      this.renderActiveFileState();
    }
    this.setStatus("Files refreshed");
  }

  pickDefaultFile() {
    const defaultGameKey = this.pickDefaultGameKey();
    if (defaultGameKey) {
      const mainFile = this.findMainFileForGame(defaultGameKey);
      if (mainFile) {
        return mainFile;
      }
    }
    const firstTextFile = this.fileEntries.find((path) => fileTypeForPath(path) === "text");
    return firstTextFile || this.fileEntries[0] || null;
  }

  getGameEntries() {
    const byKey = new Map();
    for (const path of this.fileEntries) {
      const gameKey = getGameKeyFromPath(path);
      const info = getGameInfoFromKey(gameKey);
      if (!info) {
        continue;
      }
      if (!byKey.has(info.key)) {
        byKey.set(info.key, {
          ...info,
          mainPath: null,
        });
      }
    }
    const entries = Array.from(byKey.values());
    for (const entry of entries) {
      entry.mainPath = this.findMainFileForGame(entry.key);
    }
    entries.sort((left, right) => {
      const groupCompare = left.group.localeCompare(right.group);
      if (groupCompare !== 0) {
        return groupCompare;
      }
      return left.slug.localeCompare(right.slug);
    });
    return entries;
  }

  pickDefaultGameKey() {
    const games = this.getGameEntries();
    return games[0]?.key || null;
  }

  findMainFileForGame(gameKey) {
    const info = getGameInfoFromKey(gameKey);
    if (!info) {
      return null;
    }
    const preferred = `${info.key}/code/${info.slug}.py`;
    if (this.fileEntries.includes(preferred)) {
      return preferred;
    }
    const codePrefix = `${info.key}/code/`;
    const codePythonFile = this.fileEntries.find((path) => path.startsWith(codePrefix) && path.endsWith(".py"));
    if (codePythonFile) {
      return codePythonFile;
    }
    return this.fileEntries.find((path) => path.startsWith(`${info.key}/`)) || null;
  }

  ensureTextFileState(path, content, savedContent, options = {}) {
    const existing = this.textFileStates.get(path);
    if (existing) {
      if (typeof content === "string" && existing.model.getValue() !== content && !existing.dirty) {
        existing.model.setValue(content);
      }
      existing.savedContent = savedContent;
      existing.dirty = Boolean(options.isNew) || existing.model.getValue() !== savedContent;
      existing.isNew = Boolean(options.isNew);
      return existing;
    }
    const uri = this.monaco.Uri.parse(`inmemory://ventilastation/${path}`);
    const model = this.monaco.editor.createModel(content, inferLanguage(path), uri);
    const state = {
      path,
      model,
      savedContent,
      dirty: Boolean(options.isNew) || content !== savedContent,
      isNew: Boolean(options.isNew),
    };
    this.textFileStates.set(path, state);
    return state;
  }

  ensureSpriteFileState(path) {
    if (!this.spriteFileStates.has(path)) {
      this.spriteFileStates.set(path, {
        path,
        dirty: false,
        savedPngBase64: "",
        savedSerializedText: "",
        manifestItem: null,
        rebuildInfo: null,
      });
    }
    return this.spriteFileStates.get(path);
  }

  async openFile(path, { collapseFilesDrawer = false } = {}) {
    const gameKey = getGameKeyFromPath(path);
    if (gameKey) {
      this.currentGameKey = gameKey;
    }
    const type = fileTypeForPath(path);
    if (type === "sprite") {
      await this.openSpriteFile(path, { collapseFilesDrawer });
    } else {
      await this.openTextFile(path, { collapseFilesDrawer });
    }
  }

  async openTextFile(path, { collapseFilesDrawer = false } = {}) {
    if (!isEditableTextPath(path)) {
      this.setStatus("Unsupported file");
      this.setMessage(`Only text files are editable in Monaco. "${escapeHtml(path)}" was skipped.`, {
        error: true,
      });
      return;
    }
    await this.ensureMonacoLoaded();
    this.setStatus(`Opening ${path}`);
    let state = this.textFileStates.get(path);
    if (!state) {
      try {
        const file = await this.api.readProjectFile(path, "utf8");
        state = this.ensureTextFileState(path, file.content, file.content, { isNew: false });
      } catch (error) {
        this.setStatus("Open failed");
        this.setMessage(`Could not open ${path}. ${error.message || String(error)}`, {
          error: true,
        });
        return;
      }
    }
    this.currentMode = "text";
    this.currentPath = path;
    this.isApplyingModel = true;
    this.editor.setModel(state.model);
    this.isApplyingModel = false;
    this.showEditorMode("text");
    this.editor.focus();
    this.renderGamesList();
    this.renderFileList();
    this.renderCreateState();
    this.renderActiveFileState();
    this.updateActionState();
    this.setMessage("Monaco ready", { ready: true });
    this.setStatus(state.dirty ? "Unsaved changes" : "Ready");
    if (collapseFilesDrawer && this.activeDrawer === "files") {
      this.toggleDrawer("files");
    }
    this.editor.layout();
  }

  async openSpriteFile(path, { collapseFilesDrawer = false } = {}) {
    this.setStatus(`Opening sprite ${path}`);
    const spriteState = this.ensureSpriteFileState(path);
    const spriteFile = await this.api.readProjectFile(path, "base64");
    let serializedSprite = null;

    try {
      const sidecar = await this.api.readProjectFile(getSerializedSpritePath(path), "utf8");
      serializedSprite = JSON.parse(sidecar.content);
      spriteState.savedSerializedText = sidecar.content;
    } catch (_error) {
      spriteState.savedSerializedText = "";
    }

    spriteState.manifestItem = await findStripedefItemForPath(this.api, path);
    spriteState.savedPngBase64 = spriteFile.content;
    spriteState.dirty = false;
    await this.piskel.loadSprite({
      path,
      pngBase64: spriteFile.content,
      serializedSprite,
      frames: spriteState.manifestItem?.frames || 1,
    });
    if (!serializedSprite) {
      await this.piskel.setFPS(3);
    }
    this.currentMode = "sprite";
    this.currentPath = path;
    this.showEditorMode("sprite");
    await this.piskel.focus();
    this.renderGamesList();
    this.renderFileList();
    this.renderCreateState();
    this.renderActiveFileState();
    this.updateActionState();
    this.setMessage("Piskel ready", { ready: true });
    this.setStatus("Ready");
    if (collapseFilesDrawer && this.activeDrawer === "files") {
      this.toggleDrawer("files");
    }
  }

  onSpriteDirtyChange(dirty) {
    if (this.currentMode !== "sprite" || !this.currentPath) {
      return;
    }
    const state = this.ensureSpriteFileState(this.currentPath);
    if (state.dirty === dirty) {
      return;
    }
    state.dirty = dirty;
    this.renderFileList();
    this.renderActiveFileState();
    this.updateActionState();
    this.setStatus(dirty ? "Unsaved sprite changes" : "Ready");
  }

  async saveCurrentFile() {
    if (!this.currentPath) {
      return null;
    }
    if (this.currentMode === "sprite") {
      return this.saveCurrentSprite();
    }
    return this.saveCurrentTextFile();
  }

  async saveCurrentTextFile() {
    const state = this.textFileStates.get(this.currentPath);
    if (!state) {
      return null;
    }
    this.setStatus(`Saving ${this.currentPath}`);
    const content = state.model.getValue();
    await this.api.writeProjectFile(this.currentPath, content, "utf8");
    state.savedContent = content;
    state.dirty = false;
    state.isNew = false;
    if (!this.fileEntries.includes(this.currentPath)) {
      this.fileEntries = [...this.fileEntries, this.currentPath].sort((left, right) => left.localeCompare(right));
    }
    const rebuildInfo = await maybeRebuildRomForPath(this.api, this.currentPath);
    this.renderFileList();
    this.renderActiveFileState();
    this.updateActionState();
    this.setStatus(rebuildInfo ? `Saved and rebuilt ${rebuildInfo.romPath}` : "Saved");
    return rebuildInfo;
  }

  async saveCurrentSprite() {
    const state = this.ensureSpriteFileState(this.currentPath);
    this.setStatus(`Saving sprite ${this.currentPath}`);
    const serialized = await this.piskel.serialize();
    const serializedText = typeof serialized === "string"
      ? serialized
      : JSON.stringify(serialized);
    const pngBase64 = await this.piskel.exportPngBase64();
    await this.api.writeProjectFile(this.currentPath, pngBase64, "base64");
    await this.api.writeProjectFile(getSerializedSpritePath(this.currentPath), serializedText, "utf8");
    const rebuildInfo = await maybeRebuildRomForPath(this.api, this.currentPath);
    this.spritePreviewUrls.set(this.currentPath, imageDataUrlFromBase64(pngBase64));
    state.savedPngBase64 = pngBase64;
    state.savedSerializedText = serializedText;
    state.dirty = false;
    state.rebuildInfo = rebuildInfo;
    this.renderFileList();
    this.renderActiveFileState();
    this.updateActionState();
    this.setStatus(rebuildInfo ? `Saved and rebuilt ${rebuildInfo.romPath}` : "Saved");
    return rebuildInfo;
  }

  async saveAndRun() {
    await this.saveCurrentFile();
    const autostartSlug = gameKeyToSlug(this.currentGameKey);
    this.setStatus(autostartSlug ? `Restarting runtime for ${autostartSlug}` : "Restarting runtime");
    await this.api.restartRuntime({ full: true, autostartSlug });
    this.setStatus("Runtime restarted");
  }

  async pushToConsole() {
    const gameKey = this.currentGameKey;
    if (!gameKey) {
      throw new Error("Open a game first, then push it to the console.");
    }
    await this.saveCurrentFile();
    const { slug, bytes } = await buildPackageForGame(
      this.api, gameKey, (text) => this.setStatus(text));
    await pushPackage(slug, bytes, (text) => this.setStatus(text));
    this.setStatus(`Installed ${slug} on the console`);
  }

  showEditorMode(mode) {
    this.currentMode = mode;
    this.textSurface.hidden = mode !== "text";
    this.spriteSurface.hidden = mode !== "sprite";
    this.elements.surface?.classList.toggle("is-sprite-mode", mode === "sprite");
    this.elements.surface?.classList.toggle("is-text-mode", mode === "text");
  }

  renderGamesList() {
    if (!this.elements.gamesList) {
      return;
    }
    const games = this.getGameEntries();
    if (!games.length) {
      this.elements.gamesList.innerHTML = '<div class="editor-empty-state">No games found in this workspace.</div>';
      return;
    }
    let currentGroup = null;
    const fragments = [];
    for (const game of games) {
      if (game.group !== currentGroup) {
        currentGroup = game.group;
        fragments.push(`<div class="editor-list-group">${escapeHtml(game.group)}</div>`);
      }
      fragments.push(`
        <button
          type="button"
          class="editor-file-button editor-game-button${game.key === this.currentGameKey ? " is-active" : ""}"
          data-editor-game-key="${escapeHtml(game.key)}"
        >
          <span class="editor-file-main">
            <span class="editor-game-preview"><img alt="" data-editor-game-preview="${escapeHtml(game.key)}"></span>
            <span class="editor-file-label">${escapeHtml(game.slug)}</span>
          </span>
        </button>
      `);
    }
    this.elements.gamesList.innerHTML = fragments.join("");
    for (const button of this.elements.gamesList.querySelectorAll("[data-editor-game-key]")) {
      button.addEventListener("click", () => {
        void this.runAction("Open game failed", () => this.openMainFileForGame(button.dataset.editorGameKey, {
          collapseDrawer: true,
        }));
      });
    }
    void this.renderGamePreviews();
  }

  async renderGamePreviews() {
    if (!this.elements.gamesList) {
      return;
    }
    const previewNodes = Array.from(this.elements.gamesList.querySelectorAll("[data-editor-game-preview]"));
    await Promise.all(previewNodes.map(async (node) => {
      const gameKey = node.dataset.editorGamePreview;
      if (!gameKey) {
        return;
      }
      const previewUrl = await this.getGamePreviewUrl(gameKey);
      if (previewUrl) {
        node.src = previewUrl;
      }
    }));
  }

  async loadImageElement(url) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error(`Failed to load image: ${url}`));
      image.src = url;
    });
  }

  async buildFramedPreviewUrl(path, frame = 0, frames = 1) {
    const image = await this.loadImageElement(new URL(path, import.meta.url).href);
    const totalFrames = Math.max(Number(frames) || 1, 1);
    const frameWidth = totalFrames > 1 ? Math.max(1, Math.floor(image.naturalWidth / totalFrames)) : image.naturalWidth;
    const frameHeight = image.naturalHeight;
    const safeFrame = Math.max(0, Math.min(frame, totalFrames - 1));
    const canvas = document.createElement("canvas");
    canvas.width = frameWidth;
    canvas.height = frameHeight;
    const context = canvas.getContext("2d");
    context.imageSmoothingEnabled = false;
    context.drawImage(
      image,
      safeFrame * frameWidth,
      0,
      frameWidth,
      frameHeight,
      0,
      0,
      frameWidth,
      frameHeight,
    );
    return canvas.toDataURL("image/png");
  }

  async getGamePreviewUrl(gameKey) {
    if (this.gamePreviewUrls.has(gameKey)) {
      return this.gamePreviewUrls.get(gameKey);
    }
    const info = getGameInfoFromKey(gameKey);
    const candidates = [];
    if (info) {
      candidates.push({
        path: `./games/${gameKey}/menu.png`,
        frame: 0,
        frames: 1,
      });
    }
    const mapped = GAME_MENU_PREVIEW_MAP.get(gameKey);
    if (mapped) {
      candidates.push(mapped);
    }
    candidates.push({
      path: `./games/${gameKey}/images/menu.png`,
      frame: 0,
      frames: 1,
    });
    for (const config of candidates) {
      try {
        const previewUrl = await this.buildFramedPreviewUrl(config.path, config.frame, config.frames);
        this.gamePreviewUrls.set(gameKey, previewUrl);
        return previewUrl;
      } catch (_error) {
        // Try the next candidate.
      }
    }
    this.gamePreviewUrls.set(gameKey, "");
    return "";
  }

  getCurrentGameFiles() {
    if (!this.currentGameKey) {
      return [];
    }
    return this.fileEntries.filter((path) => path.startsWith(`${this.currentGameKey}/`));
  }

  renderFileList() {
    if (!this.elements.fileList) {
      return;
    }
    if (!this.currentGameKey) {
      this.elements.fileList.innerHTML = '<div class="editor-empty-state">Choose a game to browse its code and assets.</div>';
      return;
    }
    const gameFiles = this.getCurrentGameFiles();
    if (!gameFiles.length) {
      this.elements.fileList.innerHTML = '<div class="editor-empty-state">This game does not have editable files yet.</div>';
      return;
    }
    this.elements.fileList.innerHTML = gameFiles.map((path) => {
      const type = fileTypeForPath(path);
      const state = type === "sprite"
        ? this.spriteFileStates.get(path)
        : this.textFileStates.get(path);
      const active = path === this.currentPath;
      const dirty = Boolean(state?.dirty);
      const preview = type === "sprite"
        ? `<span class="editor-file-preview"><img alt="" data-editor-image-preview="${escapeHtml(path)}"></span>`
        : "";
      return `
        <button
          type="button"
          class="editor-file-button editor-file-button-${type}${active ? " is-active" : ""}"
          data-editor-file-path="${escapeHtml(path)}"
        >
          <span class="editor-file-main">
            ${preview}
            <span class="editor-file-label">${dirty ? "* " : ""}${escapeHtml(trimGameRoot(path, this.currentGameKey))}</span>
          </span>
          <span class="editor-file-kind">${type === "sprite" ? "PNG" : "TXT"}</span>
        </button>
      `;
    }).join("");
    for (const button of this.elements.fileList.querySelectorAll("[data-editor-file-path]")) {
      button.addEventListener("click", () => {
        void this.runAction("Open failed", () => this.openFile(button.dataset.editorFilePath, {
          collapseFilesDrawer: true,
        }));
      });
    }
    void this.renderImagePreviews();
  }

  async renderImagePreviews() {
    if (!this.elements.fileList) {
      return;
    }
    const previewNodes = Array.from(this.elements.fileList.querySelectorAll("[data-editor-image-preview]"));
    await Promise.all(previewNodes.map(async (node) => {
      const path = node.dataset.editorImagePreview;
      if (!path) {
        return;
      }
      let previewUrl = this.spritePreviewUrls.get(path) || "";
      if (!previewUrl) {
        try {
          const file = await this.api.readProjectFile(path, "base64");
          previewUrl = imageDataUrlFromBase64(file.content);
          this.spritePreviewUrls.set(path, previewUrl);
        } catch (_error) {
          previewUrl = "";
        }
      }
      if (previewUrl) {
        node.src = previewUrl;
      }
    }));
  }

  renderCreateState() {
    const gameInfo = getGameInfoFromKey(this.currentGameKey);
    if (this.elements.newSourceButton) {
      this.elements.newSourceButton.disabled = !gameInfo;
    }
    if (this.elements.newStripeButton) {
      this.elements.newStripeButton.disabled = !gameInfo;
    }
    if (this.elements.createHelp) {
      this.elements.createHelp.textContent = gameInfo
        ? `Creating files inside ${gameInfo.group}/${gameInfo.slug}.`
        : "Select a game to add files and image strips.";
    }
  }

  async openMainFileForGame(gameKey, { collapseDrawer = false } = {}) {
    const mainPath = this.findMainFileForGame(gameKey);
    if (!mainPath) {
      this.currentGameKey = gameKey;
      this.renderGamesList();
      this.renderFileList();
      this.renderCreateState();
      return;
    }
    await this.openFile(mainPath, { collapseFilesDrawer: collapseDrawer });
    if (collapseDrawer && this.activeDrawer === "games") {
      this.toggleDrawer("games");
    }
  }

  closeCreateDialog(value) {
    if (typeof this.pendingCreateDialogResolver === "function") {
      const resolve = this.pendingCreateDialogResolver;
      this.pendingCreateDialogResolver = null;
      this.elements.createDialog?.close();
      resolve(value);
    }
  }

  async promptForCreation({
    title,
    description,
    label,
    hint,
    defaultValue = "",
    submitLabel = "Create",
  }) {
    const dialog = this.elements.createDialog;
    const input = this.elements.createInput;
    if (!dialog || !input) {
      return window.prompt(`${title}\n\n${hint}`, defaultValue);
    }
    this.elements.createTitle.textContent = title;
    this.elements.createDescription.textContent = description;
    this.elements.createLabel.textContent = label;
    this.elements.createHint.textContent = hint;
    this.elements.createSubmit.textContent = submitLabel;
    input.value = defaultValue;
    dialog.showModal();
    await new Promise((resolve) => window.requestAnimationFrame(resolve));
    input.focus();
    input.select();
    return new Promise((resolve) => {
      this.pendingCreateDialogResolver = resolve;
    });
  }

  async createNewGame() {
    const defaultGroup = getGameInfoFromKey(this.currentGameKey)?.group || this.getGameEntries()[0]?.group || "alecu";
    const response = await this.promptForCreation({
      title: "New Game",
      description: "Create a new game folder with starter code and asset directories.",
      label: "Game Name",
      hint: 'Use "group/slug". If you only enter a slug, it will be created in the current group.',
      defaultValue: `${defaultGroup}/new_game`,
      submitLabel: "Create Game",
    });
    if (response === null) {
      return;
    }
    const rawValue = String(response || "").trim();
    if (!rawValue) {
      return;
    }
    const normalized = rawValue.includes("/") ? normalizeWorkspacePath(rawValue) : `${defaultGroup}/${normalizeWorkspacePath(rawValue)}`;
    const info = getGameInfoFromKey(normalized);
    if (!info || /[^a-z0-9._-]/u.test(info.group) || /[^a-z0-9._-]/u.test(info.slug)) {
      throw new Error("Game names must look like group/slug and use lowercase letters, numbers, dots, dashes, or underscores.");
    }
    if (this.getGameEntries().some((entry) => entry.key === info.key)) {
      throw new Error(`Game ${info.key} already exists.`);
    }
    const mainPath = `${info.key}/code/${info.slug}.py`;
    const imagesManifestPath = `${info.key}/images/__images__.yaml`;
    const className = slugToIdentifier(info.slug);
    const gameSource = [
      "from ventilastation.scene import Scene",
      "",
      "",
      `class ${className}(Scene):`,
      `    stripes_rom = "${info.group}.${info.slug}"`,
      "",
      "    def step(self):",
      "        pass",
      "",
      "",
      "def main():",
      `    return ${className}()`,
      "",
    ].join("\n");
    await this.api.writeProjectFile(mainPath, gameSource, "utf8");
    await this.api.writeProjectFile(imagesManifestPath, "palettegroups:\n  palette1: []\n", "utf8");
    await this.api.writeProjectFile(`${info.key}/sounds/.gitkeep`, "", "utf8");
    this.currentGameKey = info.key;
    await this.refreshFiles();
    await this.openFile(mainPath);
    if (this.activeDrawer === "new") {
      this.toggleDrawer("new");
    }
  }

  async createSourceFile() {
    const gameInfo = getGameInfoFromKey(this.currentGameKey);
    if (!gameInfo) {
      return;
    }
    const response = await this.promptForCreation({
      title: "New Micropython File",
      description: `Add a Micropython source file under ${gameInfo.group}/${gameInfo.slug}/code.`,
      label: "File Name",
      hint: "Enter a Micropython filename like helpers.py or a nested path like enemies/boss.py.",
      defaultValue: "new_file.py",
      submitLabel: "Create File",
    });
    if (response === null) {
      return;
    }
    const relativePath = ensurePyModuleName(response);
    const fullPath = `${gameInfo.key}/code/${normalizeWorkspacePath(relativePath)}`;
    if (this.fileEntries.includes(fullPath)) {
      throw new Error(`File ${fullPath} already exists.`);
    }
    await this.api.writeProjectFile(fullPath, "", "utf8");
    await this.refreshFiles();
    await this.openTextFile(fullPath);
    if (this.activeDrawer === "new") {
      this.toggleDrawer("new");
    }
  }

  async appendImageManifestEntry(manifestPath, filename) {
    let manifestText = "palettegroups:\n  palette1:\n";
    try {
      manifestText = (await this.api.readProjectFile(manifestPath, "utf8")).content;
    } catch (_error) {
      // Start from a new manifest if the game does not have one yet.
    }
    const trimmed = manifestText.trimEnd();
    if (!trimmed.includes("palettegroups:")) {
      manifestText = `palettegroups:\n  palette1:\n    - strip: ${filename}\n      frames: 1\n`;
    } else if (/palette1:\s*\[\s*\]/u.test(trimmed)) {
      manifestText = trimmed.replace(/palette1:\s*\[\s*\]/u, `palette1:\n    - strip: ${filename}\n      frames: 1`) + "\n";
    } else if (/palette1:\s*$/u.test(trimmed)) {
      manifestText = `${trimmed}\n    - strip: ${filename}\n      frames: 1\n`;
    } else {
      manifestText = `${trimmed}\n    - strip: ${filename}\n      frames: 1\n`;
    }
    await this.api.writeProjectFile(manifestPath, manifestText, "utf8");
  }

  async createImageStripe() {
    const gameInfo = getGameInfoFromKey(this.currentGameKey);
    if (!gameInfo) {
      return;
    }
    const response = await this.promptForCreation({
      title: "New Image Stripe",
      description: `Create a starter PNG stripe under ${gameInfo.group}/${gameInfo.slug}/images.`,
      label: "Stripe Name",
      hint: "Enter a PNG filename like player.png. It will be added to __images__.yaml with 1 frame.",
      defaultValue: "new_strip.png",
      submitLabel: "Create Stripe",
    });
    if (response === null) {
      return;
    }
    const filename = ensurePngName(response);
    const relativePath = normalizeWorkspacePath(filename);
    const fullPath = `${gameInfo.key}/images/${relativePath}`;
    if (this.fileEntries.includes(fullPath)) {
      throw new Error(`Image ${fullPath} already exists.`);
    }
    await this.api.writeProjectFile(fullPath, EMPTY_STRIPE_PNG_BASE64, "base64");
    this.spritePreviewUrls.set(fullPath, imageDataUrlFromBase64(EMPTY_STRIPE_PNG_BASE64));
    await this.appendImageManifestEntry(`${gameInfo.key}/images/__images__.yaml`, relativePath);
    await this.refreshFiles();
    await this.openSpriteFile(fullPath);
    if (this.activeDrawer === "new") {
      this.toggleDrawer("new");
    }
  }

  renderActiveFileState() {
    if (!this.elements.activeFile || !this.elements.activeMeta) {
      return;
    }
    if (!this.currentPath) {
      const gameInfo = getGameInfoFromKey(this.currentGameKey);
      this.elements.activeFile.textContent = gameInfo
        ? `${gameInfo.group}/${gameInfo.slug}`
        : "No file selected";
      this.elements.activeMeta.textContent = gameInfo ? "game selected" : "";
      return;
    }
    this.elements.activeFile.textContent = trimWorkspaceRoot(this.currentPath, this.workspaceRoot);
    const bits = [inferDisplayLanguage(this.currentPath)];
    if (this.currentMode === "sprite") {
      const spriteState = this.spriteFileStates.get(this.currentPath);
      bits.push(makeSpriteMetaLabel(spriteState));
      bits.push(spriteState?.dirty ? "unsaved" : "saved");
    } else {
      const textState = this.textFileStates.get(this.currentPath);
      if (textState?.isNew) {
        bits.push("new");
      }
      bits.push(textState?.dirty ? "unsaved" : "saved");
    }
    this.elements.activeMeta.textContent = bits.join(" • ");
  }

  updateActionState() {
    const hasFile = Boolean(this.currentPath);
    const isBusy = this.actionInFlight;
    let canSave = false;
    if (hasFile && this.currentMode === "sprite") {
      canSave = Boolean(this.spriteFileStates.get(this.currentPath)?.dirty);
    } else if (hasFile && this.currentMode === "text") {
      const state = this.textFileStates.get(this.currentPath);
      canSave = Boolean(state && (state.dirty || state.isNew));
    }
    if (this.elements.saveButton) {
      this.elements.saveButton.disabled = isBusy || !canSave;
      this.elements.saveButton.textContent = isBusy && this.activeActionLabel === "Save failed"
        ? "Saving..."
        : "Save";
    }
    if (this.elements.runButton) {
      this.elements.runButton.disabled = isBusy || !hasFile;
      this.elements.runButton.textContent = isBusy && this.activeActionLabel === "Run failed"
        ? "Starting..."
        : "Save + Run";
    }
    if (this.elements.pushButton) {
      this.elements.pushButton.hidden = !this.packageServerAvailable;
      this.elements.pushButton.disabled =
        isBusy || !this.currentGameKey || !this.packageServerAvailable;
      this.elements.pushButton.textContent = isBusy && this.activeActionLabel === "Push failed"
        ? "Pushing..."
        : "Push to console";
    }
    this.renderCreateState();
  }

  setStatus(text) {
    if (this.root) {
      this.root.dataset.editorStatus = text;
    }
  }

  setMessage(text, { ready = false, error = false } = {}) {
    if (!this.elements.message) {
      return;
    }
    this.elements.message.textContent = text;
    this.elements.message.classList.toggle("is-ready", ready);
    this.elements.message.classList.toggle("is-error", error);
  }

  toggleDrawer(name) {
    this.activeDrawer = this.activeDrawer === name ? null : name;
    const drawers = ["games", "files", "new"];
    for (const drawerName of drawers) {
      const open = this.activeDrawer === drawerName;
      const drawer = this.getDrawerElement(drawerName);
      const button = this.getDrawerToggleButton(drawerName);
      if (drawer) {
        drawer.hidden = !open;
      }
      if (button) {
        button.setAttribute("aria-expanded", open ? "true" : "false");
      }
    }
  }
}

function startWhenReady() {
  const boot = (api) => {
    const ide = new WorkspaceIde(api);
    void ide.start();
  };
  if (window.VentilastationWebEmulator) {
    boot(window.VentilastationWebEmulator);
    return;
  }
  window.addEventListener("ventilastation:ready", (event) => {
    boot(event.detail?.api || window.VentilastationWebEmulator);
  }, { once: true });
}

startWhenReady();
