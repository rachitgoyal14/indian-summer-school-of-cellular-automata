// bench.ts — reproducible frame-time measurement for RoadRenderer.
//
// Why this exists: the curved-road work pushed the IIT (BHU) map over the
// 16.7 ms budget, and "it feels smoother now" is not a measurement. This
// replays a captured 243-lane BHU network with ~680 vehicles through the real
// renderer while a scripted camera pans and zooms, and reports the CPU cost of
// a frame.
//
// What is measured
// ----------------
// Pixi's own ticker is stopped and frames are driven by hand against a VIRTUAL
// clock, back to back in one synchronous burst. Each sample is the wall time
// of one frame's CPU work — camera easing, label relayout, state application,
// heatmap, and the draw-call submit.
//
// Two deliberate choices:
//   * CPU work, not frame-to-frame delta. On a machine that is keeping up the
//     delta just reads ~16.7 ms and hides how much headroom is left; the work
//     figure is what actually has to fit inside the budget.
//   * A virtual clock rather than rAF. rAF is throttled to a crawl whenever
//     the window is backgrounded, which silently reduces a 20-second run to a
//     handful of samples. A synchronous burst measures the same work and is
//     reproducible run to run.
//
// The GPU is therefore NOT in the numbers below — WebGL commands are queued,
// not awaited. For this workload the cost is dominated by Graphics rebuilds
// and per-vehicle JS on the CPU side, which is what the budget work targets.
//
// Run: npm --prefix frontend run dev, then open /bench/.
//   ?seconds=20   simulated duration at 60 fps (default 20)
//   ?warmup=2     simulated seconds discarded before recording (default 2)
//   ?heatmap=0    disable the heatmap overlay (default on)
//   ?theme=night  palette (default day)
// Results are printed on the page and left on window.__BENCH__ for a driver.

import { RoadRenderer } from "../src/render/RoadRenderer";
import { DAY_THEME, NIGHT_THEME } from "../src/render/theme";
import type { DisruptionDTO, NetworkMessage, StateMessage } from "../src/types";

const params = new URLSearchParams(location.search);
const SECONDS = Number(params.get("seconds") ?? 20);
const WARMUP = Number(params.get("warmup") ?? 2);
const HEATMAP = params.get("heatmap") !== "0";
const THEME = params.get("theme") === "night" ? NIGHT_THEME : DAY_THEME;
/** States arrive from the backend at this rate in normal operation. */
const STATE_HZ = 12;
/**
 * Top of the zoom sweep. Comfortably above LABEL_MIN_SCALE (0.5) so the
 * street-label pass is exercised, and around where a user reads lane
 * markings.
 */
const ZOOM_MAX = 1.6;

const out = document.getElementById("out")!;

interface Stats {
  n: number;
  mean: number;
  p50: number;
  p95: number;
  worst: number;
  overBudget: number;
}

/**
 * Frames split into two populations, because the cost is strongly bimodal and
 * a single mean hides the thing we are trying to fix.
 *
 *   state  — a backend state message landed this frame, so vehicles, heatmap
 *            and disruptions are all reapplied. ~12 of every 60 frames, and
 *            where essentially all the budget risk lives.
 *   camera — everything else: eased pan/zoom and label relayout only.
 *
 * `all` is the two together, which is what a user's frame times average out
 * to in practice.
 */
interface BenchResult {
  all: Stats;
  state: Stats;
  camera: Stats;
  seconds: number;
  heatmap: boolean;
  vehicles: number;
  roads: number;
  /** The five most expensive frames, broken into phases. */
  slowest?: Array<{
    frame: number; cost: number; setState: number; tick: number;
    scale: number; stateFrame: boolean;
  }>;
}

declare global {
  interface Window {
    __BENCH__?: BenchResult;
    __BENCH_DONE__?: boolean;
    /** Exposed so a driver can park the camera and screenshot a detail. */
    __RENDERER__?: RoadRenderer;
  }
}

function quantile(sorted: number[], q: number): number {
  if (!sorted.length) return 0;
  const i = Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))));
  return sorted[i];
}

