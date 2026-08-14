// RoadRenderer.ts — PixiJS scene for the simulation, decoupled from React.
//
// Draws a top-down campus map: a flat ground plane, asphalt lane surfaces with
// painted markings, blocky vehicles oriented along their road, disruption
// markers, an optional density heatmap, and street-name labels.
//
// Themes are data (see theme.ts). Switching one recolours and redraws; it
// never touches the simulation or the camera.
//
// Multi-lane streets: the backend already offsets each lane's origin
// perpendicular to its street's centreline, and states the lane width in the
// same units as the geometry. So a lane is drawn at its own coordinates and
// `lane_width` converts directly to pixels — the renderer never guesses an
// offset, and the same code is correct for the procedural grid (units = cells)
// and an OSM import (units = metres).
//
// Camera: eased zoom/pan, scroll-zoom toward cursor, drag-pan, double-click
// zoom, keyboard (+/- zoom, 0 fit-to-view).

import { Application, Container, Graphics, Sprite, Text, Texture } from "pixi.js";
import type { NetworkMessage, NetworkRoad, NetworkStreet, StateMessage } from "../types";
import { DAY_THEME, DISRUPTION_COLORS, type Theme } from "./theme";

export { DISRUPTION_COLORS };

/** Result of mapping a canvas click in edit mode. */
export interface EditClick {
  gridX: number;
  gridY: number;
  road: { roadId: number; cell: number } | null;
}

const CELL_SIZE = 14; // world px per cell-length

/**
 * Lane width for a road that belongs to no street, in geometry units. Matches
 * the backend's 3.5 m lane over a 7.5 m cell, so a lone road is exactly as
 * wide as one lane of a street.
 */
const DEFAULT_LANE_UNITS = 3.5 / 7.5;

/**
 * Width of a road that belongs to no street. Nothing sits beside it, so it is
 * drawn a little wider than one lane to read as a drivable surface rather than
 * a hairline. Lanes of a street keep their true width, since anything wider
 * would overlap the lane next to it.
 */
const LONE_ROAD_UNITS = 0.8;

/** Below this camera scale, street-name labels are hidden as unreadable. */
const LABEL_MIN_SCALE = 0.5;
/** Labels also need this many pixels of road to sit on. */
const LABEL_MIN_ROAD_PX = 60;

/** Camera easing: fraction of the remaining distance covered per frame. */
const CAMERA_EASE = 0.22;

/** Congestion colour ramp: green (free) → yellow → red (jammed). d ∈ [0,1]. */
function heatColor(d: number): number {
  const t = Math.max(0, Math.min(1, d));
  let r: number, g: number;
  if (t < 0.5) {
    r = Math.round(510 * t);
    g = 200;
  } else {
    r = 255;
    g = Math.round(200 * (1 - (t - 0.5) * 2));
  }
  return (r << 16) | (g << 8) | 0x30;
}

// ----------------------------------------------------------------- vehicle art
// Vehicles are drawn once in white at high resolution and tinted per type, so
// a theme switch costs a tint change rather than a re-render.

/**
 * A blocky top-down vehicle: rounded body, a lighter leading half and a darker
 * trailing edge so the direction of travel is readable at a glance.
 * Drawn pointing +x; the sprite is rotated to the road's angle at draw time.
 */
function drawVehicle(g: Graphics, lengthPx: number, widthPx: number) {
  const r = Math.min(widthPx * 0.32, lengthPx * 0.22);
  g.roundRect(0, 0, lengthPx, widthPx, r).fill({ color: 0xffffff });

  // windshield: a band across the front third, marking the leading edge
  g.roundRect(lengthPx * 0.6, widthPx * 0.18, lengthPx * 0.22, widthPx * 0.64,
              r * 0.5)
    .fill({ color: 0xffffff, alpha: 0.55 });

  // top highlight / bottom shadow — reads as a block, not a flat rectangle
  g.roundRect(0, 0, lengthPx, widthPx * 0.22, r)
    .fill({ color: 0xffffff, alpha: 0.28 });
  g.roundRect(0, widthPx * 0.8, lengthPx, widthPx * 0.2, r)
    .fill({ color: 0x000000, alpha: 0.3 });
}

export class RoadRenderer {
  readonly app: Application;
  private camera: Container;
  private roadLayer: Graphics;
  private markingLayer: Graphics;
  private navGraphLayer: Graphics;
  private heatmapLayer: Graphics;
  private junctionLayer: Graphics;
  private disruptionLayer: Graphics;
  private vehicleContainer: Container;
  private labelContainer: Container;

