// RoadRenderer.ts — PixiJS scene for the simulation, decoupled from React.
//
// Stage 3: renders multiple connected roads laid out in 2D (each cell at
// (x0 + k·dx, y0 + k·dy)), junctions as distinct nodes, and footprint-aware
// vehicles (motorbike = 1 cell, car = 2 cells) coloured and sized by type.
// Camera (scroll zoom toward cursor + drag pan) is a single container
// transform, and works across the whole network.

import { Application, Container, Graphics } from "pixi.js";
import type { DisruptionKind, NetworkMessage, StateMessage } from "../types";

const CELL_SIZE = 14; // world px per cell
const COLORS = {
  background: 0x0f1420,
  road: 0x232c3d,
  roadEdge: 0x39465e,
  junction: 0xcbd5e6,
  junctionEdge: 0x8a97ad,
  moto: 0x5cc8ff, // cyan
  motoGlow: 0x2b7fb8,
  car: 0xffb454, // amber — distinct hue AND longer footprint
  carGlow: 0xb87316,
};

// Each disruption kind gets a distinct colour so the user is never confused
// about which one they triggered (plan.md §8 point 3).
export const DISRUPTION_COLORS: Record<DisruptionKind, number> = {
  breakdown: 0xff6b6b, // red
  tree: 0x67d982, // green
  accident: 0xff2d55, // bright crimson
  flood: 0x3aa0ff, // blue
  lock: 0xb56bff, // purple
  parking: 0x9aa7bd, // slate
};

export class RoadRenderer {
  readonly app: Application;
  private camera: Container;
  private roadLayer: Graphics;
  private disruptionLayer: Graphics;
  private junctionLayer: Graphics;
  private vehicleLayer: Graphics;
  private network: NetworkMessage | null = null;

  private dragging = false;
  private lastPointer = { x: 0, y: 0 };

  private constructor(app: Application) {
    this.app = app;
    this.camera = new Container();
    this.roadLayer = new Graphics();
    this.disruptionLayer = new Graphics();
    this.junctionLayer = new Graphics();
    this.vehicleLayer = new Graphics();
    this.camera.addChild(this.roadLayer);
    this.camera.addChild(this.disruptionLayer);
    this.camera.addChild(this.junctionLayer);
    this.camera.addChild(this.vehicleLayer);
    this.app.stage.addChild(this.camera);
    this.installCameraControls();
  }

  static async create(container: HTMLElement): Promise<RoadRenderer> {
    const app = new Application();
    await app.init({
      background: COLORS.background,
      resizeTo: container,
      antialias: true,
      autoDensity: true,
      resolution: window.devicePixelRatio || 1,
    });
    container.appendChild(app.canvas);
    return new RoadRenderer(app);
  }

  destroy() {
    this.app.destroy(true, { children: true });
  }

  // ----------------------------------------------------------------- network
  setNetwork(network: NetworkMessage) {
    this.network = network;
    this.drawRoads();
    this.drawJunctions();
    this.disruptionLayer.clear();
    this.vehicleLayer.clear();
    this.fitToView();
  }

  private drawRoads() {
    const g = this.roadLayer;
    g.clear();
    if (!this.network) return;
    for (const road of this.network.roads) {
      const { x0, y0, dx, dy } = road.geometry;
      for (let k = 0; k < road.length; k++) {
        const wx = (x0 + k * dx) * CELL_SIZE;
        const wy = (y0 + k * dy) * CELL_SIZE;
        g.rect(wx, wy, CELL_SIZE - 1, CELL_SIZE - 1).fill({ color: COLORS.road });
      }
    }
  }

  private drawJunctions() {
    const g = this.junctionLayer;
    g.clear();
    if (!this.network) return;
    for (const j of this.network.junctions) {
      const cxp = j.x * CELL_SIZE + CELL_SIZE / 2;
      const cyp = j.y * CELL_SIZE + CELL_SIZE / 2;
      const r = CELL_SIZE * 0.9;
      // diamond node so junctions read as distinct from road cells
      g.moveTo(cxp, cyp - r)
        .lineTo(cxp + r, cyp)
        .lineTo(cxp, cyp + r)
        .lineTo(cxp - r, cyp)
        .closePath()
        .fill({ color: COLORS.junction })
        .stroke({ color: COLORS.junctionEdge, width: 1.5 });
    }
  }

