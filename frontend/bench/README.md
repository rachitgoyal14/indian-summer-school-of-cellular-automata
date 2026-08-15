# Frame-time bench

Replays a captured IIT (BHU) network — 243 lanes, 121 of them curved, ~680
vehicles — through the real `RoadRenderer` while a scripted camera pans and
zooms, and reports what a frame costs.

```bash
npm --prefix frontend run dev          # in one shell
node frontend/bench/run.mjs --seconds 20
```

Or open <http://localhost:5173/bench/> directly and watch it run.

## Reading the output

```
            n     mean      p50      p95    worst  >16.7
all      1200     0.78     0.10     4.20    13.10      0
state     240     2.73     1.90     6.50    13.10      0
camera    960     0.14     0.10     0.20     2.10      0
```

Cost is strongly bimodal, so the frames are split into two populations and a
single mean is not quoted on its own:

- **state** — a backend state message landed this frame, so vehicles, heatmap
  and disruptions are all reapplied. Twelve of every sixty frames, and where
  essentially all of the budget risk lives.
- **camera** — everything else: eased pan/zoom and label relayout only.

The budget is 16.7 ms. `>16.7` counts frames that missed it.

## What the numbers are, and are not

Each sample is the **CPU work of one frame**: camera easing, label relayout,
state application, heatmap, and the draw-call submit. It is deliberately not
frame-to-frame delta — on a machine that is keeping up that just reads
~16.7 ms and hides the remaining headroom.

Frames are driven by hand against a **virtual clock** in one synchronous
burst, not by `requestAnimationFrame`. rAF is throttled to a crawl whenever
the window is backgrounded, which silently turns a 20-second run into a
handful of samples.

Because WebGL commands are queued rather than awaited, GPU time is not fully
included. For this workload the cost is dominated by `Graphics` rebuilds and
per-vehicle JS, which is what the sampled window does capture.

## Two things that will mislead you

**Never quote `--headless` timings.** Headless Chromium falls back to the
SwiftShader software rasteriser. It does not just scale the numbers — it
invents a *reproducible* ~12 second frame at low zoom that no GPU-backed
browser shows, and flattens the per-state costs this bench exists to track.
The flag is there to check the harness still runs, nothing else.

**Device pixel ratio matters.** `RoadRenderer` initialises Pixi with
`resolution: window.devicePixelRatio`, so a Retina display fills four times
the pixels. The driver defaults to `--dpr 2` for that reason; measuring at
dpr 1 reports a fraction of the real per-state cost.

Absolute numbers are machine-specific. Compare runs from the same machine,
same dpr, and take three runs — the tail moves by a few ms between them.

## Regenerating the fixture

`fixtures/` was captured once so the bench does not hit Overpass on every run:

```bash
cd backend && PYTHONPATH=$PWD ../.venv/bin/python ../frontend/bench/capture_bhu.py
```

It writes `bhu-network.json` and `bhu-states.json` next to itself. The
imported network spawns vehicles from sources and so starts empty; the script
seeds it to ~680 vehicles directly, and drops the `cells` array from each
state because the renderer never reads it.
