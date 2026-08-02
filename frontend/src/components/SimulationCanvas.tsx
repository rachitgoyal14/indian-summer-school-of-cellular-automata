// SimulationCanvas.tsx — mounts the PixiJS RoadRenderer in a React component
// and feeds it network/state updates. Also renders a small debug overlay
// showing the visible cell-index range (Stage 2c: proves the camera never
// desyncs from the underlying road array) and a "Fit view" button.
//
// Stage 6: exposes the RoadRenderer instance via onRendererReady so that
// MapEditor can install an edit-click handler on it.

import { useEffect, useRef, useState } from "react";
import { RoadRenderer } from "../render/RoadRenderer";
import type { NetworkMessage, StateMessage } from "../types";

interface Props {
  network: NetworkMessage | null;
  state: StateMessage | null;
  onRendererReady?: (r: RoadRenderer | null) => void;
  loading?: boolean;
}

const LOADING_PHASES = [
  "Geocoding location…",
  "Fetching roads from OpenStreetMap…",
  "Parsing street network graph…",
  "Building node topology…",
  "Generating simulation grid…",
];

function LoadingOverlay() {
  const [phase, setPhase] = useState(0);
  const [dots, setDots] = useState("");

  useEffect(() => {
    const iv = setInterval(() => setPhase((p) => (p + 1) % LOADING_PHASES.length), 3200);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    const iv = setInterval(() => setDots((d) => (d.length >= 3 ? "" : d + ".")), 500);
    return () => clearInterval(iv);
  }, []);

  return (
    <div className="canvas-loading-overlay">
      <div className="loading-card">
        {/* Animated map illustration */}
        <div className="loading-map-scene">
          <svg viewBox="0 0 200 120" className="loading-map-svg">
            {/* Grid of faint dots — represents the area being mapped */}
            {Array.from({ length: 7 }, (_, r) =>
              Array.from({ length: 10 }, (_, c) => (
                <circle
                  key={`${r}-${c}`}
                  cx={15 + c * 19}
                  cy={12 + r * 16}
                  r="1"
                  className="loading-grid-dot"
                  style={{ animationDelay: `${(r * 10 + c) * 60}ms` }}
                />
              ))
            )}
            {/* Road lines being drawn */}
            <path d="M20,30 L80,30 L80,75 L160,75" className="loading-road-line road-1" />
            <path d="M40,15 L40,60 L120,60 L120,110" className="loading-road-line road-2" />
            <path d="M10,55 L60,55 L100,35 L180,35" className="loading-road-line road-3" />
            <path d="M90,10 L90,45 L150,45 L150,95" className="loading-road-line road-4" />
            {/* Junction dots — appear after roads */}
            <circle cx="80" cy="30" r="3.5" className="loading-junction" style={{ animationDelay: "1.2s" }} />
            <circle cx="80" cy="75" r="3.5" className="loading-junction" style={{ animationDelay: "1.6s" }} />
            <circle cx="40" cy="60" r="3.5" className="loading-junction" style={{ animationDelay: "1.4s" }} />
            <circle cx="120" cy="60" r="3.5" className="loading-junction" style={{ animationDelay: "1.8s" }} />
            <circle cx="90" cy="45" r="3.5" className="loading-junction" style={{ animationDelay: "2.0s" }} />
            {/* Pulsing location pin */}
            <g className="loading-pin" transform="translate(100,55)">
              <circle cx="0" cy="0" r="12" className="loading-pin-pulse" />
              <circle cx="0" cy="0" r="6" className="loading-pin-pulse pulse-2" />
              <path d="M0,-8 C-4.5,-8 -8,-4.5 -8,0 C-8,5 0,12 0,12 C0,12 8,5 8,0 C8,-4.5 4.5,-8 0,-8Z" fill="#F5A623" />
              <circle cx="0" cy="-1" r="2.5" fill="#1a1a1a" />
            </g>
          </svg>
        </div>

        <div className="loading-text">Importing map{dots}</div>

        {/* Phase indicator */}
        <div className="loading-phases">
          {LOADING_PHASES.map((text, i) => (
            <div key={i} className={`loading-phase ${i === phase ? "active" : i < phase ? "done" : ""}`}>
              <span className="loading-phase-dot">{i < phase ? "✓" : i === phase ? "›" : "·"}</span>
              {text}
            </div>
          ))}
        </div>

        <div className="loading-subtext">This usually takes 5–15 seconds</div>
      </div>
    </div>
  );
}

export function SimulationCanvas({ network, state, onRendererReady, loading = false }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<RoadRenderer | null>(null);
  const [ready, setReady] = useState(false);
  const [visible, setVisible] = useState<string>("—");
  const [heatmap, setHeatmap] = useState(false);
  const [navGraph, setNavGraph] = useState(false);

  // Create the Pixi app once.
  useEffect(() => {
    let cancelled = false;
    let renderer: RoadRenderer | null = null;
    const el = containerRef.current;
    if (!el) return;
    RoadRenderer.create(el).then((r) => {
      if (cancelled) {
        r.destroy();
        return;
      }
      renderer = r;
      rendererRef.current = r;
      setReady(true);
      onRendererReady?.(r);
    });
    return () => {
      cancelled = true;
      renderer?.destroy();
      rendererRef.current = null;
      onRendererReady?.(null);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Feed network structure.
  useEffect(() => {
    if (ready && network) rendererRef.current?.setNetwork(network);
  }, [ready, network]);

  // Feed per-tick state.
  useEffect(() => {
    if (ready && state) rendererRef.current?.setState(state);
  }, [ready, state]);

  // Poll the visible cell range each frame for the debug readout.
  useEffect(() => {
    if (!ready) return;
    let raf = 0;
    const tick = () => {
      const r = rendererRef.current?.getVisibleCellRange();
      if (r) setVisible(`road ${r.roadId}: cells ${r.min}–${r.max}`);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [ready]);

  return (
    <div className="canvas-wrap">
      <div ref={containerRef} className="pixi-host" />
      {loading && <LoadingOverlay />}
      <div className="canvas-overlay">
        <span className="badge">visible: {visible}</span>
        <button
          className="ghost-btn"
          onClick={() => rendererRef.current?.fitToView()}
        >
          Fit view
        </button>
        <button
          className={`ghost-btn ${heatmap ? "active" : ""}`}
          onClick={() => {
            const next = !heatmap;
            setHeatmap(next);
            rendererRef.current?.setHeatmapEnabled(next);
          }}
        >
          {heatmap ? "Heatmap ✓" : "Heatmap"}
        </button>
        <button
          className={`ghost-btn ${navGraph ? "active" : ""}`}
          onClick={() => {
            const next = !navGraph;
            setNavGraph(next);
            rendererRef.current?.setNavGraphEnabled(next);
          }}
        >
          {navGraph ? "Nav Graph ✓" : "Nav Graph"}
        </button>
        <span className="hint">scroll = zoom · drag = pan</span>
      </div>
    </div>
  );
}
