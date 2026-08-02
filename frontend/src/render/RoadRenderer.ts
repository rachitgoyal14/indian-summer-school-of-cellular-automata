// RoadRenderer.ts — PixiJS scene for the simulation, decoupled from React.
//
// Renders single-lane roads as realistic asphalt strips with gravel shoulders
// and white edge markings. Junctions are drawn as smooth asphalt pads.
// Vehicles (motorbike 1-cell, car 2-cell) are pre-rendered top-down sprites.
//
// Camera: scroll-zoom toward cursor, drag-pan with grab cursor, double-click
// zoom, and keyboard shortcuts (+/- zoom, 0 fit-to-view).

import { Application, Container, Graphics, Sprite, Texture } from "pixi.js";
import type { DisruptionKind, NetworkMessage, StateMessage } from "../types";

/** Result of mapping a canvas click in edit mode. */
export interface EditClick {
  gridX: number;
  gridY: number;
  road: { roadId: number; cell: number } | null;
}

const CELL_SIZE = 14; // world px per cell

// Road cross-section widths (world px)
const ROAD_WIDTH = CELL_SIZE + 2;       // main asphalt surface
const SHOULDER_WIDTH = ROAD_WIDTH + 5;  // gravel shoulder beneath asphalt
const EDGE_INSET = ROAD_WIDTH / 2 - 0.5;// offset for white edge lines from center

const COLORS = {
  background: 0x1e1e1e,   // dark ground — slightly warmer than pure black
  asphalt:    0x505050,    // main road surface — mid-gray asphalt
  shoulder:   0x3a3a3a,    // gravel shoulder — visible contrast
  edgeLine:   0xcccccc,    // white road-edge markings
  junctionPad:0x555555,    // intersection asphalt pad
  junctionRim:0x444444,    // subtle darker rim around junction pad
  moto:       0x4ecdc4,    // teal
  motoGlow:   0x2a8a84,
  car:        0xf5a623,    // amber
  carGlow:    0xa06b10,
  rulerTick:  0x444444,
  rulerText:  0x666666,
};

// Disruption colors
export const DISRUPTION_COLORS: Record<DisruptionKind, number> = {
  breakdown: 0xff6b6b,
  tree: 0x67d982,
  accident: 0xff2d55,
  flood: 0x3aa0ff,
  lock: 0xb56bff,
  parking: 0x9aa7bd,
};

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

// ----------------------------------------------------------------- vehicle shapes

/** Draw a top-down motorbike silhouette into a Graphics. 1 cell wide. */
function drawMotoShape(g: Graphics, cs: number) {
  const cx = cs / 2;
  const cy = cs / 2;
  const bodyW = cs * 0.78;
  const bodyH = cs * 0.32;

  g.moveTo(cx + bodyW * 0.5, cy)
    .lineTo(cx + bodyW * 0.15, cy - bodyH * 0.5)
    .lineTo(cx - bodyW * 0.35, cy - bodyH * 0.45)
    .lineTo(cx - bodyW * 0.5, cy - bodyH * 0.3)
    .lineTo(cx - bodyW * 0.5, cy + bodyH * 0.3)
    .lineTo(cx - bodyW * 0.35, cy + bodyH * 0.45)
    .lineTo(cx + bodyW * 0.15, cy + bodyH * 0.5)
    .closePath()
    .fill({ color: 0xffffff });

  g.circle(cx + bodyW * 0.38, cy, bodyH * 0.22)
    .fill({ color: 0xcccccc });
  g.circle(cx - bodyW * 0.42, cy, bodyH * 0.22)
    .fill({ color: 0xcccccc });
}

