// verify_stage5.mjs — browser verification of the Stage 5 analytics.
//
// Confirms: the live chart + entropy readout update; entropy MEASURABLY DROPS
// when disruptions cluster the traffic (the plan.md §8.4 point); and the
// heatmap overlay toggles and changes what's drawn. Screenshots →
// docs/evidence/stage5/.

import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(__dirname, "../../docs/evidence/stage5");
mkdirSync(OUT, { recursive: true });

const URL = process.argv[2] || "http://127.0.0.1:5173/";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = {};
const log = (k, v) => {
  results[k] = v;
  console.log(`[verify5] ${k}: ${JSON.stringify(v)}`);
};

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1320, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => {
  if (m.type() === "error") errors.push(m.text());
});

const entropy = async () => {
  const txt = await page.locator('[data-testid="entropy"]').innerText();
  return parseFloat(txt); // leading "0.950 norm · ..." → 0.950
};

const setProb = async (label, value) => {
  const field = page.locator(".panel .field", { hasText: label }).first();
  const slider = field.locator('input[type="range"]');
  await slider.evaluate((el, v) => {
    const set = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype, "value").set;
    set.call(el, String(v));
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
};

try {
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.waitForSelector(".pixi-host canvas", { timeout: 15000 });
  await page.waitForSelector(".conn.up", { timeout: 15000 });
  await page.locator("select").selectOption("one_way");
  await page.waitForSelector('[data-testid="entropy"]');
  await sleep(2500); // let the chart accumulate + reach steady spread

  const eBaseline = await entropy();
  log("entropy_baseline_spread", eBaseline);
  await page.screenshot({ path: `${OUT}/01_baseline_chart.png` });

  // Cluster the traffic: heavy flood + breakdowns → pile-ups → entropy drops
  await setProb("Fall car (breakdown)", 0.05);
  await setProb("Accident (two cars)", 0.05);
  await setProb("Flood", 0.03);
  for (let i = 0; i < 4; i++) {
    await page.getByRole("button", { name: /Flood now/ }).click();
    await sleep(200);
  }
  await sleep(6000); // let congestion build

  const eClustered = await entropy();
  log("entropy_after_clustering", eClustered);
  log("entropy_dropped", {
    from: eBaseline,
    to: eClustered,
    ok: eClustered < eBaseline,
  });
  await page.screenshot({ path: `${OUT}/02_clustered_chart.png` });

  // Heatmap overlay toggles and changes the canvas
  const canvas = page.locator(".pixi-host canvas");
  const before = await canvas.screenshot();
  await page.getByRole("button", { name: /Heatmap/ }).click();
  await sleep(700);
  const after = await canvas.screenshot();
  log("heatmap_changes_canvas", { changed: !before.equals(after) });
  await page.screenshot({ path: `${OUT}/03_heatmap_on.png` });

  log("page_errors", errors);
  const ok =
    errors.length === 0 &&
    Number.isFinite(eBaseline) &&
    eClustered < eBaseline &&
    results.heatmap_changes_canvas.changed;
  log("overall_ok", ok);
  console.log("\nEVIDENCE written to", OUT);
} finally {
  await browser.close();
}

const hardFail =
  results.page_errors?.length > 0 ||
  !Number.isFinite(results.entropy_baseline_spread) ||
  !results.entropy_dropped?.ok ||
  !results.heatmap_changes_canvas?.changed;
process.exit(hardFail ? 1 : 0);
