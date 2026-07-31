"""
ws_server.py — FastAPI + WebSocket server that drives a `Simulation` and
streams its state to all connected browser clients.

Architecture
------------
- A single shared `SimulationManager` owns one `Simulation` and the set of
  connected WebSocket clients.
- A background asyncio task (`SimulationManager.run`) steps the simulation
  at `steps_per_second` and broadcasts a "state" message every tick. The
  tick rate is decoupled from anything the frontend does (plan.md §5).
- Each WebSocket connection reads incoming control messages and applies
  them to the shared simulation; structural/state re-broadcasts happen
  immediately so the UI feels responsive.

Client → server control messages
---------------------------------
  {"type": "pause"}                              pause the tick loop
  {"type": "resume"}                             resume the tick loop
  {"type": "step"}                               advance exactly one step
  {"type": "reset", "density": 0.3, "seed": 1}   rebuild initial state
  {"type": "set_speed", "steps_per_second": 20}  change tick rate
  {"type": "ping", "t": 1234.5}                  → server replies {"type":"pong","t":1234.5}
  {"type": "set_delay", "seconds": 0.2}          artificial per-send delay (latency testing)

The "ping"/"pong" pair lets the frontend measure real round-trip time; the
"pong" echoes the client's timestamp back unchanged so the client can
compute RTT without any clock-sync assumptions.
"""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.engine.simulation import Simulation
from src.server.state_serializer import serialize_network, serialize_state


class SimulationManager:
    """Owns the simulation, the connected clients, and the tick loop."""

    def __init__(self, sim: Simulation | None = None) -> None:
        self.sim = sim if sim is not None else Simulation()
        self.clients: set[WebSocket] = set()
        self.artificial_delay: float = 0.0  # seconds added per send (testing)
        self._loop_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()  # serialize mutations vs. the tick loop

    # ------------------------------------------------------------- lifecycle
    def start(self) -> None:
        if self._loop_task is None:
            self._loop_task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        if self._loop_task is not None:
            self._loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._loop_task
            self._loop_task = None

    # ------------------------------------------------------------- clients
    async def register(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)
        # A newly connected client needs the structure first, then a state.
        await self._send(ws, serialize_network(self.sim))
        await self._send(ws, serialize_state(self.sim))

    def unregister(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    async def _send(self, ws: WebSocket, msg: dict[str, Any]) -> None:
        if self.artificial_delay > 0:
            await asyncio.sleep(self.artificial_delay)
        await ws.send_json(msg)

    async def broadcast(self, msg: dict[str, Any]) -> None:
        for ws in list(self.clients):
            try:
                await self._send(ws, msg)
            except Exception:
                # A broken client should never take down the tick loop.
                self.unregister(ws)

    async def broadcast_state(self) -> None:
        await self.broadcast(serialize_state(self.sim))

    async def broadcast_network(self) -> None:
        await self.broadcast(serialize_network(self.sim))

    # ------------------------------------------------------------- tick loop
    async def run(self) -> None:
        """Advance + broadcast while running; idle-poll while paused."""
        while True:
            if self.sim.running:
                async with self._lock:
                    self.sim.advance(1)
                await self.broadcast_state()
                await asyncio.sleep(1.0 / self.sim.steps_per_second)
            else:
                # Paused: don't flood identical states; just idle.
                await asyncio.sleep(0.05)

    # ------------------------------------------------------------- controls
    async def handle_message(self, msg: dict[str, Any]) -> dict[str, Any] | None:
        """
        Apply a control message. Returns an optional message to send *only*
        back to the requesting client (used for ping→pong).
        """
        t = msg.get("type")

        if t == "ping":
            # Echo the client's timestamp back untouched for RTT measurement.
            return {"type": "pong", "t": msg.get("t")}

        if t == "set_delay":
            self.artificial_delay = float(max(0.0, msg.get("seconds", 0.0)))
            return None

        async with self._lock:
            if t == "pause":
                self.sim.pause()
            elif t == "resume":
                self.sim.resume()
            elif t == "step":
                self.sim.single_step()
            elif t == "reset":
                self.sim.reset(
                    density=msg.get("density"),
                    seed=msg.get("seed"),
                    length=msg.get("length"),
                )
            elif t == "set_speed":
                self.sim.set_speed(float(msg.get("steps_per_second", 12.0)))
            else:
                return None  # unknown message: ignore

        # Reflect the mutation to everyone immediately for responsiveness.
        if t == "reset":
            await self.broadcast_network()
        await self.broadcast_state()
        return None


# --------------------------------------------------------------------------- app
manager = SimulationManager()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # Start the tick loop when the app boots; cancel it on shutdown.
    manager.start()
    try:
        yield
    finally:
        await manager.stop()


app = FastAPI(title="CA Rule 184 Traffic Simulator", lifespan=lifespan)

# The React dev server runs on a different origin; allow it for local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {"status": "ok", **manager.sim.summary()}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await manager.register(ws)
    try:
        while True:
            msg = await ws.receive_json()
            reply = await manager.handle_message(msg)
            if reply is not None:
                await ws.send_json(reply)
    except WebSocketDisconnect:
        manager.unregister(ws)
    except Exception:
        manager.unregister(ws)
