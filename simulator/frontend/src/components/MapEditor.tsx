// MapEditor.tsx — Stage 6 map editing panel + save/load UI.
//
// Active-mode indicator is always visible; each mode sends the appropriate
// WebSocket message (add_road, add_vehicle, remove_vehicle, set_turn) when the
// user clicks on the canvas. Backend is the source of truth: we never
// speculatively update local state — we send and wait for the next broadcast.
//
// Edit modes:
//   "add_road"      — click empty area → addRoad at that grid position
//   "add_vehicle"   — click road cell → addVehicle (moto or car per sub-mode)
//   "delete"        — click road cell → removeVehicle; click empty → removeRoad
//   "set_turn"      — opens a small inline form for the selected junction
//   null            — normal pan/zoom (no edit handler)

import { useCallback, useEffect, useRef, useState } from "react";
import type { SocketApi } from "../hooks/useSimulationSocket";
import type { NetworkMessage, StateMessage } from "../types";
import type { RoadRenderer } from "../render/RoadRenderer";
import type { EditClick } from "../render/RoadRenderer";

interface Props {
  api: SocketApi;
  network: NetworkMessage | null;
  state: StateMessage | null;
  renderer: RoadRenderer | null;
}

type EditMode = "add_road" | "add_vehicle" | "delete" | "set_turn" | null;
type VehicleSubMode = "moto" | "car";

const ROAD_LENGTH_DEFAULT = 30;

const MODE_LABELS: Record<Exclude<EditMode, null>, string> = {
  add_road: "➕ Add road",
  add_vehicle: "🚗 Place vehicle",
  delete: "🗑 Delete",
  set_turn: "↩ Set turn",
};

const MODE_HINTS: Record<Exclude<EditMode, null>, string> = {
  add_road: "Click empty canvas to add a road at that grid position.",
  add_vehicle:
    "Click a road cell to place a vehicle. Pick moto or car below.",
  delete: "Click a road cell to remove its vehicle. Click open space to remove a road.",
  set_turn: "Pick a junction and incoming road, then adjust the turn proportions.",
};

