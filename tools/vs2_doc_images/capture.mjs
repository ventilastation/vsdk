// Regenerates the images in docs/vs2/images/.
//
//   cd web && python3 -m http.server 8765      # serve the web emulator
//   cd tools/vs2_doc_images && npm install && node capture.mjs [name ...]
//
// Emulator screenshots: each example in examples/ is written into the browser
// emulator's workspace as games/docs/<name>, its ROM is built in the browser,
// the runtime is restarted into it, and the polar canvas is saved after the
// scripted key presses. Nothing is written into the repo's games/ tree. The
// `game` entry instead loads the finished tutorial game, as it is in the repo
// (games/demos/tutorial_game).
//
// Diagrams: each diagrams/*.svg is rendered to a PNG with the same browser.
// `{{art:<path under games/>}}` in an SVG is replaced by that image as a data
// URI, so diagrams can show the real art.


import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(HERE, "../..");
const BASE = process.env.BASE || "http://localhost:8765";
const OUT = process.env.OUT || path.join(REPO, "docs/vs2/images");
// Which browser: $CHROMIUM (a Chrome/Chromium binary), else the one in
// /opt/pw-browsers if it exists, else Playwright's own (npx playwright-core install chromium).
const CHROMIUM = process.env.CHROMIUM
  || (fs.existsSync("/opt/pw-browsers/chromium") ? "/opt/pw-browsers/chromium" : undefined);

const ART = {
  "ship.png": ["alecu/vixeous/images/ship.png", 4],
  "shots.png": ["alecu/vixeous/images/shots.png", 3],
  "enemy.png": ["alecu/vixeous/images/enemy.png", 6],
  "explosion.png": ["alecu/vixeous/images/explosion.png", 6],
  "numerals.png": ["alecu/vyruss_vs2/images/numerals.png", 12, "0123456789 *"],
  "terrain.png": ["alecu/mapdemo/images/terrain.png", 6],
  "rainbow437.png": ["../system/shared/other/images/rainbow437.png", 256],
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
        { x: 210, y: 300, text: "TUNNEL layer\ny = 0, 40, 80,\n120, 170, 220", color: "#8fb4ff" },
        { x: 640, y: 740, text: "HUD layer\ny = 0, 14, 28, 40", color: "#ffd166" },
      ],
    }],
  },
  layers: {
    art: ["ship.png", "enemy.png", "numerals.png"],
    fullscreen: ["clouds.png"],
    steps: [{ wait: 800 }, {
      shot: "display-layers.png",
    }],
  },
  flips: {
    art: ["numerals.png"],
    steps: [{ wait: 800 }, {
      shot: "labels-flips.png",
      labels: [
        { x: 440, y: 330, size: 24, text: "top, y = 1, no flips: upside-down", color: "#ff8f8f" },
        { x: 440, y: 368, size: 24, text: "top, y = 14, flip_x and flip_y: upright", color: "#7ee0a1" },
        { x: 440, y: 406, size: 24, text: "bottom, y = 1, no flips: upright", color: "#7ee0a1" },
      ],
    }],
  },
  game: {
    repoGame: "demos/tutorial_game",
    steps: [
      { wait: 800 }, { shot: "game-title.png" },
      ...key("Space"), { wait: 7000 },
      { down: "ArrowLeft" }, { wait: 150 }, { up: "ArrowLeft" },
      ...key("Space"), { wait: 250 }, ...key("Space"), { wait: 250 },
      { down: "ArrowRight" }, { wait: 300 }, { up: "ArrowRight" },
      ...key("Space"), { wait: 250 }, ...key("Space"), { wait: 150 },
      { shot: "game-play.png" },
    ],
  },
  gameover: {
    art: ["numerals.png", "rainbow437.png"],
    alsoLoad: ["demos/tutorial_game/code/tutorial_game.py"],
    steps: [{ wait: 800 }, { shot: "game-over.png" }],
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
};

const only = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const wanted = (name) => only.length === 0 || only.includes(name);

fs.mkdirSync(OUT, { recursive: true });

const gamesPath = (rel) =>
  rel.startsWith("local:") ? path.join(HERE, "art", rel.slice(6)) : path.join(REPO, "games", rel);
const b64 = (file) => fs.readFileSync(file).toString("base64");

// A game that lives in the repo (games/<group>/<name>) is loaded as it is.
function repoGameFiles(ex) {
  const dir = path.join(REPO, "games", ex.repoGame);
  const [group, name] = ex.repoGame.split("/");
  const root = `games/${group}/${name}`;
  const files = [];
  const walk = (sub) => {
    for (const entry of fs.readdirSync(path.join(dir, sub), { withFileTypes: true })) {
      const rel = path.posix.join(sub, entry.name);
      if (entry.isDirectory()) {
        if (entry.name !== "__pycache__") walk(rel);
      } else if (/\.(py|json|yaml)$/.test(entry.name)) {
        files.push({ path: `${root}/${rel}`, enc: "utf8", content: fs.readFileSync(path.join(dir, rel), "utf8") });
      } else if (/\.png$/.test(entry.name)) {
        files.push({ path: `${root}/${rel}`, enc: "base64", content: b64(path.join(dir, rel)) });
      }
    }
  };
  walk("");
  return { files, imagesRoot: `${root}/images`, slug: `${group}.${name}` };
}