  // ----------------------------------------------------------------- state
  setState(state: StateMessage) {
    if (!this.network) return;
    const roadById = new Map(this.network.roads.map((r) => [r.id, r]));

    // ---- disruptions (blocked cells), coloured by kind ----
    const d = this.disruptionLayer;
    d.clear();
    for (const dis of state.disruptions) {
      const meta = roadById.get(dis.road_id);
      if (!meta) continue;
      const { x0, y0, dx, dy } = meta.geometry;
      const color = DISRUPTION_COLORS[dis.kind] ?? 0xffffff;
      for (const idx of dis.cells) {
        const wx = (x0 + idx * dx) * CELL_SIZE;
        const wy = (y0 + idx * dy) * CELL_SIZE;
        d.rect(wx - 2, wy - 2, CELL_SIZE + 3, CELL_SIZE + 3).fill({
          color,
          alpha: 0.35,
        }); // glow halo
        d.rect(wx, wy, CELL_SIZE - 1, CELL_SIZE - 1).fill({ color });
        // permanent reservations get an inner marker so they read differently
        if (dis.permanent) {
          d.rect(wx + CELL_SIZE / 2 - 1, wy + 2, 2, CELL_SIZE - 5).fill({
            color: 0x0f1420,
          });
        }
      }
    }

    // ---- vehicles ----
    const g = this.vehicleLayer;
    g.clear();
    for (const road of state.roads) {
      const meta = roadById.get(road.id);
      if (!meta) continue;
      const { x0, y0, dx, dy } = meta.geometry;
      const L = meta.length;
      for (const v of road.vehicles) {
        const glow = v.t === "car" ? COLORS.carGlow : COLORS.motoGlow;
        const body = v.t === "car" ? COLORS.car : COLORS.moto;
        // draw each occupied cell of the footprint as a tile (robust to ring wrap)
        for (let k = 0; k < v.l; k++) {
          let idx = v.f - k;
          if (meta.periodic) idx = ((idx % L) + L) % L;
          else if (idx < 0 || idx >= L) continue;
          const wx = (x0 + idx * dx) * CELL_SIZE;
          const wy = (y0 + idx * dy) * CELL_SIZE;
          g.rect(wx - 1, wy - 1, CELL_SIZE + 1, CELL_SIZE + 1).fill({
            color: glow,
            alpha: 0.5,
          });
          g.rect(wx + 1, wy + 1, CELL_SIZE - 3, CELL_SIZE - 3).fill({
            color: body,
          });
        }
      }
    }
  }

  // ----------------------------------------------------------------- camera
  private installCameraControls() {
    const canvas = this.app.canvas;
    canvas.addEventListener("wheel", (e: WheelEvent) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
      this.zoomAt(e.offsetX, e.offsetY, factor);
    });
    canvas.addEventListener("pointerdown", (e: PointerEvent) => {
      this.dragging = true;
      this.lastPointer = { x: e.offsetX, y: e.offsetY };
      canvas.setPointerCapture(e.pointerId);
    });
    canvas.addEventListener("pointermove", (e: PointerEvent) => {
      if (!this.dragging) return;
      this.camera.x += e.offsetX - this.lastPointer.x;
      this.camera.y += e.offsetY - this.lastPointer.y;
      this.lastPointer = { x: e.offsetX, y: e.offsetY };
    });
    const endDrag = (e: PointerEvent) => {
      this.dragging = false;
      try {
        canvas.releasePointerCapture(e.pointerId);
      } catch {
        /* already released */
      }
    };
    canvas.addEventListener("pointerup", endDrag);
    canvas.addEventListener("pointercancel", endDrag);
  }

  zoomAt(sx: number, sy: number, factor: number) {
    const worldX = (sx - this.camera.x) / this.camera.scale.x;
    const worldY = (sy - this.camera.y) / this.camera.scale.y;
    const newScale = Math.min(20, Math.max(0.03, this.camera.scale.x * factor));
    this.camera.scale.set(newScale);
    this.camera.x = sx - worldX * newScale;
    this.camera.y = sy - worldY * newScale;
  }

  /** World-space bounding box over all roads + junctions (in px). */
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

  /** Reset the camera so the whole network fits with a margin. */
  fitToView() {
    const { minX, minY, maxX, maxY } = this.bounds();
    const w = this.app.renderer.width;
    const h = this.app.renderer.height;
    const margin = 50;
    const bw = Math.max(maxX - minX, CELL_SIZE);
    const bh = Math.max(maxY - minY, CELL_SIZE);
    const scale = Math.min((w - margin) / bw, (h - margin) / bh);
    const s = Math.min(Math.max(scale, 0.03), 6);
    this.camera.scale.set(s);
    // center the network in the viewport
    this.camera.x = (w - bw * s) / 2 - minX * s;
    this.camera.y = (h - bh * s) / 2 - minY * s;
  }

  /**
   * Which cell indices of road 0 are within the viewport — proves the camera
   * stays in sync with the underlying array (Stage 2c debug readout).
   */
  getVisibleCellRange(): { roadId: number; min: number; max: number } | null {
    if (!this.network || this.network.roads.length === 0) return null;
    const road = this.network.roads[0];
    const { x0, dx, dy } = road.geometry;
    const scale = this.camera.scale.x;
    // Project the road's principal axis. For horizontal roads use x; for
    // vertical use y. (dx,dy ∈ {-1,0,1}.)
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
