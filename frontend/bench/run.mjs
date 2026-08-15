// run.mjs — drive the frame-time bench in a real browser and print the result.
//
// Needs the dev server up (npm --prefix frontend run dev).
//
//   node frontend/bench/run.mjs [--seconds 20] [--heatmap 0] [--theme night]
//                              [--headless] [--url http://localhost:5173]
//
// Headed by default, and that is not cosmetic. Headless Chromium falls back to
// the SwiftShader software rasteriser, which does not merely scale the numbers
// — it invents a reproducible ~12 second frame at low zoom that no GPU-backed
// browser shows, and flattens the per-state costs this bench exists to track.
// Use --headless only to check that the harness still runs; never quote its
// timings. The --disable-*backgrounding flags keep the measurement burst from
// being throttled when the window is not frontmost.

import { chromium } from "playwright";

const argv = process.argv.slice(2);
const arg = (name, fallback) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback;
};

const base = arg("url", "http://localhost:5173");
const qs = new URLSearchParams({
  seconds: arg("seconds", "20"),
  heatmap: arg("heatmap", "1"),
  theme: arg("theme", "day"),
});
const url = `${base}/bench/?${qs}`;

const browser = await chromium.launch({
  headless: argv.includes("--headless"),
  args: [
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
  ],
});
// deviceScaleFactor 2 on purpose: RoadRenderer initialises Pixi with
// `resolution: window.devicePixelRatio`, so on the Retina machines this is
// actually developed on it fills four times the pixels. Measuring at dpr 1
// quietly reports a fifth of the real per-state cost.
const page = await browser.newPage({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: Number(arg("dpr", "2")),
});

const errors = [];
// The bench page has no favicon, and Chromium logs that as a console error.
// It says nothing about the renderer, and leaving it in would make the
// "zero console errors" check in the regression sweep permanently red.
const isNoise = (text) => /favicon/i.test(text);
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => {
  if (m.type() === "error" && !isNoise(m.text())) errors.push(m.text());
});
page.on("requestfailed", (r) => {
  if (!isNoise(r.url())) errors.push(`request failed: ${r.url()}`);
});
page.on("response", (r) => {
  if (r.status() >= 400 && !isNoise(r.url())) {
    errors.push(`HTTP ${r.status()}: ${r.url()}`);
  }
});

await page.goto(url, { waitUntil: "load" });
await page.waitForFunction(() => window.__BENCH_DONE__ === true, null, { timeout: 180_000 });
const result = await page.evaluate(() => window.__BENCH__);
await browser.close();

if (!result) {
  console.error("bench produced no result");
  console.error(errors.join("\n"));
  process.exit(1);
}

const pad = (s, n) => String(s).padStart(n);
const row = (label, s) =>
  `${label.padEnd(8)}${pad(s.n, 5)}  ${pad(s.mean.toFixed(2), 7)}  ` +
  `${pad(s.p50.toFixed(2), 7)}  ${pad(s.p95.toFixed(2), 7)}  ` +
  `${pad(s.worst.toFixed(2), 7)}  ${pad(s.overBudget, 5)}`;

console.log(
  `${result.roads} roads · ${result.vehicles} vehicles · ` +
  `heatmap ${result.heatmap ? "ON" : "OFF"} · ${result.seconds}s @60fps`,
);
console.log(
  `${"".padEnd(8)}${pad("n", 5)}  ${pad("mean", 7)}  ${pad("p50", 7)}  ` +
  `${pad("p95", 7)}  ${pad("worst", 7)}  ${pad(">16.7", 5)}`,
);
console.log(row("all", result.all));
console.log(row("state", result.state));
console.log(row("camera", result.camera));

if (result.slowest?.length) {
  console.log("\nslowest frames (cost = setState + tick):");
  for (const s of result.slowest) {
    console.log(
      `  #${pad(s.frame, 5)}  ${pad(s.cost.toFixed(2), 9)} ms  ` +
      `setState ${pad(s.setState.toFixed(2), 8)}  tick ${pad(s.tick.toFixed(2), 9)}  ` +
      `scale ${s.scale}${s.stateFrame ? "  [state]" : ""}`,
    );
  }
}

if (errors.length) {
  console.log(`\nconsole errors (${errors.length}):`);
  for (const e of errors.slice(0, 10)) console.log("  " + e);
} else {
  console.log("\nzero console errors");
}
