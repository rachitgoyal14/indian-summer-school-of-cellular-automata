// types.ts — TypeScript mirror of the backend message schema
// (see backend/src/server/state_serializer.py). Every later stage extends
// these interfaces rather than replacing them.

export interface Geometry {
  x0: number;
  y0: number;
  dx: number;
  dy: number;
}

export interface NetworkRoad {
  id: number;
  length: number;
  geometry: Geometry;
  periodic: boolean;
  /** Street this road is a lane of, or null/absent for a standalone road. */
  street_id?: string | null;
  /** Position within its street's direction group, 0 = leftmost. */
  lane_index?: number;
}

export interface NetworkJunction {
  id: number;
  x: number;
  y: number;
}

// --- Multi-lane streets (backend Stage 9–12) --------------------------------
// A street groups parallel lanes that share a centreline. Lanes are ordinary
// roads; the grouping tells the renderer to draw ONE road surface with lane
// markings rather than N nearly-overlapping lines, and tells the UI which
// lanes a vehicle can change between.

export type LaneDirection = "forward" | "backward";

/** A street's centreline, in the same projected space as road geometry. */
export interface BaselineGeometry {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
}

export interface NetworkLane {
  road_id: number;
  lane_index: number;
  direction: LaneDirection;
  /** Adjacent lane ids, stated by the server so adjacency is never guessed. */
  left_road_id: number | null;
  right_road_id: number | null;
}

export interface NetworkStreet {
  id: string;
  /** Null for streets built by hand with no recorded centreline. */
  baseline: BaselineGeometry | null;
  lane_width: number;
  n_forward: number;
  n_backward: number;
  lanes: NetworkLane[];
}

export interface NetworkMessage {
  type: "network";
  config: string;
  roads: NetworkRoad[];
  junctions: NetworkJunction[];
  /**
   * Absent from a pre-Stage-12 server, and empty for a single-lane network.
   * Either way the renderer falls back to drawing roads independently.
   */
  streets?: NetworkStreet[];
}

export type VehicleType = "moto" | "car";

export interface VehicleDTO {
  f: number; // front cell index
  l: number; // footprint length in cells
  t: VehicleType;
}

export interface Segment {
  s: number; // start cell index
  n: number; // segment length in cells
  d: number; // congestion density 0..1
}

export interface StateRoad {
  id: number;
  cells: number[]; // occupancy 0/1
  vehicles: VehicleDTO[];
  segments: Segment[]; // per-segment congestion for the heatmap
}

export interface StateJunction {
  id: number;
  queue: number; // backup length (vehicles queued near this junction)
}

export type DisruptionKind =
  | "breakdown"
  | "tree"
  | "accident"
  | "flood"
  | "lock"
  | "parking";

export interface DisruptionDTO {
  id: number;
  kind: DisruptionKind;
  label: string;
  road_id: number;
  cells: number[];
  permanent: boolean;
  remaining: number;
}

export interface Analytics {
  density: number;
  flow: number;
  entropy: number; // normalised 0..1
  entropy_bits: number;
  blocked_fraction: number;
  avg_queue: number;
  landscape: Landscape;
  /** Lateral transfers on this step. Absent from a pre-Stage-12 server. */
  lane_changes?: number;
}

export type Landscape = "trivial" | "average" | "worst";

/** Whether a state came from the live tick loop or a batch run's result. */
export type SimulationMode = "live" | "batch";

export interface StateMessage {
  type: "state";
  step: number;
  running: boolean;
  steps_per_second: number;
  roads: StateRoad[];
  junctions: StateJunction[];
  disruptions: DisruptionDTO[];
  analytics: Analytics;
  // --- all optional: a pre-Stage-12 server sends none of them ---
  mode?: SimulationMode;
  lane_change_prob?: number;
  lane_changes?: number;
  rear_safety_gap?: number;
  lane_change_require_gain?: boolean;
}

/**
 * Payload for `set_lane_change_params`. Every field is optional: the server
 * applies only the keys present, leaving the rest untouched.
 */
export interface LaneChangeParams {
  probability?: number;
  rear_safety_gap?: number;
  require_gain?: boolean;
}

export interface PongMessage {
  type: "pong";
  t: number;
}

