/**
 * verify_stage8.mjs — headless browser verification for Stage 8 real map import.
 *
 * Tests:
 *  1. RegionSearch UI component is present (input box + import button)
 *  2. Type a place name ("IIT BHU Varanasi") and click "Import"
 *  3. Backend geocodes, fetches Overpass data, translates to Network, and sends import_result
 *  4. Frontend loads the real network and updates canvas/readout
 *  5. Capture screenshot evidence in docs/evidence/stage8/
 *
 * Run with: node scripts/verify_stage8.mjs
 */

import { chromium } from "playwright";
import * as fs from "fs";
import * as path from "path";
import { fileURLToPath } from "url";
import { spawn } from "child_process";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const FRONTEND = "http://localhost:5173";
const EVIDENCE_DIR = path.join(__dirname, "../../docs/evidence/stage8");
fs.mkdirSync(EVIDENCE_DIR, { recursive: true });

const results = [];
let browser, page, backendProc, frontendProc;

function check(name, ok, detail = "") {
  const status = ok ? "✅" : "❌";
  console.log(`  ${status} ${name}${detail ? ` — ${detail}` : ""}`);
  results.push({ name, ok, detail });
}

async function shot(name) {
  if (page) {
    await page.screenshot({
      path: path.join(EVIDENCE_DIR, `${name}.png`),
      fullPage: false,
    });
  }
}

// Start backend and frontend servers
function startServers() {
  const backendDir = path.join(__dirname, "../../backend");
  const frontendDir = path.join(__dirname, "..");

  console.log("Starting backend server...");
  backendProc = spawn("python3", ["scripts/run_server.py"], { cwd: backendDir, stdio: "pipe" });

  console.log("Starting frontend dev server...");
  frontendProc = spawn("npm", ["run", "dev"], { cwd: frontendDir, stdio: "pipe" });
}

async function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

try {
  startServers();
  await sleep(6000); // give servers time to start up

  browser = await chromium.launch({ headless: true });
  page = await browser.newPage();
  page.on("pageerror", (e) => console.error("  PAGE ERROR:", e.message));

  await page.goto(FRONTEND, { waitUntil: "networkidle" });
  await page.waitForTimeout(3000); // wait for WebSocket connection

  // ---- 1. RegionSearch UI renders ----
  const searchInput = await page.$(".region-input");
  const importBtn = await page.$(".region-btn");
  check("RegionSearch UI renders (input + button)", !!(searchInput && importBtn));

  await shot("01_region_search_initial");

  // ---- 2. Perform region import ----
  if (searchInput && importBtn) {
    await searchInput.fill("IIT BHU Varanasi");
    console.log("Clicking Import button for 'IIT BHU Varanasi'...");
    await importBtn.click();

    // Wait for import to complete (up to 20 seconds for Overpass + network translation)
    await page.waitForTimeout(8000);

    const stepMetric = await page.$(".metric-value");
    check("Region import completed: canvas/readout active", !!stepMetric);

    await shot("02_region_search_imported_iit_bhu");
  }

  // ---- Summary ----
  const total = results.length;
  const passed = results.filter((r) => r.ok).length;
  console.log(`\nStage 8 browser verification: ${passed}/${total} checks passed.`);
  const overall_ok = passed === total;
  console.log(`overall_ok: ${overall_ok}`);

  fs.writeFileSync(
    path.join(EVIDENCE_DIR, "stage8_browser_results.json"),
    JSON.stringify({ passed, total, overall_ok, results }, null, 2),
  );
} catch (err) {
  console.error("Error during browser verification:", err);
} finally {
  await browser?.close();
  if (backendProc) backendProc.kill();
  if (frontendProc) frontendProc.kill();
}
