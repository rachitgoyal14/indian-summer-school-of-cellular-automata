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
   "probability": 0.3, "rear_safety_gap": 1,     subset of the three keys may be
   "require_gain": true}                         sent (partial update). The
                                                 short aliases "prob"/"rear_gap"
                                                 are accepted too.
  {"type": "set_lane_change_prob", "p": 0.3}     older alias for "probability"
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
from pydantic import BaseModel, Field

from src.engine.simulation import Simulation
from src.engine.scenario_runner import ScenarioError, run_scenario
from src.server.state_serializer import serialize_network, serialize_state


def _first(msg: dict[str, Any], *keys: str) -> Any:
    """First key present in `msg`, so partial updates stay partial."""
    for key in keys:
        if msg.get(key) is not None:
            return msg[key]
    return None


def _scenario_error(message: str, code: str) -> dict[str, Any]:
    """
    A batch failure the client can branch on.

    `code` is the stable tag (`ALREADY_RUNNING`, `INVALID_CONFIG`,
    `OVERSIZED_REQUEST`, `INTERNAL_ERROR`); `message` is for humans. `error`
    repeats the message so a client written against the first cut still works.
    """
    return {"type": "scenario_error", "code": code,
            "message": message, "error": message}


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
            return _scenario_error(
                "a scenario is already running; wait for it to finish",
                "ALREADY_RUNNING",
            )
        self._batch_running = True
        try:
            # to_thread keeps the event loop — and the live tick — responsive
            result = await asyncio.to_thread(run_scenario, spec)
        except ScenarioError as exc:
            return _scenario_error(str(exc), exc.code)
        except Exception as exc:  # a bad scenario must never kill the server
            return _scenario_error(
                f"scenario failed: {type(exc).__name__}: {exc}", "INTERNAL_ERROR"
            )
        finally:
            self._batch_running = False

        # `final_state` is a scenario dict, ready for load_scenario. `network`
        # is the same world in the live "network" message shape, so the client
        # can render the result without special-casing a second schema.
        preview = Simulation()
        preview.apply_scenario(result["final_state"])
        return {
            "type": "scenario_result",
            "mode": "batch",
            "network": serialize_network(preview),
            **result,
        }

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
                # Partial update: only the keys present are changed. Both the
                # long names and the short aliases are accepted so neither
                # spelling of the client is wrong.
                self.sim.set_lane_change_params(
                    prob=_first(msg, "probability", "prob"),
                    rear_gap=_first(msg, "rear_safety_gap", "rear_gap"),
                    require_gain=_first(msg, "require_gain",
                                        "lane_change_require_gain"),
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
                # Off the event loop. `import_region` geocodes and then queries
                # Overpass with blocking urllib, up to ~85 s of timeouts in the
                # worst case. Called directly it froze the whole server for
                # that long: the tick loop stopped, pings went unanswered, and
                # every other client's messages sat unread in the socket — so
                # the import looked like it had never reached the handler at
                # all. `run_scenario` above already does this; this did not.
                #
                # The lock is deliberately still held. It makes the network
                # swap atomic against the tick loop, and an asyncio lock held
                # across an await blocks only the tasks that want the
                # simulation, not the event loop itself.
                result = await asyncio.to_thread(self.sim.import_region, place_name)
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


# --------------------------------------------------------------------------- models
class ResetParams(BaseModel):
    density: float = Field(default=0.3, ge=0.0, le=1.0, description="Target vehicle density [0..1]")
    seed: int | None = Field(default=None, description="Random seed for reproducibility")
    car_fraction: float | None = Field(default=None, ge=0.0, le=1.0, description="Fraction of multi-cell vehicles")


class SpeedParams(BaseModel):
    steps_per_second: float = Field(default=12.0, ge=0.5, le=120.0, description="Simulation tick rate")


class DisruptionParams(BaseModel):
    kind: str = Field(..., description="Disruption type: 'breakdown', 'tree', 'accident', 'flood'")


class OsmImportParams(BaseModel):
    place_name: str = Field(..., description="Place or landmark name, e.g. 'IIT BHU Varanasi'")


class ScenarioParams(BaseModel):
    scenario: dict[str, Any] = Field(..., description="Batch scenario definition")


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


API_DESCRIPTION = """
## 🚦 CA Rule 184 Real-Time Traffic Simulator Backend

### ⚡ Live WebSocket Stream
Connect to **`/ws`** (`wss://<your-host>/ws` or `ws://localhost:8000/ws`) for high-frequency (20–60 FPS) bidirectional state streaming.

- **Client → Server control messages**:
  - `{"type": "pause"}`
  - `{"type": "resume"}`
  - `{"type": "step"}`
  - `{"type": "reset", "density": 0.3, "seed": 42}`
  - `{"type": "set_speed", "steps_per_second": 20}`
  - `{"type": "trigger_disruption", "kind": "accident"}`
  - `{"type": "import_region", "place_name": "..."}`
  - `{"type": "run_scenario", "scenario": {...}}`
  - `{"type": "ping", "t": 1234.5}`

### 🌐 REST API
Below are the HTTP REST endpoints to monitor health, query snapshots of simulation state/network, and trigger simulator actions.
"""

app = FastAPI(
    title="CA Rule 184 Traffic Simulator",
    description=API_DESCRIPTION,
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration for cross-origin requests (e.g., Vercel frontend → Railway backend)
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


# --------------------------------------------------------------------------- REST Endpoints
@app.get("/health", tags=["System"], summary="Health check & simulation summary")
async def health() -> dict[str, Any]:
    """Check backend health and retrieve live simulation summary."""
    return {"status": "ok", **manager.sim.summary()}


@app.get("/api/state", tags=["Simulation State"], summary="Get live simulation state snapshot")
async def get_state() -> dict[str, Any]:
    """Retrieve full cell occupancy, vehicles, disruptions, and real-time metrics (density, flow, entropy, landscape)."""
    return serialize_state(manager.sim)


@app.get("/api/network", tags=["Simulation State"], summary="Get road network topology")
async def get_network() -> dict[str, Any]:
    """Retrieve road geometries, lengths, lanes, and junction connections."""
    return serialize_network(manager.sim)


@app.post("/api/control/pause", tags=["Simulation Controls"], summary="Pause simulation")
async def control_pause() -> dict[str, Any]:
    """Pause the simulation tick loop."""
    async with manager._lock:
        manager.sim.pause()
    await manager.broadcast_state()
    return {"status": "paused", "running": False}


@app.post("/api/control/resume", tags=["Simulation Controls"], summary="Resume simulation")
async def control_resume() -> dict[str, Any]:
    """Resume the continuous simulation tick loop."""
    async with manager._lock:
        manager.sim.resume()
    await manager.broadcast_state()
    return {"status": "resumed", "running": True}


@app.post("/api/control/step", tags=["Simulation Controls"], summary="Single step simulation")
async def control_step() -> dict[str, Any]:
    """Advance the simulation by exactly one step."""
    async with manager._lock:
        manager.sim.single_step()
    await manager.broadcast_state()
    return {"status": "stepped", "step": manager.sim.step_count}


@app.post("/api/control/reset", tags=["Simulation Controls"], summary="Reset simulation")
async def control_reset(params: ResetParams) -> dict[str, Any]:
    """Reset the road network with fresh vehicles matching target density."""
    async with manager._lock:
        manager.sim.reset(
            density=params.density,
            seed=params.seed,
            car_fraction=params.car_fraction,
        )
    await manager.broadcast_network()
    await manager.broadcast_state()
    return {"status": "reset", "step": 0, "summary": manager.sim.summary()}


@app.post("/api/control/speed", tags=["Simulation Controls"], summary="Set simulation speed")
async def control_speed(params: SpeedParams) -> dict[str, Any]:
    """Set simulation speed in steps per second [0.5..120]."""
    async with manager._lock:
        manager.sim.set_speed(params.steps_per_second)
    await manager.broadcast_state()
    return {"status": "speed_updated", "steps_per_second": manager.sim.steps_per_second}


@app.post("/api/control/disruptions", tags=["Disruptions"], summary="Trigger disruption")
async def control_disruption(params: DisruptionParams) -> dict[str, Any]:
    """Trigger a disruption ('breakdown', 'tree', 'accident', 'flood')."""
    async with manager._lock:
        manager.sim.trigger_disruption(params.kind)
    await manager.broadcast_state()
    return {"status": "disruption_triggered", "kind": params.kind}


@app.post("/api/control/disruptions/clear", tags=["Disruptions"], summary="Clear disruptions")
async def control_clear_disruptions(kind: str | None = None) -> dict[str, Any]:
    """Clear active disruptions on all roads."""
    async with manager._lock:
        manager.sim.clear_disruptions(kind)
    await manager.broadcast_state()
    return {"status": "disruptions_cleared"}


@app.post("/api/osm/import", tags=["OpenStreetMap"], summary="Import OpenStreetMap region")
async def import_osm(params: OsmImportParams) -> dict[str, Any]:
    """Fetch real-world road networks from OpenStreetMap Overpass API and convert to simulation grid."""
    async with manager._lock:
        result = await asyncio.to_thread(manager.sim.import_region, params.place_name)
    await manager.broadcast({"type": "import_result", **result})
    if result.get("ok"):
        await manager.broadcast_network()
        await manager.broadcast_state()
    return result


@app.post("/api/scenarios/run", tags=["Scenarios"], summary="Run batch scenario")
async def run_scenario_endpoint(params: ScenarioParams) -> dict[str, Any]:
    """Execute a batch scenario on a worker thread and return result metrics."""
    return await manager.run_batch(params.scenario)


# --------------------------------------------------------------------------- WebSocket Endpoint
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    """Primary bidirectional WebSocket channel for real-time simulation streaming and control."""
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
