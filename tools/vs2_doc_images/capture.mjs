// Regenerates the images in docs/vs2/images/.
//
//   cd web && python3 -m http.server 8765      # serve the web emulator
//   cd tools/vs2_doc_images && npm install && node capture.mjs [name ...]
//
// Emulator screenshots: each example in examples/ is written into the browser
// emulator's workspace as games/docs/<name>, its ROM is built in the browser,
// the runtime is restarted into it, and the polar canvas is saved after the
// scripted key presses. Nothing is written into the repo's games/ tree.
//
// Diagrams: each diagrams/*.svg is rendered to a PNG with the same browser.
// `{{art:<path under games/>}}` in an SVG is replaced by that image as a data
// URI, so diagrams can show the real art.
//
// The browser ROM builder does not read `glyphs:` from __images__.yaml, so the
// examples pass glyphs= to label() instead.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "../..");
const BASE = process.env.BASE || "http://localhost:8765";
const OUT = process.env.OUT || path.join(REPO, "docs/vs2/images");
const CHROMIUM = process.env.CHROMIUM || "/opt/pw-browsers/chromium";

const ART = {
  "ship.png": ["alecu/vixeous/images/ship.png", 4],
  "shots.png": ["alecu/vixeous/images/shots.png", 3],
  "enemy.png": ["alecu/vixeous/images/enemy.png", 6],
  "explosion.png": ["alecu/vixeous/images/explosion.png", 6],
  "numerals.png": ["alecu/vyruss_vs2/images/numerals.png", 12],
  "messages.png": ["alecu/vixeous/images/messages.png", 3],
  "terrain.png": ["alecu/mapdemo/images/terrain.png", 6],
};
// Local art (under tools/vs2_doc_images/art) is written as "local:<file>".
const FULLSCREEN_ART = { "clouds.png": ["local:clouds.png", 54] };

// name -> { art: [...], shots: [[step, ...], ...] }
// steps: {wait: ms} {down: key} {up: key} {press: key} {shot: file, labels: [...]}
const key = (code, ms = 60) => [{ down: code }, { wait: ms }, { up: code }];
const EXAMPLES = {
  first: {
    art: ["ship.png"],
    steps: [
      { wait: 800 }, { shot: "first-game.png" },
      { down: "ArrowLeft" }, { wait: 700 }, { up: "ArrowLeft" }, { wait: 200 },
      { shot: "first-game-moved.png" },
    ],
  },
  angles: {
    art: ["ship.png"],
    steps: [{ wait: 800 }, {
      shot: "display-angles.png",
      labels: [
        { x: 440, y: 690, text: "x = 0" },
        { x: 160, y: 440, text: "x = 64" },
        { x: 440, y: 190, text: "x = 128" },
        { x: 720, y: 440, text: "x = 192" },
      ],
    }],
  },
  projections: {
    art: ["ship.png"],
    steps: [{ wait: 800 }, {
      shot: "display-projections.png",
      labels: [
        { x: 700, y: 150, text: "TUNNEL layer\ny = 0, 40, 80, 120, 170, 220", color: "#8fb4ff" },
        { x: 640, y: 740, text: "HUD layer\ny = 0, 14, 28, 40", color: "#ffd166" },
      ],
    }],
  },
  layers: {
    art: ["ship.png", "enemy.png", "numerals.png"],
    fullscreen: ["clouds.png"],
    steps: [{ wait: 800 }, {
      shot: "display-layers.png",
      labels: [
        { x: 24, y: 735, left: true, size: 22, text: "hud (HUD): the score", color: "#ffd166" },
        { x: 24, y: 765, left: true, size: 22, text: "clouds (FULLSCREEN): drawn over the world", color: "#8fb4ff" },
        { x: 24, y: 795, left: true, size: 22, text: "world (TUNNEL): the ship and enemies", color: "#7ee0a1" },
      ],
    }],
  },
  flips: {
    art: ["numerals.png"],
    steps: [{ wait: 800 }, {
      shot: "labels-flips.png",
      labels: [
        { x: 24, y: 690, left: true, size: 24, text: "top, y = 1, no flips: upside-down", color: "#ff8f8f" },
        { x: 24, y: 725, left: true, size: 24, text: "top, y = 14, flip_x and flip_y: upright", color: "#7ee0a1" },
        { x: 24, y: 760, left: true, size: 24, text: "bottom, y = 1, no flips: upright", color: "#7ee0a1" },
      ],
    }],
  },
  frames: {
    art: ["ship.png"],
    steps: [{ wait: 800 }, {
      shot: "sprites-frames.png",
      labels: [
        { x: 440, y: 330, text: "frame = 0, 1, 2, 3  (left to right)" },
      ],
    }],
  },
  pools: {
    art: ["ship.png", "shots.png", "enemy.png", "explosion.png"],
    steps: [
      { wait: 800 },
      ...key("Space"), { wait: 450 },
      ...key("Space"), { wait: 450 },
      ...key("Space"), { wait: 120 },
      { shot: "pools.png" },
    ],
  },
  tilemap: {
    art: ["ship.png", "terrain.png"],
    steps: [{ wait: 800 }, { shot: "tilemaps.png" }],
  },
  labels: {
    art: ["ship.png", "terrain.png", "numerals.png"],
    steps: [{ wait: 800 }, {
      shot: "labels.png",
      labels: [
        { x: 24, y: 690, left: true, size: 24, text: "top: x = 118, y = 14, flip_x and flip_y", color: "#7ee0a1" },
        { x: 24, y: 725, left: true, size: 24, text: "bottom: x = 246, y = 1, no flips", color: "#7ee0a1" },
      ],
    }],
  },
  legibility: {
    art: ["numerals.png"],
    steps: [{ wait: 800 }, {
      shot: "budgets-legibility.png",
      labels: [
        { x: 440, y: 785, text: "y = 1: crisp" },
        { x: 440, y: 590, text: "y = 44: unreadable" },
      ],
    }],
  },
  title: {
    art: ["ship.png", "enemy.png", "messages.png"],
    steps: [
      { wait: 800 }, { shot: "scenes-title.png" },
      ...key("Space"), { wait: 1500 }, { shot: "scenes-play.png" },
    ],
  },
};

