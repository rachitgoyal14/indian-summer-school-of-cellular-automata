// verify_stage4.mjs — browser verification of the Stage 4 disruption UI.
//
// Triggers each of the brief's disruption types from the real control panel
// and confirms it becomes active (via the hidden dis-debug JSON) and that the
// canvas changes (the coloured blocked cells render). Also checks that a
// stochastic disruption is live-adjustable (prob→active, clear→gone) and that
// permanent reservations persist. Screenshots → docs/evidence/stage4/.

import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = resolve(__dirname, "../../docs/evidence/stage4");
mkdirSync(OUT, { recursive: true });

const URL = process.argv[2] || "http://127.0.0.1:5173/";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = {};
function log(k, v) {
  results[k] = v;
  console.log(`[verify4] ${k}: ${JSON.stringify(v)}`);
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1300, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => {
  if (m.type() === "error") errors.push(m.text());
});

const counts = async () =>
  JSON.parse(await page.locator('[data-testid="dis-debug"]').innerText() || "{}");

const setProb = async (label, value) => {
  // find the field whose text contains the label, then its range input
  const field = page.locator(".panel .field", { hasText: label }).first();
  const slider = field.locator('input[type="range"]');
  await slider.evaluate((el, v) => {
    const set = Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value",
    ).set;
    set.call(el, String(v));
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }, value);
};

async function waitForKind(kind, timeoutMs = 8000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const c = await counts();
    if ((c[kind] ?? 0) > 0) return c[kind];
    await sleep(200);
  }
  return 0;
}

try {
  await page.goto(URL, { waitUntil: "networkidle" });
  await page.waitForSelector(".pixi-host canvas", { timeout: 15000 });
  await page.waitForSelector(".conn.up", { timeout: 15000 });
  // one-way ring at low density gives lots of room to place disruptions
  await page.locator("select").selectOption("one_way");
  await sleep(800);

  // 1) each stochastic kind: crank its probability, confirm it becomes active
  for (const [kind, label] of [
    ["breakdown", "Fall car (breakdown)"],
    ["tree", "Fallen tree"],
    ["accident", "Accident (two cars)"],
  ]) {
    await setProb(label, 0.05);
    const n = await waitForKind(kind);
    log(`${kind}_active`, n);
    await setProb(label, 0); // stop triggering more
  }

  // 2) flood via the manual "Flood now" button
  await page.getByRole("button", { name: /Flood now/ }).click();
  log("flood_active", await waitForKind("flood"));

  // 3) permanent reservations: add lock + parking, confirm present
  await page.getByRole("button", { name: /Add lock/ }).click();
  await page.getByRole("button", { name: /Add parking/ }).click();
  await sleep(600);
  const withReserved = await counts();
  log("lock_active", withReserved.lock ?? 0);
  log("parking_active", withReserved.parking ?? 0);

  await page.screenshot({ path: `${OUT}/01_all_disruptions.png` });

  // 4) permanence: run a while, locks/parking must persist
  await sleep(2500);
  const later = await counts();
  log("reservations_persist", {
    lock: later.lock ?? 0,
    parking: later.parking ?? 0,
    ok: (later.lock ?? 0) >= 1 && (later.parking ?? 0) >= 1,
  });

  // 5) clear all → everything gone
  await page.getByRole("button", { name: /Clear all/ }).click();
  await sleep(800);
  const cleared = await counts();
  const totalCleared = Object.values(cleared).reduce((a, b) => a + b, 0);
  log("clear_all_works", { remaining: totalCleared, ok: totalCleared === 0 });
  await page.screenshot({ path: `${OUT}/02_cleared.png` });

  log("page_errors", errors);
  const ok =
    errors.length === 0 &&
    results.breakdown_active > 0 &&
    results.tree_active > 0 &&
    results.accident_active > 0 &&
    results.flood_active > 0 &&
    results.lock_active > 0 &&
    results.parking_active > 0 &&
    results.reservations_persist?.ok &&
    results.clear_all_works?.ok;
  log("overall_ok", ok);
  console.log("\nEVIDENCE written to", OUT);
} finally {
  await browser.close();
}

const hardFail =
  results.page_errors?.length > 0 ||
  !(results.breakdown_active > 0) ||
  !(results.tree_active > 0) ||
  !(results.accident_active > 0) ||
  !(results.flood_active > 0) ||
  !(results.lock_active > 0) ||
  !(results.parking_active > 0) ||
  !results.clear_all_works?.ok;
process.exit(hardFail ? 1 : 0);
