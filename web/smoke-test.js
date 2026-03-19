import { createVentilastationWasmBridge } from "./micropython-bridge.js";

const checks = [
  { id: "bridge", label: "Create Worker Bridge", status: "pending" },
  { id: "init", label: "Initialize Worker Runtime", status: "pending" },
  { id: "configure", label: "Configure Browser Runtime", status: "pending" },
  { id: "import_main", label: "Import main.py", status: "pending" },
  { id: "export_frame", label: "Export Frame Snapshot", status: "pending" },
];

const elements = {
  overallStatus: document.querySelector("#overall-status"),
  checkList: document.querySelector("#check-list"),
  frameOutput: document.querySelector("#frame-output"),
  logOutput: document.querySelector("#log-output"),
};

const logLines = [];

function log(message) {
  const timestamp = new Date().toISOString().slice(11, 19);
  logLines.push(`[${timestamp}] ${message}`);
  elements.logOutput.textContent = logLines.join("\n");
}

function setCheckStatus(id, status, detail = "") {
  const check = checks.find((entry) => entry.id === id);
  if (!check) {
    return;
  }
  check.status = status;
  check.detail = detail;
  renderChecks();
}

function renderChecks() {
  elements.checkList.innerHTML = checks.map((check) => `
    <div class="summary-card">
      <strong>${check.label}</strong>
      <span>${check.status}${check.detail ? `: ${check.detail}` : ""}</span>
    </div>
  `).join("");

  const failed = checks.find((check) => check.status === "failed");
  const pending = checks.find((check) => check.status === "pending");
  if (failed) {
    elements.overallStatus.textContent = "Failed";
    elements.overallStatus.style.borderColor = "rgba(255, 107, 107, 0.4)";
    elements.overallStatus.style.color = "#ff6b6b";
    return;
  }
  if (pending) {
    elements.overallStatus.textContent = "Running";
    return;
  }
  elements.overallStatus.textContent = "Passed";
}

function simplifyFrame(frame) {
  return {
    frame: frame.frame,
    buttons: frame.buttons,
    column_offset: frame.column_offset,
    gamma_mode: frame.gamma_mode,
    sprites: frame.sprites,
    assets: frame.assets.map((asset) => ({
      ...asset,
      data: `[${asset.data?.length ?? 0} bytes]`,
    })),
    events: frame.events,
    palette: frame.palette ? `[${frame.palette.length} bytes]` : undefined,
  };
}

async function run() {
  renderChecks();
  let bridge;

  try {
    log("Creating worker bridge");
    bridge = await createVentilastationWasmBridge();
    setCheckStatus("bridge", "passed");
  } catch (error) {
    setCheckStatus("bridge", "failed", error.message);
    log(`Bridge creation failed: ${error.message}`);
    return;
  }

  try {
    log("Initializing worker runtime");
    const initResult = await bridge.initialize();
    setCheckStatus("init", "passed", initResult.runtime || "ok");
    log(`Worker initialized: ${JSON.stringify(initResult)}`);
  } catch (error) {
    setCheckStatus("init", "failed", error.message);
    log(`Worker initialization failed: ${error.message}`);
    return;
  }

  try {
    log("Configuring browser runtime");
    await bridge.exec(`
import sys
if '/apps/micropython' not in sys.path:
    sys.path.insert(0, '/apps/micropython')
from ventilastation.director import configure_runtime
configure_runtime('browser')
`);
    setCheckStatus("configure", "passed");
  } catch (error) {
    setCheckStatus("configure", "failed", error.message);
    log(`Runtime configuration failed: ${error.message}`);
    return;
  }

  try {
    log("Importing main.py");
    await bridge.exec("import main");
    setCheckStatus("import_main", "passed");
  } catch (error) {
    setCheckStatus("import_main", "failed", error.message);
    log(`main import failed: ${error.message}`);
    return;
  }

  try {
    log("Exporting frame snapshot");
    const frame = await bridge.call("ventilastation.browser", "export_frame", true);
    setCheckStatus("export_frame", "passed", `frame=${frame.frame}`);
    elements.frameOutput.textContent = JSON.stringify(simplifyFrame(frame), null, 2);
    log("Frame export succeeded");
  } catch (error) {
    setCheckStatus("export_frame", "failed", error.message);
    log(`Frame export failed: ${error.message}`);
  }
}

run();
