// verify_stage2.mjs — headless-browser verification of the Stage 2 frontend.
//
// Drives the REAL React+PixiJS app in Chromium against a running backend and
// produces non-fabricated evidence:
//   - the WebGL canvas mounts and the socket connects
//   - the step counter actually progresses over time (live motion)
//   - the rendered canvas pixels change between frames (visible motion)
//   - zoom (wheel) changes the visible cell-range readout (camera works,
//     stays in sync with the array)
//   - pause halts progress; single-step advances by exactly one
//   - ping/pong reports a real round-trip time
// Screenshots are written to docs/evidence/stage2/.
//
// Prereqs: backend on :8000 and the vite dev server on :5173 (see the
// verify_stage2.sh wrapper). Usage: node scripts/verify_stage2.mjs [url]

import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(__dirname, "../../docs/evidence/stage2");
mkdirSync(OUT, { recursive: true });

const URL = process.argv[2] || "http://127.0.0.1:5173/";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = {};
function log(k, v) {
  results[k] = v;
  console.log(`[verify] ${k}: ${JSON.stringify(v)}`);
}

const stepText = async (page) =>
  parseInt(
    await page
      .locator(".metric", { hasText: "step" })
      .locator(".metric-value")
      .innerText(),
    10,
  );

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
  log("connected", true);

  // 1) step progression over ~1.5s
  const s0 = await stepText(page);
  await sleep(1500);
  const s1 = await stepText(page);
  log("step_progressed", { from: s0, to: s1, ok: s1 > s0 });
  await page.screenshot({ path: `${OUT}/01_running.png` });

  // 2) canvas pixels change between frames (visible motion)
  const canvas = page.locator(".pixi-host canvas");
  const b0 = await canvas.screenshot();
  await sleep(500);
  const b1 = await canvas.screenshot();
  log("canvas_pixels_changed", { changed: !b0.equals(b1) });

  // 3) zoom (wheel) changes the visible cell-range readout
  const box = await canvas.boundingBox();
  const cx = box.x + box.width / 2;
  const cy = box.y + box.height / 2;
  const badgeText = async () =>
    (await page.locator(".canvas-overlay .badge").innerText()).trim();
  const visBefore = await badgeText();
  await page.mouse.move(cx, cy);
  for (let i = 0; i < 6; i++) {
    await page.mouse.wheel(0, -200); // zoom in
    await sleep(60);
  }
  await sleep(200);
  const visAfter = await badgeText();
  log("zoom_changed_visible_range", {
    before: visBefore,
    after: visAfter,
    ok: visBefore !== visAfter,
  });
  await page.screenshot({ path: `${OUT}/02_zoomed.png` });

  // 4) pan (drag) moves the scene
  const pb0 = await canvas.screenshot();
  await page.mouse.move(cx, cy);
  await page.mouse.down();
  await page.mouse.move(cx - 220, cy, { steps: 12 });
  await page.mouse.up();
  await sleep(200);
  const pb1 = await canvas.screenshot();
  log("pan_moved_scene", { changed: !pb0.equals(pb1) });
  await page.screenshot({ path: `${OUT}/03_panned.png` });

  // 5) pause halts progress; single-step advances by exactly one
  await page.getByRole("button", { name: /Pause/ }).click();
  await sleep(400);
  const p0 = await stepText(page);
  await sleep(900);
  const p1 = await stepText(page);
  log("pause_halts", { p0, p1, ok: p0 === p1 });
  await page.getByRole("button", { name: /Step/ }).click();
  await sleep(400);
  const p2 = await stepText(page);
  log("single_step_advances_by_one", { from: p1, to: p2, ok: p2 === p1 + 1 });
  await page.screenshot({ path: `${OUT}/04_paused_stepped.png` });

  // 6) ping/pong RTT
  await page.getByRole("button", { name: /Ping/ }).click();
  await sleep(300);
  const rtt = (
    await page.locator(".badge", { hasText: "RTT" }).innerText()
  ).trim();
  log("rtt_readout", rtt);

  log("page_errors", errors);
  log("overall_ok", errors.length === 0 && s1 > s0);
  console.log("\nEVIDENCE written to", OUT);
} finally {
  await browser.close();
}

// Exit non-zero if a hard check failed, so the wrapper can detect it.
const hardFail =
  !results.connected ||
  !results.step_progressed?.ok ||
  !results.canvas_pixels_changed?.changed ||
  !results.pause_halts?.ok ||
  !results.single_step_advances_by_one?.ok;
process.exit(hardFail ? 1 : 0);