  private theme: Theme = DAY_THEME;
  private network: NetworkMessage | null = null;
  private lastState: StateMessage | null = null;
  private heatmapEnabled = false;
  private navGraphEnabled = false;

  /** road id → the street it is a lane of, for width and marking lookups. */
  private streetOfRoad = new Map<number, NetworkStreet>();

  private motoTexture: Texture | null = null;
  private carTexture: Texture | null = null;
  private vehicleSprites: Sprite[] = [];
  private labels: Text[] = [];

  // Eased camera: the pointer sets a target, the ticker chases it.
  private target = { x: 0, y: 0, scale: 1 };
  private dragging = false;
  private lastPointer = { x: 0, y: 0 };
  private downPos = { x: 0, y: 0 };
  private editClickHandler: ((loc: EditClick) => void) | null = null;
  /** Extent of the last network, so an unchanged map keeps the user's view. */
  private lastExtent: string | null = null;

  private constructor(app: Application) {
    this.app = app;
    this.camera = new Container();
    this.roadLayer = new Graphics();
    this.markingLayer = new Graphics();
    this.navGraphLayer = new Graphics();
    this.heatmapLayer = new Graphics();
    this.junctionLayer = new Graphics();
    this.disruptionLayer = new Graphics();
    this.vehicleContainer = new Container();
    this.labelContainer = new Container();

    // Bottom → top. The heatmap tints the road bed and sits *under* the
    // markings, disruptions and vehicles, so it can never hide them.
    this.camera.addChild(this.roadLayer);
    this.camera.addChild(this.heatmapLayer);
    this.camera.addChild(this.junctionLayer);
    this.camera.addChild(this.markingLayer);
    this.camera.addChild(this.navGraphLayer);
    this.camera.addChild(this.disruptionLayer);
    this.camera.addChild(this.vehicleContainer);
    this.camera.addChild(this.labelContainer);
    this.app.stage.addChild(this.camera);

    this.installCameraControls();
    this.app.ticker.add(() => this.stepCamera());
  }

  static async create(container: HTMLElement): Promise<RoadRenderer> {
    const app = new Application();
    await app.init({
      background: DAY_THEME.background,
      resizeTo: container,
      antialias: true,
      autoDensity: true,
      resolution: window.devicePixelRatio || 1,
    });
    container.appendChild(app.canvas);
    const renderer = new RoadRenderer(app);
    renderer.generateVehicleTextures();
    return renderer;
  }

  destroy() {
    this.motoTexture?.destroy(true);
    this.carTexture?.destroy(true);
    this.app.destroy(true, { children: true });
  }

  // ------------------------------------------------------------------ theme
  /**
   * Swap the palette and redraw. Deliberately does NOT refit the camera or
   * touch simulation state: a theme toggle must leave the user exactly where
   * they were looking.
   */
  setTheme(theme: Theme) {
    this.theme = theme;
    this.app.renderer.background.color = theme.background;
    this.drawRoads();
    this.drawJunctions();
    this.drawMarkings();
    this.drawNavGraph();
    this.drawHeatmap();
    this.drawLabels();
    if (this.lastState) this.setState(this.lastState);
  }

  getTheme(): Theme {
    return this.theme;
  }

  // --------------------------------------------------------------- textures
  private generateVehicleTextures() {
    const scale = 4; // supersample, then draw at 1/4 size
    const laneW = DEFAULT_LANE_UNITS * CELL_SIZE * scale;

    const motoG = new Graphics();
    drawVehicle(motoG, CELL_SIZE * scale * 0.92, laneW * 0.62);
    this.motoTexture = this.app.renderer.generateTexture({ target: motoG, resolution: 1 });
    motoG.destroy();

    const carG = new Graphics();
    drawVehicle(carG, CELL_SIZE * 2 * scale * 0.94, laneW * 0.8);
    this.carTexture = this.app.renderer.generateTexture({ target: carG, resolution: 1 });
    carG.destroy();
  }

  private getSprite(index: number): Sprite {
    if (index < this.vehicleSprites.length) {
      const s = this.vehicleSprites[index];
      s.visible = true;
      return s;
    }
    const s = new Sprite();
    s.anchor.set(0.5, 0.5);
    this.vehicleContainer.addChild(s);
    this.vehicleSprites.push(s);
    return s;
  }

