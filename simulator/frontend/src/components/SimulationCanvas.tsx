// SimulationCanvas.tsx — mounts the PixiJS RoadRenderer in a React component
// and feeds it network/state updates. Also renders a small debug overlay
// showing the visible cell-index range (Stage 2c: proves the camera never
// desyncs from the underlying road array) and a "Fit view" button.

import { useEffect, useRef, useState } from "react";
import { RoadRenderer } from "../render/RoadRenderer";
import type { NetworkMessage, StateMessage } from "../types";

interface Props {
  network: NetworkMessage | null;
  state: StateMessage | null;
}

export function SimulationCanvas({ network, state }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<RoadRenderer | null>(null);
  const [ready, setReady] = useState(false);
  const [visible, setVisible] = useState<string>("—");
  const [heatmap, setHeatmap] = useState(false);

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
    });
    return () => {
      cancelled = true;
      renderer?.destroy();
      rendererRef.current = null;
    };
  }, []);

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
        <span className="hint">scroll = zoom · drag = pan</span>
      </div>
    </div>
  );
}
