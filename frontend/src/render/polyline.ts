// polyline.ts — arc-length maths for curved roads.
//
// A curved road arrives as a chain of projected points. Everything the
// renderer needs from it — where cell k sits, which way a vehicle faces there,
// and where to paint a line parallel to it — is arc-length work, so it lives
// here rather than being re-derived in three places.

export type Pt = [number, number];

/** Cumulative distance at each vertex; last entry is the total length. */
export function cumulative(points: Pt[]): number[] {
  const acc = [0];
  for (let i = 1; i < points.length; i++) {
    acc.push(acc[i - 1] + Math.hypot(points[i][0] - points[i - 1][0],
                                     points[i][1] - points[i - 1][1]));
  }
  return acc;
}

/**
 * Point and tangent at fraction `t` (0..1) of the total arc length.
 *
 * Sampling by arc length rather than by vertex index is what keeps cells
 * evenly spaced around a bend: OSM nodes cluster where a road curves, so
 * walking vertices would bunch vehicles up exactly where the curve is
 * tightest.
 */
export function sampleAt(
  points: Pt[], acc: number[], t: number,
): { x: number; y: number; angle: number } {
  const total = acc[acc.length - 1];
  if (points.length < 2 || total <= 0) {
    const [x, y] = points[0] ?? [0, 0];
    return { x, y, angle: 0 };
  }
  const target = Math.max(0, Math.min(1, t)) * total;

  // binary search for the segment containing `target`
  let lo = 0, hi = acc.length - 1;
  while (lo + 1 < hi) {
    const mid = (lo + hi) >> 1;
    if (acc[mid] <= target) lo = mid; else hi = mid;
  }
  const segLen = acc[hi] - acc[lo] || 1;
  const f = (target - acc[lo]) / segLen;
  const [ax, ay] = points[lo];
  const [bx, by] = points[hi];
  return {
    x: ax + (bx - ax) * f,
    y: ay + (by - ay) * f,
    angle: Math.atan2(by - ay, bx - ax),
  };
}

/** A parallel copy of `points`, `dist` to the right of travel. */
export function offsetPath(points: Pt[], dist: number): Pt[] {
  if (points.length < 2 || dist === 0) return points;
  return points.map(([x, y], i) => {
    const [ax, ay] = points[Math.max(0, i - 1)];
    const [bx, by] = points[Math.min(points.length - 1, i + 1)];
    const len = Math.hypot(bx - ax, by - ay);
    if (len < 1e-9) return [x, y] as Pt;
    return [x - ((by - ay) / len) * dist, y + ((bx - ax) / len) * dist] as Pt;
  });
}

/** Pointwise mean of two equal-length paths — a street's centreline. */
export function midPath(a: Pt[], b: Pt[]): Pt[] {
  if (a.length !== b.length || a.length < 2) return a;
  return a.map(([x, y], i) => [(x + b[i][0]) / 2, (y + b[i][1]) / 2] as Pt);
}

/**
 * Resample a chain through a Catmull-Rom spline, `perSegment` points per
 * input segment. The curve passes exactly through every original node, so the
 * road still follows the surveyed centreline — it just stops having corners
 * at each one. Endpoints are duplicated so the first and last segments curve
 * like the rest.
 */
export function smooth(points: Pt[], perSegment = 6): Pt[] {
  if (points.length < 3) return points;
  const p = [points[0], ...points, points[points.length - 1]];
  const out: Pt[] = [];
  for (let i = 1; i < p.length - 2; i++) {
    const [x0, y0] = p[i - 1], [x1, y1] = p[i], [x2, y2] = p[i + 1], [x3, y3] = p[i + 2];
    for (let s = 0; s < perSegment; s++) {
      const t = s / perSegment, t2 = t * t, t3 = t2 * t;
      out.push([
        0.5 * ((2 * x1) + (-x0 + x2) * t + (2 * x0 - 5 * x1 + 4 * x2 - x3) * t2 + (-x0 + 3 * x1 - 3 * x2 + x3) * t3),
        0.5 * ((2 * y1) + (-y0 + y2) * t + (2 * y0 - 5 * y1 + 4 * y2 - y3) * t2 + (-y0 + 3 * y1 - 3 * y2 + y3) * t3),
      ]);
    }
  }
  out.push(points[points.length - 1]);
  return out;
}
