// useSimulationSocket.ts — owns the WebSocket connection to the backend,
// exposes the latest network/state to React, and provides control senders.
//
// Desync guard (Stage 2c): the backend stamps every "state" with a monotonic
// `step`. We drop any state whose step is *older* than the last one we
// rendered, so an out-of-order / delayed message can never make the display
// jump backward in time. A "network" message begins a new epoch (e.g. after
// a reset, which legitimately restarts step at 0), so it clears the guard.

import { useCallback, useEffect, useRef, useState } from "react";
import type { ImportResultMessage, NetworkMessage, ScenarioMessage, ServerMessage, StateMessage } from "../types";

function defaultWsUrl(): string {
  // In production (Vercel), use the environment variable pointing to Railway backend
  // In development, use same-origin (Vite proxies /ws → backend)
  // Can override with ?ws=... query param for testing
  const params = new URLSearchParams(window.location.search);
  const override = params.get("ws");
  if (override) return override;

  // Check for Vite environment variable first (production deployment)
  const envWsUrl = import.meta.env.VITE_BACKEND_WS_URL;
  if (envWsUrl) return envWsUrl;

  // Fallback to same-origin for local dev (Vite proxy handles this)
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${window.location.host}/ws`;
}

export interface SocketApi {
  connected: boolean;
  network: NetworkMessage | null;
  state: StateMessage | null;
  rttMs: number | null; // latest measured round-trip time
  staleDropped: number; // count of out-of-order states rejected by the guard
  pause: () => void;
  resume: () => void;
  singleStep: () => void;
  reset: (density: number, seed?: number, carFraction?: number) => void;
  setSpeed: (stepsPerSecond: number) => void;
  loadConfig: (config: string, opts?: { density?: number; carFraction?: number }) => void;
  setDisruptionParams: (probs?: Record<string, number>, repairScale?: number) => void;
  triggerDisruption: (kind: string) => void;
  addReserved: (kind: string) => void;
  clearDisruptions: (kind?: string) => void;
  // Stage 6 — map editing + save/load
  addRoad: (x0: number, y0: number, dx: number, dy: number, length: number) => void;
  removeRoad: (roadId: number) => void;
  addVehicle: (roadId: number, cell: number, vtype: string) => void;
  removeVehicle: (roadId: number, cell: number) => void;
  setTurn: (junctionId: number, inRoad: number, proportions: Record<number, number>) => void;
  saveScenario: (cb: (data: unknown) => void) => void;
  loadScenario: (data: unknown) => void;
  importRegion: (placeName: string, cb: (result: ImportResultMessage) => void) => void;
  ping: () => void;
  setArtificialDelay: (seconds: number) => void;
}

export function useSimulationSocket(url: string = defaultWsUrl()): SocketApi {
  const wsRef = useRef<WebSocket | null>(null);
  const [connected, setConnected] = useState(false);
  const [network, setNetwork] = useState<NetworkMessage | null>(null);
  const [state, setState] = useState<StateMessage | null>(null);
  const [rttMs, setRttMs] = useState<number | null>(null);
  const [staleDropped, setStaleDropped] = useState(0);

  // Guard state kept in refs so it never triggers re-renders.
  const lastStepRef = useRef<number>(-1);
  // one-shot callback for a save_scenario reply
  const scenarioCbRef = useRef<((data: unknown) => void) | null>(null);
  // one-shot callback for an import_region reply (Stage 8)
  const importCbRef = useRef<((data: ImportResultMessage) => void) | null>(null);

  const send = useCallback((msg: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
  }, []);

  useEffect(() => {
    let closed = false;
    let reconnectTimer: number | undefined;

    const connect = () => {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);

      ws.onclose = () => {
        setConnected(false);
        if (!closed) {
          // Simple fixed-interval reconnect so a server restart self-heals.
          reconnectTimer = window.setTimeout(connect, 1000);
        }
      };

      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data as string) as ServerMessage;
        if (msg.type === "scenario") {
          const cb = scenarioCbRef.current;
          scenarioCbRef.current = null;
          if (cb) cb((msg as ScenarioMessage).data);
          return;
        }
        if (msg.type === "import_result") {
          console.log("[WebSocket] Received import_result:", msg);
          const cb = importCbRef.current;
          importCbRef.current = null;
          if (cb) {
            console.log("[WebSocket] Invoking import callback");
            cb(msg as ImportResultMessage);
          } else {
            console.warn("[WebSocket] No callback registered for import_result");
          }
          return;
        }
        if (msg.type === "network") {
          lastStepRef.current = -1; // new epoch: accept the next state (step 0)
          setNetwork(msg);
        } else if (msg.type === "state") {
          if (msg.step < lastStepRef.current) {
            setStaleDropped((n) => n + 1); // reject stale/out-of-order
            return;
          }
          lastStepRef.current = msg.step;
          setState(msg);
        } else if (msg.type === "pong") {
          setRttMs(performance.now() - msg.t);
        }
      };
    };

    connect();
    return () => {
      closed = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, [url]);

  const pause = useCallback(() => send({ type: "pause" }), [send]);
  const resume = useCallback(() => send({ type: "resume" }), [send]);
  const singleStep = useCallback(() => send({ type: "step" }), [send]);
  const reset = useCallback(
    (density: number, seed?: number, carFraction?: number) =>
      send({
        type: "reset",
        density,
        ...(seed !== undefined ? { seed } : {}),
        ...(carFraction !== undefined ? { car_fraction: carFraction } : {}),
      }),
    [send],
  );
  const loadConfig = useCallback(
    (config: string, opts?: { density?: number; carFraction?: number }) =>
      send({
        type: "load_config",
        config,
        ...(opts?.density !== undefined ? { density: opts.density } : {}),
        ...(opts?.carFraction !== undefined ? { car_fraction: opts.carFraction } : {}),
      }),
    [send],
  );
  const setSpeed = useCallback(
    (stepsPerSecond: number) =>
      send({ type: "set_speed", steps_per_second: stepsPerSecond }),
    [send],
  );
  const setDisruptionParams = useCallback(
    (probs?: Record<string, number>, repairScale?: number) =>
      send({
        type: "set_disruption_params",
        ...(probs ? { probs } : {}),
        ...(repairScale !== undefined ? { repair_scale: repairScale } : {}),
      }),
    [send],
  );
  const triggerDisruption = useCallback(
    (kind: string) => send({ type: "trigger_disruption", kind }),
    [send],
  );
  const addReserved = useCallback(
    (kind: string) => send({ type: "add_reserved", kind }),
    [send],
  );
  const clearDisruptions = useCallback(
    (kind?: string) =>
      send({ type: "clear_disruptions", ...(kind ? { kind } : {}) }),
    [send],
  );
  const addRoad = useCallback(
    (x0: number, y0: number, dx: number, dy: number, length: number) =>
      send({ type: "add_road", x0, y0, dx, dy, length }),
    [send],
  );
  const removeRoad = useCallback(
    (roadId: number) => send({ type: "remove_road", road_id: roadId }),
    [send],
  );
  const addVehicle = useCallback(
    (roadId: number, cell: number, vtype: string) =>
      send({ type: "add_vehicle", road_id: roadId, cell, vtype }),
    [send],
  );
  const removeVehicle = useCallback(
    (roadId: number, cell: number) =>
      send({ type: "remove_vehicle", road_id: roadId, cell }),
    [send],
  );
  const setTurn = useCallback(
    (junctionId: number, inRoad: number, proportions: Record<number, number>) =>
      send({ type: "set_turn", junction_id: junctionId, in_road: inRoad, proportions }),
    [send],
  );
  const saveScenario = useCallback(
    (cb: (data: unknown) => void) => {
      scenarioCbRef.current = cb;
      send({ type: "save_scenario" });
    },
    [send],
  );
  const loadScenario = useCallback(
    (data: unknown) => send({ type: "load_scenario", data }),
    [send],
  );
  const importRegion = useCallback(
    (placeName: string, cb: (result: ImportResultMessage) => void) => {
      importCbRef.current = cb;
      send({ type: "import_region", place_name: placeName });
    },
    [send],
  );
  const ping = useCallback(
    () => send({ type: "ping", t: performance.now() }),
    [send],
  );
  const setArtificialDelay = useCallback(
    (seconds: number) => send({ type: "set_delay", seconds }),
    [send],
  );

  return {
    connected,
    network,
    state,
    rttMs,
    staleDropped,
    pause,
    resume,
    singleStep,
    reset,
    setSpeed,
    loadConfig,
    setDisruptionParams,
    triggerDisruption,
    addReserved,
    clearDisruptions,
    addRoad,
    removeRoad,
    addVehicle,
    removeVehicle,
    setTurn,
    saveScenario,
    loadScenario,
    importRegion,
    ping,
    setArtificialDelay,
  };
}
