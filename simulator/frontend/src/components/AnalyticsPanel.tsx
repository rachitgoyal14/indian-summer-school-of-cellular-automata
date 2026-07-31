// AnalyticsPanel.tsx — live density/flow (log scale) + Shannon entropy.
//
// Charting choice (stages.md asks us to pick one that keeps up and document
// it): a dependency-free custom <canvas> renderer driven by a fixed-size ring
// buffer of recent samples, redrawn on requestAnimationFrame. This trivially
// keeps up with the ~12 Hz state stream (one lightweight canvas repaint per
// frame, no React re-render or DOM churn per sample) and adds no chart lib to
// the bundle.

import { useEffect, useRef } from "react";
import type { StateMessage } from "../types";

interface Props {
  state: StateMessage | null;
}

interface Sample {
  step: number;
  density: number;
  flow: number;
  entropy: number;
}

const CAP = 240; // samples kept (~20 s at 12 Hz)
const LOG_MIN = 1e-3; // log-y floor so density/flow=0 is representable

export function AnalyticsPanel({ state }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const buf = useRef<Sample[]>([]);
  const lastStep = useRef(-1);

  // push a sample whenever a new step arrives
  useEffect(() => {
    if (!state) return;
    if (state.step === lastStep.current) return;
    lastStep.current = state.step;
    const s: Sample = {
      step: state.step,
      density: state.analytics.density,
      flow: state.analytics.flow,
      entropy: state.analytics.entropy,
    };
    const b = buf.current;
    b.push(s);
    if (b.length > CAP) b.shift();
  }, [state]);

  // draw loop
  useEffect(() => {
    let raf = 0;
    const draw = () => {
      const cv = canvasRef.current;
      if (cv) render(cv, buf.current);
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, []);

  const a = state?.analytics;
  return (
    <div className="panel">
      <h2>Analytics</h2>
      <canvas ref={canvasRef} className="chart" width={288} height={200} />
      <div className="chart-legend">
        <span><i className="ln cyan" /> density (log)</span>
        <span><i className="ln green" /> flow (log)</span>
        <span><i className="ln amber" /> entropy (0–1)</span>
      </div>
      <div className="entropy-readout">
        <div className="metric-label">Shannon entropy (spread)</div>
        <div className="entropy-bar">
          <div
            className="entropy-fill"
            style={{ width: `${((a?.entropy ?? 0) * 100).toFixed(1)}%` }}
          />
        </div>
        <div className="entropy-val" data-testid="entropy">
          {a ? a.entropy.toFixed(3) : "—"} norm ·{" "}
          {a ? a.entropy_bits.toFixed(2) : "—"} bits
        </div>
        <div className="sub">
          high = traffic evenly spread · drops when a disruption clusters it
        </div>
      </div>
    </div>
  );
}

function logY(v: number, h: number, pad: number): number {
  const lv = Math.log10(Math.max(v, LOG_MIN));
  const lmin = Math.log10(LOG_MIN);
  const lmax = Math.log10(1);
  const t = (lv - lmin) / (lmax - lmin); // 0..1
  return h - pad - t * (h - 2 * pad);
}

function render(cv: HTMLCanvasElement, data: Sample[]) {
  const ctx = cv.getContext("2d");
  if (!ctx) return;
  const w = cv.width;
  const h = cv.height;
  const pad = 18;
  const splitY = h * 0.66; // top: density/flow (log); bottom: entropy (linear)

  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = "#141b2b";
  ctx.fillRect(0, 0, w, h);

  // gridlines for the log panel at 1, 0.1, 0.01
  ctx.strokeStyle = "#2a3448";
  ctx.fillStyle = "#6b7891";
  ctx.font = "9px monospace";
  ctx.lineWidth = 1;
  for (const gv of [1, 0.1, 0.01]) {
    const y = logY(gv, splitY, pad);
    ctx.beginPath();
    ctx.moveTo(pad, y);
    ctx.lineTo(w - 2, y);
    ctx.stroke();
    ctx.fillText(String(gv), 1, y + 3);
  }
  // entropy panel baseline (0 and 1)
  ctx.strokeStyle = "#2a3448";
  ctx.beginPath();
  ctx.moveTo(pad, splitY + pad);
  ctx.lineTo(w - 2, splitY + pad);
  ctx.moveTo(pad, h - pad);
  ctx.lineTo(w - 2, h - pad);
  ctx.stroke();

  if (data.length < 2) return;
  const n = data.length;
  const x = (i: number) => pad + (i / (CAP - 1)) * (w - pad - 2);

  const line = (
    color: string,
    getY: (s: Sample) => number,
  ) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const px = x(i);
      const py = getY(data[i]);
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.stroke();
  };

  line("#5cc8ff", (s) => logY(s.density, splitY, pad)); // density
  line("#67d982", (s) => logY(s.flow, splitY, pad)); // flow
  // entropy on linear 0..1 in the bottom panel
  const eTop = splitY + pad;
  const eBot = h - pad;
  line("#ffb454", (s) => eBot - s.entropy * (eBot - eTop));
}