const only = process.argv.slice(2);
const wanted = (name) => only.length === 0 || only.includes(name);

fs.mkdirSync(OUT, { recursive: true });

const gamesPath = (rel) =>
  rel.startsWith("local:") ? path.join(HERE, "art", rel.slice(6)) : path.join(REPO, "games", rel);
const b64 = (file) => fs.readFileSync(file).toString("base64");

function exampleFiles(name, ex) {
  const root = `games/docs/${name}`;
  const files = [
    {
      path: `${root}/meta.json`,
      enc: "utf8",
      content: JSON.stringify({ api: "vs2", api_revision: 2, title: name, hidden: true }),
    },
    {
      path: `${root}/code/${name}.py`,
      enc: "utf8",
      content: fs.readFileSync(path.join(HERE, "examples", `${name}.py`), "utf8"),
    },
  ];
  const strips = [];
  for (const art of ex.art) {
    const [src, frames] = ART[art];
    files.push({ path: `${root}/images/${art}`, enc: "base64", content: b64(gamesPath(src)) });
    strips.push(`    - strip: ${art}\n      frames: ${frames}`);
  }
  let yaml = "palettegroups:\n  main:\n" + strips.join("\n") + "\n";
  for (const art of ex.fullscreen || []) {
    const [src, radius] = FULLSCREEN_ART[art];
    files.push({ path: `${root}/images/${art}`, enc: "base64", content: b64(gamesPath(src)) });
    yaml += `  clouds:\n    - fullscreen: ${art}\n      radius: ${radius}\n`;
  }
  files.push({ path: `${root}/images/__images__.yaml`, enc: "utf8", content: yaml });
  return { files, imagesRoot: `${root}/images`, slug: `docs.${name}` };
}

