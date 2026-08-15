// App.tsx — top-level layout: canvas on the left, control panel + live
// readouts on the right.
//
// Stage 6: adds MapEditor to the sidebar and wires the renderer instance
// through so MapEditor can install click handlers.
//
// Visual polish (pulled forward from Stage 7): fixed-viewport cockpit layout,
// tarmac-grounded palette, amber road-marking accent, Overpass/Inter/JetBrains
// Mono typography.

import { useCallback, useRef, useState } from "react";
import { SimulationCanvas } from "./components/SimulationCanvas";
import { ControlPanel } from "./components/ControlPanel";
import { DisruptionPanel } from "./components/DisruptionPanel";
import { AnalyticsPanel } from "./components/AnalyticsPanel";
import { MapEditor } from "./components/MapEditor";
import { RegionSearch } from "./components/RegionSearch";
import { ScenarioPanel } from "./components/ScenarioPanel";
import { LaneChangePanel } from "./components/LaneChangePanel";
import { TopBar } from "./components/TopBar";
import { useSimulationSocket } from "./hooks/useSimulationSocket";
import { useSliderFill } from "./hooks/useSliderFill";
import type { ThemeName } from "./render/theme";
import type { RoadRenderer } from "./render/RoadRenderer";
import "./App.css";

const THEME_KEY = "ca-sim-theme";

export default function App() {
  const api = useSimulationSocket();
  // Day is the default; Night preserves the original dark palette.
  const [theme, setTheme] = useState<ThemeName>(() => {
    // Restore the last choice so a refresh does not throw the user back to
    // a palette they switched away from.
    const saved = typeof localStorage !== "undefined" ? localStorage.getItem(THEME_KEY) : null;
    return saved === "night" || saved === "day" ? saved : "day";
  });
  const toggleTheme = useCallback(() => {
    setTheme((t) => {
      const next: ThemeName = t === "day" ? "night" : "day";
      try { localStorage.setItem(THEME_KEY, next); } catch { /* private mode */ }
      return next;
    });
  }, []);
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


  // Every range input in the sidebar gets its filled track painted from here,
  // rather than each panel remembering to do it.
  const sidebarRef = useRef<HTMLElement | null>(null);
  useSliderFill(sidebarRef);

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
      <TopBar
        state={st}
        connected={api.connected}
        theme={theme}
        onThemeToggle={toggleTheme}
      />

      <main className="layout">
        <section className="stage">
          <SimulationCanvas
            network={api.network}
            state={st}
            onRendererReady={handleRendererReady}
            loading={mapLoading}
            theme={theme}
            onThemeToggle={toggleTheme}
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

        <aside className="sidebar" ref={sidebarRef}>
          {/* No dividers here: each Panel draws its own hairline rule, so
              the sidebar reads as one surface divided rather than a stack. */}
          <AnalyticsPanel state={st} />
          <ControlPanel api={api} />
          <LaneChangePanel api={api} />
          <ScenarioPanel api={api} />
          <RegionSearch api={api} onLoadingChange={handleLoadingChange} />
          <MapEditor
            api={api}
            network={api.network}
            state={st}
            renderer={renderer}
          />
          <DisruptionPanel api={api} />
        </aside>
      </main>

    </div>
  );
}
