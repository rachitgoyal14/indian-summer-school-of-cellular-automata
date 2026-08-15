// ControlPanel.tsx — configuration selector, playback + reset controls,
// footprint legend, and the latency test hooks.

import { useState } from "react";
import { Panel } from "./Panel";
import type { SocketApi } from "../hooks/useSimulationSocket";

interface Props {
  api: SocketApi;
}

// The 5 brief-specified lane/junction configurations, in order.
const CONFIGS: { value: string; label: string }[] = [
  { value: "one_way", label: "1 · One-way ring" },
  { value: "two_way_no_interaction", label: "2 · Two-way (no interaction)" },
  { value: "two_way_turns", label: "3 · Two-way with turns" },
  { value: "two_way_bidirectional_turns", label: "4 · Bidirectional + turns" },
  { value: "grid", label: "5 · Multi-junction grid" },
];

export function ControlPanel({ api }: Props) {
  const running = api.state?.running ?? false;
  const [config, setConfig] = useState("one_way");
  const [density, setDensity] = useState(0.3);
  const [carFraction, setCarFraction] = useState(0.3);
  const [speed, setSpeed] = useState(api.state?.steps_per_second ?? 12);
  const [delay, setDelay] = useState(0);

  const ringLike = config === "one_way" || config === "two_way_no_interaction";

  return (
    <>
      <Panel title="Configuration" defaultOpen hint="lane case, density, mix">
      <label className="field">
        Lane / junction case
        <select
          value={config}
          onChange={(e) => {
            const c = e.target.value;
            setConfig(c);
            api.loadConfig(c, { density, carFraction });
          }}
        >
          {CONFIGS.map((c) => (
            <option key={c.value} value={c.value}>
              {c.label}
            </option>
          ))}
        </select>
      </label>

      <div className="legend">
        <span>
          <svg className="legend-icon" width="16" height="14" viewBox="0 0 16 14">
            <path d="M14,7 L10,4 L5,4.5 L2,5.5 L2,8.5 L5,9.5 L10,10 Z" fill="#4ECDC4" opacity="0.9"/>
            <circle cx="12" cy="7" r="1.5" fill="#3aaba4"/>
            <circle cx="3.5" cy="7" r="1.5" fill="#3aaba4"/>
          </svg>
          motorbike (1 cell)
        </span>
        <span>
          <svg className="legend-icon" width="28" height="14" viewBox="0 0 28 14">
            <path d="M25,7 L23,3 L17,2 L10,2 L8,3.5 L8,2.5 L4,3 L2,4.5 L2,9.5 L4,11 L8,11.5 L8,10.5 L10,12 L17,12 L23,11 Z" fill="#F5A623" opacity="0.9"/>
            <rect x="16" y="3.5" width="5" height="7" rx="0.5" fill="#c4851c" opacity="0.4"/>
            <rect x="7" y="4" width="4" height="6" rx="0.5" fill="#c4851c" opacity="0.3"/>
          </svg>
          car (2 cells)
        </span>
        <span>
          <svg className="legend-icon" width="16" height="14" viewBox="0 0 16 14">
            <circle cx="8" cy="7" r="3" fill="#E8E4DD" opacity="0.8"/>
            <rect x="2" y="6" width="12" height="2" rx="1" fill="#E8E4DD" opacity="0.4"/>
            <rect x="7" y="1" width="2" height="12" rx="1" fill="#E8E4DD" opacity="0.4"/>
          </svg>
          junction
        </span>
      </div>

      </Panel>

      <Panel title="Playback" defaultOpen hint="run, step, speed">

      <div className="btn-row">
        {running ? (
          <button onClick={api.pause}>⏸ Pause</button>
        ) : (
          <button onClick={api.resume}>▶ Resume</button>
        )}
        <button onClick={api.singleStep} disabled={running}>
          ⏭ Step
        </button>
        <button onClick={() => api.reset(density, undefined, carFraction)}>
          ↺ Reset
        </button>
      </div>

      <label className="field">
        Density: <strong>{density.toFixed(2)}</strong>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={density}
          onChange={(e) => setDensity(parseFloat(e.target.value))}
          onMouseUp={() => api.reset(density, undefined, carFraction)}
        />
        <span className="sub">
          {ringLike ? "Drag to adjust, release to apply" : "Adjusts initial vehicle density"}
        </span>
      </label>

      <label className="field">
        Car fraction: <strong>{carFraction.toFixed(2)}</strong>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={carFraction}
          onChange={(e) => setCarFraction(parseFloat(e.target.value))}
          onMouseUp={() =>
            ringLike
              ? api.reset(density, undefined, carFraction)
              : api.loadConfig(config, { density, carFraction })
          }
        />
        <span className="sub">Proportion of 2-cell cars vs 1-cell motorbikes</span>
      </label>

      <label className="field">
        Speed: <strong>{speed.toFixed(0)}</strong> steps/s
        <input
          type="range"
          min={1}
          max={60}
          step={1}
          value={speed}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            setSpeed(v);
            api.setSpeed(v);
          }}
        />
      </label>

      </Panel>

      <Panel title="Network diagnostics" hint="round-trip time, latency test">
      <div className="btn-row">
        <button onClick={api.ping}>Ping</button>
        <span className="badge">
          RTT: {api.rttMs === null ? "—" : `${api.rttMs.toFixed(1)} ms`}
        </span>
      </div>
      <label className="field">
        Artificial server delay: <strong>{(delay * 1000).toFixed(0)} ms</strong>
        <input
          type="range"
          min={0}
          max={0.5}
          step={0.02}
          value={delay}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            setDelay(v);
            api.setArtificialDelay(v);
          }}
        />
        <span className="sub">
          Simulates network latency for testing
        </span>
      </label>
      <div className="badge">stale states dropped: {api.staleDropped}</div>
      </Panel>
    </>
  );
}