  private hideExtraSprites(usedCount: number) {
    for (let i = usedCount; i < this.vehicleSprites.length; i++) {
      this.vehicleSprites[i].visible = false;
    }
  }

  // ----------------------------------------------------------------- network
  setNetwork(network: NetworkMessage) {
    this.network = network;
    this.streetOfRoad.clear();
    for (const street of network.streets ?? []) {
      for (const lane of street.lanes) this.streetOfRoad.set(lane.road_id, street);
    }
    this.drawRoads();
    this.drawJunctions();
    this.drawMarkings();
    this.drawNavGraph();
    this.drawLabels();
    this.heatmapLayer.clear();
    this.disruptionLayer.clear();
    this.hideExtraSprites(0);

    // Refit only when the map itself changed shape — a config switch, a
    // region import, a road added. Promoting a scenario's final state or
    // resetting the density sends the same extent back, and refitting there
    // would yank the view out from under the user for no reason.
    const b = this.bounds();
    const extent = [b.minX, b.minY, b.maxX, b.maxY]
      .map((n) => Math.round(n)).join(",");
    if (extent !== this.lastExtent) {
      this.lastExtent = extent;
      this.fitToView();
    }
  }

  setHeatmapEnabled(enabled: boolean) {
    this.heatmapEnabled = enabled;
    this.drawHeatmap();
  }

  setNavGraphEnabled(enabled: boolean) {
    this.navGraphEnabled = enabled;
    this.drawNavGraph();
  }

  // ------------------------------------------------------------- geometry
  /** A lane's painted width in pixels. */
  private laneWidthPx(road: NetworkRoad): number {
    const street = this.streetOfRoad.get(road.id);
    const units = street && street.lane_width > 0 ? street.lane_width : DEFAULT_LANE_UNITS;
    return Math.max(units * CELL_SIZE, 3);
  }

  /** Endpoints of a road's painted surface, in world pixels. */
  private roadEnds(road: NetworkRoad) {
    const { x0, y0, dx, dy } = road.geometry;
    return {
      p0x: (x0 + 0.5 * dx) * CELL_SIZE,
      p0y: (y0 + 0.5 * dy) * CELL_SIZE,
      p1x: (x0 + (road.length - 0.5) * dx) * CELL_SIZE,
      p1y: (y0 + (road.length - 0.5) * dy) * CELL_SIZE,
    };
  }

  /** Unit vector 90° to the right of a road's heading. */
  private static perp(dx: number, dy: number): [number, number] {
    const len = Math.hypot(dx, dy);
    return len < 1e-9 ? [0, 0] : [-dy / len, dx / len];
  }

  // ------------------------------------------------------------ road surface
  private drawRoads() {
    const g = this.roadLayer;
    g.clear();
    if (!this.network) return;

    const roadById = new Map(this.network.roads.map((r) => [r.id, r]));
    const inStreet = new Set<number>();

    // A street is ONE piece of asphalt carrying all its lanes, so it is drawn
    // as a single slab down the centreline. Drawing each lane separately would
    // leave hairline seams between them and make the street read as N ribbons.
    for (const street of this.network.streets ?? []) {
      const lanes = street.lanes
        .map((l) => roadById.get(l.road_id))
        .filter((r): r is NetworkRoad => !!r);
      if (!lanes.length) continue;
      for (const r of lanes) inStreet.add(r.id);

      const width = this.laneWidthPx(lanes[0]) * lanes.length;
      const ends = this.streetEnds(street, lanes[0]);
      g.moveTo(ends.p0x, ends.p0y).lineTo(ends.p1x, ends.p1y)
        .stroke({ color: this.theme.road, width, cap: "butt", join: "round" });
    }

    for (const road of this.network.roads) {
      if (inStreet.has(road.id)) continue;
      const { p0x, p0y, p1x, p1y } = this.roadEnds(road);
      g.moveTo(p0x, p0y).lineTo(p1x, p1y).stroke({
        color: this.theme.road,
        width: LONE_ROAD_UNITS * CELL_SIZE,
        cap: "butt",
        join: "round",
      });
    }
  }

