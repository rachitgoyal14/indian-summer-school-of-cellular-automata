// App.tsx — top-level layout: canvas on the left, control panel + live
// readouts on the right.

import { SimulationCanvas } from "./components/SimulationCanvas";
import { ControlPanel } from "./components/ControlPanel";
import { useSimulationSocket } from "./hooks/useSimulationSocket";
import "./App.css";

export default function App() {
  const api = useSimulationSocket();
  const st = api.state;

  return (
    <div className="app">
      <header className="topbar">
        <h1>CA Rule 184 — Traffic Simulator</h1>
        <div className={`conn ${api.connected ? "up" : "down"}`}>
          {api.connected ? "● connected" : "○ disconnected"}
        </div>
      </header>

      <main className="layout">
        <section className="stage">
          <SimulationCanvas network={api.network} state={st} />
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
            <Metric label="running" value={st ? String(st.running) : "—"} />
          </div>

          {st && st.junctions.length > 0 && (
            <div className="queues">
              <span className="queues-label">junction queues:</span>
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
          <ControlPanel api={api} />
        </aside>
      </main>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
    </div>
  );
}
