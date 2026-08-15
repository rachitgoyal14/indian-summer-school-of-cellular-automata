// TopBar.tsx — the full-width HUD strip across the top of the app.
//
// Left: the simulator's name. Centre: the live readouts (step, density, flow,
// entropy, landscape). Right: connection state, the Day/Night toggle, and a
// static compass rose.
//
// The readouts used to live in a strip along the bottom of the window. They
// are here and only here now — showing them in both places was the one thing
// the reference layout does not do.

import type { StateMessage } from "../types";
import type { ThemeName } from "../render/theme";

/**
 * A fixed north indicator.
 *
 * Deliberately does not rotate with the camera. The camera never rotates
 * either — it only pans and zooms — so north is always up, and a compass that
 * animated would imply a freedom the view does not have.
 */
function CompassRose() {
  return (
    <svg
      className="compass"
      viewBox="0 0 32 32"
      width="26"
      height="26"
      role="img"
      aria-label="north is up"
    >
      <circle cx="16" cy="16" r="14" className="compass-ring" />
      {/* N/E/S/W cross */}
      <path d="M16 4 V28 M4 16 H28" className="compass-cross" />
      {/* north needle, filled so the top reads as the pointed end */}
      <path d="M16 5 L19.4 15 L16 12.6 L12.6 15 Z" className="compass-needle" />
      <text x="16" y="11.2" className="compass-n" textAnchor="middle">N</text>
    </svg>
  );
}

function Metric({ label, value, extraClass = "" }: {
  label: string;
  value: string;
  extraClass?: string;
}) {
  return (
    <div className="hud-metric">
      <span className="hud-label">{label}</span>
      <span className={`hud-value ${extraClass}`}>{value}</span>
    </div>
  );
}

export function TopBar({ state, connected, theme, onThemeToggle }: {
  state: StateMessage | null;
  connected: boolean;
  theme: ThemeName;
  onThemeToggle: () => void;
}) {
  const a = state?.analytics;
  return (
    <header className="topbar">
      <div className="topbar-left">
        <span className="topbar-name">Sarak</span>
      </div>

      <div className="topbar-center" data-testid="hud-readouts">
        <Metric label="step" value={state ? String(state.step) : "—"} />
        <Metric label="density" value={a ? a.density.toFixed(3) : "—"} />
        <Metric label="flow" value={a ? a.flow.toFixed(3) : "—"} />
        <Metric label="entropy"
                value={a ? `${a.entropy_bits.toFixed(2)} bits` : "—"} />
        <div className="hud-metric">
          <span className="hud-label">landscape</span>
          <span className={`hud-badge landscape-${a?.landscape ?? "none"}`}>
            {a?.landscape ?? "—"}
          </span>
        </div>
      </div>

      <div className="topbar-right">
        <span className={`conn ${connected ? "up" : "down"}`}>
          {connected ? "● connected" : "○ disconnected"}
        </span>
        <button
          className="theme-toggle"
          onClick={onThemeToggle}
          data-testid="theme-toggle"
          title="Switch between the Day campus map and the Night palette"
        >
          {theme === "day" ? "☀️ Day" : "🌙 Night"}
        </button>
        <CompassRose />
      </div>
    </header>
  );
}