  /**
   * A street's painted extent. Prefers its recorded centreline; falls back to
   * a lane's own geometry for streets built without one.
   */
  private streetEnds(street: NetworkStreet, lane: NetworkRoad) {
    if (street.baseline) {
      const b = street.baseline;
      const [ux, uy] = RoadRenderer.perp(b.y0 - b.y1, b.x1 - b.x0); // along
      const inset = 0.5 * CELL_SIZE * 0;
      return {
        p0x: b.x0 * CELL_SIZE + ux * inset, p0y: b.y0 * CELL_SIZE + uy * inset,
        p1x: b.x1 * CELL_SIZE - ux * inset, p1y: b.y1 * CELL_SIZE - uy * inset,
      };
    }
    return this.roadEnds(lane);
  }

  // --------------------------------------------------------------- markings
  /**
   * Painted lines, drawn on the road surface:
   *   - dashed centre line between adjacent lanes going the same way,
   *   - a solid median between the two directions of a street,
   *   - a solid edge line down each outer side of a street.
   * A road with no street gets edge lines only — there is nothing to divide.
   */
  private drawMarkings() {
    const g = this.markingLayer;
    g.clear();
    if (!this.network) return;

    const roadById = new Map(this.network.roads.map((r) => [r.id, r]));
    const inStreet = new Set<number>();

    for (const street of this.network.streets ?? []) {
      const lanes = street.lanes
        .map((l) => ({ lane: l, road: roadById.get(l.road_id) }))
        .filter((e): e is { lane: typeof e.lane; road: NetworkRoad } => !!e.road);
      if (!lanes.length) continue;
      for (const e of lanes) inStreet.add(e.road.id);

      const wPx = this.laneWidthPx(lanes[0].road);

      // A divider between two neighbouring lanes sits on the boundary they
      // share: half a lane to the right of the left-hand one.
      for (const { lane, road } of lanes) {
        if (lane.right_road_id === null) continue;
        this.strokeOffset(g, road, wPx / 2, {
          color: this.theme.centerLine, width: 1.1, alpha: 0.95, dashed: true,
        });
      }

      // Median: between the innermost forward lane and the oncoming side.
      const forward = lanes.filter((e) => e.lane.direction === "forward");
      const backward = lanes.filter((e) => e.lane.direction === "backward");
      if (forward.length && backward.length) {
        const innermost = forward[forward.length - 1];
        this.strokeOffset(g, innermost.road, wPx / 2, {
          color: this.theme.median, width: 1.0, alpha: 1,
        });
        this.strokeOffset(g, innermost.road, wPx / 2 + 1.4, {
          color: this.theme.median, width: 1.0, alpha: 1,
        });
      }

      // Outer edges of the whole street.
      const leftMost = lanes[0];
      const rightMost = lanes[lanes.length - 1];
      this.strokeOffset(g, leftMost.road, -wPx / 2 + 0.4, {
        color: this.theme.edgeLine, width: 1.0, alpha: 0.9,
      });
      this.strokeOffset(g, rightMost.road, wPx / 2 - 0.4, {
        color: this.theme.edgeLine, width: 1.0, alpha: 0.9,
      });
    }

    // Roads that belong to no street: an edge line down each side.
    for (const road of this.network.roads) {
      if (inStreet.has(road.id)) continue;
      const half = (LONE_ROAD_UNITS * CELL_SIZE) / 2 - 0.4;
      for (const side of [-half, half]) {
        this.strokeOffset(g, road, side, {
          color: this.theme.edgeLine, width: 0.9, alpha: 0.75,
        });
      }
    }
  }

  /**
   * Stroke a line parallel to `road`, `offset` pixels to its right.
   * Dash length scales with the cell size so markings read at any zoom.
   */
  private strokeOffset(
    g: Graphics,
    road: NetworkRoad,
    offset: number,
    style: { color: number; width: number; alpha: number; dashed?: boolean },
  ) {
    const { p0x, p0y, p1x, p1y } = this.roadEnds(road);
    const [px, py] = RoadRenderer.perp(p1x - p0x, p1y - p0y);
    const ax = p0x + px * offset;
    const ay = p0y + py * offset;
    const bx = p1x + px * offset;
    const by = p1y + py * offset;

    if (!style.dashed) {
      g.moveTo(ax, ay).lineTo(bx, by)
        .stroke({ color: style.color, width: style.width, alpha: style.alpha });
      return;
    }

    const len = Math.hypot(bx - ax, by - ay);
    if (len < 1) return;
    const ux = (bx - ax) / len;
    const uy = (by - ay) / len;
    const dash = CELL_SIZE * 0.55;
    const gap = CELL_SIZE * 0.45;
    for (let t = 0; t < len; t += dash + gap) {
      const e = Math.min(t + dash, len);
      g.moveTo(ax + ux * t, ay + uy * t).lineTo(ax + ux * e, ay + uy * e)
        .stroke({ color: style.color, width: style.width, alpha: style.alpha });
    }
  }

