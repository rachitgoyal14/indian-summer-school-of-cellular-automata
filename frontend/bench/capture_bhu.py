"""Capture a real IIT BHU network + a few stepped states as JSON fixtures.

Run once; the fixtures are then replayed by the frontend benchmark so frame
time is measured against the real 243-lane network without hitting Overpass
on every run.

Run from the backend directory so `src` is importable:

    cd backend && PYTHONPATH=$PWD ../.venv/bin/python ../frontend/bench/capture_bhu.py
"""
import json
import os
import sys

import numpy as np

from src.engine.simulation import Simulation
from src.server.state_serializer import serialize_network, serialize_state

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
os.makedirs(OUT, exist_ok=True)

sim = Simulation(config="one_way", seed=42)
res = sim.import_region("IIT BHU Varanasi")
print("import_region ->", json.dumps(res, indent=2))
if not res.get("ok"):
    sys.exit("import failed")

net = serialize_network(sim)
print(f"roads={len(net['roads'])} junctions={len(net['junctions'])} "
      f"streets={len(net.get('streets') or [])}")
curved = sum(1 for r in net["roads"] if r.get("path") and len(r["path"]) > 2)
print(f"curved lanes = {curved}")

with open(os.path.join(OUT, "bhu-network.json"), "w") as f:
    json.dump(net, f)

# The imported network starts empty (source-driven spawning), but the frame
# time we are chasing was measured with a populated map. Seed it directly on
# the imported network rather than via reset(), which would rebuild from
# config and throw the import away.
sim.network.populate_density(0.18, sim.car_fraction, np.random.default_rng(42))
print("seeded vehicles =",
      sum(len(r.vehicles) for r in sim.roads))

# A handful of states so the benchmark cycles realistic occupancy instead of
# re-rendering one frozen frame. `cells` is dropped: it is the desync-check /
# analytics channel and the renderer never reads it, so keeping it would
# quadruple the fixture for nothing.
states = []
for i in range(8):
    sim.single_step()
    s = serialize_state(sim)
    for r in s["roads"]:
        r.pop("cells", None)
    states.append(s)
nveh = sum(len(r["vehicles"]) for r in states[-1]["roads"])
print(f"vehicles in final state = {nveh}")
with open(os.path.join(OUT, "bhu-states.json"), "w") as f:
    json.dump(states, f, separators=(",", ":"))
print("wrote fixtures to", OUT)
