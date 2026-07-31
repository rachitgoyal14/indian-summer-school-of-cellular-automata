// useSimulationSocket.ts — owns the WebSocket connection to the backend,
// exposes the latest network/state to React, and provides control senders.
//
// Desync guard (Stage 2c): the backend stamps every "state" with a monotonic
// `step`. We drop any state whose step is *older* than the last one we
// rendered, so an out-of-order / delayed message can never make the display
// jump backward in time. A "network" message begins a new epoch (e.g. after
// a reset, which legitimately restarts step at 0), so it clears the guard.

import { useCallback, useEffect, useRef, useState } from "react";
import type { NetworkMessage, ServerMessage, StateMessage } from "../types";

function defaultWsUrl(): string {
  // Same-origin in dev (Vite proxies /ws → backend). Override with ?ws=...
  const params = new URLSearchParams(window.location.search);
  const override = params.get("ws");
  if (override) return override;
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
  reset: (density: number, seed?: number) => void;
  setSpeed: (stepsPerSecond: number) => void;
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
    (density: number, seed?: number) =>
      send({ type: "reset", density, ...(seed !== undefined ? { seed } : {}) }),
    [send],
  );
  const setSpeed = useCallback(
    (stepsPerSecond: number) =>
      send({ type: "set_speed", steps_per_second: stepsPerSecond }),
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
    ping,
    setArtificialDelay,
  };
}
