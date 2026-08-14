// useSimulationSocket.test.ts — the WebSocket hook against a mock socket.
//
// The hook is the whole integration layer: message routing, the batch-run
// flag, partial parameter payloads, and the fallbacks that keep an older
// server working. None of that is reachable from the UI until the scenario
// controls exist, so it is exercised directly here.

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSimulationSocket } from "./useSimulationSocket";
import type {
  ImportResultMessage,
  NetworkMessage,
  ScenarioErrorMessage,
  ScenarioResultMessage,
  ScenarioRequest,
  StateMessage,
} from "../types";

// --------------------------------------------------------------- mock socket
type Handler = ((ev: unknown) => void) | null;

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;

  readyState = MockWebSocket.OPEN;
  sent: Array<Record<string, unknown>> = [];
  onopen: Handler = null;
  onclose: Handler = null;
  onmessage: Handler = null;
  onerror: Handler = null;

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }

  send(raw: string) {
    this.sent.push(JSON.parse(raw));
  }

  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({});
  }

  /** Deliver a server message to the hook. */
  emit(msg: unknown) {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }

  static get latest(): MockWebSocket {
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1];
    if (!ws) throw new Error("no socket was opened");
    return ws;
  }
}

// ------------------------------------------------------------------ fixtures
function networkMessage(overrides: Partial<NetworkMessage> = {}): NetworkMessage {
  return {
    type: "network",
    config: "grid",
    roads: [
      {
        id: 0, length: 40, periodic: false,
        geometry: { x0: 0, y0: -0.23, dx: 1, dy: 0 },
        street_id: "h0_0", lane_index: 0,
      },
      {
        id: 1, length: 40, periodic: false,
        geometry: { x0: 0, y0: 0.23, dx: 1, dy: 0 },
        street_id: "h0_0", lane_index: 1,
      },
    ],
    junctions: [{ id: 0, x: 40, y: 0 }],
    streets: [
      {
        id: "h0_0",
        baseline: { x0: 0, y0: 0, x1: 40, y1: 0 },
        lane_width: 0.4667,
        n_forward: 2,
        n_backward: 0,
        lanes: [
          { road_id: 0, lane_index: 0, direction: "forward", left_road_id: null, right_road_id: 1 },
          { road_id: 1, lane_index: 1, direction: "forward", left_road_id: 0, right_road_id: null },
        ],
      },
    ],
    ...overrides,
  };
}

function stateMessage(overrides: Partial<StateMessage> = {}): StateMessage {
  return {
    type: "state",
    step: 1,
    running: true,
    steps_per_second: 12,
    roads: [{ id: 0, cells: [0, 1], vehicles: [], segments: [] }],
    junctions: [{ id: 0, queue: 0 }],
    disruptions: [],
    analytics: {
      density: 0.3, flow: 0.1, entropy: 0.8, entropy_bits: 3.2,
      blocked_fraction: 0, avg_queue: 0, landscape: "average",
    },
    ...overrides,
  };
}

const SCENARIO: ScenarioRequest = {
  seed: 7,
  config: "grid",
  density: 0.3,
  batch: { steps: 50 },
};

function scenarioResult(): ScenarioResultMessage {
  return {
    type: "scenario_result",
    mode: "batch",
    network: networkMessage(),
    final_state: { roads: [], junctions: [] },
    trajectory: [],
    snapshots: [],
    summary: {
      steps: 50, records: 51, peak_flow: 0.2, mean_flow: 0.1,
      steady_state_flow: 0.12, min_entropy: 0, max_entropy: 0.9,
      final_density: 0.3, final_landscape: "average", peak_avg_queue: 2,
      total_lane_changes: 5, total_spawned: 10, total_exited: 3,
      events_fired: [], elapsed_seconds: 0.04,
    },
  };
}

function scenarioError(
  code = "INVALID_CONFIG",
  message = "'seed' is required so the run is reproducible",
): ScenarioErrorMessage {
  return { type: "scenario_error", code, message, error: message };
}

// --------------------------------------------------------------------- setup
beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

function mount() {
  const rendered = renderHook(() => useSimulationSocket("ws://test/ws"));
  act(() => {
    MockWebSocket.latest.onopen?.({});
  });
  return rendered;
}

function lastSent(type: string): Record<string, unknown> | undefined {
  return [...MockWebSocket.latest.sent].reverse().find((m) => m.type === type);
}

// ---------------------------------------------------------------- connection
describe("connection", () => {
  it("connects and exposes safe defaults before any message", () => {
    const { result } = mount();
    expect(result.current.connected).toBe(true);
    expect(result.current.streets).toEqual([]);
    expect(result.current.laneChangeProb).toBe(0);
    expect(result.current.laneChanges).toBe(0);
    expect(result.current.mode).toBe("live");
    expect(result.current.scenarioRunning).toBe(false);
    expect(result.current.scenarioResult).toBeNull();
    expect(result.current.scenarioError).toBeNull();
  });

  it("closes the socket on unmount without reconnecting", () => {
    vi.useFakeTimers();
    const { unmount } = mount();
    const ws = MockWebSocket.latest;
    unmount();
    expect(ws.readyState).toBe(MockWebSocket.CLOSED);
    act(() => {
      vi.advanceTimersByTime(5000);
    });
    // the unmount close must not schedule a reconnect
    expect(MockWebSocket.instances).toHaveLength(1);
  });
});

