// verify-sidebar.mjs — the sidebar redesign must not have cost any behaviour.
//
// Needs the dev server up (npm --prefix frontend run dev):
//
//     node frontend/bench/verify-sidebar.mjs
//
// A screenshot proves the sidebar looks right; this proves it still works. It
// covers what the redesign actually put at risk: panels that now collapse,
// sliders whose filled track is painted by a hook instead of by each call
// site, class names the sidebar shares with the canvas overlay, and the rule
// that the sidebar chrome ignores the map theme.

import { chromium } from "playwright";
const b = await chromium.launch({ args:["--disable-renderer-backgrounding"] });
const page = await b.newPage({ viewport: { width: 1500, height: 1000 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type()==="error" && !/favicon/i.test(m.text())) errors.push(m.text()); });
await page.addInitScript(() => localStorage.setItem("ca-sim-theme","day"));
await page.goto("http://localhost:5173/", { waitUntil:"load" });
await page.waitForTimeout(2500);

let fails = 0;
const check = (ok, msg) => { if(!ok) fails++; console.log(`${ok?"PASS":"FAIL"}  ${msg}`); };

// 1. collapse + expand a panel
const head = page.locator('.panel-head', { hasText: 'Configuration' });
await head.click(); await page.waitForTimeout(250);
const closed = await page.locator('.panel.is-closed .panel-title', { hasText:'Configuration' }).count();
await head.click(); await page.waitForTimeout(250);
const open = await page.locator('.panel.is-open .panel-title', { hasText:'Configuration' }).count();
check(closed === 1 && open === 1, "panel collapses and expands");

// 2. pause / resume actually reaches the server
const pause = page.locator('.sidebar button', { hasText: 'Pause' });
await pause.click(); await page.waitForTimeout(900);
const resumed = await page.locator('.sidebar button', { hasText: 'Resume' }).count();
check(resumed === 1, "Pause reached the server (button flipped to Resume)");
await page.locator('.sidebar button', { hasText: 'Resume' }).click();
await page.waitForTimeout(600);

// 3. a slider still commits, and its filled track follows.
// Driven by the keyboard rather than by assigning `.value`: React tracks an
// input's value through a native setter, so a direct assignment is invisible
// to it and the component would re-render straight back over the change.
const slider = page.locator('.sidebar input[type="range"]').first();
const before3 = await slider.evaluate((el) => Number(el.value));
const pctBefore = await slider.evaluate((el) => el.style.getPropertyValue("--pct"));
await slider.focus();
for (let i = 0; i < 5; i++) await page.keyboard.press("ArrowRight");
await page.waitForTimeout(800);
const after3 = await slider.evaluate((el) => Number(el.value));
const pctAfter = await slider.evaluate((el) => el.style.getPropertyValue("--pct"));
check(after3 > before3, `slider value committed (${before3} -> ${after3})`);
check(pctAfter !== pctBefore && pctAfter.endsWith("%"),
  `slider fill followed the value (${pctBefore} -> ${pctAfter})`);

// 4. every slider on screen has a painted fill, not just the one touched
const unpainted = await page.evaluate(() =>
  [...document.querySelectorAll('aside.sidebar input[type="range"]')]
    .filter((el) => !el.style.getPropertyValue("--pct")).length);
check(unpainted === 0, `all sliders painted (${unpainted} unpainted)`);

// 5. the canvas overlay chips kept their own styling, not the sidebar's
const overlayRadius = await page.evaluate(() => {
  const el = document.querySelector('.canvas-overlay .ghost-btn');
  return el ? getComputedStyle(el).borderRadius : null;
});
check(overlayRadius === "4px", `canvas overlay button untouched by sidebar rules (radius ${overlayRadius})`);

// 6. sidebar chrome stays dark after a theme switch
const before = await page.evaluate(() => getComputedStyle(document.querySelector("aside.sidebar")).backgroundColor);
await page.locator('.topbar .theme-toggle').click();
await page.waitForTimeout(500);
const after = await page.evaluate(() => getComputedStyle(document.querySelector("aside.sidebar")).backgroundColor);
check(before === after, `sidebar stays dark across themes (${before} -> ${after})`);

// 7. select still changes config
await page.selectOption('.sidebar select', 'grid');
await page.waitForTimeout(1200);
const cfg = await page.evaluate(() => document.querySelector('.sidebar select')?.value);
check(cfg === "grid", `select still drives config (${cfg})`);

check(errors.length === 0, errors.length ? "console errors: "+errors.join("; ") : "zero console errors");
await b.close();
process.exit(fails ? 1 : 0);
