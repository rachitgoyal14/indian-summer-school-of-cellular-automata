// ScenarioPanel.tsx — the batch "what-if" explorer.
//
// Configure a run, fire it at the backend's batch engine, and inspect the
// result: summary cards, a trajectory chart, and a button to drop the final
// state back into the live simulation and keep exploring from there.
//
// The live simulation is untouched by any of this — the backend runs each
// scenario on its own Simulation instance (Stage 10), so a run can never
// disturb what the user is watching.

import { useCallback, useMemo, useRef, useState } from "react";
import type { SocketApi } from "../hooks/useSimulationSocket";
import type { ScheduleEvent, ScenarioRequest, TrajectoryRecord } from "../types";
import { TrajectoryChart } from "./TrajectoryChart";

interface Props {
  api: SocketApi;
}

/** Ready-made disruption profiles, so the common cases are one click. */
const PRESETS: Record<string, { label: string; probs: Record<string, number>; repair?: number }> = {
  none: { label: "None", probs: { breakdown: 0, tree: 0, accident: 0, flood: 0 } },
  light: { label: "Light breakdowns", probs: { breakdown: 0.004, tree: 0.002, accident: 0, flood: 0 } },
  heavy: { label: "Heavy flooding", probs: { breakdown: 0.004, tree: 0.003, accident: 0.002, flood: 0.02 }, repair: 1.6 },
  custom: { label: "Custom (use Disruptions panel)", probs: {} },
};

const SCHEDULE_PLACEHOLDER = `[
  { "step": 200, "action": "block_cells", "road_id": 0,
    "cells": [20, 21, 22], "permanent": true, "kind": "flood" },
  { "step": 400, "action": "clear_disruptions", "kind": "flood" }
]`;

