const MONACO_VERSION = "0.52.2";
const MONACO_BASE_URL = `https://cdn.jsdelivr.net/npm/monaco-editor@${MONACO_VERSION}/min/vs`;
const WORKSPACE_ROOT_CANDIDATES = ["."];
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
  const workerSource = [
    `self.MonacoEnvironment = { baseUrl: ${JSON.stringify(`${MONACO_BASE_URL}/`)} };`,
    `importScripts(${JSON.stringify(`${MONACO_BASE_URL}/base/worker/workerMain.js`)});`,
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

class MonacoWorkspaceIde {
  constructor(api) {
    this.api = api;
    this.workspaceRoot = "";
    this.fileEntries = [];
    this.fileStates = new Map();
    this.currentPath = null;
    this.editor = null;
    this.monaco = null;
    this.isApplyingModel = false;
    this.activeDrawer = null;
    this.root = document.querySelector("#editor-panel-shell");
    if (!this.root) {
      return;
    }
    this.elements = {
      fileList: document.querySelector("#editor-file-list"),
      surface: document.querySelector("#editor-surface"),
      message: document.querySelector("#editor-message"),
      activeFile: document.querySelector("#editor-active-file"),
      activeMeta: document.querySelector("#editor-active-meta"),
      toggleFilesButton: document.querySelector("#editor-toggle-files-button"),
      filesDrawer: document.querySelector("#editor-files-drawer"),
      saveButton: document.querySelector("#editor-save-button"),
      runButton: document.querySelector("#editor-run-button"),
    };
  }

  async start() {
    if (!this.root) {
      return;
    }
    this.bindUi();
    this.setStatus("Loading Monaco");
    try {
      this.monaco = await loadMonaco();
      this.createEditor();
    } catch (error) {
      this.setStatus("Monaco failed");
      this.setMessage(
        `Monaco could not load. ${error.message || String(error)} ` +
        "This first version loads Monaco from jsDelivr, so browser network access is required.",
        { error: true },
      );
      return;
    }
    try {
      await this.refreshFiles({ openDefault: true });
      this.setMessage("Monaco ready", { ready: true });
      this.setStatus("Ready");
    } catch (error) {
      this.setStatus("Workspace failed");
      this.setMessage(
        `Monaco loaded, but the workspace could not be opened. ${error.message || String(error)}`,
        { error: true },
      );
      console.error("Workspace refresh failed", error);
    }
  }

  bindUi() {
    this.elements.toggleFilesButton?.addEventListener("click", () => {
      this.toggleDrawer("files");
    });
    this.elements.saveButton?.addEventListener("click", () => {
      void this.runAction("Save failed", () => this.saveCurrentFile());
    });
    this.elements.runButton?.addEventListener("click", () => {
      void this.runAction("Run failed", () => this.saveAndRun());
    });
    window.addEventListener("ventilastation:editor-toggle", (event) => {
      if (event.detail?.open) {
        this.editor?.layout();
      }
    });
    document.addEventListener("pointerdown", (event) => {
      if (this.activeDrawer !== "files" || !this.root) {
        return;
      }
      const toggleButton = this.elements.toggleFilesButton;
      const drawer = this.elements.filesDrawer;
      const target = event.target;
      if (
        (toggleButton && toggleButton.contains(target)) ||
        (drawer && drawer.contains(target))
      ) {
        return;
      }
      this.toggleDrawer("files");
    });
  }

  async runAction(failureLabel, action) {
    try {
      await action();
    } catch (error) {
      this.handleError(failureLabel, error);
    }
  }

  handleError(label, error) {
    console.error(label, error);
    this.setStatus(label);
    this.setMessage(`${label}. ${error.message || String(error)}`, { error: true });
  }

  createEditor() {
    this.editor = this.monaco.editor.create(this.elements.surface, {
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
      if (this.isApplyingModel || !this.currentPath) {
        return;
      }
      const state = this.fileStates.get(this.currentPath);
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
    for (const candidate of WORKSPACE_ROOT_CANDIDATES) {
      try {
        await this.api.listProjectFiles(candidate);
        this.workspaceRoot = candidate;
        return candidate;
      } catch (_error) {
        // Try the next known root from the migrated repo layout.
      }
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
      .filter((path) => pathIsWithinWorkspace(path, workspaceRoot) && isEditableTextPath(path))
      .sort((left, right) => left.localeCompare(right));
    this.renderFileList();
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
    const preferred = [
      resolveWorkspaceFilePath(this.workspaceRoot, "registry.py"),
      resolveWorkspaceFilePath(this.workspaceRoot, "alecu/vyruss/code/vyruss.py"),
      resolveWorkspaceFilePath(this.workspaceRoot, "other/aaa/code/aaa.py"),
      resolveWorkspaceFilePath(this.workspaceRoot, "vsjam-may25/vs/code/vs.py"),
    ];
    for (const candidate of preferred) {
      if (this.fileEntries.includes(candidate)) {
        return candidate;
      }
    }
    return this.fileEntries[0] || null;
  }

  ensureFileState(path, content, savedContent, options = {}) {
    const existing = this.fileStates.get(path);
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
    this.fileStates.set(path, state);
    return state;
  }

  async openFile(path, { collapseFilesDrawer = false } = {}) {
    if (!isEditableTextPath(path)) {
      this.setStatus("Unsupported file");
      this.setMessage(`Only text files are editable right now. "${escapeHtml(path)}" was skipped.`, {
        error: true,
      });
      return;
    }
    this.setStatus(`Opening ${path}`);
    let state = this.fileStates.get(path);
    if (!state) {
      try {
        const file = await this.api.readProjectFile(path, "utf8");
        state = this.ensureFileState(path, file.content, file.content, { isNew: false });
      } catch (error) {
        this.setStatus("Open failed");
        this.setMessage(`Could not open ${path}. ${error.message || String(error)}`, {
          error: true,
        });
        return;
      }
    }
    this.currentPath = path;
    this.isApplyingModel = true;
    this.editor.setModel(state.model);
    this.isApplyingModel = false;
    this.editor.focus();
    this.renderFileList();
    this.renderActiveFileState();
    this.updateActionState();
    this.setMessage("Monaco ready", { ready: true });
    this.setStatus(state.dirty ? "Unsaved changes" : "Ready");
    if (collapseFilesDrawer && this.activeDrawer === "files") {
      this.toggleDrawer("files");
    }
    this.editor.layout();
  }

  async saveCurrentFile() {
    if (!this.currentPath) {
      return;
    }
    const state = this.fileStates.get(this.currentPath);
    if (!state) {
      return;
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
    this.renderFileList();
    this.renderActiveFileState();
    this.updateActionState();
    this.setStatus("Saved");
  }

  async saveAndRun() {
    await this.saveCurrentFile();
    this.setStatus("Restarting runtime");
    await this.api.restartRuntime({ full: true });
    this.setStatus("Runtime restarted");
  }

  renderFileList() {
    if (!this.elements.fileList) {
      return;
    }
    if (!this.fileEntries.length) {
      this.elements.fileList.innerHTML = '<div class="editor-empty-state">No editable files found.</div>';
      return;
    }
    this.elements.fileList.innerHTML = this.fileEntries.map((path) => {
      const state = this.fileStates.get(path);
      const active = path === this.currentPath;
      const dirty = Boolean(state?.dirty);
      return `
        <button
          type="button"
          class="editor-file-button${active ? " is-active" : ""}"
          data-editor-file-path="${escapeHtml(path)}"
        >${dirty ? "* " : ""}${escapeHtml(trimWorkspaceRoot(path, this.workspaceRoot))}</button>
      `;
    }).join("");
    for (const button of this.elements.fileList.querySelectorAll("[data-editor-file-path]")) {
      button.addEventListener("click", () => {
        void this.runAction("Open failed", () => this.openFile(button.dataset.editorFilePath, {
          collapseFilesDrawer: true,
        }));
      });
    }
  }

  renderActiveFileState() {
    if (!this.elements.activeFile || !this.elements.activeMeta) {
      return;
    }
    if (!this.currentPath) {
      this.elements.activeFile.textContent = "No file selected";
      this.elements.activeMeta.textContent = "";
      return;
    }
    const state = this.fileStates.get(this.currentPath);
    this.elements.activeFile.textContent = trimWorkspaceRoot(this.currentPath, this.workspaceRoot);
    const bits = [inferDisplayLanguage(this.currentPath)];
    if (state?.isNew) {
      bits.push("new");
    }
    bits.push(state?.dirty ? "unsaved" : "saved");
    this.elements.activeMeta.textContent = bits.join(" • ");
  }

  updateActionState() {
    const state = this.currentPath ? this.fileStates.get(this.currentPath) : null;
    const hasFile = Boolean(state);
    const canSave = Boolean(hasFile && (state.dirty || state.isNew));
    if (this.elements.saveButton) {
      this.elements.saveButton.disabled = !canSave;
    }
    if (this.elements.runButton) {
      this.elements.runButton.disabled = !hasFile;
    }
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
    const filesOpen = this.activeDrawer === "files";
    if (this.elements.filesDrawer) {
      this.elements.filesDrawer.hidden = !filesOpen;
    }
    if (this.elements.toggleFilesButton) {
      this.elements.toggleFilesButton.setAttribute("aria-expanded", filesOpen ? "true" : "false");
    }
  }
}

function startWhenReady() {
  const boot = (api) => {
    const ide = new MonacoWorkspaceIde(api);
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
