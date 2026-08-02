"""
demo_congestion_propagation.py — camera-independent proof that congestion at
one junction grows and propagates *upstream* to a neighbouring junction
(Stage 3 acceptance: "not inferred from a camera move").

Setup — a two-junction chain with a deliberate downstream bottleneck:

    west source ──R0──▶ (J0) ──R1──▶ (J1) ──R2──▶ sink        (eastbound)
                                       ▲
                              north flood ──R3──┘

Both R1 (the J0→J1 link) and R3 (a flooded side inflow) can only leave J1 via
the single outlet R2, which accepts one vehicle per step. The flood on R3
hogs R2, so the shared link R1 starves and fills; once R1 is full the backup
crosses J0 and fills R0. We print each junction's queue length over time: the
downstream junction (J1) congests first, then — measurably later — the
upstream neighbour (J0). The lag is the propagation.
"""

from __future__ import annotations

import os
import sys

import numpy as np

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from src.core.junction import Junction
from src.network.network import Network, Road


def build_chain() -> Network:
    net = Network()
    net.add_junction(Junction(id=0, x=40, y=0))
    net.add_junction(Junction(id=1, x=80, y=0))
    L = 40
    # R0: west entry (moderate source) -> J0
    net.add_road(Road(id=0, length=L, x0=0, y0=0, dx=1, dy=0, periodic=False,
                      head_junction=0, source_rate=0.5))
    # R1: J0 -> J1 (the shared link)
    net.add_road(Road(id=1, length=L, x0=40, y0=0, dx=1, dy=0, periodic=False,
                      tail_junction=0, head_junction=1))
    # R2: J1 -> sink (the single, capacity-limited outlet)
    net.add_road(Road(id=2, length=L, x0=80, y0=0, dx=1, dy=0, periodic=False,
                      tail_junction=1))
    # R3: north flood -> J1 (hogs the outlet)
    net.add_road(Road(id=3, length=L, x0=80, y0=-L, dx=0, dy=1, periodic=False,
                      head_junction=1, source_rate=1.0))
    net.junctions[0].turns = {0: {1: 1.0}}          # R0 -> R1
    net.junctions[1].turns = {1: {2: 1.0}, 3: {2: 1.0}}  # R1,R3 both -> R2 (contend)
    net.validate()
    return net


def main() -> int:
    net = build_chain()
    rng = np.random.default_rng(0)

    print(f"{'step':>5} | {'queue J0 (upstream)':>20} | {'queue J1 (downstream)':>22}")
    print("-" * 54)
    first_j1 = first_j0 = None
    for step in range(1, 801):
        net.step(rng)
        q = net.junction_queue_lengths()
        q0, q1 = q.get(0, 0), q.get(1, 0)
        if first_j1 is None and q1 >= 6:
            first_j1 = step
        if first_j0 is None and q0 >= 6:
            first_j0 = step
        if step % 60 == 0:
            print(f"{step:>5} | {q0:>20} | {q1:>22}")

    print("-" * 54)
    print(f"downstream junction J1 first backed up (queue≥6) at step: {first_j1}")
    print(f"upstream   junction J0 first backed up (queue≥6) at step: {first_j0}")
    if first_j1 is not None and first_j0 is not None and first_j1 < first_j0:
        print(
            f"→ PROPAGATION CONFIRMED: backup began downstream (J1 @ step {first_j1}) "
            f"and reached the neighbouring upstream junction (J0 @ step {first_j0}) "
            f"{first_j0 - first_j1} steps later."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