async function openEmulator(browser) {
  const page = await browser.newPage({ viewport: { width: 1000, height: 1000 } });
  page.on("pageerror", (e) => console.log("pageerror:", e.message.slice(0, 300)));
  await page.goto(`${BASE}/index.html`);
  await page.waitForFunction(() => window.VentilastationWebEmulator, null, { timeout: 60000 });
  // The 2D renderer reads back reliably in headless Chromium; WebGL needs a GPU.
  await page.evaluate(() => {
    const box = document.getElementById("force-2d-fallback");
    if (box && !box.checked) box.click();
  });
  if (process.env.RENDERER === "shader") {
    await page.evaluate(() => {
      const select = document.getElementById("scene-renderer-mode");
      select.value = "shader";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }
  await page.waitForTimeout(1000);
  return page;
}

async function canvasPng(page) {
  const data = await page.evaluate(() => {
    const canvas = [...document.querySelectorAll("canvas")].find(
      (c) => !c.hidden && c.offsetParent !== null && c.id.startsWith("frame-canvas"));
    return canvas ? canvas.toDataURL("image/png") : null;
  });
  if (!data) throw new Error("no visible frame canvas");
  return Buffer.from(data.split(",")[1], "base64");
}

// Draws text labels (canvas pixel coordinates, centred on x/y, or starting at x
// with `left`) over a screenshot. Keep them clear of the drawing and of each other.
async function annotate(browser, png, labels) {
  const page = await browser.newPage({ viewport: { width: 880, height: 880 } });
  const items = labels.map((l) =>
    `<div style="position:absolute;left:${l.x}px;top:${l.y}px;` +
    `transform:translate(${l.left ? "0" : "-50%"},-50%);` +
    `color:${l.color || "#e6edf3"};white-space:pre;text-align:${l.left ? "left" : "center"};` +
    `font:600 ${l.size || 26}px/1.3 system-ui,sans-serif;` +
    `text-shadow:0 0 6px #000,0 0 3px #000">${l.text}</div>`).join("");
  await page.setContent(
    `<body style="margin:0;position:relative;width:880px;height:880px;overflow:hidden">` +
    `<img src="data:image/png;base64,${png.toString("base64")}" width="880" height="880">${items}</body>`);
  const out = await page.screenshot({ clip: { x: 0, y: 0, width: 880, height: 880 } });
  await page.close();
  return out;
}

async function runExample(browser, name, ex) {
  const page = await openEmulator(browser);
  const { files, imagesRoot, slug } = exampleFiles(name, ex);
  await page.evaluate(async ({ files, imagesRoot, slug, base }) => {
    const api = window.VentilastationWebEmulator;
    for (const f of files) await api.writeProjectFile(f.path, f.content, f.enc);
    const builder = await import(`${base}/workspace-rom-builder.js`);
    await builder.rebuildRomForImagesRoot(api, imagesRoot);
    await api.restartRuntime({ full: true, autostartSlug: slug });
  }, { files, imagesRoot, slug, base: BASE });
  await page.waitForTimeout(1500);
  for (const step of ex.steps) {
    if (step.wait) await page.waitForTimeout(step.wait);
    else if (step.down) await page.keyboard.down(step.down);
    else if (step.up) await page.keyboard.up(step.up);
    else if (step.shot) {
      const out = path.join(OUT, step.shot);
      let png = await canvasPng(page);
      if (step.labels) png = await annotate(browser, png, step.labels);
      fs.writeFileSync(out, png);
      console.log("wrote", path.relative(REPO, out));
    }
  }
  await page.close();
}

async function renderDiagram(browser, svgFile) {
  let svg = fs.readFileSync(svgFile, "utf8");
  svg = svg.replace(/\{\{art:([^}]+)\}\}/g, (_, rel) =>
    `data:image/png;base64,${b64(gamesPath(rel))}`);
  const m = svg.match(/viewBox="0 0 (\d+) (\d+)"/);
  const [w, h] = [Number(m[1]), Number(m[2])];
  const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: 2 });
  await page.setContent(`<body style="margin:0;background:#0b0f14">${svg}</body>`);
  const out = path.join(OUT, path.basename(svgFile, ".svg") + ".png");
  await page.screenshot({ path: out, clip: { x: 0, y: 0, width: w, height: h } });
  await page.close();
  console.log("wrote", path.relative(REPO, out));
}

const browser = await chromium.launch({
  executablePath: CHROMIUM,
  args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--no-sandbox"],
});
try {
  const diagramDir = path.join(HERE, "diagrams");
  for (const f of fs.readdirSync(diagramDir).filter((f) => f.endsWith(".svg")).sort()) {
    if (wanted(path.basename(f, ".svg"))) await renderDiagram(browser, path.join(diagramDir, f));
  }
  for (const [name, ex] of Object.entries(EXAMPLES)) {
    if (wanted(name)) await runExample(browser, name, ex);
  }
} finally {
  await browser.close();
}
