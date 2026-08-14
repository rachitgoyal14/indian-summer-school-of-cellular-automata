#!/usr/bin/env python3
"""
plot_network.py — draw a network's lanes so multi-lane streets can be eyeballed.

Every lane is drawn as its own line from `(x0, y0)` along `(dx, dy)` for
`length` cells, with an arrowhead showing travel direction. Lanes of the same
street get the same colour, so a 2-lane street shows as two visibly separated
parallel lines rather than one — which is the whole point of the geometric
offsets in `src/network/lane_geometry.py`.

Usage
-----
    # procedural grid, 2 lanes per direction
    python scripts/plot_network.py --config grid --lanes 2 --out grid2.png

    # a saved scenario (including one produced by an OSM import)
    python scripts/plot_network.py --scenario my_import.json --out iit.png

    # a real place, if this machine has network access
    python scripts/plot_network.py --place "IIT BHU, Varanasi" --out iit.png
"""

from __future__ import annotations

import argparse
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.io.scenario_io import network_from_scenario
from src.network import grid_builder
from src.network.network import Network


def load_network(args: argparse.Namespace) -> Network:
    if args.scenario:
        with open(args.scenario) as fh:
            return network_from_scenario(json.load(fh))
    if args.place:
        from src.engine.simulation import Simulation

        sim = Simulation()
        result = sim.import_region(args.place)
        if not result["ok"]:
            raise SystemExit(f"import failed: {result['error']}")
        print(f"imported {args.place}: {result['roads']} roads, "
              f"{result['junctions']} junctions, {result['total_cells']} cells")
        return sim.network
    kwargs = {}
    if args.config == "grid":
        kwargs = {"rows": args.rows, "cols": args.cols,
                  "lanes_per_direction": args.lanes}
    return grid_builder.build(args.config, **kwargs)


def plot(net: Network, out_path: str, title: str, zoom: float = 0.0) -> None:
    """
    Draw every lane. `zoom` limits the view to that many coordinate units
    around the first junction.

    Lane offsets are real: 3.5 m lanes on a 300 m road are genuinely thin, so
    at whole-network scale a 2-lane street looks like one thick line. That is
    honest geometry, not a bug — use `--zoom` to see the lanes resolve into
    separate tracks rather than inflating the width and lying about the map.
    """
    fig, ax = plt.subplots(figsize=(11, 11))

    # one colour per street; unstreeted roads fall back to grey
    street_of = {r.id: r.street_id for r in net.roads.values()}
    names = sorted({s for s in street_of.values() if s is not None})
    palette = plt.colormaps["tab20"]
    colour_of = {name: palette(i % 20) for i, name in enumerate(names)}

    for road in net.roads_ordered():
        x1 = road.x0 + road.dx * road.length
        y1 = road.y0 + road.dy * road.length
        colour = colour_of.get(street_of[road.id], "0.6")
        ax.plot([road.x0, x1], [road.y0, y1], "-", color=colour, linewidth=1.6,
                solid_capstyle="butt", zorder=2)
        # arrowhead at 60% along, so direction is readable on short lanes
        ax.annotate(
            "", xytext=(road.x0 + road.dx * road.length * 0.55,
                        road.y0 + road.dy * road.length * 0.55),
            xy=(road.x0 + road.dx * road.length * 0.7,
                road.y0 + road.dy * road.length * 0.7),
            arrowprops={"arrowstyle": "-|>", "color": colour, "lw": 1.0},
            zorder=3,
        )

    for j in net.junctions.values():
        ax.plot(j.x, j.y, "o", color="black", markersize=3, zorder=4)

    total_cells = sum(r.length for r in net.roads.values())
    ax.set_title(
        f"{title}\n{len(net.roads)} lanes, {len(net.streets)} streets, "
        f"{len(net.junctions)} junctions, {total_cells} cells"
    )
    ax.set_aspect("equal")
    if zoom > 0 and net.junctions:
        # centre on the busiest junction: the most interesting place to look
        j = max(net.junctions.values(), key=lambda j: len(j.turns))
        ax.set_xlim(j.x - zoom, j.x + zoom)
        ax.set_ylim(j.y - zoom, j.y + zoom)
    ax.invert_yaxis()  # +y is downward in the renderer's space
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(out_path, dpi=140)
    print(f"wrote {out_path}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="grid", help="procedural config name")
    p.add_argument("--rows", type=int, default=2)
    p.add_argument("--cols", type=int, default=2)
    p.add_argument("--lanes", type=int, default=2, help="lanes per direction")
    p.add_argument("--scenario", help="path to a saved scenario JSON")
    p.add_argument("--place", help="geocode + import a real place (needs network)")
    p.add_argument("--out", default="network.png")
    p.add_argument("--zoom", type=float, default=0.0,
                   help="view half-width around the first junction (0 = whole network)")
    args = p.parse_args()

    net = load_network(args)
    title = args.place or args.scenario or f"{args.config} (lanes={args.lanes})"
    plot(net, args.out, title, zoom=args.zoom)


if __name__ == "__main__":
    main()
