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
  {"type": "set_lane_change_params",             lateral-transfer settings; any
   "prob": 0.3, "rear_gap": 1,                   subset of the three keys may be
   "require_gain": true}                         sent (partial update)
  {"type": "set_lane_change_prob", "p": 0.3}     older alias for "prob" alone
  {"type": "ping", "t": 1234.5}                  → server replies {"type":"pong","t":1234.5}
  {"type": "set_delay", "seconds": 0.2}          artificial per-send delay (latency testing)
  {"type": "run_scenario", "scenario": {...}}    batch "what-if" run; replies to the
                                                 requesting client only, with
                                                 {"type": "scenario_result", ...} or
                                                 {"type": "scenario_error", "error": ...}

A batch run executes on its own `Simulation` on a worker thread: the live
simulation is never touched and its stream never pauses. Only one batch runs
at a time; a concurrent request is rejected with a `scenario_error`.

The "ping"/"pong" pair lets the frontend measure real round-trip time; the
"pong" echoes the client's timestamp back unchanged so the client can
compute RTT without any clock-sync assumptions.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.engine.simulation import Simulation
from src.engine.scenario_runner import ScenarioError, run_scenario
from src.server.state_serializer import serialize_network, serialize_state


class SimulationManager:
    """Owns the simulation, the connected clients, and the tick loop."""

    def __init__(self, sim: Simulation | None = None) -> None:
        self.sim = sim if sim is not None else Simulation()
        self.clients: set[WebSocket] = set()
        self.artificial_delay: float = 0.0  # seconds added per send (testing)
        self._loop_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()  # serialize mutations vs. the tick loop
        # Batch runs are one-at-a-time. This flag is *not* the tick-loop lock:
        # a batch must never hold that, or the live stream would stall for the
        # whole run. A second request while one is in flight is rejected.
        self._batch_running = False

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

    # ------------------------------------------------------------- batch mode
    async def run_batch(self, spec: dict[str, Any]) -> dict[str, Any]:
        """
        Run a batch scenario and return its result to the requesting client only.

        The run happens on a worker thread and on its own `Simulation`, so the
        tick loop keeps stepping and broadcasting throughout — other clients
        see an uninterrupted live stream and never see the batch's states.

        One batch at a time: a second request while one is in flight is
        rejected immediately rather than queued, so the client always gets a
        prompt answer and the server's memory stays bounded. Clients should
        show a busy state between `run_scenario` and its reply.
        """
        if self._batch_running:
            return {
                "type": "scenario_error",
                "error": "a scenario is already running; wait for it to finish",
            }
        self._batch_running = True
        try:
            # to_thread keeps the event loop — and the live tick — responsive
            result = await asyncio.to_thread(run_scenario, spec)
        except ScenarioError as exc:
            return {"type": "scenario_error", "error": str(exc)}
        except Exception as exc:  # a bad scenario must never kill the server
            return {"type": "scenario_error",
                    "error": f"scenario failed: {type(exc).__name__}: {exc}"}
        finally:
            self._batch_running = False
        return {"type": "scenario_result", **result}

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

        if t == "save_scenario":
            # Return the full scenario to the requesting client for download.
            async with self._lock:
                return {"type": "scenario", "data": self.sim.to_scenario()}

        if t == "run_scenario":
            return await self.run_batch(msg.get("scenario") or {})

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
                    car_fraction=msg.get("car_fraction"),
                    lane_change_prob=msg.get("lane_change_prob"),
                    rear_safety_gap=msg.get("rear_safety_gap"),
                    lane_change_require_gain=msg.get("lane_change_require_gain"),
                )
            elif t == "set_lane_change_params":
                # partial update: only the keys present are changed
                self.sim.set_lane_change_params(
                    prob=msg.get("prob"),
                    rear_gap=msg.get("rear_gap"),
                    require_gain=msg.get("require_gain"),
                )
            elif t == "set_lane_change_prob":
                # kept for older clients; equivalent to set_lane_change_params
                self.sim.set_lane_change_prob(float(msg.get("p", 0.0)))
            elif t == "load_config":
                # Switch lane/junction configuration (Stage 3). Optional
                # density/car_fraction override the defaults for the new config.
                if msg.get("density") is not None:
                    self.sim.density_target = float(msg["density"])
                if msg.get("car_fraction") is not None:
                    self.sim.car_fraction = float(msg["car_fraction"])
                self.sim.load_config(
                    msg.get("config", "one_way"),
                    **(msg.get("build_kwargs") or {}),
                )
            elif t == "set_speed":
                self.sim.set_speed(float(msg.get("steps_per_second", 12.0)))
            elif t == "set_disruption_params":
                # {probs: {breakdown, tree, accident, flood}, repair_scale}
                self.sim.set_disruption_params(
                    probs=msg.get("probs"),
                    repair_scale=msg.get("repair_scale"),
                )
            elif t == "trigger_disruption":
                self.sim.trigger_disruption(msg.get("kind", ""))
            elif t == "add_reserved":
                self.sim.add_reserved(msg.get("kind", ""))
            elif t == "clear_disruptions":
                self.sim.clear_disruptions(msg.get("kind"))
            elif t == "load_scenario":
                self.sim.apply_scenario(msg.get("data") or {})
            elif t == "add_road":
                self.sim.add_road(
                    x0=msg.get("x0", 0), y0=msg.get("y0", 0),
                    dx=msg.get("dx", 1), dy=msg.get("dy", 0),
                    length=int(msg.get("length", 30)),
                    periodic=bool(msg.get("periodic", False)),
                )
            elif t == "remove_road":
                self.sim.remove_road(int(msg.get("road_id")))
            elif t == "add_vehicle":
                self.sim.add_vehicle(
                    int(msg.get("road_id")), int(msg.get("cell")),
                    msg.get("vtype", "moto"),
                )
            elif t == "remove_vehicle":
                self.sim.remove_vehicle(int(msg.get("road_id")), int(msg.get("cell")))
            elif t == "set_turn":
                props = {int(k): float(v) for k, v in (msg.get("proportions") or {}).items()}
                self.sim.set_turn(int(msg.get("junction_id")), int(msg.get("in_road")), props)
            elif t == "import_region":
                place_name = msg.get("place_name", "")
                result = self.sim.import_region(place_name)
                # Send the import result back to all clients
                await self.broadcast({"type": "import_result", **result})
            else:
                return None  # unknown message: ignore

        # Reflect the mutation to everyone immediately for responsiveness.
        structural = t in (
            "reset", "load_config", "load_scenario", "import_region",
            "add_road", "remove_road", "set_turn",
        )
        if structural:
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

# CORS configuration for cross-origin requests (e.g., Vercel frontend → Railway backend)
# ALLOWED_ORIGINS env var should be a comma-separated list of allowed origins.
# Default to "*" for initial testing, but lock down to specific Vercel domain(s) in production.
allowed_origins_str = os.environ.get("ALLOWED_ORIGINS", "*")
allowed_origins = (
    [origin.strip() for origin in allowed_origins_str.split(",")]
    if allowed_origins_str != "*"
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
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
