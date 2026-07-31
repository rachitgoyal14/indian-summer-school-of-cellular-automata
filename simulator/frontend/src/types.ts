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

export interface NetworkMessage {
  type: "network";
  roads: NetworkRoad[];
  junctions: unknown[]; // Stage 3
}

export interface StateRoad {
  id: number;
  cells: number[]; // 0 = empty, 1 = vehicle (Stage 2)
}

export interface Analytics {
  density: number;
  flow: number;
}

export interface StateMessage {
  type: "state";
  step: number;
  running: boolean;
  steps_per_second: number;
  roads: StateRoad[];
  disruptions: unknown[]; // Stage 4
  analytics: Analytics;
}

export interface PongMessage {
  type: "pong";
  t: number;
}

export type ServerMessage = NetworkMessage | StateMessage | PongMessage;