  // -------------------------------------------------------------- junctions
  /**
   * Junctions are just paved area where roads meet — no node graphics. The pad
   * is sized from the widest lane touching it so it fills the intersection
   * without spilling onto the grass.
   */
  private drawJunctions() {
    const g = this.junctionLayer;
    g.clear();
    if (!this.network) return;

    let pad = DEFAULT_LANE_UNITS * CELL_SIZE;
    for (const road of this.network.roads) {
      const street = this.streetOfRoad.get(road.id);
      const lanes = street ? street.lanes.length : 1;
      pad = Math.max(pad, this.laneWidthPx(road) * lanes);
    }
    const r = pad * 0.62;

    for (const j of this.network.junctions) {
      const cx = j.x * CELL_SIZE + CELL_SIZE / 2;
      const cy = j.y * CELL_SIZE + CELL_SIZE / 2;
      g.rect(cx - r, cy - r, r * 2, r * 2).fill({ color: this.theme.junction });
    }
  }

  private drawNavGraph() {
    const g = this.navGraphLayer;
    g.clear();
    if (!this.navGraphEnabled || !this.network) return;

    for (const road of this.network.roads) {
      const { x0, y0, dx, dy } = road.geometry;
      const { p0x, p0y, p1x, p1y } = this.roadEnds(road);
      g.moveTo(p0x, p0y).lineTo(p1x, p1y)
        .stroke({ color: this.theme.navGraph, width: 2, alpha: 0.8 });
      for (let k = 0; k < road.length; k++) {
        const cx = (x0 + (k + 0.5) * dx) * CELL_SIZE;
        const cy = (y0 + (k + 0.5) * dy) * CELL_SIZE;
        g.circle(cx, cy, 2).fill({ color: this.theme.navGraphNode, alpha: 0.9 });
      }
    }
  }

  // ---------------------------------------------------------------- heatmap
  /** Tints the road bed. Sits under markings, disruptions and vehicles. */
  private drawHeatmap() {
    const g = this.heatmapLayer;
    g.clear();
    if (!this.heatmapEnabled || !this.network || !this.lastState) return;
    const roadById = new Map(this.network.roads.map((r) => [r.id, r]));

    for (const road of this.lastState.roads) {
      const meta = roadById.get(road.id);
      if (!meta) continue;
      const { x0, y0, dx, dy } = meta.geometry;
      for (const seg of road.segments) {
        const p0x = (x0 + (seg.s + 0.5) * dx) * CELL_SIZE;
        const p0y = (y0 + (seg.s + 0.5) * dy) * CELL_SIZE;
        const p1x = (x0 + (seg.s + seg.n - 0.5) * dx) * CELL_SIZE;
        const p1y = (y0 + (seg.s + seg.n - 0.5) * dy) * CELL_SIZE;
        g.moveTo(p0x, p0y).lineTo(p1x, p1y).stroke({
          color: heatColor(seg.d),
          width: this.laneWidthPx(meta),
          alpha: this.theme.heatmapAlpha,
          cap: "butt",
        });
      }
    }
  }

  // ----------------------------------------------------------------- labels
  /**
   * Street names along their road, on a translucent pill so they stay legible
   * against grass. Shown only when the camera is zoomed in far enough that
   * they fit; hidden entirely when zoomed out.
   */
  private drawLabels() {
    for (const t of this.labels) t.visible = false;
    if (!this.network) return;

    const scale = this.camera.scale.x;
    if (scale < LABEL_MIN_SCALE) return;

    // one label per named street (or per named road, if it has no street)
    const seen = new Set<string>();
    let i = 0;

    for (const road of this.network.roads) {
      const name = road.name?.trim();
      if (!name) continue;
      const key = road.street_id ?? `road:${road.id}`;
      if (seen.has(key)) continue;

      const { p0x, p0y, p1x, p1y } = this.roadEnds(road);
      if (Math.hypot(p1x - p0x, p1y - p0y) * scale < LABEL_MIN_ROAD_PX) continue;
      seen.add(key);

      const label = this.getLabel(i++);
      label.text = name;
      label.style.fill = this.theme.label;
      label.position.set((p0x + p1x) / 2, (p0y + p1y) / 2);
      // keep text upright and at a constant on-screen size
      label.scale.set(1 / scale);
      let angle = Math.atan2(p1y - p0y, p1x - p0x);
      if (angle > Math.PI / 2 || angle < -Math.PI / 2) angle += Math.PI;
      label.rotation = angle;
      label.visible = true;
    }
  }

