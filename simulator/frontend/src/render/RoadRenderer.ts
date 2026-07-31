// RoadRenderer.ts — PixiJS scene for the simulation, decoupled from React.
//
// Responsibilities:
//   - own a PixiJS Application (WebGL)
//   - draw static road geometry once per "network" message
//   - redraw vehicle occupancy each "state" message
//   - camera: scroll-wheel zoom (toward cursor) + drag pan, via a single
//     container transform (scale + position) — GPU-accelerated, the reason
//     PixiJS was chosen over a software renderer (plan.md §5)
//   - expose the visible cell-index range so the UI can prove the camera
//     never desyncs from the underlying road array (stages.md 2c)

import { Application, Container, Graphics } from "pixi.js";
import type { NetworkMessage, StateMessage } from "../types";

const CELL_SIZE = 14; // world px per cell
const COLORS = {
  background: 0x0f1420,
  road: 0x232c3d,
  roadEdge: 0x39465e,
  vehicle: 0x5cc8ff,
  vehicleGlow: 0x2b7fb8,
};

export class RoadRenderer {
  readonly app: Application;
  private camera: Container;
  private roadLayer: Graphics;
  private vehicleLayer: Graphics;
  private network: NetworkMessage | null = null;

  // camera drag state
  private dragging = false;
  private lastPointer = { x: 0, y: 0 };

  private constructor(app: Application) {
    this.app = app;
    this.camera = new Container();
    this.roadLayer = new Graphics();
    this.vehicleLayer = new Graphics();
    this.camera.addChild(this.roadLayer);
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
    this.fitToView();
  }

  private drawRoads() {
    const g = this.roadLayer;
    g.clear();
    if (!this.network) return;
    for (const road of this.network.roads) {
      const { x0, y0, dx, dy } = road.geometry;
      // Draw the road as a filled strip made of faint per-cell tiles so the
      // lane structure is legible even when empty.
      for (let k = 0; k < road.length; k++) {
        const wx = (x0 + k * dx) * CELL_SIZE;
        const wy = (y0 + k * dy) * CELL_SIZE;
        g.rect(wx, wy, CELL_SIZE - 1, CELL_SIZE - 1).fill({
          color: COLORS.road,
        });
      }
      // Edge outline for the whole segment.
      const ex = (x0 + road.length * dx) * CELL_SIZE;
      const ey = (y0 + road.length * dy) * CELL_SIZE;
      g.moveTo(x0 * CELL_SIZE, y0 * CELL_SIZE)
        .lineTo(ex, ey)
        .stroke({ color: COLORS.roadEdge, width: 1 });
    }
  }

  // ----------------------------------------------------------------- state
  setState(state: StateMessage) {
    if (!this.network) return;
    const geomById = new Map(this.network.roads.map((r) => [r.id, r.geometry]));
    const g = this.vehicleLayer;
    g.clear();
    for (const road of state.roads) {
      const geom = geomById.get(road.id);
      if (!geom) continue;
      const { x0, y0, dx, dy } = geom;
      for (let k = 0; k < road.cells.length; k++) {
        if (road.cells[k] === 0) continue;
        const wx = (x0 + k * dx) * CELL_SIZE;
        const wy = (y0 + k * dy) * CELL_SIZE;
        // soft glow underlay + crisp vehicle body
        g.rect(wx - 1, wy - 1, CELL_SIZE + 1, CELL_SIZE + 1).fill({
          color: COLORS.vehicleGlow,
          alpha: 0.5,
        });
        g.rect(wx + 1, wy + 1, CELL_SIZE - 3, CELL_SIZE - 3).fill({
          color: COLORS.vehicle,
        });
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
        /* pointer already released */
      }
    };
    canvas.addEventListener("pointerup", endDrag);
    canvas.addEventListener("pointercancel", endDrag);
  }

  /** Zoom by `factor` keeping the world point under (sx, sy) fixed on screen. */
  zoomAt(sx: number, sy: number, factor: number) {
    const worldX = (sx - this.camera.x) / this.camera.scale.x;
    const worldY = (sy - this.camera.y) / this.camera.scale.y;
    const newScale = Math.min(20, Math.max(0.05, this.camera.scale.x * factor));
    this.camera.scale.set(newScale);
    this.camera.x = sx - worldX * newScale;
    this.camera.y = sy - worldY * newScale;
  }

  /** Reset the camera so the whole network fits with a margin. */
  fitToView() {
    if (!this.network) return;
    let maxX = 1;
    let maxY = 1;
    for (const road of this.network.roads) {
      const { x0, y0, dx, dy } = road.geometry;
      maxX = Math.max(maxX, (x0 + road.length * dx) * CELL_SIZE);
      maxY = Math.max(maxY, (y0 + road.length * dy + 1) * CELL_SIZE);
    }
    const w = this.app.renderer.width;
    const h = this.app.renderer.height;
    const margin = 40;
    const scale = Math.min(
      (w - margin) / maxX,
      (h - margin) / Math.max(maxY, CELL_SIZE * 2),
    );
    this.camera.scale.set(Math.min(Math.max(scale, 0.05), 4));
    // center vertically, small left margin
    this.camera.x = margin / 2;
    this.camera.y = (h - maxY * this.camera.scale.y) / 2;
  }

  /**
   * Which cell indices of road 0 are currently within the viewport.
   * Used by the debug readout to prove the rendered range matches the array.
   */
  getVisibleCellRange(): { roadId: number; min: number; max: number } | null {
    if (!this.network || this.network.roads.length === 0) return null;
    const road = this.network.roads[0];
    const { x0, dx } = road.geometry;
    const scale = this.camera.scale.x;
    const worldLeft = (0 - this.camera.x) / scale;
    const worldRight = (this.app.renderer.width - this.camera.x) / scale;
    // world x of cell k center ≈ (x0 + k*dx + 0.5) * CELL_SIZE
    const toK = (wx: number) => (wx / CELL_SIZE - x0) / (dx || 1) - 0.5;
    let kLo = Math.floor(toK(worldLeft));
    let kHi = Math.ceil(toK(worldRight));
    if (kLo > kHi) [kLo, kHi] = [kHi, kLo];
    return {
      roadId: road.id,
      min: Math.max(0, Math.min(road.length - 1, kLo)),
      max: Math.max(0, Math.min(road.length - 1, kHi)),
    };
  }
}