// ------------------------------------------------------------------- streets
describe("streets", () => {
  it("stores the streets block from a multi-lane network message", () => {
    const { result } = mount();
    act(() => MockWebSocket.latest.emit(networkMessage()));

    expect(result.current.streets).toHaveLength(1);
    const street = result.current.streets[0];
    expect(street.id).toBe("h0_0");
    expect([street.n_forward, street.n_backward]).toEqual([2, 0]);
    expect(street.baseline).toEqual({ x0: 0, y0: 0, x1: 40, y1: 0 });
    expect(street.lanes.map((l) => l.road_id)).toEqual([0, 1]);
    expect(street.lanes[0].right_road_id).toBe(1);
    expect(street.lanes[1].left_road_id).toBe(0);
  });

  it("falls back to [] when the server omits streets entirely", () => {
    const { result } = mount();
    const old = networkMessage();
    delete (old as Partial<NetworkMessage>).streets; // a pre-Stage-12 server
    act(() => MockWebSocket.latest.emit(old));

    expect(result.current.network).not.toBeNull();
    expect(result.current.streets).toEqual([]);
  });

  it("falls back to [] for a single-lane network", () => {
    const { result } = mount();
    act(() => MockWebSocket.latest.emit(networkMessage({ streets: [] })));
    expect(result.current.streets).toEqual([]);
  });
});

// ------------------------------------------------------------ lane-change UI
describe("lane-change parameters", () => {
  it("reads the current values back from state messages", () => {
    const { result } = mount();
    act(() =>
      MockWebSocket.latest.emit(
        stateMessage({ lane_change_prob: 0.35, lane_changes: 4, mode: "live" }),
      ),
    );
    expect(result.current.laneChangeProb).toBe(0.35);
    expect(result.current.laneChanges).toBe(4);
    expect(result.current.mode).toBe("live");
  });

  it("defaults gracefully when an older server omits the fields", () => {
    const { result } = mount();
    act(() => MockWebSocket.latest.emit(stateMessage()));
    expect(result.current.laneChangeProb).toBe(0);
    expect(result.current.laneChanges).toBe(0);
    expect(result.current.mode).toBe("live");
  });

  it("reads lane_changes from analytics when only mirrored there", () => {
    const { result } = mount();
    act(() =>
      MockWebSocket.latest.emit(
        stateMessage({
          analytics: { ...stateMessage().analytics, lane_changes: 9 },
        }),
      ),
    );
    expect(result.current.laneChanges).toBe(9);
  });

  it("sends only the fields supplied, so partial updates stay partial", () => {
    const { result } = mount();

    act(() => result.current.setLaneChangeParams({ probability: 0.5 }));
    expect(lastSent("set_lane_change_params")).toEqual({
      type: "set_lane_change_params",
      probability: 0.5,
    });

    act(() => result.current.setLaneChangeParams({ rear_safety_gap: 2 }));
    expect(lastSent("set_lane_change_params")).toEqual({
      type: "set_lane_change_params",
      rear_safety_gap: 2,
    });

    // false is a value, not an absence: it must survive onto the wire
    act(() => result.current.setLaneChangeParams({ require_gain: false }));
    expect(lastSent("set_lane_change_params")).toEqual({
      type: "set_lane_change_params",
      require_gain: false,
    });

    act(() =>
      result.current.setLaneChangeParams({
        probability: 0.2, rear_safety_gap: 1, require_gain: true,
      }),
    );
    expect(lastSent("set_lane_change_params")).toEqual({
      type: "set_lane_change_params",
      probability: 0.2, rear_safety_gap: 1, require_gain: true,
    });
  });
});

