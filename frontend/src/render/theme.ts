// theme.ts — named colour schemes for the simulation canvas.
//
// Day is the default: a bright top-down campus map — grass, asphalt, painted
// lane markings — meant to read as a real place at a glance. Night is the
// original dark instrument-panel palette, kept for anyone who prefers it.
//
// A theme is data only. Switching one swaps colours and redraws; it never
// touches the simulation, the camera, or any geometry.

import type { DisruptionKind } from "../types";

export interface Theme {
  name: string;
  /** Ground the whole map sits on. */
  background: number;
  /** Drivable surface. */
  road: number;
  /** Slightly darker paving where roads meet. */
  junction: number;
  /** Painted markings. */
  centerLine: number;   // dashed lane divider
  edgeLine: number;     // solid outer edge / curb
  median: number;       // between opposing directions
  /** Masses that are not road. */
  building: number;
  parking: number;
  /** Vehicles. Type distinction is a feature here, so cars and motorbikes
   *  differ — the reference image uses uniform red. */
  car: number;
  moto: number;
  /** Lighter top / darker bottom edge, to read as a block not a rectangle. */
  vehicleHighlight: number;
  vehicleShadow: number;
  /** Overlay text (queue readouts, street names). */
  label: number;
  labelBackdrop: number;
  labelBackdropAlpha: number;
  /** Nav-graph debug overlay. */
  navGraph: number;
  navGraphNode: number;
  /** Disruption markers. Kept semantically identical across themes so a
   *  flood is always blue; only the outline changes for contrast. */
  disruptionOutline: number;
  /** Strength of the density heatmap tint over the road bed. */
  heatmapAlpha: number;
}

export const DISRUPTION_COLORS: Record<DisruptionKind, number> = {
  breakdown: 0xff6b6b,
  tree: 0x2f9e44,
  accident: 0xd6336c,
  flood: 0x1c7ed6,
  lock: 0x7048e8,
  parking: 0x5c7cfa,
};

// Reference palette. These are the exact values from Prof. Martinez's
// simulator; they are matched deliberately and should not be "improved"
// without checking against the reference first.
export const DAY_THEME: Theme = {
  name: "day",
  background: 0x008000,       // flat green — no gradient
  road: 0x808080,             // mid-grey asphalt
  junction: 0x707070,         // a shade darker: paved intersection
  centerLine: 0xffff00,       // bright yellow lane divider
  edgeLine: 0xffffff,         // white curb line
  median: 0xffff00,
  building: 0xd3d3d3,
  parking: 0x808080,          // bays are asphalt; their borders use centerLine
  car: 0xdc143c,              // crimson
  moto: 0xff6347,             // tomato
  vehicleHighlight: 0xffffff,
  vehicleShadow: 0x000000,
  label: 0x2b2b2b,
  labelBackdrop: 0xffffff,
  labelBackdropAlpha: 0.78,
  navGraph: 0xff9500,
  navGraphNode: 0xffcc00,
  disruptionOutline: 0x2b2b2b,
  heatmapAlpha: 0.5,
};

export const NIGHT_THEME: Theme = {
  name: "night",
  background: 0x1e1e1e,
  road: 0x505050,
  junction: 0x555555,
  centerLine: 0xb8963c,
  edgeLine: 0xcccccc,
  median: 0xb8963c,
  building: 0x3a3a3a,
  parking: 0x2f2f33,
  car: 0xf5a623,
  moto: 0x4ecdc4,
  vehicleHighlight: 0xffffff,
  vehicleShadow: 0x000000,
  label: 0xe6e6e6,
  labelBackdrop: 0x101010,
  labelBackdropAlpha: 0.7,
  navGraph: 0xff9500,
  navGraphNode: 0xffcc00,
  disruptionOutline: 0xf0f0f0,
  heatmapAlpha: 0.55,
};

export const THEMES: Record<string, Theme> = {
  day: DAY_THEME,
  night: NIGHT_THEME,
};

export type ThemeName = keyof typeof THEMES & string;