  private getLabel(index: number): Text {
    if (index < this.labels.length) return this.labels[index];
    const t = new Text({
      text: "",
      style: {
        fontFamily: "system-ui, sans-serif",
        fontSize: 11,
        fill: this.theme.label,
        // a soft halo does the job of a pill background at a fraction of the
        // cost, and never boxes in a rotated label
        stroke: { color: this.theme.labelBackdrop, width: 3, join: "round" },
      },
    });
    t.anchor.set(0.5, 0.5);
    this.labelContainer.addChild(t);
    this.labels.push(t);
    return t;
  }

  // ------------------------------------------------------------------ state
  setState(state: StateMessage) {
    if (!this.network) return;
    this.lastState = state;
    const roadById = new Map(this.network.roads.map((r) => [r.id, r]));

    this.drawHeatmap();
    this.drawDisruptions(roadById);

    let spriteIdx = 0;
    for (const road of state.roads) {
      const meta = roadById.get(road.id);
      if (!meta) continue;
      const { x0, y0, dx, dy } = meta.geometry;
      const L = meta.length;
      const angle = Math.atan2(dy, dx);
      // scale the sprite so a vehicle always fills its own lane
      const laneScale = this.laneWidthPx(meta) / (DEFAULT_LANE_UNITS * CELL_SIZE);

      for (const v of road.vehicles) {
        const tex = v.t === "car" ? this.carTexture : this.motoTexture;
        if (!tex) continue;

        let centerIdx = v.f - (v.l - 1) / 2;
        if (meta.periodic && v.f - (v.l - 1) < 0) {
          centerIdx = ((centerIdx % L) + L) % L;
        }
        const cx = (x0 + (centerIdx + 0.5) * dx) * CELL_SIZE;
        const cy = (y0 + (centerIdx + 0.5) * dy) * CELL_SIZE;

        const body = this.getSprite(spriteIdx++);
        body.texture = tex;
        body.tint = v.t === "car" ? this.theme.car : this.theme.moto;
        body.alpha = 1;
        body.rotation = angle;          // faces its direction of travel
        body.position.set(cx, cy);
        body.scale.set(laneScale / 4);  // /4 undoes the texture supersample
      }
    }
    this.hideExtraSprites(spriteIdx);
  }

  /**
   * Disruptions as markers on the road, not flat colour fills: a triangle for
   * a temporary incident, a bordered diamond for a permanent reservation.
   * Drawn above the heatmap so a jam can never hide the thing causing it.
   */
  private drawDisruptions(roadById: Map<number, NetworkRoad>) {
    const g = this.disruptionLayer;
    g.clear();
    if (!this.lastState) return;

    for (const dis of this.lastState.disruptions) {
      const meta = roadById.get(dis.road_id);
      if (!meta) continue;
      const { x0, y0, dx, dy } = meta.geometry;
      const color = DISRUPTION_COLORS[dis.kind] ?? 0xffffff;
      const r = Math.max(this.laneWidthPx(meta) * 0.75, CELL_SIZE * 0.42);

      for (const idx of dis.cells) {
        const cx = (x0 + (idx + 0.5) * dx) * CELL_SIZE;
        const cy = (y0 + (idx + 0.5) * dy) * CELL_SIZE;

        if (dis.permanent) {
          // diamond + border: infrastructure, not an incident
          g.moveTo(cx, cy - r).lineTo(cx + r, cy).lineTo(cx, cy + r)
            .lineTo(cx - r, cy).closePath()
            .fill({ color })
            .stroke({ color: this.theme.disruptionOutline, width: 1, alpha: 0.9 });
        } else {
          // upward triangle: hazard
          g.moveTo(cx, cy - r).lineTo(cx + r * 0.92, cy + r * 0.7)
            .lineTo(cx - r * 0.92, cy + r * 0.7).closePath()
            .fill({ color })
            .stroke({ color: this.theme.disruptionOutline, width: 1, alpha: 0.9 });
        }
      }
    }
  }

