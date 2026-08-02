// App.tsx — top-level layout: canvas on the left, control panel + live
// readouts on the right.
//
// Stage 6: adds MapEditor to the sidebar and wires the renderer instance
// through so MapEditor can install click handlers.
//
// Visual polish (pulled forward from Stage 7): fixed-viewport cockpit layout,
// tarmac-grounded palette, amber road-marking accent, Overpass/Inter/JetBrains
// Mono typography.

import { useCallback, useState } from "react";
import { SimulationCanvas } from "./components/SimulationCanvas";
import { ControlPanel } from "./components/ControlPanel";
import { DisruptionPanel } from "./components/DisruptionPanel";
import { AnalyticsPanel } from "./components/AnalyticsPanel";
import { MapEditor } from "./components/MapEditor";
import { RegionSearch } from "./components/RegionSearch";
import { useSimulationSocket } from "./hooks/useSimulationSocket";
import type { RoadRenderer } from "./render/RoadRenderer";
import "./App.css";

export default function App() {
  const api = useSimulationSocket();
  const st = api.state;

  // Renderer instance: set once the canvas mounts, cleared on unmount.
  const [renderer, setRenderer] = useState<RoadRenderer | null>(null);
  const handleRendererReady = useCallback(
    (r: RoadRenderer | null) => setRenderer(r),
    [],
  );

  // Map import loading state
  const [mapLoading, setMapLoading] = useState(false);
  const handleLoadingChange = useCallback((loading: boolean) => {
    setMapLoading(loading);
  }, []);

  // Map import loading state
  const [mapLoading, setMapLoading] = useState(false);
  const handleLoadingChange = useCallback((loading: boolean) => {
    setMapLoading(loading);
  }, []);

  // counts of active disruptions by kind — hidden, for automated verification
  const disCounts: Record<string, number> = {};
  for (const d of st?.disruptions ?? []) {
    disCounts[d.kind] = (disCounts[d.kind] ?? 0) + 1;
  }

  return (
    <div className="app">
      <div data-testid="dis-debug" style={{ display: "none" }}>
        {JSON.stringify(disCounts)}
      </div>
      <header className="topbar">
        <h1><span className="topbar-issca">ISSCA</span>CA Rule 184 — Traffic Simulator</h1>
        <div className={`conn ${api.connected ? "up" : "down"}`}>
          {api.connected ? "● connected" : "○ disconnected"}
        </div>
      </header>

      <main className="layout">
        <section className="stage">
          <SimulationCanvas
            network={api.network}
            state={st}
            onRendererReady={handleRendererReady}
            loading={mapLoading}
          />

          {st && st.junctions.length > 0 && (
            <div className="queues">
              <span className="queues-label">junction queues</span>
              {st.junctions.map((j) => (
                <span
                  key={j.id}
                  className={`qbadge ${j.queue >= 6 ? "hot" : ""}`}
                  title={`vehicles backed up near junction ${j.id}`}
                >
                  J{j.id}: {j.queue}
                </span>
              ))}
            </div>
          )}
        </section>

        <aside className="sidebar">
          <AnalyticsPanel state={st} />
          <div className="divider" />
          <ControlPanel api={api} />
          <div className="divider" />
          <RegionSearch api={api} onLoadingChange={handleLoadingChange} />
          <div className="divider" />
          <MapEditor
            api={api}
            network={api.network}
            state={st}
            renderer={renderer}
          />
          <div className="divider" />
          <DisruptionPanel api={api} />
        </aside>
      </main>

      <div className="readout">
        <Metric label="step" value={st ? String(st.step) : "—"} />
        <Metric
          label="density"
          value={st ? st.analytics.density.toFixed(3) : "—"}
        />
        <Metric
          label="flow"
          value={st ? st.analytics.flow.toFixed(3) : "—"}
        />
        <Metric
          label="entropy"
          value={st ? `${st.analytics.entropy_bits.toFixed(2)} bits` : "—"}
        />
        <Metric
          label="landscape"
          value={st ? st.analytics.landscape : "—"}
        />
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div
        className={`metric-value${label === "landscape" ? ` landscape-text-${value}` : ""}`}
      >
        {value}
      </div>
    </div>
  );
}