export function ScenarioPanel({ api }: Props) {
  const [open, setOpen] = useState(true);
  const [steps, setSteps] = useState(500);
  const [density, setDensity] = useState(0.3);
  const [carFraction, setCarFraction] = useState(0.3);
  const [laneProb, setLaneProb] = useState(0.3);
  const [preset, setPreset] = useState<keyof typeof PRESETS>("none");
  const [seedText, setSeedText] = useState("");
  const [scheduleText, setScheduleText] = useState("");
  const [scheduleError, setScheduleError] = useState<string | null>(null);
  const [lastSeed, setLastSeed] = useState<number | null>(null);

  const { scenarioRunning, scenarioResult, scenarioError } = api;

  /** Parse the schedule box. Empty is valid and means "no events". */
  const parseSchedule = useCallback((): ScheduleEvent[] | null => {
    const raw = scheduleText.trim();
    if (!raw) return [];
    try {
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) throw new Error("expected a JSON array of events");
      return parsed as ScheduleEvent[];
    } catch (e) {
      setScheduleError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }, [scheduleText]);

  const run = useCallback(() => {
    setScheduleError(null);
    const schedule = parseSchedule();
    if (schedule === null) return; // invalid JSON: never leaves the browser

    // A seed is mandatory server-side so a run reproduces. If the user left it
    // blank we pick one here and show it, rather than letting the result be
    // un-repeatable.
    const seed = seedText.trim() === ""
      ? Math.floor(Math.random() * 1_000_000)
      : Math.trunc(Number(seedText));
    setLastSeed(seed);

    const scenario: ScenarioRequest = {
      seed,
      config: "grid",
      density,
      car_fraction: carFraction,
      lane_change_prob: laneProb,
      build_kwargs: { rows: 2, cols: 2, seg: 40, lanes_per_direction: 2 },
      batch: { steps, ...(schedule.length ? { schedule } : {}) },
    };
    api.runScenario(scenario);
  }, [api, parseSchedule, seedText, density, carFraction, laneProb, steps]);

  const applyPreset = useCallback((key: keyof typeof PRESETS) => {
    setPreset(key);
    const p = PRESETS[key];
    // The scenario inherits the live disruption settings, so setting them here
    // is what makes the preset take effect on the next run.
    if (key !== "custom") api.setDisruptionParams(p.probs, p.repair);
  }, [api]);

  const trajectory: TrajectoryRecord[] = scenarioResult?.trajectory ?? [];
  const summary = scenarioResult?.summary;

  const avgDensity = useMemo(() => {
    if (!trajectory.length) return 0;
    return trajectory.reduce((a, r) => a + r.density, 0) / trajectory.length;
  }, [trajectory]);

  return (
    <section className="panel scenario-panel">
      <button className="panel-head" onClick={() => setOpen((o) => !o)}>
        <span className="panel-title">Scenario explorer</span>
        <span className="panel-chevron">{open ? "▾" : "▸"}</span>
      </button>
      {!open && <div className="panel-collapsed-hint">batch “what-if” runs</div>}

      {open && (
        <div className="panel-body">
          <Field label={`Duration: ${steps} steps`}>
            <input
              type="number" min={10} max={10000} step={10} value={steps}
              onChange={(e) => setSteps(clamp(Number(e.target.value), 10, 10000))}
            />
          </Field>

          <Slider label="Initial density" value={density} onCommit={setDensity} />
          <Slider label="Car fraction" value={carFraction} onCommit={setCarFraction} />
          <Slider label="Lane-change probability" value={laneProb} onCommit={setLaneProb} />

          <Field label="Disruption preset">
            <select
              value={preset}
              onChange={(e) => applyPreset(e.target.value as keyof typeof PRESETS)}
            >
              {Object.entries(PRESETS).map(([k, v]) => (
                <option key={k} value={k}>{v.label}</option>
              ))}
            </select>
          </Field>

          <Field label="Seed (blank = random, reported below)">
            <input
              type="number" value={seedText} placeholder="random"
              onChange={(e) => setSeedText(e.target.value)}
            />
          </Field>

          <details className="scenario-schedule">
            <summary>Scheduled events (JSON)</summary>
            <textarea
              rows={5} value={scheduleText} placeholder={SCHEDULE_PLACEHOLDER}
              onChange={(e) => { setScheduleText(e.target.value); setScheduleError(null); }}
            />
            {scheduleError && <div className="scenario-error small">{scheduleError}</div>}
          </details>

          <button
            className="run-btn"
            onClick={run}
            disabled={scenarioRunning}
            data-testid="run-scenario"
          >
            {scenarioRunning ? (
              <><span className="spinner" aria-hidden /> Running…</>
            ) : "▶ Run scenario"}
          </button>

          {scenarioError && (
            <div className="scenario-error" role="alert" data-testid="scenario-error">
              <strong>Scenario failed</strong>
              <div>{scenarioError.message}</div>
              <div className="small">{scenarioError.code}</div>
            </div>
          )}

          {summary && !scenarioError && (
            <div className="scenario-results" data-testid="scenario-results">
              <div className="cards">
                <Card label="peak flow" value={summary.peak_flow.toFixed(3)} />
                <Card label="min entropy" value={summary.min_entropy.toFixed(3)} />
                <Card label="avg density" value={avgDensity.toFixed(3)} />
                <Card label="lane changes" value={String(summary.total_lane_changes)} />
                <Card label="landscape" value={summary.final_landscape} />
                <Card label="elapsed" value={`${summary.elapsed_seconds.toFixed(2)}s`} />
              </div>
              {lastSeed !== null && (
                <div className="small">seed {lastSeed} · {summary.records} records
                  {summary.events_fired.length > 0 &&
                    ` · ${summary.events_fired.length} event(s) fired`}
                </div>
              )}

              <TrajectoryChart trajectory={trajectory} />

              <button
                className="ghost-btn wide"
                disabled={!scenarioResult}
                onClick={() => api.loadScenario(scenarioResult!.final_state)}
                title="Replace the live simulation with this scenario's end state"
              >
                ⤒ Resume in live mode
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function clamp(n: number, lo: number, hi: number) {
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : lo;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
    </label>
  );
}

function Card({ label, value }: { label: string; value: string }) {
  return (
    <div className="scenario-card">
      <div className="scenario-card-label">{label}</div>
      <div className="scenario-card-value">{value}</div>
    </div>
  );
}

/**
 * A 0–1 slider that reports only on release. Dragging fires `input` on every
 * mouse move; committing on `change` keeps one gesture to one update instead
 * of a burst of them.
 */
function Slider({
  label, value, onCommit,
}: { label: string; value: number; onCommit: (v: number) => void }) {
  const [local, setLocal] = useState(value);
  const dragging = useRef(false);
  const shown = dragging.current ? local : value;
  return (
    <label className="field">
      <span className="field-label">{label}: {shown.toFixed(2)}</span>
      <input
        type="range" min={0} max={1} step={0.01} value={shown}
        onInput={(e) => { dragging.current = true; setLocal(Number((e.target as HTMLInputElement).value)); }}
        onChange={(e) => { dragging.current = false; onCommit(Number(e.target.value)); }}
      />
    </label>
  );
}