/** Draw a top-down car silhouette into a Graphics. Spans footprint × 1 cell. */
function drawCarShape(g: Graphics, cs: number, footprint: number) {
  const w = cs * footprint - 1;
  const h = cs * 0.72;
  const cx = w / 2;
  const cy = cs / 2;

  const noseX = cx + w * 0.48;
  const rearX = cx - w * 0.50;
  const topY = cy - h * 0.50;
  const botY = cy + h * 0.50;

  g.moveTo(noseX, cy)
    .lineTo(noseX - w * 0.06, topY + h * 0.15)
    .lineTo(cx + w * 0.20, topY)
    .lineTo(cx - w * 0.05, topY)
    .lineTo(cx - w * 0.15, topY + h * 0.08)
    .lineTo(cx - w * 0.15, topY)
    .lineTo(rearX + w * 0.05, topY + h * 0.05)
    .lineTo(rearX, topY + h * 0.15)
    .lineTo(rearX, botY - h * 0.15)
    .lineTo(rearX + w * 0.05, botY - h * 0.05)
    .lineTo(cx - w * 0.15, botY)
    .lineTo(cx - w * 0.15, botY - h * 0.08)
    .lineTo(cx - w * 0.05, botY)
    .lineTo(cx + w * 0.20, botY)
    .lineTo(noseX - w * 0.06, botY - h * 0.15)
    .closePath()
    .fill({ color: 0xffffff });

  g.moveTo(cx + w * 0.16, topY + h * 0.12)
    .lineTo(cx - w * 0.04, topY + h * 0.12)
    .lineTo(cx - w * 0.04, botY - h * 0.12)
    .lineTo(cx + w * 0.16, botY - h * 0.12)
    .closePath()
    .fill({ color: 0x888888, alpha: 0.5 });

  g.moveTo(cx - w * 0.18, topY + h * 0.18)
    .lineTo(cx - w * 0.30, topY + h * 0.18)
    .lineTo(cx - w * 0.30, botY - h * 0.18)
    .lineTo(cx - w * 0.18, botY - h * 0.18)
    .closePath()
    .fill({ color: 0x888888, alpha: 0.4 });
}


export class RoadRenderer {
  readonly app: Application;
  private camera: Container;
  private roadLayer: Graphics;
  private navGraphLayer: Graphics;
  private heatmapLayer: Graphics;
  private disruptionLayer: Graphics;
  private junctionLayer: Graphics;
  private vehicleContainer: Container;
  private rulerLayer: Graphics;
  private network: NetworkMessage | null = null;
  private lastState: StateMessage | null = null;
  private heatmapEnabled = false;
  private navGraphEnabled = false;

  private motoTexture: Texture | null = null;
  private carTexture: Texture | null = null;

  private vehicleSprites: Sprite[] = [];

  private dragging = false;
  private lastPointer = { x: 0, y: 0 };
  private downPos = { x: 0, y: 0 };
  private editClickHandler: ((loc: EditClick) => void) | null = null;

  private constructor(app: Application) {
    this.app = app;
    this.camera = new Container();
    this.roadLayer = new Graphics();
    this.navGraphLayer = new Graphics();
    this.heatmapLayer = new Graphics();
    this.disruptionLayer = new Graphics();
    this.junctionLayer = new Graphics();
    this.vehicleContainer = new Container();
    this.rulerLayer = new Graphics();

    // Layer order (bottom→top)
    this.camera.addChild(this.roadLayer);
    this.camera.addChild(this.navGraphLayer);
    this.camera.addChild(this.heatmapLayer);
    this.camera.addChild(this.disruptionLayer);
    this.camera.addChild(this.junctionLayer);
    this.camera.addChild(this.vehicleContainer);
    this.camera.addChild(this.rulerLayer);
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
    const renderer = new RoadRenderer(app);
    renderer.generateVehicleTextures();
    return renderer;
  }

  destroy() {
    this.motoTexture?.destroy(true);
    this.carTexture?.destroy(true);
    this.app.destroy(true, { children: true });
  }

  // ----------------------------------------------------------------- textures
  private generateVehicleTextures() {
    const scale = 4;
    const cs = CELL_SIZE * scale;

    const motoG = new Graphics();
    drawMotoShape(motoG, cs);
    this.motoTexture = this.app.renderer.generateTexture({
      target: motoG,
      resolution: 1,
    });
    motoG.destroy();

    const carG = new Graphics();
    drawCarShape(carG, cs, 2);
    this.carTexture = this.app.renderer.generateTexture({
      target: carG,
      resolution: 1,
    });
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
    this.drawRoads();
    this.drawNavGraph();
    this.drawJunctions();
    this.drawRuler();
    this.heatmapLayer.clear();
    this.disruptionLayer.clear();
    this.hideExtraSprites(0);
    this.fitToView();
  }

  setHeatmapEnabled(enabled: boolean) {
    this.heatmapEnabled = enabled;
    this.drawHeatmap();
  }

  setNavGraphEnabled(enabled: boolean) {
    this.navGraphEnabled = enabled;
    this.drawNavGraph();
  }

