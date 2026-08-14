// realServerMessages.test.ts — the hook against payloads the backend really
// emitted, not hand-written fixtures.
//
// `__fixtures__/real-server-messages.json` was captured from the actual
// FastAPI server over a real WebSocket (multi-lane 2x2 grid, one step, one
// batch run, one rejected batch). Hand-written fixtures only prove the hook
// is self-consistent; these prove the frontend's types and parsing agree with
// what the server sends. Regenerate with the snippet in the repo's Stage 13
// commit message if the schema changes on purpose.

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useSimulationSocket } from "./useSimulationSocket";
import fixtures from "./__fixtures__/real-server-messages.json";
import type {
  NetworkMessage,
  ScenarioErrorMessage,
  ScenarioResultMessage,
  StateMessage,
} from "../types";

// The casts are the point of this file: if the server's real payload stops
// satisfying the frontend's declared types, this stops compiling.
const network = fixtures.network as unknown as NetworkMessage;
const state = fixtures.state as unknown as StateMessage;
const scenarioResult = fixtures.scenario_result as unknown as ScenarioResultMessage;
const scenarioError = fixtures.scenario_error as unknown as ScenarioErrorMessage;

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  readyState = MockWebSocket.OPEN;
  sent: string[] = [];
  onopen: ((ev: unknown) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: unknown) => void) | null = null;
  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }
  send(raw: string) {
    this.sent.push(raw);
  }
  close() {
    this.onclose?.({});
  }
  emit(msg: unknown) {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }
  static get latest() {
    return MockWebSocket.instances[MockWebSocket.instances.length - 1];
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  vi.stubGlobal("WebSocket", MockWebSocket);
});
afterEach(() => vi.unstubAllGlobals());

function mount() {
  const rendered = renderHook(() => useSimulationSocket("ws://test/ws"));
  act(() => {
    MockWebSocket.latest.onopen?.({});
  });
  return rendered;
}

describe("real backend payloads", () => {
  it("stores the streets block the server actually sent", () => {
    const { result } = mount();
    act(() => MockWebSocket.latest.emit(network));

    // a 2x2 grid at lanes_per_direction=2
    expect(result.current.streets).toHaveLength(12);
    expect(result.current.network?.roads).toHaveLength(24);

    for (const street of result.current.streets) {
      expect(street.lanes).toHaveLength(street.n_forward + street.n_backward);
      expect(street.baseline).not.toBeNull();
      expect(street.lane_width).toBeGreaterThan(0);
      // adjacency the server states must be internally consistent
      const ids = street.lanes.map((l) => l.road_id);
      for (const lane of street.lanes) {
        if (lane.right_road_id !== null) expect(ids).toContain(lane.right_road_id);
        if (lane.left_road_id !== null) expect(ids).toContain(lane.left_road_id);
      }
    }

    // every lane in a street is a road in the same message
    const roadIds = new Set(result.current.network!.roads.map((r) => r.id));
    for (const street of result.current.streets) {
      for (const lane of street.lanes) expect(roadIds.has(lane.road_id)).toBe(true);
    }
  });

  it("reads the lane fields off a real state message", () => {
    const { result } = mount();
    act(() => MockWebSocket.latest.emit(state));

    expect(result.current.mode).toBe("live");
    expect(result.current.laneChangeProb).toBeCloseTo(0.35);
    expect(typeof result.current.laneChanges).toBe("number");
    expect(result.current.state?.analytics.landscape).toMatch(
      /^(trivial|average|worst)$/,
    );
  });

  it("parses a real scenario_result", () => {
    const { result } = mount();
    act(() => MockWebSocket.latest.emit(scenarioResult));

    const got = result.current.scenarioResult!;
    expect(got.mode).toBe("batch");
    expect(got.summary.steps).toBe(20);
    expect(got.network.type).toBe("network");
    expect(got.trajectory[0].step).toBe(0);
    expect(got.trajectory[0].landscape).toMatch(/^(trivial|average|worst)$/);
    expect(result.current.scenarioRunning).toBe(false);
  });

  it("parses a real scenario_error, code and all", () => {
    const { result } = mount();
    act(() => MockWebSocket.latest.emit(scenarioError));

    expect(result.current.scenarioError?.code).toBe("INVALID_CONFIG");
    expect(result.current.scenarioError?.message).toContain("seed");
    expect(result.current.scenarioError?.error).toBe(
      result.current.scenarioError?.message,
    );
  });

  it("survives the real connect sequence end to end", () => {
    const { result } = mount();
    act(() => MockWebSocket.latest.emit(network));
    act(() => MockWebSocket.latest.emit(state));
    act(() => MockWebSocket.latest.emit(scenarioResult));

    expect(result.current.connected).toBe(true);
    expect(result.current.staleDropped).toBe(0);
    expect(result.current.network).not.toBeNull();
    expect(result.current.state).not.toBeNull();
    expect(result.current.scenarioResult).not.toBeNull();
  });
});