/**
 * Three disruptions on long roads, since the sweep is specified with 2–3
 * active. The captured states carry none: the imported network spawns them
 * probabilistically and a fixture that happened to catch some would make the
 * benchmark depend on which tick was captured.
 */
function syntheticDisruptions(net: NetworkMessage): DisruptionDTO[] {
  const longest = [...net.roads].sort((a, b) => b.length - a.length).slice(0, 3);
  const kinds = ["accident", "flood", "tree"] as const;
  return longest.map((road, i) => ({
    id: 9000 + i,
    kind: kinds[i],
    label: kinds[i],
    road_id: road.id,
    cells: [Math.floor(road.length * 0.3), Math.floor(road.length * 0.5)],
    permanent: false,
    remaining: 999,
  }));
}

/** Centre and span of a network in cell units, for the camera script. */
function networkExtent(net: NetworkMessage) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const road of net.roads) {
    const pts: Array<[number, number]> = road.path?.length
      ? road.path
      : [[road.geometry.x0, road.geometry.y0]];
    for (const [x, y] of pts) {
      minX = Math.min(minX, x); maxX = Math.max(maxX, x);
      minY = Math.min(minY, y); maxY = Math.max(maxY, y);
    }
  }
  if (!isFinite(minX)) { minX = maxX = minY = maxY = 0; }
  return {
    cx: (minX + maxX) / 2,
    cy: (minY + maxY) / 2,
    spanX: Math.max(1, maxX - minX),
    spanY: Math.max(1, maxY - minY),
  };
}