  // ----------------------------------------------------------------- road drawing
  // Layered cross-section for each road segment:
  //   1. Gravel shoulder (widest, dark)
  //   2. Asphalt surface (mid-gray)
  //   3. White edge markings (thin lines along both sides)
  private drawRoads() {
    const g = this.roadLayer;
    g.clear();
    if (!this.network) return;

    for (const road of this.network.roads) {
      const { x0, y0, dx, dy } = road.geometry;

      const p0x = (x0 + 0.5 * dx) * CELL_SIZE;
      const p0y = (y0 + 0.5 * dy) * CELL_SIZE;
      const p1x = (x0 + (road.length - 0.5) * dx) * CELL_SIZE;
      const p1y = (y0 + (road.length - 0.5) * dy) * CELL_SIZE;

      // 1. Gravel shoulder
      g.moveTo(p0x, p0y)
        .lineTo(p1x, p1y)
        .stroke({ color: COLORS.shoulder, width: SHOULDER_WIDTH, cap: "round", join: "round" });

      // 2. Asphalt surface
      g.moveTo(p0x, p0y)
        .lineTo(p1x, p1y)
        .stroke({ color: COLORS.asphalt, width: ROAD_WIDTH, cap: "round", join: "round" });

      // 3. White edge markings — thin solid lines along each edge
      const roadLen = Math.hypot(p1x - p0x, p1y - p0y);
      if (roadLen > 2) {
        const angle = Math.atan2(p1y - p0y, p1x - p0x);
        // Perpendicular unit vector
        const px = -Math.sin(angle);
        const py = Math.cos(angle);

        // Left edge line
        g.moveTo(p0x + px * EDGE_INSET, p0y + py * EDGE_INSET)
          .lineTo(p1x + px * EDGE_INSET, p1y + py * EDGE_INSET)
          .stroke({ color: COLORS.edgeLine, width: 0.8, alpha: 0.45 });

        // Right edge line
        g.moveTo(p0x - px * EDGE_INSET, p0y - py * EDGE_INSET)
          .lineTo(p1x - px * EDGE_INSET, p1y - py * EDGE_INSET)
          .stroke({ color: COLORS.edgeLine, width: 0.8, alpha: 0.45 });
      }
    }
  }

  private drawNavGraph() {
    const g = this.navGraphLayer;
    g.clear();
    if (!this.navGraphEnabled || !this.network) return;

    for (const road of this.network.roads) {
      const { x0, y0, dx, dy } = road.geometry;

      const p0x = (x0 + 0.5 * dx) * CELL_SIZE;
      const p0y = (y0 + 0.5 * dy) * CELL_SIZE;
      const p1x = (x0 + (road.length - 0.5) * dx) * CELL_SIZE;
      const p1y = (y0 + (road.length - 0.5) * dy) * CELL_SIZE;

      g.moveTo(p0x, p0y)
        .lineTo(p1x, p1y)
        .stroke({ color: 0xff9500, width: 2, alpha: 0.8 });

      for (let k = 0; k < road.length; k++) {
        const cx = (x0 + (k + 0.5) * dx) * CELL_SIZE;
        const cy = (y0 + (k + 0.5) * dy) * CELL_SIZE;
        g.circle(cx, cy, 2.5).fill({ color: 0xffcc00, alpha: 0.9 });
      }
    }
  }

  // ----------------------------------------------------------------- junctions
  // Draw a smooth asphalt pad at each junction — looks like a real intersection.
  private drawJunctions() {
    const g = this.junctionLayer;
    g.clear();
    if (!this.network) return;

    for (const j of this.network.junctions) {
      const cx = j.x * CELL_SIZE + CELL_SIZE / 2;
      const cy = j.y * CELL_SIZE + CELL_SIZE / 2;
      const pad = ROAD_WIDTH * 0.7;

      // Outer rim (gravel edge around the intersection)
      g.circle(cx, cy, pad + 2)
        .fill({ color: COLORS.junctionRim });

      // Main asphalt pad
      g.circle(cx, cy, pad)
        .fill({ color: COLORS.junctionPad });

      // Subtle center dot — helps visually locate the node
      g.circle(cx, cy, 2)
        .fill({ color: COLORS.edgeLine, alpha: 0.3 });
    }
  }

