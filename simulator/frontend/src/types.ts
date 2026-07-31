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
}

export interface NetworkJunction {
  id: number;
  x: number;
  y: number;
}

export interface NetworkMessage {
  type: "network";
  config: string;
  roads: NetworkRoad[];
  junctions: NetworkJunction[];
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
}

export interface StateMessage {
  type: "state";
  step: number;
  running: boolean;
  steps_per_second: number;
  roads: StateRoad[];
  junctions: StateJunction[];
  disruptions: DisruptionDTO[];
  analytics: Analytics;
}

export interface PongMessage {
  type: "pong";
  t: number;
}

export type ServerMessage = NetworkMessage | StateMessage | PongMessage;
