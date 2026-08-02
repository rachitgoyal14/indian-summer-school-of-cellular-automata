"""
derive_landscape_thresholds.py — empirically derive the trivial/average/worst
landscape thresholds from real simulation runs (Stage 6).

We sweep scenarios spanning free-flow → jammed and, for each, record the three
classifier inputs — network density, blocked-cell fraction, average junction
queue — alongside a ground-truth "flow efficiency" = measured flow / 0.5 (0.5
is the maximum flow of a Rule 184 lane). We then bucket each scenario by flow
efficiency (trivial > 0.66, average 0.33–0.66, worst < 0.33) and print the
observed range of each input per bucket. The thresholds hardcoded in
landscape.py are read off these ranges; run this to reproduce/justify them.
"""

from __future__ import annotations

import os
import sys

import numpy as np

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from src.engine.simulation import Simulation

MAX_LANE_FLOW = 0.5  # Rule 184 max flow per lane (at ρ=0.5)


def measure(sim: Simulation, warmup: int, window: int) -> dict:
    for _ in range(warmup):
        sim.advance(1)
    dens, flow, blocked, queue = [], [], [], []
    for _ in range(window):
        sim.advance(1)
        dens.append(sim.density())
        flow.append(sim.flow())
        total_cells = sum(r.length for r in sim.roads)
        nblocked = sum(len(s) for s in sim.network.blocked.values())
        blocked.append(nblocked / total_cells if total_cells else 0.0)
        q = sim.junction_queue_lengths()
        queue.append(np.mean(list(q.values())) if q else 0.0)
    eff = float(np.mean(flow)) / MAX_LANE_FLOW
    return {
        "density": float(np.mean(dens)),
        "blocked": float(np.mean(blocked)),
        "queue": float(np.mean(queue)),
        "flow": float(np.mean(flow)),
        "efficiency": eff,
    }


def main() -> int:
    rows = []

    # 1) ring density sweep (no disruptions): free-flow to jammed
    for rho in np.linspace(0.05, 0.95, 19):
        sim = Simulation(config="one_way", length=400, density=float(rho), seed=1)
        rows.append(("ring", round(float(rho), 2), measure(sim, 400, 200)))

    # 2) ring with increasing breakdown probability (blocked_fraction rises)
    for p in [0.0, 0.01, 0.02, 0.04, 0.08]:
        sim = Simulation(config="one_way", length=400, density=0.3, seed=2)
        sim.set_disruption_params(probs={"breakdown": p, "accident": p})
        rows.append(("ring+dis", p, measure(sim, 400, 200)))

    # 3) grid with increasing source load (queues rise)
    for sr in [0.2, 0.4, 0.7, 1.0]:
        sim = Simulation(config="grid", seed=3, build_kwargs={"source_rate": sr})
        rows.append(("grid", sr, measure(sim, 400, 200)))

    def bucket(eff: float) -> str:
        return "trivial" if eff > 0.66 else "average" if eff >= 0.33 else "worst"

    print(f"{'scenario':10s} {'param':>6} | {'dens':>5} {'blkd':>5} {'queue':>6} "
          f"{'flow':>5} {'eff':>5} | bucket")
    print("-" * 66)
    by_bucket: dict[str, list[dict]] = {"trivial": [], "average": [], "worst": []}
    for name, param, m in rows:
        b = bucket(m["efficiency"])
        by_bucket[b].append(m)
        print(f"{name:10s} {param:>6} | {m['density']:5.2f} {m['blocked']:5.3f} "
              f"{m['queue']:6.2f} {m['flow']:5.3f} {m['efficiency']:5.2f} | {b}")

    print("\nPer-bucket observed ranges (min–max):")
    for b in ("trivial", "average", "worst"):
        ms = by_bucket[b]
        if not ms:
            print(f"  {b:8s}: (none)")
            continue
        d = [m["density"] for m in ms]
        bl = [m["blocked"] for m in ms]
        q = [m["queue"] for m in ms]
        print(f"  {b:8s}: density {min(d):.2f}–{max(d):.2f}  "
              f"blocked {min(bl):.3f}–{max(bl):.3f}  queue {min(q):.2f}–{max(q):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