  /** Draw a thin cell-index ruler along the top edge of road 0. */
  private drawRuler() {
    const g = this.rulerLayer;
    g.clear();
    if (!this.navGraphEnabled || !this.network || this.network.roads.length === 0) return;

    const road = this.network.roads[0];
    const { x0, y0, dx, dy } = road.geometry;
    const isHoriz = Math.abs(dx) >= Math.abs(dy);

    for (let k = 0; k < road.length; k += 10) {
      const wx = (x0 + (k + 0.5) * dx) * CELL_SIZE;
      const wy = (y0 + (k + 0.5) * dy) * CELL_SIZE;

      if (isHoriz) {
        const tickTop = wy - 10;
        const tickH = k % 20 === 0 ? 6 : 3;
        g.moveTo(wx, tickTop).lineTo(wx, tickTop + tickH)
          .stroke({ color: COLORS.rulerTick, width: 0.8 });
      } else {
        const tickLeft = wx - 10;
        const tickW = k % 20 === 0 ? 6 : 3;
        g.moveTo(tickLeft, wy).lineTo(tickLeft + tickW, wy)
          .stroke({ color: COLORS.rulerTick, width: 0.8 });
      }
    }
  }

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
        const color = heatColor(seg.d);
        const p0x = (x0 + (seg.s + 0.5) * dx) * CELL_SIZE;
        const p0y = (y0 + (seg.s + 0.5) * dy) * CELL_SIZE;
        const p1x = (x0 + (seg.s + seg.n - 0.5) * dx) * CELL_SIZE;
        const p1y = (y0 + (seg.s + seg.n - 0.5) * dy) * CELL_SIZE;
        g.moveTo(p0x, p0y)
          .lineTo(p1x, p1y)
          .stroke({ color, width: CELL_SIZE - 2, alpha: 0.55, cap: "round" });
      }
    }
  }

  // ----------------------------------------------------------------- state
  setState(state: StateMessage) {
    if (!this.network) return;
    this.lastState = state;
    const roadById = new Map(this.network.roads.map((r) => [r.id, r]));

    this.drawHeatmap();

    // ---- disruptions ----
    const d = this.disruptionLayer;
    d.clear();
    for (const dis of state.disruptions) {
      const meta = roadById.get(dis.road_id);
      if (!meta) continue;
      const { x0, y0, dx, dy } = meta.geometry;
      const color = DISRUPTION_COLORS[dis.kind] ?? 0xffffff;
      for (const idx of dis.cells) {
        const cx = (x0 + (idx + 0.5) * dx) * CELL_SIZE;
        const cy = (y0 + (idx + 0.5) * dy) * CELL_SIZE;
        d.circle(cx, cy, CELL_SIZE * 0.55).fill({ color, alpha: 0.35 });
        d.circle(cx, cy, CELL_SIZE * 0.4).fill({ color });
        if (dis.permanent) {
          d.circle(cx, cy, CELL_SIZE * 0.15).fill({ color: 0x1a1a1a });
        }
      }
    }

    // ---- vehicles ----
    let spriteIdx = 0;

    for (const road of state.roads) {
      const meta = roadById.get(road.id);
      if (!meta) continue;
      const { x0, y0, dx, dy } = meta.geometry;
      const L = meta.length;
      const angle = Math.atan2(dy, dx);

      for (const v of road.vehicles) {
        const tex = v.t === "car" ? this.carTexture : this.motoTexture;
        const tint = v.t === "car" ? COLORS.car : COLORS.moto;
        const glowTint = v.t === "car" ? COLORS.carGlow : COLORS.motoGlow;

        if (!tex) continue;

        const frontIdx = v.f;
        const rearOffset = v.l - 1;
        let centerIdx = frontIdx - rearOffset / 2;
        if (meta.periodic && frontIdx - rearOffset < 0) {
          const unwrappedRear = frontIdx - rearOffset;
          centerIdx = frontIdx - rearOffset / 2;
          if (unwrappedRear < 0) {
            centerIdx = ((centerIdx % L) + L) % L;
          }
        }

        const cx = (x0 + (centerIdx + 0.5) * dx) * CELL_SIZE;
        const cy = (y0 + (centerIdx + 0.5) * dy) * CELL_SIZE;

        // Glow sprite
        const glow = this.getSprite(spriteIdx++);
        glow.texture = tex;
        glow.tint = glowTint;
        glow.alpha = 0.4;
        glow.rotation = angle;
        glow.position.set(cx, cy);
        const texScale = 1 / 4;
        glow.scale.set(texScale * 1.15);

        // Main body sprite
        const body = this.getSprite(spriteIdx++);
        body.texture = tex;
        body.tint = tint;
        body.alpha = 1;
        body.rotation = angle;
        body.position.set(cx, cy);
        body.scale.set(texScale);
      }
    }

    this.hideExtraSprites(spriteIdx);
  }

  // ----------------------------------------------------------------- camera
  private installCameraControls() {
    const canvas = this.app.canvas;

    // --- cursor: grab / grabbing ---
    canvas.style.cursor = "grab";

    // --- scroll zoom (toward cursor) ---
    canvas.addEventListener("wheel", (e: WheelEvent) => {
      e.preventDefault();
      // Smoother zoom: smaller step factor for trackpads / fine-grained scrolls
      const raw = Math.abs(e.deltaY) > 50 ? 1.12 : 1.06;
      const factor = e.deltaY < 0 ? raw : 1 / raw;
      this.zoomAt(e.offsetX, e.offsetY, factor);
    });

    // --- drag pan ---
    canvas.addEventListener("pointerdown", (e: PointerEvent) => {
      this.dragging = true;
      this.lastPointer = { x: e.offsetX, y: e.offsetY };
      this.downPos = { x: e.offsetX, y: e.offsetY };
      canvas.setPointerCapture(e.pointerId);
      if (!this.editClickHandler) canvas.style.cursor = "grabbing";
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
      canvas.style.cursor = this.editClickHandler ? "crosshair" : "grab";
      const moved = Math.hypot(e.offsetX - this.downPos.x, e.offsetY - this.downPos.y);
      if (moved < 6 && this.editClickHandler) {
        this.editClickHandler(this.mapClick(e.offsetX, e.offsetY));
      }
    };
    canvas.addEventListener("pointerup", endDrag);
    canvas.addEventListener("pointercancel", endDrag);

    // --- double-click: zoom in (shift+double-click: zoom out) ---
    canvas.addEventListener("dblclick", (e: MouseEvent) => {
      e.preventDefault();
      const factor = e.shiftKey ? 0.5 : 2;
      this.zoomAt(e.offsetX, e.offsetY, factor);
    });

    // --- keyboard: +/- zoom, 0 fit-to-view ---
    // Make canvas focusable so it receives key events
    canvas.tabIndex = 0;
    canvas.style.outline = "none";
    canvas.addEventListener("keydown", (e: KeyboardEvent) => {
      const w = this.app.renderer.width;
      const h = this.app.renderer.height;
      if (e.key === "=" || e.key === "+") {
        this.zoomAt(w / 2, h / 2, 1.25);
      } else if (e.key === "-" || e.key === "_") {
        this.zoomAt(w / 2, h / 2, 1 / 1.25);
      } else if (e.key === "0") {
        this.fitToView();
      }
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
    const road = best && bestDist < CELL_SIZE * 1.5 ? best : null;
    return { gridX, gridY, road };
  }

  zoomAt(sx: number, sy: number, factor: number) {
    const worldX = (sx - this.camera.x) / this.camera.scale.x;
    const worldY = (sy - this.camera.y) / this.camera.scale.y;
    const newScale = Math.min(20, Math.max(0.03, this.camera.scale.x * factor));
    this.camera.scale.set(newScale);
    this.camera.x = sx - worldX * newScale;
    this.camera.y = sy - worldY * newScale;
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
  fitToView() {
    const { minX, minY, maxX, maxY } = this.bounds();
    const w = this.app.renderer.width;
    const h = this.app.renderer.height;
    const margin = 80;
    const bw = Math.max(maxX - minX, CELL_SIZE);
    const bh = Math.max(maxY - minY, CELL_SIZE);
    const fitScale = Math.min((w - margin) / bw, (h - margin) / bh);
    const minCellPx = 6;
    const minScale = minCellPx / CELL_SIZE;
    const s = Math.min(Math.max(Math.max(fitScale, minScale), 0.1), 6);
    this.camera.scale.set(s);
    this.camera.x = (w - bw * s) / 2 - minX * s;
    this.camera.y = (h - bh * s) / 2 - minY * s;
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
