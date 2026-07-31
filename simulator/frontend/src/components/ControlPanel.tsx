// ControlPanel.tsx — playback + reset controls and the latency test hooks.

import { useState } from "react";
import type { SocketApi } from "../hooks/useSimulationSocket";

interface Props {
  api: SocketApi;
}

export function ControlPanel({ api }: Props) {
  const running = api.state?.running ?? false;
  const [density, setDensity] = useState(0.3);
  const [speed, setSpeed] = useState(api.state?.steps_per_second ?? 12);
  const [delay, setDelay] = useState(0);

  return (
    <div className="panel">
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
        <button onClick={() => api.reset(density)}>↺ Reset</button>
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
          onMouseUp={() => api.reset(density)}
        />
        <span className="sub">release to reset with this density</span>
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