  // ----------------------------------------------------------------- camera
  /** Chase the target each frame, so zoom and pan glide instead of snapping. */
  private stepCamera() {
    const c = this.camera;
    const ds = this.target.scale - c.scale.x;
    const dx = this.target.x - c.x;
    const dy = this.target.y - c.y;
    if (Math.abs(ds) < 1e-4 && Math.abs(dx) < 0.2 && Math.abs(dy) < 0.2) {
      if (ds !== 0 || dx !== 0 || dy !== 0) {
        c.scale.set(this.target.scale);
        c.position.set(this.target.x, this.target.y);
        this.drawLabels();
      }
      return;
    }
    c.scale.set(c.scale.x + ds * CAMERA_EASE);
    c.x += dx * CAMERA_EASE;
    c.y += dy * CAMERA_EASE;
    this.drawLabels();
  }

  private installCameraControls() {
    const canvas = this.app.canvas;
    canvas.style.cursor = "grab";

    canvas.addEventListener("wheel", (e: WheelEvent) => {
      e.preventDefault();
      const raw = Math.abs(e.deltaY) > 50 ? 1.12 : 1.06;
      this.zoomAt(e.offsetX, e.offsetY, e.deltaY < 0 ? raw : 1 / raw);
    });

    canvas.addEventListener("pointerdown", (e: PointerEvent) => {
      this.dragging = true;
      this.lastPointer = { x: e.offsetX, y: e.offsetY };
      this.downPos = { x: e.offsetX, y: e.offsetY };
      canvas.setPointerCapture(e.pointerId);
      if (!this.editClickHandler) canvas.style.cursor = "grabbing";
    });

    canvas.addEventListener("pointermove", (e: PointerEvent) => {
      if (!this.dragging) return;
      // Dragging moves the camera directly: a grabbed map should track the
      // finger exactly, with no lag. Only zoom is eased.
      const mx = e.offsetX - this.lastPointer.x;
      const my = e.offsetY - this.lastPointer.y;
      this.camera.x += mx;
      this.camera.y += my;
      this.target.x += mx;
      this.target.y += my;
      this.lastPointer = { x: e.offsetX, y: e.offsetY };
    });

    const endDrag = (e: PointerEvent) => {
      this.dragging = false;
      try {
        canvas.releasePointerCapture(e.pointerId);
      } catch {
        /* already released */
      }
      canvas.style.cursor = this.editClickHandler ? "crosshair" : "grab";
      const moved = Math.hypot(e.offsetX - this.downPos.x, e.offsetY - this.downPos.y);
      if (moved < 6 && this.editClickHandler) {
        this.editClickHandler(this.mapClick(e.offsetX, e.offsetY));
      }
    };
    canvas.addEventListener("pointerup", endDrag);
    canvas.addEventListener("pointercancel", endDrag);

    canvas.addEventListener("dblclick", (e: MouseEvent) => {
      e.preventDefault();
      this.zoomAt(e.offsetX, e.offsetY, e.shiftKey ? 0.5 : 2);
    });

    canvas.tabIndex = 0;
    canvas.style.outline = "none";
    canvas.addEventListener("keydown", (e: KeyboardEvent) => {
      const w = this.app.renderer.width;
      const h = this.app.renderer.height;
      if (e.key === "=" || e.key === "+") this.zoomAt(w / 2, h / 2, 1.25);
      else if (e.key === "-" || e.key === "_") this.zoomAt(w / 2, h / 2, 1 / 1.25);
      else if (e.key === "0") this.fitToView();
    });
  }

  setEditClickHandler(fn: ((loc: EditClick) => void) | null) {
    this.editClickHandler = fn;
    this.app.canvas.style.cursor = fn ? "crosshair" : "grab";
  }

  private mapClick(sx: number, sy: number): EditClick {
    const scale = this.camera.scale.x;
    const worldX = (sx - this.camera.x) / scale;
    const worldY = (sy - this.camera.y) / scale;
    const gridX = Math.round(worldX / CELL_SIZE);
    const gridY = Math.round(worldY / CELL_SIZE);
    let best: { roadId: number; cell: number } | null = null;
    let bestDist = Infinity;
    if (this.network) {
      for (const road of this.network.roads) {
        const { x0, y0, dx, dy } = road.geometry;
        for (let k = 0; k < road.length; k++) {
          const cxp = (x0 + k * dx + 0.5) * CELL_SIZE;
          const cyp = (y0 + k * dy + 0.5) * CELL_SIZE;
          const d = Math.hypot(cxp - worldX, cyp - worldY);
          if (d < bestDist) {
            bestDist = d;
            best = { roadId: road.id, cell: k };
          }
        }
      }
    }
    return { gridX, gridY, road: best && bestDist < CELL_SIZE * 1.5 ? best : null };
  }

