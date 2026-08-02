// AnalyticsPanel.tsx — live density/flow (log scale) + Shannon entropy.
//
// Charting choice (stages.md asks us to pick one that keeps up and document
// it): a dependency-free custom <canvas> renderer driven by a fixed-size ring
// buffer of recent samples, redrawn on requestAnimationFrame. This trivially
// keeps up with the ~12 Hz state stream (one lightweight canvas repaint per
// frame, no React re-render or DOM churn per sample) and adds no chart lib to
// the bundle.
//
// Visual polish: thicker lines with area fills, visible grid labels,
// current-value markers, warmer tarmac-grounded palette.

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

// palette — matches the design system
const C = {
  bg:       "#1a1a1a",   // tarmac
  grid:     "#3a3a3a",   // kerb
  gridText: "#8C8478",   // gravel
  density:  "#4ECDC4",   // teal (motorbike accent)
  flow:     "#67d982",   // green
  entropy:  "#F5A623",   // amber (road marking)
  densityFill: "rgba(78,205,196,0.10)",
  flowFill:    "rgba(103,217,130,0.08)",
  entropyFill: "rgba(245,166,35,0.10)",
  divider:  "#3a3a3a",
};

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
      <canvas ref={canvasRef} className="chart" width={288} height={210} />
      <div className="chart-legend">
        <span><i className="ln teal" /> density (log)</span>
        <span><i className="ln green" /> flow (log)</span>
        <span><i className="ln amber" /> entropy (0–1)</span>
      </div>
      <div className="entropy-readout">
        <div className="metric-label">Shannon entropy</div>
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
  const pad = 22;
  const splitY = h * 0.64; // top: density/flow (log); bottom: entropy (linear)

  ctx.clearRect(0, 0, w, h);
  ctx.fillStyle = C.bg;
  ctx.fillRect(0, 0, w, h);

  // ---- gridlines for the log panel ----
  ctx.strokeStyle = C.grid;
  ctx.fillStyle = C.gridText;
  ctx.font = "500 9px 'JetBrains Mono', monospace";
  ctx.lineWidth = 1;
  for (const gv of [1, 0.1, 0.01]) {
    const y = logY(gv, splitY, pad);
    ctx.beginPath();
    ctx.setLineDash([3, 3]);
    ctx.moveTo(pad, y);
    ctx.lineTo(w - 4, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillText(String(gv), 2, y + 3);
  }

  // ---- divider between panels ----
  ctx.strokeStyle = C.divider;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(pad, splitY + 4);
  ctx.lineTo(w - 4, splitY + 4);
  ctx.stroke();

  // ---- entropy panel baseline labels ----
  ctx.fillStyle = C.gridText;
  ctx.font = "500 8px 'JetBrains Mono', monospace";
  const eTop = splitY + pad;
  const eBot = h - pad;
  ctx.fillText("1", 5, eTop + 3);
  ctx.fillText("0", 5, eBot + 3);
  // gridlines for entropy
  ctx.strokeStyle = C.grid;
  ctx.setLineDash([3, 3]);
  ctx.beginPath();
  ctx.moveTo(pad, eTop);
  ctx.lineTo(w - 4, eTop);
  ctx.moveTo(pad, eBot);
  ctx.lineTo(w - 4, eBot);
  ctx.stroke();
  ctx.setLineDash([]);

  if (data.length < 2) return;
  const n = data.length;
  const x = (i: number) => pad + (i / (CAP - 1)) * (w - pad - 4);

  // ---- area fill + line helper ----
  const areaLine = (
    color: string,
    fillColor: string,
    getY: (s: Sample) => number,
    baseY: number,
  ) => {
    // area fill
    ctx.fillStyle = fillColor;
    ctx.beginPath();
    ctx.moveTo(x(0), baseY);
    for (let i = 0; i < n; i++) {
      ctx.lineTo(x(i), getY(data[i]));
    }
    ctx.lineTo(x(n - 1), baseY);
    ctx.closePath();
    ctx.fill();

    // line
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.lineJoin = "round";
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      const px = x(i);
      const py = getY(data[i]);
      if (i === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.stroke();

    // current-value dot (last sample)
    const last = data[n - 1];
    const lx = x(n - 1);
    const ly = getY(last);
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(lx, ly, 3, 0, Math.PI * 2);
    ctx.fill();
    // outer ring
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(lx, ly, 5.5, 0, Math.PI * 2);
    ctx.stroke();
  };

  // density
  areaLine(
    C.density, C.densityFill,
    (s) => logY(s.density, splitY, pad),
    splitY - pad,
  );
  // flow
  areaLine(
    C.flow, C.flowFill,
    (s) => logY(s.flow, splitY, pad),
    splitY - pad,
  );
  // entropy
  areaLine(
    C.entropy, C.entropyFill,
    (s) => eBot - s.entropy * (eBot - eTop),
    eBot,
  );

  // ---- panel labels ----
  ctx.fillStyle = C.gridText;
  ctx.font = "600 8px 'Overpass', sans-serif";
  ctx.textAlign = "right";
  ctx.fillText("DENSITY / FLOW", w - 6, pad - 6);
  ctx.fillText("ENTROPY", w - 6, splitY + pad - 6);
  ctx.textAlign = "left";
}
