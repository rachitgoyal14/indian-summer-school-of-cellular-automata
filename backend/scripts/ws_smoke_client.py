"""
ws_smoke_client.py — a headless WebSocket client that exercises the live
server exactly as the browser will, and prints real numbers:

  - confirms a "network" message arrives first, then "state" messages
  - confirms step counts are monotonically non-decreasing (ordering)
  - measures ping→pong round-trip time over N samples (latency)
  - exercises pause / step / resume / reset control messages

This provides automated, non-fabricated evidence for Stage 2's latency and
message-ordering acceptance criteria against a real uvicorn process (the
pytest suite exercises the ASGI app in-process; this hits a real socket).

Usage:
    python backend/scripts/ws_smoke_client.py [ws://127.0.0.1:8000/ws]
"""

from __future__ import annotations

import asyncio
import statistics
import sys
import time

import websockets


async def main(url: str) -> int:
    async with websockets.connect(url) as ws:
        import json

        # 1) First message must be the network structure.
        first = json.loads(await ws.recv())
        assert first["type"] == "network", first
        print(f"[ok] network message: {len(first['roads'])} road(s), "
              f"length={first['roads'][0]['length']}")

        # 2) Collect a burst of state messages, check monotonic ordering.
        steps = []
        while len(steps) < 15:
            msg = json.loads(await ws.recv())
            if msg["type"] == "state":
                steps.append(msg["step"])
        assert steps == sorted(steps), f"out-of-order steps: {steps}"
        print(f"[ok] step ordering monotonic over {len(steps)} states: "
              f"{steps[0]}..{steps[-1]}")

        # 3) Round-trip-time measurement via ping/pong.
        rtts = []
        for _ in range(20):
            t0 = time.perf_counter()
            await ws.send(json.dumps({"type": "ping", "t": t0}))
            # scan forward for the matching pong (states may interleave)
            while True:
                msg = json.loads(await ws.recv())
                if msg["type"] == "pong" and msg["t"] == t0:
                    rtts.append((time.perf_counter() - t0) * 1000.0)
                    break
        print(f"[ok] ping/pong RTT over {len(rtts)} samples (ms): "
              f"min={min(rtts):.2f} median={statistics.median(rtts):.2f} "
              f"mean={statistics.mean(rtts):.2f} max={max(rtts):.2f}")

        # 4) Control-message round trip: pause → step → resume → reset.
        async def next_state():
            while True:
                m = json.loads(await ws.recv())
                if m["type"] == "state":
                    return m

        t0 = time.perf_counter()
        await ws.send(json.dumps({"type": "pause"}))
        paused = await next_state()
        assert paused["running"] is False
        pause_ms = (time.perf_counter() - t0) * 1000.0

        await ws.send(json.dumps({"type": "step"}))
        stepped = await next_state()
        assert stepped["step"] == paused["step"] + 1
        print(f"[ok] pause ack {pause_ms:.2f} ms; single-step advanced "
              f"{paused['step']} → {stepped['step']}")

        await ws.send(json.dumps({"type": "reset", "density": 0.5, "seed": 1}))
        # reset broadcasts network then state
        reset_state = await next_state()
        occ = sum(reset_state["roads"][0]["cells"])
        n = len(reset_state["roads"][0]["cells"])
        assert occ == round(0.5 * n), (occ, n)
        assert reset_state["step"] == 0
        print(f"[ok] reset density=0.5 → {occ}/{n} vehicles, step reset to 0")

        await ws.send(json.dumps({"type": "resume"}))
        print("[ok] resume sent")

        print("\nALL LIVE-SERVER CHECKS PASSED")
        return 0


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:8000/ws"
    raise SystemExit(asyncio.run(main(url)))