/** Sent by the backend in response to a save_scenario request. */
export interface ScenarioMessage {
  type: "scenario";
  data: unknown;
}

/** Sent by the backend after an import_region request (Stage 8). */
export interface ImportResultMessage {
  type: "import_result";
  ok: boolean;
  error?: string;
  roads?: number;
  junctions?: number;
  total_cells?: number;
  // --- Stage 12 street-level detail; absent from an older server ---
  streets?: number;
  /** Streets with more than one lane in a single direction. */
  multi_lane_streets?: number;
  max_lanes_per_direction?: number;
  two_way_streets?: number;
}

// --- Batch scenarios (backend Stage 10–12) ----------------------------------

/** One timed mutation applied during a batch run, before the step it names. */
export interface ScheduleEvent {
  step: number;
  action:
    | "trigger_disruption"
    | "clear_disruptions"
    | "block_cells"
    | "set_disruption_params"
    | "set_source_rate"
    | "set_lane_change_params";
  [field: string]: unknown;
}

export interface BatchOptions {
  steps: number;
  /** Scalar-analytics sampling stride. Defaults to every step. */
  record_every?: number;
  /** Vehicle-snapshot stride; 0 (default) = first, middle and final only. */
  snapshot_every?: number;
  include_segments?: boolean;
  schedule?: ScheduleEvent[];
}

/**
 * A batch request. Either a short config naming a builder, or a full saved
 * scenario (which carries a `roads` array), plus the `batch` block. A `seed`
 * is mandatory so the run reproduces.
 */
export interface ScenarioRequest {
  seed: number;
  batch: BatchOptions;
  config?: string;
  length?: number;
  density?: number;
  car_fraction?: number;
  lane_change_prob?: number;
  rear_safety_gap?: number;
  lane_change_require_gain?: boolean;
  build_kwargs?: Record<string, unknown>;
  [field: string]: unknown;
}

/** One row of the analytics trajectory — dense enough to plot time series. */
export interface TrajectoryRecord {
  step: number;
  density: number;
  flow: number;
  entropy: number;
  entropy_bits: number;
  blocked_fraction: number;
  avg_queue: number;
  landscape: Landscape;
  lane_changes: number;
  spawned: number;
  exited: number;
  vehicles: number;
}

/** Heavy per-road data, recorded only on snapshot steps. */
export interface ScenarioSnapshot {
  step: number;
  roads: Array<{
    id: number;
    vehicles: VehicleDTO[];
    segments?: Segment[];
  }>;
}

export interface ScenarioSummary {
  steps: number;
  records: number;
  peak_flow: number;
  mean_flow: number;
  /** Mean flow over the second half of the run: the steady-state estimate. */
  steady_state_flow: number;
  min_entropy: number;
  max_entropy: number;
  final_density: number;
  final_landscape: Landscape;
  peak_avg_queue: number;
  total_lane_changes: number;
  total_spawned: number;
  total_exited: number;
  events_fired: Array<Record<string, unknown>>;
  elapsed_seconds: number;
}

export interface ScenarioResultMessage {
  type: "scenario_result";
  mode: "batch";
  /** The finished world in the live `network` shape, ready to render. */
  network: NetworkMessage;
  /** The same world as a scenario dict — pass this to `load_scenario`. */
  final_state: unknown;
  trajectory: TrajectoryRecord[];
  snapshots: ScenarioSnapshot[];
  summary: ScenarioSummary;
}

/**
 * Known failure codes. The union keeps `string` open so an unrecognised code
 * from a newer server is still assignable rather than a compile error.
 */
export type ScenarioErrorCode =
  | "ALREADY_RUNNING"
  | "INVALID_CONFIG"
  | "OVERSIZED_REQUEST"
  | "INTERNAL_ERROR"
  | (string & {});

export interface ScenarioErrorMessage {
  type: "scenario_error";
  code: ScenarioErrorCode;
  message: string;
  /** Legacy alias for `message`, kept by the server for older clients. */
  error?: string;
}

export type ServerMessage =
  | NetworkMessage
  | StateMessage
  | PongMessage
  | ScenarioMessage
  | ImportResultMessage
  | ScenarioResultMessage
  | ScenarioErrorMessage;