  zoomAt(sx: number, sy: number, factor: number) {
    // Zoom about the cursor, computed against the *target* so repeated wheel
    // ticks compose correctly instead of fighting the easing.
    const worldX = (sx - this.target.x) / this.target.scale;
    const worldY = (sy - this.target.y) / this.target.scale;
    const newScale = Math.min(20, Math.max(0.03, this.target.scale * factor));
    this.target.scale = newScale;
    this.target.x = sx - worldX * newScale;
    this.target.y = sy - worldY * newScale;
  }

  private bounds() {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    const acc = (wx: number, wy: number) => {
      minX = Math.min(minX, wx); minY = Math.min(minY, wy);
      maxX = Math.max(maxX, wx + CELL_SIZE); maxY = Math.max(maxY, wy + CELL_SIZE);
    };
    if (this.network) {
      for (const road of this.network.roads) {
        const { x0, y0, dx, dy } = road.geometry;
        acc(x0 * CELL_SIZE, y0 * CELL_SIZE);
        acc((x0 + (road.length - 1) * dx) * CELL_SIZE, (y0 + (road.length - 1) * dy) * CELL_SIZE);
      }
      for (const j of this.network.junctions) acc(j.x * CELL_SIZE, j.y * CELL_SIZE);
    }
    if (!isFinite(minX)) { minX = 0; minY = 0; maxX = CELL_SIZE; maxY = CELL_SIZE; }
    return { minX, minY, maxX, maxY };
  }

  /** Reset camera so the entire network fits comfortably. */
  fitToView(immediate = false) {
    const { minX, minY, maxX, maxY } = this.bounds();
    const w = this.app.renderer.width;
    const h = this.app.renderer.height;
    const margin = 80;
    const bw = Math.max(maxX - minX, CELL_SIZE);
    const bh = Math.max(maxY - minY, CELL_SIZE);
    // Fit must always fit: a large OSM import needs a much smaller scale than
    // the interactive zoom floor allows, so no minimum is applied here. The
    // floor lives in zoomAt, where it stops the user zooming into mush.
    const s = Math.min(Math.max((w - margin) / bw, 0.005),
                       Math.max((h - margin) / bh, 0.005), 6);
    this.target.scale = s;
    this.target.x = (w - bw * s) / 2 - minX * s;
    this.target.y = (h - bh * s) / 2 - minY * s;
    if (immediate) {
      this.camera.scale.set(s);
      this.camera.position.set(this.target.x, this.target.y);
      this.drawLabels();
    }
  }

  /** Centre the view on a world point at a given scale (eased). */
  focusOn(worldX: number, worldY: number, scale: number) {
    const w = this.app.renderer.width;
    const h = this.app.renderer.height;
    this.target.scale = Math.min(20, Math.max(0.005, scale));
    this.target.x = w / 2 - worldX * CELL_SIZE * this.target.scale;
    this.target.y = h / 2 - worldY * CELL_SIZE * this.target.scale;
  }

  /** Camera scale actually on screen — used by tests and the zoom readout. */
  getScale(): number {
    return this.camera.scale.x;
  }

  getVisibleCellRange(): { roadId: number; min: number; max: number } | null {
    if (!this.network || this.network.roads.length === 0) return null;
    const road = this.network.roads[0];
    const { x0, dx, dy } = road.geometry;
    const scale = this.camera.scale.x;
    const horizontal = Math.abs(dx) >= Math.abs(dy);
    const camPos = horizontal ? this.camera.x : this.camera.y;
    const span = horizontal ? this.app.renderer.width : this.app.renderer.height;
    const axis0 = horizontal ? x0 : road.geometry.y0;
    const step = horizontal ? dx : dy || 1;
    const worldLo = (0 - camPos) / scale;
    const worldHi = (span - camPos) / scale;
    const toK = (w: number) => (w / CELL_SIZE - axis0) / (step || 1) - 0.5;
    let kLo = Math.floor(toK(worldLo));
    let kHi = Math.ceil(toK(worldHi));
    if (kLo > kHi) [kLo, kHi] = [kHi, kLo];
    return {
      roadId: road.id,
      min: Math.max(0, Math.min(road.length - 1, kLo)),
      max: Math.max(0, Math.min(road.length - 1, kHi)),
    };
  }
}
