// TrajectoryChart.tsx — the scenario's analytics over time.
//
// Same canvas-drawing approach as the live Analytics panel, but fed from a
// finished trajectory rather than a rolling buffer: density and flow on a log
// axis (they span orders of magnitude), entropy on a linear 0–1 axis.
//
// A long run has far more steps than the canvas has pixels, so the series are
// downsampled to one point per column — which is also what keeps a 10,000-step
// result from costing 10,000 line segments to draw.

import { useEffect, useRef } from "react";
import type { TrajectoryRecord } from "../types";

const H_TOP = 96;   // density / flow (log)
const H_BOT = 52;   // entropy (linear 0–1)
const GAP = 10;
const PAD_L = 26;

const LOG_MIN = 1e-3; // floor for the log axis; zeros clamp to it

function toLog(v: number): number {
  const c = Math.max(v, LOG_MIN);
  return (Math.log10(c) - Math.log10(LOG_MIN)) / (0 - Math.log10(LOG_MIN));
}

export function TrajectoryChart({ trajectory }: { trajectory: TrajectoryRecord[] }) {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || trajectory.length === 0) return;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = H_TOP + GAP + H_BOT;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const plotW = Math.max(1, w - PAD_L - 4);
    // one sample per pixel column: the chart cannot show more than that
    const columns = Math.min(plotW, trajectory.length);
    const pick = (i: number) =>
      trajectory[Math.min(trajectory.length - 1,
        Math.round((i / Math.max(1, columns - 1)) * (trajectory.length - 1)))];

    const frame = (top: number, height: number, label: string) => {
      ctx.strokeStyle = "rgba(255,255,255,0.07)";
      ctx.lineWidth = 1;
      ctx.strokeRect(PAD_L + 0.5, top + 0.5, plotW - 1, height - 1);
      // Muted, monospaced, and lower case: uppercase is reserved for the
      // sidebar's panel headers so the two never read as the same level.
      ctx.fillStyle = "rgba(255,255,255,0.34)";
      ctx.font = "9px ui-monospace, monospace";
      ctx.textAlign = "right";
      ctx.fillText(label, PAD_L + plotW - 4, top + 11);
    };

    const series = (
      top: number, height: number, colour: string,
      value: (r: TrajectoryRecord) => number,
    ) => {
      ctx.strokeStyle = colour;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      for (let i = 0; i < columns; i++) {
        const x = PAD_L + (i / Math.max(1, columns - 1)) * (plotW - 1);
        const y = top + height - 2 - value(pick(i)) * (height - 4);
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      }
      ctx.stroke();
    };

    frame(0, H_TOP, "density / flow (log)");
    series(0, H_TOP, "#4ecdc4", (r) => toLog(r.density));
    series(0, H_TOP, "#7bd88f", (r) => toLog(r.flow));

    frame(H_TOP + GAP, H_BOT, "entropy");
    series(H_TOP + GAP, H_BOT, "#f5a623", (r) => Math.max(0, Math.min(1, r.entropy)));

    // step axis
    ctx.fillStyle = "rgba(255,255,255,0.4)";
    ctx.font = "9px ui-monospace, monospace";
    ctx.textAlign = "left";
    ctx.fillText("0", PAD_L, h - 1);
    ctx.textAlign = "right";
    ctx.fillText(String(trajectory[trajectory.length - 1].step), PAD_L + plotW, h - 1);
  }, [trajectory]);

  if (!trajectory.length) return null;
  return (
    <div className="trajectory-chart">
      <canvas ref={ref} style={{ width: "100%", height: H_TOP + GAP + H_BOT }} />
      <div className="chart-legend">
        <span><i style={{ background: "#4ecdc4" }} />density</span>
        <span><i style={{ background: "#7bd88f" }} />flow</span>
        <span><i style={{ background: "#f5a623" }} />entropy</span>
      </div>
    </div>
  );
}
