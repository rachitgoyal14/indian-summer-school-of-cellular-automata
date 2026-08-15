// LaneChangePanel.tsx — the three lateral-transfer knobs.
//
// Every control shows the value the *server* last broadcast, not a local
// mirror, so the UI can never drift from what the simulation is actually
// doing. Each control sends only the parameter it changed — the backend
// applies partial updates, so touching one knob must not resend the others.

import { useState } from "react";
import type { SocketApi } from "../hooks/useSimulationSocket";
import { Panel } from "./Panel";

export function LaneChangePanel({ api }: { api: SocketApi }) {
  const state = api.state;
  const prob = api.laneChangeProb;
  const gap = state?.rear_safety_gap ?? 0;
  const requireGain = state?.lane_change_require_gain ?? true;

  // Local value only while a drag is in flight; the server's value wins as
  // soon as the gesture ends and the next state message lands.
  const [dragProb, setDragProb] = useState<number | null>(null);
  const [dragGap, setDragGap] = useState<number | null>(null);

  const shownProb = dragProb ?? prob;
  const shownGap = dragGap ?? gap;

  return (
    <Panel
      title="Lane changing"
      defaultOpen
      hint="lateral transfer probability and gap"
      badge={
        <span className="lane-live" title="lateral transfers on the last step">
          {api.laneChanges} / step
        </span>
      }
    >
        <label className="field">
          <span className="field-label">Probability: {shownProb.toFixed(2)}</span>
          <input
            type="range" min={0} max={1} step={0.01} value={shownProb}
            data-testid="lane-prob"
            onInput={(e) => setDragProb(Number((e.target as HTMLInputElement).value))}
            onChange={(e) => {
              setDragProb(null);
              api.setLaneChangeParams({ probability: Number(e.target.value) });
            }}
          />
        </label>

        <label className="field">
          <span className="field-label">Rear safety gap: {shownGap} cell{shownGap === 1 ? "" : "s"}</span>
          <input
            type="range" min={0} max={3} step={1} value={shownGap}
            data-testid="lane-gap"
            onInput={(e) => setDragGap(Number((e.target as HTMLInputElement).value))}
            onChange={(e) => {
              setDragGap(null);
              api.setLaneChangeParams({ rear_safety_gap: Number(e.target.value) });
            }}
          />
        </label>

        <label className="field checkbox">
          <input
            type="checkbox" checked={requireGain}
            data-testid="lane-gain"
            onChange={(e) => api.setLaneChangeParams({ require_gain: e.target.checked })}
          />
          <span>Only change lane if it helps</span>
        </label>

        {api.streets.length === 0 && (
          <div className="small muted">
            This network has no multi-lane streets, so lane changing has nothing
            to do. Load a multi-lane configuration to see it act.
          </div>
        )}
    </Panel>
  );
}
