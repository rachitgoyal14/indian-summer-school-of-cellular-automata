// RegionSearch.tsx — Stage 8: place-name search + region import UI.
//
// A simple text input + search button that sends a region-import request
// to the backend. Uses the existing WebSocket architecture (import_region
// message → network replacement → existing renderer displays it).

import { useState } from "react";
import type { SocketApi } from "../hooks/useSimulationSocket";

interface Props {
  api: SocketApi;
}

export function RegionSearch({ api }: Props) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{
    ok: boolean;
    error?: string;
    roads?: number;
    junctions?: number;
    total_cells?: number;
  } | null>(null);

  const handleSearch = () => {
    if (!query.trim() || loading) return;
    setLoading(true);
    setResult(null);
    api.importRegion(query.trim(), (res) => {
      setResult(res);
      setLoading(false);
    });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSearch();
  };

  return (
    <div className="panel">
      <h2>Import Real Map</h2>
      <div className="region-search">
        <div className="region-input-row">
          <input
            type="text"
            className="region-input"
            placeholder="e.g. IIT BHU Varanasi"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
          />
          <button
            onClick={handleSearch}
            disabled={loading || !query.trim()}
            className="region-btn"
          >
            {loading ? "Importing…" : "Import"}
          </button>
        </div>
        <div className="field sub">
          Enter a place name or campus. The map will be fetched from
          OpenStreetMap in real time.
        </div>
        {result && (
          <div
            className={`region-result ${result.ok ? "region-ok" : "region-err"}`}
          >
            {result.ok ? (
              <>
                ✓ Imported: {result.roads} roads, {result.junctions} junctions,{" "}
                {result.total_cells} cells
              </>
            ) : (
              <>✗ {result.error}</>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
