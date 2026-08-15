// verify-visuals.mjs — automated checks for the reference-style requirements
// that a screenshot cannot prove.
//
// Needs the dev server up (npm --prefix frontend run dev):
//
//     node frontend/bench/verify-visuals.mjs
//
// Checks:
//   1. Vehicles SNAP. Between two state messages a vehicle must not move at
//      all, and across one it must jump a whole cell. A screenshot cannot show
//      the absence of a tween, so this samples the sprite over 30 render
//      frames with the camera parked and no new state.
//   2. Headlights survive. The body colour and the white headlight are baked
//      into one texture, because a Pixi tint propagates to children and would
//      turn a separate white headlight sprite red. This probes the actual
//      rendered pixels rather than trusting that.

import { chromium } from "playwright";

const base = process.argv.includes("--url")
  ? process.argv[process.argv.indexOf("--url") + 1]
  : "http://localhost:5173";

const browser = await chromium.launch({
  args: [
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
  ],
});
const page = await browser.newPage({
  viewport: { width: 1200, height: 800 },
  deviceScaleFactor: 2,
});

const errors = [];
const isNoise = (t) => /favicon/i.test(t);
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => {
  if (m.type() === "error" && !isNoise(m.text())) errors.push(m.text());
});

await page.goto(`${base}/bench/?seconds=1`, { waitUntil: "load" });
await page.waitForFunction(() => window.__BENCH_DONE__ === true, null, { timeout: 60000 });

// ------------------------------------------------------------------ 1. snap
const snap = await page.evaluate(async () => {
  const r = window.__RENDERER__;
  r.app.ticker.stop();
  // Park the camera hard, so anything that moves is the vehicle itself.
  r.focusOn(-64, -37, 1.0);
  for (let i = 0; i < 400; i++) r.app.ticker.update(performance.now() + i * 16);

  const states = await fetch("./fixtures/bhu-states.json").then((x) => x.json());
  const pos = () => {
    const s = r.vehicleSprites.find((v) => v.visible);
    return s ? { x: +s.x.toFixed(4), y: +s.y.toFixed(4) } : null;
  };

  r.setState(states[0]);
  const first = pos();
  let moved = 0;
  for (let i = 0; i < 30; i++) {
    r.app.ticker.update(performance.now() + 10000 + i * 16);
    const p = pos();
    if (p.x !== first.x || p.y !== first.y) moved++;
  }
  r.setState(states[1]);
  const next = pos();
  return {
    framesBetweenStates: 30,
    framesThatMoved: moved,
    jumpAcrossOneState: +Math.hypot(next.x - first.x, next.y - first.y).toFixed(2),
  };
});

// ------------------------------------------------------------- 2. headlights
const lamps = await page.evaluate(async () => {
  const r = window.__RENDERER__;
  const near = (a, b) => Math.abs(a - b) < 12;
  const probe = async (tex, label, want) => {
    // The texture goes straight in; constructing a Sprite here would need a
    // second import of pixi, which re-registers its extensions and throws.
    const px = await r.app.renderer.extract.pixels(tex);
    const d = px.pixels ?? px;
    let white = 0, body = 0, total = 0;
    for (let i = 0; i < d.length; i += 4) {
      if (d[i + 3] < 128) continue;
      total++;
      if (d[i] > 240 && d[i + 1] > 240 && d[i + 2] > 240) white++;
      else if (near(d[i], (want >> 16) & 255) && near(d[i + 1], (want >> 8) & 255)
               && near(d[i + 2], want & 255)) body++;
    }
    return {
      label,
      color: "#" + want.toString(16).padStart(6, "0"),
      opaque: total, bodyPixels: body, headlightPixels: white,
    };
  };
  return [
    await probe(r.carTexture, "car", r.theme.car),
    await probe(r.motoTexture, "moto", r.theme.moto),
  ];
});

await browser.close();

let failed = 0;
const check = (ok, msg) => {
  if (!ok) failed++;
  console.log(`${ok ? "PASS" : "FAIL"}  ${msg}`);
};

console.log(JSON.stringify({ snap, lamps }, null, 1));
console.log();
check(snap.framesThatMoved === 0,
  `vehicle held its cell across all ${snap.framesBetweenStates} frames between state messages`);
check(snap.jumpAcrossOneState > 1,
  `vehicle jumped ${snap.jumpAcrossOneState}px on the state message (a whole cell, not a fraction)`);
for (const l of lamps) {
  check(l.headlightPixels > 0, `${l.label} texture has a white headlight (${l.headlightPixels}px)`);
  check(l.bodyPixels > l.headlightPixels,
    `${l.label} body is ${l.color} (${l.bodyPixels}px)`);
}
check(errors.length === 0,
  errors.length ? `console errors: ${errors.join("; ")}` : "zero console errors");

process.exit(failed ? 1 : 0);
