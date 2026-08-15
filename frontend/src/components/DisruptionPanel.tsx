// DisruptionPanel.tsx — live controls for all 8 brief "liberty degrees".
//
// Per plan.md §4 these map onto 3 underlying mechanisms, but each is exposed
// as its own independent, live-adjustable control and rendered in its own
// colour, so the user is never confused about which one is active.

import { useState } from "react";
import type { SocketApi } from "../hooks/useSimulationSocket";
import type { DisruptionKind } from "../types";
import { Panel } from "./Panel";

interface Props {
  api: SocketApi;
}

const COLORS: Record<string, string> = {
  breakdown: "#ff6b6b",
  tree: "#67d982",
  accident: "#ff2d55",
  flood: "#3aa0ff",
  lock: "#b56bff",
  parking: "#9aa7bd",
};

// A glyph per kind, so a row is identifiable without relying on colour
// alone — the stripe and the symbol say the same thing two ways.
const GLYPHS: Record<string, string> = {
  breakdown: "▲",
  tree: "✸",
  accident: "✖",
  flood: "≋",
  lock: "⬥",
  parking: "P",
};

const PROB_KINDS: { kind: DisruptionKind; label: string }[] = [
  { kind: "breakdown", label: "Fall car (breakdown)" },
  { kind: "tree", label: "Fallen tree" },
  { kind: "accident", label: "Accident (two cars)" },
  { kind: "flood", label: "Flood" },
];

export function DisruptionPanel({ api }: Props) {
  const [probs, setProbs] = useState<Record<string, number>>({
    breakdown: 0,
    tree: 0,
    accident: 0,
    flood: 0,
  });
  const [repair, setRepair] = useState(1.0);

  // live counts per kind, from the latest state
  const counts: Record<string, number> = {};
  for (const dis of api.state?.disruptions ?? []) {
    counts[dis.kind] = (counts[dis.kind] ?? 0) + 1;
  }

  const setProb = (kind: string, value: number) => {
    const next = { ...probs, [kind]: value };
    setProbs(next);
    api.setDisruptionParams({ [kind]: value });
  };

  return (
    <Panel title="Disruptions" hint="breakdowns, trees, floods">

      {PROB_KINDS.map(({ kind, label }) => (
        <label className="field" key={kind}>
          <span className="dis-row">
            <i className="swatch" style={{ background: COLORS[kind] }} />
            <span className="dis-glyph" style={{ color: COLORS[kind] }}>
              {GLYPHS[kind]}
            </span>
            {label}
            <span className="count">{counts[kind] ?? 0} active</span>
          </span>
          <input
            type="range"
            min={0}
            max={0.05}
            step={0.001}
            value={probs[kind]}
            onChange={(e) => setProb(kind, parseFloat(e.target.value))}
          />
          <span className="sub">
            P(trigger)/step = {probs[kind].toFixed(3)}
            {kind === "flood" && (
              <>
                {"  "}
                <button
                  className="mini"
                  onClick={() => api.triggerDisruption("flood")}
                >
                  Flood now
                </button>
              </>
            )}
          </span>
        </label>
      ))}

      <label className="field">
        <span className="dis-row">Repair speed</span>
        <input
          type="range"
          min={0.3}
          max={2}
          step={0.1}
          value={repair}
          onChange={(e) => {
            const v = parseFloat(e.target.value);
            setRepair(v);
            api.setDisruptionParams(undefined, v);
          }}
        />
        <span className="sub">
          Multiplier: {repair.toFixed(1)}× — lower values clear blockages sooner
        </span>
      </label>

      <div className="dis-manual">
        <span className="dis-row">
          <i className="swatch" style={{ background: COLORS.lock }} />
          Locks / gears
          <span className="count">{counts.lock ?? 0}</span>
        </span>
        <div className="btn-row">
          <button className="mini" onClick={() => api.addReserved("lock")}>
            + Add lock
          </button>
          <button className="mini" onClick={() => api.clearDisruptions("lock")}>
            Clear
          </button>
        </div>

        <span className="dis-row">
          <i className="swatch" style={{ background: COLORS.parking }} />
          Parking
          <span className="count">{counts.parking ?? 0}</span>
        </span>
        <div className="btn-row">
          <button className="mini" onClick={() => api.addReserved("parking")}>
            + Add parking
          </button>
          <button
            className="mini"
            onClick={() => api.clearDisruptions("parking")}
          >
            Clear
          </button>
        </div>
      </div>

      <div className="sub turn-note">
        <strong>Turns</strong> are handled by junction routing, not disruptions.
      </div>

      <div className="btn-row">
        <button onClick={() => api.clearDisruptions()}>Clear all</button>
      </div>
    </Panel>
  );
}
