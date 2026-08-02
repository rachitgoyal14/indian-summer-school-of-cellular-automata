// capture_video.mjs — capture a ~12s frame sequence of the live app (with a
// zoom and a pan action mid-way) into docs/evidence/stage2/frames/. The
// wrapper then stitches these into an MP4 with ffmpeg. This is the automated
// stand-in for the "screen-recorded video" acceptance item: real distinct
// frames with a progressing step counter, captured from the real browser.

import { chromium } from "playwright";
import { mkdirSync, rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FRAMES = resolve(__dirname, "../../docs/evidence/stage2/frames");
rmSync(FRAMES, { recursive: true, force: true });
mkdirSync(FRAMES, { recursive: true });

const URL = process.argv[2] || "http://127.0.0.1:5173/";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const pad = (n) => String(n).padStart(4, "0");

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
await page.goto(URL, { waitUntil: "networkidle" });
await page.waitForSelector(".conn.up", { timeout: 15000 });

// Ensure the sim is running before we start capturing.
const resumeBtn = page.getByRole("button", { name: /Resume/ });
if (await resumeBtn.count()) await resumeBtn.click();
await sleep(300);

const canvas = page.locator(".pixi-host canvas");
const box = await canvas.boundingBox();
const cx = box.x + box.width / 2;
const cy = box.y + box.height / 2;
await page.mouse.move(cx, cy);

const TOTAL = 120; // frames
const FPS_SLEEP = 100; // ms between frames → ~10 fps, ~12s
let i = 0;
for (; i < TOTAL; i++) {
  // scripted camera actions interleaved with the running sim
  if (i >= 30 && i < 42) await page.mouse.wheel(0, -160); // zoom in
  if (i === 60) {
    // pan
    await page.mouse.move(cx, cy);
    await page.mouse.down();
    await page.mouse.move(cx - 260, cy, { steps: 10 });
    await page.mouse.up();
  }
  if (i >= 90 && i < 100) await page.mouse.wheel(0, 160); // zoom back out
  await page.screenshot({ path: `${FRAMES}/frame_${pad(i)}.png` });
  await sleep(FPS_SLEEP);
}
console.log(`[capture] wrote ${i} frames to ${FRAMES}`);
await browser.close();
