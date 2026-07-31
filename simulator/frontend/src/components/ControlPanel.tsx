// ControlPanel.tsx — configuration selector, playback + reset controls,
// footprint legend, and the latency test hooks.

import { useState } from "react";
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
    <div className="panel">
      <h2>Configuration</h2>
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
        <span><i className="chip moto" /> motorbike (1 cell)</span>
        <span><i className="chip car" /> car (2 cells)</span>
        <span><i className="chip junc" /> junction</span>
      </div>

      <div className="divider" />

      <h2>Controls</h2>

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
          {ringLike ? "release to reset with this density" : "seeds ring lanes; open lanes fill from sources"}
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
        <span className="sub">share of vehicles that are cars (2 cells)</span>
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

      <div className="divider" />

      <h3>Latency test</h3>
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
          inject delay, then confirm the step counter never jumps backward
        </span>
      </label>
      <div className="badge">stale states dropped: {api.staleDropped}</div>
    </div>
  );
}