async function main() {
  const [net, states] = await Promise.all([
    fetch("./fixtures/bhu-network.json").then((r) => r.json() as Promise<NetworkMessage>),
    fetch("./fixtures/bhu-states.json").then((r) => r.json() as Promise<StateMessage[]>),
  ]);

  const disruptions = syntheticDisruptions(net);
  for (const s of states) s.disruptions = disruptions;

  const vehicles = states[0].roads.reduce((n, r) => n + r.vehicles.length, 0);

  const renderer = await RoadRenderer.create(document.getElementById("stage")!);
  window.__RENDERER__ = renderer;
  renderer.setTheme(THEME);
  renderer.setNetwork(net);
  renderer.setHeatmapEnabled(HEATMAP);
  renderer.setState(states[0]);
  renderer.fitToView(true);

  // Take the frame loop away from Pixi so each sample is one measured unit of
  // work rather than whatever vsync handed us.
  renderer.app.ticker.stop();

  const fitScale = renderer.getScale();
  // Bounds in CELL units, straight off the network — `focusOn` takes cell
  // coordinates, and deriving them here keeps the bench off the renderer's
  // private geometry helpers.
  const { cx, cy, spanX, spanY } = networkExtent(net);

  const stateSamples: number[] = [];
  const cameraSamples: number[] = [];
  /** Per-frame phase breakdown, so a spike can be attributed instead of averaged away. */
  const trace: Array<{
    i: number; cost: number; setState: number; tick: number;
    scale: number; stateFrame: boolean;
  }> = [];
  const FRAME_MS = 1000 / 60;
  const totalFrames = Math.round(((WARMUP + SECONDS) * 1000) / FRAME_MS);
  const warmupFrames = Math.round((WARMUP * 1000) / FRAME_MS);
  let stateIdx = 0;
  let nextState = 0;

  function run() {
    for (let i = 0; i < totalFrames; i++) {
      // Virtual clock: what the wall clock WOULD read at frame i if we were
      // holding 60 fps. The camera script and the state cadence both key off
      // it, so the workload is identical on a fast and a slow machine.
      const vnow = i * FRAME_MS;
      const elapsed = vnow / 1000;

      const mark = performance.now();

      // Scripted pan + zoom. The camera never rests: label relayout and the
      // eased camera are part of the cost we are trying to hold under budget,
      // and a parked camera would measure neither.
      //
      // The sweep runs geometrically from the fit scale up to ZOOM_MAX, which
      // is above the threshold where street labels switch on. Oscillating
      // around the fit scale instead — as an earlier version did — never
      // crossed that threshold on a map as large as BHU, so the label pass
      // was silently excluded from every sample.
      const phase = elapsed * 0.35;
      const k = (1 - Math.cos(phase)) / 2; // 0..1, smooth
      const zoom = fitScale * Math.pow(ZOOM_MAX / fitScale, k);
      renderer.focusOn(
        cx + Math.cos(phase * 0.8) * spanX * 0.22,
        cy + Math.sin(phase * 1.1) * spanY * 0.22,
        zoom,
      );

      let isStateFrame = false;
      const beforeState = performance.now();
      if (vnow >= nextState) {
        renderer.setState(states[stateIdx % states.length]);
        stateIdx++;
        nextState += 1000 / STATE_HZ;
        isStateFrame = true;
      }
      const afterState = performance.now();

      // Runs the renderer's own ticker callbacks (camera easing, labels) and
      // then Pixi's render, all inside the measured window.
      renderer.app.ticker.update(vnow);

      const end = performance.now();
      const cost = end - mark;
      if (i >= warmupFrames) {
        (isStateFrame ? stateSamples : cameraSamples).push(cost);
        trace.push({
          i,
          cost,
          setState: afterState - beforeState,
          tick: end - afterState,
          scale: renderer.getScale(),
          stateFrame: isStateFrame,
        });
      }
    }
    finish();
  }

  function stats(xs: number[]): Stats {
    const sorted = [...xs].sort((a, b) => a - b);
    const mean = xs.reduce((a, b) => a + b, 0) / (xs.length || 1);
    return {
      n: xs.length,
      mean: +mean.toFixed(2),
      p50: +quantile(sorted, 0.5).toFixed(2),
      p95: +quantile(sorted, 0.95).toFixed(2),
      worst: +(sorted[sorted.length - 1] ?? 0).toFixed(2),
      overBudget: xs.filter((s) => s > 16.7).length,
    };
  }

  function finish() {
    const result: BenchResult = {
      all: stats([...stateSamples, ...cameraSamples]),
      state: stats(stateSamples),
      camera: stats(cameraSamples),
      seconds: SECONDS,
      heatmap: HEATMAP,
      vehicles,
      roads: net.roads.length,
    };
    result.slowest = [...trace].sort((a, b) => b.cost - a.cost).slice(0, 5)
      .map((t) => ({
        frame: t.i,
        cost: +t.cost.toFixed(2),
        setState: +t.setState.toFixed(2),
        tick: +t.tick.toFixed(2),
        scale: +t.scale.toFixed(3),
        stateFrame: t.stateFrame,
      }));
    window.__BENCH__ = result;
    window.__BENCH_DONE__ = true;
    const row = (label: string, s: Stats) =>
      `${label.padEnd(8)}${String(s.n).padStart(5)}  ` +
      `${s.mean.toFixed(2).padStart(7)}  ${s.p50.toFixed(2).padStart(7)}  ` +
      `${s.p95.toFixed(2).padStart(7)}  ${s.worst.toFixed(2).padStart(7)}  ` +
      `${String(s.overBudget).padStart(5)}`;
    out.textContent =
      `DONE  ${result.roads} roads, ${result.vehicles} vehicles, ` +
      `heatmap ${HEATMAP ? "ON" : "OFF"}\n\n` +
      `${"".padEnd(8)}${"n".padStart(5)}  ${"mean".padStart(7)}  ` +
      `${"p50".padStart(7)}  ${"p95".padStart(7)}  ${"worst".padStart(7)}  ` +
      `${">16.7".padStart(5)}\n` +
      row("all", result.all) + "\n" +
      row("state", result.state) + "\n" +
      row("camera", result.camera);
    console.log("[bench]", JSON.stringify(result));
  }

  // A beat of breathing room so the first-paint cost of setNetwork is not
  // caught in the burst, then measure. Deliberately a timer and not rAF: rAF
  // never fires at all in a backgrounded window, which would hang the run.
  out.textContent = "measuring…";
  setTimeout(run, 50);
}

main().catch((e) => {
  out.textContent = "FAILED: " + (e?.stack ?? e);
  window.__BENCH_DONE__ = true;
});