function exampleFiles(name, ex) {
  if (ex.repoGame) return repoGameFiles(ex);
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
  // Repo files the example imports (games/<path>), written to the same place.
  for (const rel of ex.alsoLoad || []) {
    files.push({ path: `games/${rel}`, enc: "utf8", content: fs.readFileSync(gamesPath(rel), "utf8") });
  }
  const strips = [];
  for (const art of ex.art) {
    const [src, frames, glyphs] = ART[art];
    files.push({ path: `${root}/images/${art}`, enc: "base64", content: b64(gamesPath(src)) });
    strips.push(`    - strip: ${art}\n      frames: ${frames}` + (glyphs ? `\n      glyphs: "${glyphs}"` : ""));
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

// RENDERER picks what draws the disc: "2d" (default; the canvas fallback, which
// works in headless Chromium without a GPU), "webgl" (the WebGL renderer with the
// CPU compositor) or "shader" (WebGL plus the GPU shader compositor). The last
// two want a real GPU: run with GPU=1 so Chromium is not forced onto SwiftShader.
const RENDERER = process.env.RENDERER || "2d";

// 880 CSS pixels is the size of every emulator screenshot, and what the label
// coordinates below are written for. The stage is the viewport height minus the
// 120px control bar above it (see .stage-display in web/styles.css).
const STAGE = 880;

async function openEmulator(browser) {
  // A fresh context per run, so no UI state (open panels) carries over.
  const context = await browser.newContext({ viewport: { width: 1300, height: STAGE + 120 } });
  const page = await context.newPage();
  page.on("pageerror", (e) => console.log("pageerror:", e.message.slice(0, 300)));
  await page.goto(`${BASE}/index.html`);
  await page.waitForFunction(() => window.VentilastationWebEmulator, null, { timeout: 60000 });
  // Screenshots are of the stage only: no base-controls preview or fullscreen button.
  await page.addStyleTag({ content: ".base-preview, .stage-fullscreen-toggle { display: none !important; }" });
  await page.evaluate((renderer) => {
    const force2d = document.getElementById("force-2d-fallback");
    if (force2d && force2d.checked !== (renderer === "2d")) force2d.click();
    if (renderer === "shader") {
      const select = document.getElementById("scene-renderer-mode");
      select.value = "shader";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }, RENDERER);
  await page.waitForTimeout(1000);
  return page;
}

// The stage element: the dark panel and the black disc inset in it, as the
// emulator shows them.
async function stagePng(page) {
  return page.locator(".stage-display").screenshot();
}

// The label coordinates were written for a disc that filled the stage; the disc
// now sits inside a margin (see #frame-canvas-gl in web/styles.css). Labels that
// point at the drawing are pulled in by the same factor; `left` legends are not.
const DISC_FIT = 0.889;
const fit = (l) => (l.left ? l : {
  ...l,
  x: STAGE / 2 + (l.x - STAGE / 2) * DISC_FIT,
  y: STAGE / 2 + (l.y - STAGE / 2) * DISC_FIT,
});

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
      if (process.env.DEBUG) {
        console.log(await page.evaluate(() => JSON.stringify({
          shell: document.querySelector(".app-shell").className,
          error: document.getElementById("scene-error-message")?.textContent?.slice(0, 300),
          errorHidden: document.getElementById("scene-error-banner")?.hidden,
          stage: document.querySelector(".stage-display").getBoundingClientRect().width,
          panel: document.querySelector(".stage-panel").className,
          inner: [window.innerWidth, window.innerHeight],
          bodyH: document.body.scrollHeight,
          mobile: document.body.className + "|" + document.documentElement.className,
        })));
      }
      let png = await stagePng(page);
      if (step.labels) png = await annotate(browser, png, step.labels.map(fit));
      fs.writeFileSync(out, png);
      console.log("wrote", path.relative(REPO, out));
    }
  }
  await page.context().close();
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

// --list: print every image this script makes, how it is made and where the docs
// use it, as a Markdown table (the table in README.md comes from this).
if (process.argv.includes("--list")) {
  const docs = [];
  const walkDocs = (dir) => {
    for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) { if (e.name !== "images" && e.name !== "_build") walkDocs(p); }
      else if (e.name.endsWith(".md")) docs.push([path.relative(path.join(REPO, "docs/vs2"), p), fs.readFileSync(p, "utf8")]);
    }
  };
  walkDocs(path.join(REPO, "docs/vs2"));
  const usedIn = (file) => docs.filter(([, text]) => text.includes(`images/${file}`)).map(([n]) => n).join(", ") || "-";
  const rows = [];
  for (const f of fs.readdirSync(path.join(HERE, "diagrams")).filter((f) => f.endsWith(".svg")).sort()) {
    const file = f.replace(/\.svg$/, ".png");
    rows.push([file, "diagram", `diagrams/${f}`, `node capture.mjs ${f.replace(/\.svg$/, "")}`, usedIn(file)]);
  }
  for (const [name, ex] of Object.entries(EXAMPLES)) {
    for (const step of ex.steps.filter((x) => x.shot)) {
      const source = ex.repoGame ? `games/${ex.repoGame} (played)` : `examples/${name}.py`;
      rows.push([step.shot, step.labels ? "emulator screenshot, annotated" : "emulator screenshot", source,
        `node capture.mjs ${name}`, usedIn(step.shot)]);
    }
  }
  console.log("| Image | Kind | Source | Command | Used in |\n|---|---|---|---|---|");
  for (const [file, kind, source, cmd, used] of rows) {
    console.log(`| \`${file}\` | ${kind} | \`${source}\` | \`${cmd}\` | ${used} |`);
  }
  process.exit(0);
}

const browser = await chromium.launch({
  executablePath: CHROMIUM,
  headless: !process.env.HEADFUL,
  args: process.env.GPU
    ? ["--no-sandbox"]
    : ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist", "--no-sandbox"],
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
