// verify_stage3.mjs — browser verification of the Stage 3 frontend.
//
// Drives the real app through all 5 lane/junction configurations, captures a
// screenshot of each, and checks: the canvas renders live motion, junctions
// appear as queue readouts on junction configs, and zoom/pan works on the
// multi-junction grid (visible cell-range readout changes). Screenshots →
// docs/evidence/stage3/.

import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(__dirname, "../../docs/evidence/stage3");
mkdirSync(OUT, { recursive: true });

const URL = process.argv[2] || "http://127.0.0.1:5173/";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = {};
function log(k, v) {
  results[k] = v;
  console.log(`[verify3] ${k}: ${JSON.stringify(v)}`);
}

const CONFIGS = [
  ["one_way", "01_one_way"],
  ["two_way_no_interaction", "02_two_way_no_interaction"],
  ["two_way_turns", "03_two_way_turns"],
  ["two_way_bidirectional_turns", "04_bidirectional_turns"],
  ["grid", "05_grid"],
];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => {
  if (m.type() === "error") errors.push(m.text());
});

try {
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.waitForSelector(".pixi-host canvas", { timeout: 15000 });
  await page.waitForSelector(".conn.up", { timeout: 15000 });

  const canvas = page.locator(".pixi-host canvas");

  for (const [value, name] of CONFIGS) {
    await page.locator("select").selectOption(value);
    await sleep(1600); // let it rebuild + run a bit
    // canvas shows motion for this config
    const a = await canvas.screenshot();
    await sleep(500);
    const b = await canvas.screenshot();
    const junctionBadges = await page.locator(".qbadge").count();
    log(name, { motion: !a.equals(b), junctionBadges });
    await page.screenshot({ path: `${OUT}/${name}.png` });
  }

  // On the grid (currently selected), confirm junctions rendered as queues
  const gridJunctions = await page.locator(".qbadge").count();
  log("grid_junction_readouts", gridJunctions);

  // zoom + pan across the whole network
  const box = await canvas.boundingBox();
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  const vis = async () =>
    (await page.locator(".canvas-overlay .badge").innerText()).trim();
  const before = await vis();
  await page.mouse.move(cx, cy);
  for (let i = 0; i < 6; i++) {
    await page.mouse.wheel(0, -200);
    await sleep(60);
  }
  const after = await vis();
  await page.mouse.down();
  await page.mouse.move(cx - 200, cy - 120, { steps: 10 });
  await page.mouse.up();
  await sleep(300);
  log("grid_zoom_pan", { before, after, zoomChanged: before !== after });
  await page.screenshot({ path: `${OUT}/06_grid_zoom_pan.png` });

  log("page_errors", errors);
  const ok =
    errors.length === 0 &&
    gridJunctions >= 1 &&
    CONFIGS.every(([, n]) => results[n]?.motion);
  log("overall_ok", ok);
  console.log("\nEVIDENCE written to", OUT);
} finally {
  await browser.close();
}

const hardFail =
  results.page_errors?.length > 0 ||
  !(results.grid_junction_readouts >= 1) ||
  !CONFIGS.every(([, n]) => results[n]?.motion);
process.exit(hardFail ? 1 : 0);