export function MapEditor({ api, network, state, renderer }: Props) {
  const [mode, setMode] = useState<EditMode>(null);
  const [vehicleType, setVehicleType] = useState<VehicleSubMode>("moto");
  const [roadLength, setRoadLength] = useState(ROAD_LENGTH_DEFAULT);
  const [roadDirH, setRoadDirH] = useState(true); // horizontal vs vertical

  // turn editor state
  const [turnJunctionId, setTurnJunctionId] = useState<number | null>(null);
  const [turnInRoad, setTurnInRoad] = useState<number | null>(null);
  const [turnPropsStr, setTurnPropsStr] = useState(""); // "roadId:frac,roadId:frac"

  // save/load
  const [loadText, setLoadText] = useState("");
  const [loadError, setLoadError] = useState("");
  const [lastSaved, setLastSaved] = useState<string | null>(null);

  // ---- wire edit-click handler onto the renderer ----
  const handleEditClick = useCallback(
    (loc: EditClick) => {
      if (mode === "add_road") {
        // Place a road at the snapped grid position
        const dx = roadDirH ? 1 : 0;
        const dy = roadDirH ? 0 : 1;
        api.addRoad(loc.gridX, loc.gridY, dx, dy, roadLength);
      } else if (mode === "add_vehicle") {
        if (loc.road) {
          api.addVehicle(loc.road.roadId, loc.road.cell, vehicleType);
        }
      } else if (mode === "delete") {
        if (loc.road) {
          // Try vehicle first (click on any occupied cell removes that vehicle)
          api.removeVehicle(loc.road.roadId, loc.road.cell);
        } else {
          // No road nearby — nothing to delete (road removal is menu-driven)
        }
      }
      // set_turn is handled separately via the form below
    },
    [mode, api, roadLength, roadDirH, vehicleType],
  );

  // Sync the renderer's edit-click handler whenever mode or deps change.
  const handleEditClickRef = useRef(handleEditClick);
  handleEditClickRef.current = handleEditClick;

  useEffect(() => {
    if (!renderer) return;
    if (mode !== null && mode !== "set_turn") {
      renderer.setEditClickHandler((loc) => handleEditClickRef.current(loc));
    } else {
      renderer.setEditClickHandler(null);
    }
    return () => {
      renderer.setEditClickHandler(null);
    };
  }, [renderer, mode]);

  // ---- helpers ----
  const selectMode = (m: EditMode) => setMode((prev) => (prev === m ? null : m));

  // Save: ask the backend for the scenario JSON, download it as a file.
  const handleSave = () => {
    api.saveScenario((data) => {
      const json = JSON.stringify(data, null, 2);
      setLastSaved(json);
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `scenario_step${state?.step ?? 0}.json`;
      a.click();
      URL.revokeObjectURL(url);
    });
  };

  // Load: parse the pasted/uploaded JSON and send it to the backend.
  const handleLoad = () => {
    setLoadError("");
    try {
      const data = JSON.parse(loadText);
      api.loadScenario(data);
      setLoadText("");
    } catch (e) {
      setLoadError("Invalid JSON — check the format and try again.");
    }
  };

  // File-upload path for load
  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      setLoadText((ev.target?.result as string) ?? "");
    };
    reader.readAsText(file);
    // reset so the same file can be re-uploaded
    e.target.value = "";
  };

  // Turn editor: submit
  const handleSetTurn = () => {
    if (turnJunctionId === null || turnInRoad === null) return;
    try {
      const props: Record<number, number> = {};
      for (const part of turnPropsStr.split(",")) {
        const [k, v] = part.trim().split(":");
        props[parseInt(k)] = parseFloat(v);
      }
      api.setTurn(turnJunctionId, turnInRoad, props);
    } catch {
      // ignore parse errors; backend will validate
    }
  };

  // Remove-road by ID (explicit menu rather than canvas click, to avoid
  // accidents while trying to remove a vehicle)
  const [removeRoadId, setRemoveRoadId] = useState("");
  const handleRemoveRoad = () => {
    const id = parseInt(removeRoadId);
    if (!isNaN(id)) {
      api.removeRoad(id);
      setRemoveRoadId("");
    }
  };

  // analytics from state
  const analytics = state?.analytics;

  return (
    <div className="panel">
      <h2>Map Editor</h2>

      {/* landscape badge */}
      {analytics && (
        <div
          className={`landscape-badge landscape-${analytics.landscape}`}
          title={`density ${analytics.density.toFixed(2)}, blocked ${(analytics.blocked_fraction * 100).toFixed(1)}%, avg queue ${analytics.avg_queue.toFixed(1)}`}
        >
          {analytics.landscape === "trivial" && "🟢 Trivial"}
          {analytics.landscape === "average" && "🟡 Average"}
          {analytics.landscape === "worst" && "🔴 Worst"}
          <span className="landscape-sub">landscape</span>
        </div>
      )}

      {/* active-mode indicator */}
      <div className="edit-mode-bar">
        {(["add_road", "add_vehicle", "delete", "set_turn"] as const).map(
          (m) => (
            <button
              key={m}
              className={`mini ${mode === m ? "mode-active" : ""}`}
              onClick={() => selectMode(m)}
              title={MODE_HINTS[m]}
            >
              {MODE_LABELS[m]}
            </button>
          ),
        )}
      </div>

      {mode && mode !== "set_turn" && (
        <div className="mode-hint">{MODE_HINTS[mode]}</div>
      )}

      {/* ---- add_road options ---- */}
      {mode === "add_road" && (
        <div className="edit-sub">
          <label className="field">
            Road length (cells):{" "}
            <strong>{roadLength}</strong>
            <input
              type="range"
              min={5}
              max={80}
              step={1}
              value={roadLength}
              onChange={(e) => setRoadLength(parseInt(e.target.value))}
            />
          </label>
          <div className="btn-row">
            <button
              className={`mini ${roadDirH ? "mode-active" : ""}`}
              onClick={() => setRoadDirH(true)}
            >
              → Horizontal
            </button>
            <button
              className={`mini ${!roadDirH ? "mode-active" : ""}`}
              onClick={() => setRoadDirH(false)}
            >
              ↓ Vertical
            </button>
          </div>
        </div>
      )}

      {/* ---- add_vehicle sub-mode ---- */}
      {mode === "add_vehicle" && (
        <div className="edit-sub btn-row">
          <button
            className={`mini ${vehicleType === "moto" ? "mode-active" : ""}`}
            onClick={() => setVehicleType("moto")}
          >
            <svg width="12" height="10" viewBox="0 0 16 14" style={{verticalAlign: "middle", marginRight: 3}}>
              <path d="M14,7 L10,4 L5,4.5 L2,5.5 L2,8.5 L5,9.5 L10,10 Z" fill="#4ECDC4" opacity="0.9"/>
            </svg>
            Moto
          </button>
          <button
            className={`mini ${vehicleType === "car" ? "mode-active" : ""}`}
            onClick={() => setVehicleType("car")}
          >
            <svg width="20" height="10" viewBox="0 0 28 14" style={{verticalAlign: "middle", marginRight: 3}}>
              <path d="M25,7 L23,3 L17,2 L10,2 L8,3.5 L8,2.5 L4,3 L2,4.5 L2,9.5 L4,11 L8,11.5 L8,10.5 L10,12 L17,12 L23,11 Z" fill="#F5A623" opacity="0.9"/>
            </svg>
            Car
          </button>
        </div>
      )}

      {/* ---- remove road by ID (available always) ---- */}
      <div className="divider" />
      <h3>Remove road by ID</h3>
      <div className="btn-row">
        <select
          value={removeRoadId}
          onChange={(e) => setRemoveRoadId(e.target.value)}
          style={{ flex: 1 }}
        >
          <option value="">select road…</option>
          {network?.roads.map((r) => (
            <option key={r.id} value={String(r.id)}>
              Road {r.id} ({r.length} cells)
            </option>
          ))}
        </select>
        <button className="mini" onClick={handleRemoveRoad} disabled={!removeRoadId}>
          Remove
        </button>
      </div>

      {/* ---- turn proportions ---- */}
      {network && network.junctions.length > 0 && (
        <>
          <div className="divider" />
          <h3>Set turn proportions</h3>
          <div className="edit-sub">
            <label className="field">
              Junction
              <select
                value={turnJunctionId ?? ""}
                onChange={(e) =>
                  setTurnJunctionId(
                    e.target.value === "" ? null : parseInt(e.target.value),
                  )
                }
              >
                <option value="">select…</option>
                {network.junctions.map((j) => (
                  <option key={j.id} value={j.id}>
                    Junction {j.id}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Incoming road
              <select
                value={turnInRoad ?? ""}
                onChange={(e) =>
                  setTurnInRoad(
                    e.target.value === "" ? null : parseInt(e.target.value),
                  )
                }
              >
                <option value="">select…</option>
                {network.roads.map((r) => (
                  <option key={r.id} value={r.id}>
                    Road {r.id}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Proportions{" "}
              <span className="sub">
                e.g. <code>2:0.6, 3:0.4</code> (road_id:fraction, must sum to
                1)
              </span>
              <input
                type="text"
                value={turnPropsStr}
                onChange={(e) => setTurnPropsStr(e.target.value)}
                placeholder="2:0.6, 3:0.4"
                style={{
                  background: "var(--tarmac)",
                  color: "var(--chalk)",
                  border: "1px solid var(--kerb)",
                  borderRadius: 6,
                  padding: "5px 8px",
                  fontSize: 13,
                }}
              />
            </label>
            <button className="mini" onClick={handleSetTurn}>
              Apply turn
            </button>
          </div>
        </>
      )}

      {/* ---- save / load ---- */}
      <div className="divider" />
      <h3>Save / Load scenario</h3>
      <div className="btn-row">
        <button onClick={handleSave} className="mini">
          💾 Save &amp; download
        </button>
        {lastSaved && (
          <button
            className="mini"
            onClick={() => {
              if (lastSaved) {
                api.loadScenario(JSON.parse(lastSaved));
              }
            }}
            title="Reload the last saved snapshot without a file picker"
          >
            ↩ Re-load last
          </button>
        )}
      </div>

      <label className="field">
        <span>Upload scenario file</span>
        <input
          id="scenario-file-upload"
          type="file"
          accept="application/json,.json"
          onChange={handleFileUpload}
          style={{ fontSize: 12, color: "var(--gravel)" }}
        />
      </label>

      <label className="field">
        <span>Or paste JSON</span>
        <textarea
          id="scenario-paste"
          rows={4}
          value={loadText}
          onChange={(e) => setLoadText(e.target.value)}
          placeholder='{"version": 1, ...}'
          style={{
            background: "var(--tarmac)",
            color: "var(--chalk)",
            border: "1px solid var(--kerb)",
            borderRadius: 6,
            padding: "6px 8px",
            fontSize: 11,
            fontFamily: "monospace",
            resize: "vertical",
          }}
        />
      </label>
      {loadError && <div className="load-error">{loadError}</div>}
      <button
        className="mini"
        onClick={handleLoad}
        disabled={!loadText.trim()}
      >
        📂 Load scenario
      </button>
    </div>
  );
}
