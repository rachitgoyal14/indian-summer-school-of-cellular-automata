// RoadRenderer.ts — PixiJS scene for the simulation, decoupled from React.
//
// Stage 3: renders multiple connected roads laid out in 2D (each cell at
// (x0 + k·dx, y0 + k·dy)), junctions as distinct nodes, and footprint-aware
// vehicles (motorbike = 1 cell, car = 2 cells) coloured and sized by type.
// Camera (scroll zoom toward cursor + drag pan) is a single container
// transform, and works across the whole network.
//
// Vehicle glyph pass: pre-rendered top-down vehicle silhouettes as textures,
// drawn via a pooled Sprite layer instead of re-drawing Graphics paths each
// tick. Roads get asphalt material and lane-marking dashes. Junctions get a
// crossroads icon instead of a plain diamond.

import { Application, Container, Graphics, Sprite, Texture } from "pixi.js";
import type { DisruptionKind, NetworkMessage, StateMessage } from "../types";

/** Result of mapping a canvas click in edit mode. */
export interface EditClick {
  gridX: number; // grid cell coords (for placing a new road)
  gridY: number;
  road: { roadId: number; cell: number } | null; // nearest road cell, if close
}

const CELL_SIZE = 14; // world px per cell
const COLORS = {
  background: 0x1a1a1a,  // tarmac dark
  road: 0x2e2e2e,        // bitumen surface — slightly lighter for material presence
  roadShoulder: 0x222222, // road shoulder — between bg and road
  laneMarking: 0x555548,  // lane dashes — warm subtle yellow-gray
  junction: 0xe8e4dd,     // chalk
  junctionEdge: 0x8c8478, // gravel
  moto: 0x4ecdc4,        // teal — visible on tarmac, distinct from amber
  motoGlow: 0x2a8a84,
  car: 0xf5a623,         // amber road-marking yellow
  carGlow: 0xa06b10,
  rulerTick: 0x444444,   // cell index ruler ticks
  rulerText: 0x666666,   // cell index ruler labels
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

/** Congestion colour ramp: green (free) → yellow → red (jammed). d ∈ [0,1]. */
function heatColor(d: number): number {
  const t = Math.max(0, Math.min(1, d));
  let r: number, g: number;
  if (t < 0.5) {
    // green → yellow
    r = Math.round(510 * t); // 0..255
    g = 200;
  } else {
    // yellow → red
    r = 255;
    g = Math.round(200 * (1 - (t - 0.5) * 2));
  }
  return (r << 16) | (g << 8) | 0x30;
}

// ----------------------------------------------------------------- vehicle shapes
// Draw vehicle silhouettes pointing RIGHT (+x direction) at a generous size,
// then generateTexture once. At draw time, Sprites are tinted + rotated.

/** Draw a top-down motorbike silhouette into a Graphics. 1 cell wide. */
function drawMotoShape(g: Graphics, cs: number) {
  // Motorbike pointing right: slim tapered body, two wheel hints.
  // Drawn at cs × cs bounding box, centered vertically.
  const cx = cs / 2;
  const cy = cs / 2;
  const bodyW = cs * 0.78;
  const bodyH = cs * 0.32;

  // body: tapered front, flatter rear
  g.moveTo(cx + bodyW * 0.5, cy)                        // nose (pointed)
    .lineTo(cx + bodyW * 0.15, cy - bodyH * 0.5)        // upper front
    .lineTo(cx - bodyW * 0.35, cy - bodyH * 0.45)       // upper mid
    .lineTo(cx - bodyW * 0.5, cy - bodyH * 0.3)         // upper rear
    .lineTo(cx - bodyW * 0.5, cy + bodyH * 0.3)         // lower rear
    .lineTo(cx - bodyW * 0.35, cy + bodyH * 0.45)       // lower mid
    .lineTo(cx + bodyW * 0.15, cy + bodyH * 0.5)        // lower front
    .closePath()
    .fill({ color: 0xffffff });

  // front wheel hint — small circle at front
  g.circle(cx + bodyW * 0.38, cy, bodyH * 0.22)
    .fill({ color: 0xcccccc });

  // rear wheel hint — small circle at rear
  g.circle(cx - bodyW * 0.42, cy, bodyH * 0.22)
    .fill({ color: 0xcccccc });
}

/** Draw a top-down car silhouette into a Graphics. Spans footprint × 1 cell. */
function drawCarShape(g: Graphics, cs: number, footprint: number) {
  // Car pointing right: wider body, windshield notch, asymmetric front/rear.
  const w = cs * footprint - 1; // total width of the multi-cell vehicle
  const h = cs * 0.72;         // wider than motorbike
  const cx = w / 2;
  const cy = cs / 2;

  // main body
  const noseX = cx + w * 0.48;
  const rearX = cx - w * 0.50;
  const topY = cy - h * 0.50;
  const botY = cy + h * 0.50;

  // body outline: rounded front, boxier rear
  g.moveTo(noseX, cy)                              // nose point (slightly rounded)
    .lineTo(noseX - w * 0.06, topY + h * 0.15)     // upper front curve
    .lineTo(cx + w * 0.20, topY)                    // hood top edge
    .lineTo(cx - w * 0.05, topY)                    // windshield top
    .lineTo(cx - w * 0.15, topY + h * 0.08)        // windshield notch step down
    .lineTo(cx - w * 0.15, topY)                    // roof top
    .lineTo(rearX + w * 0.05, topY + h * 0.05)     // rear top
    .lineTo(rearX, topY + h * 0.15)                 // rear upper corner
    .lineTo(rearX, botY - h * 0.15)                 // rear lower corner
    .lineTo(rearX + w * 0.05, botY - h * 0.05)     // rear bottom
    .lineTo(cx - w * 0.15, botY)                    // roof bottom
    .lineTo(cx - w * 0.15, botY - h * 0.08)        // windshield notch (bottom)
    .lineTo(cx - w * 0.05, botY)                    // windshield bottom
    .lineTo(cx + w * 0.20, botY)                    // hood bottom edge
    .lineTo(noseX - w * 0.06, botY - h * 0.15)     // lower front curve
    .closePath()
    .fill({ color: 0xffffff });

  // windshield line — dark notch
  g.moveTo(cx + w * 0.16, topY + h * 0.12)
    .lineTo(cx - w * 0.04, topY + h * 0.12)
    .lineTo(cx - w * 0.04, botY - h * 0.12)
    .lineTo(cx + w * 0.16, botY - h * 0.12)
    .closePath()
    .fill({ color: 0x888888, alpha: 0.5 });

  // rear window — smaller dark area
  g.moveTo(cx - w * 0.18, topY + h * 0.18)
    .lineTo(cx - w * 0.30, topY + h * 0.18)
    .lineTo(cx - w * 0.30, botY - h * 0.18)
    .lineTo(cx - w * 0.18, botY - h * 0.18)
    .closePath()
    .fill({ color: 0x888888, alpha: 0.4 });
}


// ----------------------------------------------------------------- junction icon
/** Draw a crossroads icon into a Graphics at given center. */
function drawJunctionIcon(g: Graphics, cx: number, cy: number, cs: number) {
  const arm = cs * 0.65;
  const thick = cs * 0.28;
  const half = thick / 2;

  // center circle
  g.circle(cx, cy, cs * 0.25)
    .fill({ color: COLORS.junction })
    .stroke({ color: COLORS.junctionEdge, width: 1 });

  // four arms (cross shape)
  // horizontal bar
  g.roundRect(cx - arm, cy - half, arm * 2, thick, 2)
    .fill({ color: COLORS.junction, alpha: 0.5 });
  // vertical bar
  g.roundRect(cx - half, cy - arm, thick, arm * 2, 2)
    .fill({ color: COLORS.junction, alpha: 0.5 });

  // small direction arrows at arm tips (subtle)
  const arrowSz = cs * 0.15;
  for (const [ax, ay, angle] of [
    [cx + arm - 1, cy, 0],           // right
    [cx - arm + 1, cy, Math.PI],     // left
    [cx, cy - arm + 1, -Math.PI/2],  // up
    [cx, cy + arm - 1, Math.PI/2],   // down
  ] as [number, number, number][]) {
    g.moveTo(ax + Math.cos(angle) * arrowSz, ay + Math.sin(angle) * arrowSz)
      .lineTo(ax + Math.cos(angle + 2.4) * arrowSz * 0.6, ay + Math.sin(angle + 2.4) * arrowSz * 0.6)
      .lineTo(ax + Math.cos(angle - 2.4) * arrowSz * 0.6, ay + Math.sin(angle - 2.4) * arrowSz * 0.6)
      .closePath()
      .fill({ color: COLORS.junctionEdge });
  }
}


export class RoadRenderer {
  readonly app: Application;
  private camera: Container;
  private roadLayer: Graphics;
  private heatmapLayer: Graphics;
  private disruptionLayer: Graphics;
  private junctionLayer: Graphics;
  private vehicleContainer: Container;
  private rulerLayer: Graphics;
  private network: NetworkMessage | null = null;
  private lastState: StateMessage | null = null;
  private heatmapEnabled = false;

  // pre-rendered vehicle textures (generated once)
  private motoTexture: Texture | null = null;
  private carTexture: Texture | null = null;

  // sprite pool for vehicles
  private vehicleSprites: Sprite[] = [];

  private dragging = false;
  private lastPointer = { x: 0, y: 0 };
  private downPos = { x: 0, y: 0 };
  private editClickHandler: ((loc: EditClick) => void) | null = null;

  private constructor(app: Application) {
    this.app = app;
    this.camera = new Container();
    this.roadLayer = new Graphics();
    // Layer order (bottom→top): road, heatmap tint, disruptions, junctions,
    // vehicles, ruler. So the heatmap tints the roadbed but disruption cells
    // (their explicit kind-colour) and vehicles always draw on top of it.
    this.heatmapLayer = new Graphics();
    this.disruptionLayer = new Graphics();
    this.junctionLayer = new Graphics();
    this.vehicleContainer = new Container();
    this.rulerLayer = new Graphics();
    this.camera.addChild(this.roadLayer);
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
  /** Pre-render vehicle silhouettes to textures (called once after app.init). */
  private generateVehicleTextures() {
    // Motorbike: draw at 4x CELL_SIZE for high quality, downscale via sprite
    const scale = 4;
    const cs = CELL_SIZE * scale;

    // Motorbike texture
    const motoG = new Graphics();
    drawMotoShape(motoG, cs);
    this.motoTexture = this.app.renderer.generateTexture({
      target: motoG,
      resolution: 1,
    });
    motoG.destroy();

    // Car texture (2-cell footprint)
    const carG = new Graphics();
    drawCarShape(carG, cs, 2);
    this.carTexture = this.app.renderer.generateTexture({
      target: carG,
      resolution: 1,
    });
    carG.destroy();
  }

  /** Get or create a pooled sprite. */
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

  /** Hide all unused pooled sprites. */
  private hideExtraSprites(usedCount: number) {
    for (let i = usedCount; i < this.vehicleSprites.length; i++) {
      this.vehicleSprites[i].visible = false;
    }
  }

  // ----------------------------------------------------------------- network
  setNetwork(network: NetworkMessage) {
    this.network = network;
    this.drawRoads();
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

  private drawRoads() {
    const g = this.roadLayer;
    g.clear();
    if (!this.network) return;

    for (const road of this.network.roads) {
      const { x0, y0, dx, dy } = road.geometry;
      const isHoriz = Math.abs(dx) >= Math.abs(dy);

      // ---- road shoulder (wider strip behind the cells for material presence) ----
      const shoulderPad = 3; // px of shoulder on each side
      const startWx = x0 * CELL_SIZE;
      const startWy = y0 * CELL_SIZE;
      const endWx = (x0 + (road.length - 1) * dx) * CELL_SIZE;
      const endWy = (y0 + (road.length - 1) * dy) * CELL_SIZE;

      if (isHoriz) {
        const minX = Math.min(startWx, endWx) - shoulderPad;
        const maxX = Math.max(startWx, endWx) + CELL_SIZE + shoulderPad;
        const baseY = startWy - shoulderPad;
        g.roundRect(minX, baseY, maxX - minX, CELL_SIZE + shoulderPad * 2, 3)
          .fill({ color: COLORS.roadShoulder });
      } else {
        const baseX = startWx - shoulderPad;
        const minY = Math.min(startWy, endWy) - shoulderPad;
        const maxY = Math.max(startWy, endWy) + CELL_SIZE + shoulderPad;
        g.roundRect(baseX, minY, CELL_SIZE + shoulderPad * 2, maxY - minY, 3)
          .fill({ color: COLORS.roadShoulder });
      }

      // ---- cell tiles (the actual road surface) ----
      for (let k = 0; k < road.length; k++) {
        const wx = (x0 + k * dx) * CELL_SIZE;
        const wy = (y0 + k * dy) * CELL_SIZE;
        g.rect(wx, wy, CELL_SIZE - 1, CELL_SIZE - 1)
          .fill({ color: COLORS.road });
      }

      // ---- lane-marking dashes (every 4 cells) ----
      for (let k = 0; k < road.length; k++) {
        if (k % 4 !== 0) continue;
        const wx = (x0 + k * dx) * CELL_SIZE;
        const wy = (y0 + k * dy) * CELL_SIZE;
        if (isHoriz) {
          // horizontal road: short vertical dash at left edge of cell
          const dashH = CELL_SIZE * 0.3;
          const dashW = 2;
          g.rect(wx - 0.5, wy + (CELL_SIZE - dashH) / 2, dashW, dashH)
            .fill({ color: COLORS.laneMarking, alpha: 0.5 });
        } else {
          // vertical road: short horizontal dash at top edge of cell
          const dashW = CELL_SIZE * 0.3;
          const dashH = 2;
          g.rect(wx + (CELL_SIZE - dashW) / 2, wy - 0.5, dashW, dashH)
            .fill({ color: COLORS.laneMarking, alpha: 0.5 });
        }
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
      drawJunctionIcon(g, cxp, cyp, CELL_SIZE);
    }
  }

  /** Draw a thin cell-index ruler along the top edge of road 0. */
  private drawRuler() {
    const g = this.rulerLayer;
    g.clear();
    if (!this.network || this.network.roads.length === 0) return;

    const road = this.network.roads[0];
    const { x0, y0, dx, dy } = road.geometry;
    const isHoriz = Math.abs(dx) >= Math.abs(dy);

    // ticks every 10 cells, labels every 20
    for (let k = 0; k < road.length; k += 10) {
      const wx = (x0 + k * dx) * CELL_SIZE + CELL_SIZE / 2;
      const wy = (y0 + k * dy) * CELL_SIZE;

      if (isHoriz) {
        // tick above the road
        const tickTop = wy - 10;
        const tickH = k % 20 === 0 ? 6 : 3;
        g.moveTo(wx, tickTop).lineTo(wx, tickTop + tickH)
          .stroke({ color: COLORS.rulerTick, width: 0.8 });
      } else {
        // tick to the left of the road
        const tickLeft = wx - 10;
        const tickW = k % 20 === 0 ? 6 : 3;
        g.moveTo(tickLeft, wy + CELL_SIZE / 2).lineTo(tickLeft + tickW, wy + CELL_SIZE / 2)
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
        for (let k = seg.s; k < seg.s + seg.n; k++) {
          const wx = (x0 + k * dx) * CELL_SIZE;
          const wy = (y0 + k * dy) * CELL_SIZE;
          g.rect(wx, wy, CELL_SIZE - 1, CELL_SIZE - 1).fill({
            color,
            alpha: 0.55,
          });
        }
      }
    }
  }

  // ----------------------------------------------------------------- state
  setState(state: StateMessage) {
    if (!this.network) return;
    this.lastState = state;
    const roadById = new Map(this.network.roads.map((r) => [r.id, r]));

    this.drawHeatmap();

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
            color: 0x1a1a1a,
          });
        }
      }
    }

    // ---- vehicles (sprite-based with pre-rendered silhouettes) ----
    let spriteIdx = 0;

    for (const road of state.roads) {
      const meta = roadById.get(road.id);
      if (!meta) continue;
      const { x0, y0, dx, dy } = meta.geometry;
      const L = meta.length;

      // Compute direction angle for this road
      const angle = Math.atan2(dy, dx);

      for (const v of road.vehicles) {
        const tex = v.t === "car" ? this.carTexture : this.motoTexture;
        const tint = v.t === "car" ? COLORS.car : COLORS.moto;
        const glowTint = v.t === "car" ? COLORS.carGlow : COLORS.motoGlow;

        if (!tex) continue;

        // Compute center position of the full vehicle footprint
        // front cell = v.f, footprint = v.l cells behind it
        const frontIdx = v.f;
        const rearOffset = v.l - 1;

        // For single-cell vehicles, center is just the front cell
        // For multi-cell, center is midpoint of front and rear
        let centerIdx = frontIdx - rearOffset / 2;
        // Handle ring wrapping for the center calculation
        if (meta.periodic && frontIdx - rearOffset < 0) {
          // vehicle wraps around the ring — compute via unwrapped then re-wrap
          const unwrappedRear = frontIdx - rearOffset;
          centerIdx = frontIdx - rearOffset / 2;
          if (unwrappedRear < 0) {
            centerIdx = ((centerIdx % L) + L) % L;
          }
        }

        const cx = (x0 + centerIdx * dx) * CELL_SIZE + CELL_SIZE / 2;
        const cy = (y0 + centerIdx * dy) * CELL_SIZE + CELL_SIZE / 2;

        // Glow sprite (slightly larger, dimmer)
        const glow = this.getSprite(spriteIdx++);
        glow.texture = tex;
        glow.tint = glowTint;
        glow.alpha = 0.4;
        glow.rotation = angle;
        glow.position.set(cx, cy);
        // Scale: texture was drawn at 4x, we want it to fit footprint cells
        const texScale = 1 / 4;
        const glowExtra = 1.15;
        glow.scale.set(texScale * glowExtra);

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
    canvas.addEventListener("wheel", (e: WheelEvent) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
      this.zoomAt(e.offsetX, e.offsetY, factor);
    });
    canvas.addEventListener("pointerdown", (e: PointerEvent) => {
      this.dragging = true;
      this.lastPointer = { x: e.offsetX, y: e.offsetY };
      this.downPos = { x: e.offsetX, y: e.offsetY };
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
      // a click (negligible movement) in edit mode → map to a location
      const moved = Math.hypot(e.offsetX - this.downPos.x, e.offsetY - this.downPos.y);
      if (moved < 6 && this.editClickHandler) {
        this.editClickHandler(this.mapClick(e.offsetX, e.offsetY));
      }
    };
    canvas.addEventListener("pointerup", endDrag);
    canvas.addEventListener("pointercancel", endDrag);
  }

  setEditClickHandler(fn: ((loc: EditClick) => void) | null) {
    this.editClickHandler = fn;
    this.app.canvas.style.cursor = fn ? "crosshair" : "default";
  }

  /** Map a screen click to grid coords + the nearest road cell (if close). */
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
    // only accept a road hit if within ~1.5 cells (in world units)
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

  /** Reset the camera so the whole network fits with a margin.
   *  BUG 1 FIX: ensures a minimum rendered cell size of 6px so vehicles
   *  are legible on first load — not just mathematically "fitting" into
   *  a sub-pixel line across the full canvas width.
   */
  fitToView() {
    const { minX, minY, maxX, maxY } = this.bounds();
    const w = this.app.renderer.width;
    const h = this.app.renderer.height;
    const margin = 60;
    const bw = Math.max(maxX - minX, CELL_SIZE);
    const bh = Math.max(maxY - minY, CELL_SIZE);
    // Scale that fits the entire network into the viewport
    const fitScale = Math.min((w - margin) / bw, (h - margin) / bh);
    // Minimum scale: each cell must render at least 6px wide on screen
    const minCellPx = 6;
    const minScale = minCellPx / CELL_SIZE;
    // Use the larger of fit-scale and min-legibility-scale,
    // clamped to reasonable bounds
    const s = Math.min(Math.max(Math.max(fitScale, minScale), 0.1), 6);
    this.camera.scale.set(s);
    // Center the network in the viewport
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