// ------------------------------------------------------------ batch scenarios
describe("batch scenarios", () => {
  it("goes busy on send and clears on a result", () => {
    const { result } = mount();

    act(() => result.current.runScenario(SCENARIO));
    expect(result.current.scenarioRunning).toBe(true);
    expect(lastSent("run_scenario")).toEqual({
      type: "run_scenario",
      scenario: SCENARIO,
    });

    act(() => MockWebSocket.latest.emit(scenarioResult()));
    expect(result.current.scenarioRunning).toBe(false);
    expect(result.current.scenarioError).toBeNull();
    expect(result.current.scenarioResult?.summary.steps).toBe(50);
  });

  it("clears the flag on an error and surfaces code and message", () => {
    const { result } = mount();
    act(() => result.current.runScenario(SCENARIO));
    act(() => MockWebSocket.latest.emit(scenarioError("ALREADY_RUNNING", "busy")));

    expect(result.current.scenarioRunning).toBe(false);
    expect(result.current.scenarioResult).toBeNull();
    expect(result.current.scenarioError?.code).toBe("ALREADY_RUNNING");
    expect(result.current.scenarioError?.message).toBe("busy");
  });

  it("clears the flag when the socket drops mid-run", () => {
    vi.useFakeTimers();
    const { result } = mount();
    act(() => result.current.runScenario(SCENARIO));
    expect(result.current.scenarioRunning).toBe(true);

    act(() => MockWebSocket.latest.close());

    expect(result.current.scenarioRunning).toBe(false);
    expect(result.current.connected).toBe(false);
  });

  it("drops a stale error the moment a new run starts", () => {
    const { result } = mount();
    act(() => result.current.runScenario(SCENARIO));
    act(() => MockWebSocket.latest.emit(scenarioError()));
    expect(result.current.scenarioError).not.toBeNull();

    act(() => result.current.runScenario(SCENARIO));
    expect(result.current.scenarioError).toBeNull();
    expect(result.current.scenarioRunning).toBe(true);
  });

  it("replaces the previous result on a new run", () => {
    const { result } = mount();
    act(() => MockWebSocket.latest.emit(scenarioResult()));
    expect(result.current.scenarioResult?.summary.steps).toBe(50);

    const second = scenarioResult();
    second.summary = { ...second.summary, steps: 120 };
    act(() => MockWebSocket.latest.emit(second));
    expect(result.current.scenarioResult?.summary.steps).toBe(120);
  });

  it("exposes the result so it can be handed back to load_scenario", () => {
    const { result } = mount();
    act(() => MockWebSocket.latest.emit(scenarioResult()));

    act(() => result.current.loadScenario(result.current.scenarioResult!.final_state));
    expect(lastSent("load_scenario")).toEqual({
      type: "load_scenario",
      data: { roads: [], junctions: [] },
    });
  });

  it("clears result and error on demand", () => {
    const { result } = mount();
    act(() => MockWebSocket.latest.emit(scenarioResult()));
    act(() => MockWebSocket.latest.emit(scenarioError()));

    act(() => result.current.clearScenarioResult());
    act(() => result.current.clearScenarioError());
    expect(result.current.scenarioResult).toBeNull();
    expect(result.current.scenarioError).toBeNull();
  });

  it("does not disturb live streaming", () => {
    const { result } = mount();
    act(() => MockWebSocket.latest.emit(stateMessage({ step: 5 })));
    act(() => result.current.runScenario(SCENARIO));
    act(() => MockWebSocket.latest.emit(stateMessage({ step: 6 })));

    // live states keep arriving while a batch is in flight
    expect(result.current.state?.step).toBe(6);
    expect(result.current.scenarioRunning).toBe(true);
  });
});

// ------------------------------------------------------------- import_result
describe("import_result", () => {
  it("passes street-level lane counts to the caller's callback", () => {
    const { result } = mount();
    const seen: ImportResultMessage[] = [];

    act(() => result.current.importRegion("IIT BHU, Varanasi", (r) => seen.push(r)));
    act(() =>
      MockWebSocket.latest.emit({
        type: "import_result", ok: true, roads: 243, junctions: 107,
        total_cells: 3647, streets: 123, multi_lane_streets: 0,
        max_lanes_per_direction: 1, two_way_streets: 120,
      }),
    );

    expect(seen).toHaveLength(1);
    expect(seen[0].streets).toBe(123);
    expect(seen[0].multi_lane_streets).toBe(0);
    expect(seen[0].max_lanes_per_direction).toBe(1);
  });

  it("still works when an older server omits the street fields", () => {
    const { result } = mount();
    const seen: ImportResultMessage[] = [];
    act(() => result.current.importRegion("Somewhere", (r) => seen.push(r)));
    act(() =>
      MockWebSocket.latest.emit({
        type: "import_result", ok: true, roads: 12, junctions: 4, total_cells: 480,
      }),
    );
    expect(seen[0].streets).toBeUndefined();
    expect(seen[0].roads).toBe(12);
  });
});

// -------------------------------------------------------- backward compat
describe("backward compatibility", () => {
  it("handles a pre-Stage-12 server end to end", () => {
    const { result } = mount();
    const oldNetwork = networkMessage({ streets: undefined });
    oldNetwork.roads = oldNetwork.roads.map(({ id, length, geometry, periodic }) => ({
      id, length, geometry, periodic,           // no street_id, no lane_index
    }));

    act(() => MockWebSocket.latest.emit(oldNetwork));
    act(() => MockWebSocket.latest.emit(stateMessage()));

    expect(result.current.network?.roads).toHaveLength(2);
    expect(result.current.state?.step).toBe(1);
    expect(result.current.streets).toEqual([]);
    expect(result.current.mode).toBe("live");
  });

  it("keeps the stale-state guard working", () => {
    const { result } = mount();
    act(() => MockWebSocket.latest.emit(stateMessage({ step: 10 })));
    act(() => MockWebSocket.latest.emit(stateMessage({ step: 3 })));

    expect(result.current.state?.step).toBe(10);
    expect(result.current.staleDropped).toBe(1);
  });

  it("ignores an unknown message type without throwing", () => {
    const { result } = mount();
    act(() => MockWebSocket.latest.emit({ type: "something_new", x: 1 }));
    expect(result.current.connected).toBe(true);
  });
});
