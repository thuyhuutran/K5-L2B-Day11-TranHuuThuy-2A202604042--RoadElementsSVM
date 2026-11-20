"""Pure-Python geometry used by the checker and the converters (no numpy needed)."""
from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

Point = tuple[float, float]
Interval = tuple[float, float]


# --------------------------------------------------------------------------- polylines
def _seg_closest(p: Point, a: Point, b: Point) -> tuple[float, float]:
    """Return (distance, t in [0,1]) of the closest point to p on segment ab."""
    ax, ay = a
    dx, dy = b[0] - ax, b[1] - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(p[0] - cx, p[1] - cy), t


def polyline_length(pts: Sequence[Point]) -> float:
    return sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))


def closest_on_polyline(p: Point, pts: Sequence[Point]) -> tuple[float, float]:
    """(distance, arc-length parameter s) of the closest point of polyline `pts` to p."""
    if len(pts) == 1:
        return math.dist(p, pts[0]), 0.0
    best_d, best_s, acc = math.inf, 0.0, 0.0
    for i in range(len(pts) - 1):
        seg = math.dist(pts[i], pts[i + 1])
        d, t = _seg_closest(p, pts[i], pts[i + 1])
        if d < best_d:
            best_d, best_s = d, acc + t * seg
        acc += seg
    return best_d, best_s


def resample(pts: Sequence[Point], step: float = 2.0) -> list[Point]:
    """Points every `step` px along the polyline, always including both ends."""
    if len(pts) < 2:
        return list(pts)
    out: list[Point] = [pts[0]]
    carry = 0.0
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        seg = math.dist(a, b)
        if seg == 0:
            continue
        s = step - carry
        while s <= seg:
            t = s / seg
            out.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
            s += step
        carry = seg - (s - step)
    if out[-1] != pts[-1]:
        out.append(pts[-1])
    return out


def mean_distance(sub: Sequence[Point], gt: Sequence[Point], step: float = 2.0) -> float:
    samples = resample(sub, step)
    return sum(closest_on_polyline(p, gt)[0] for p in samples) / max(1, len(samples))


def max_deviation(sub: Sequence[Point], gt: Sequence[Point], step: float = 2.0) -> float:
    """Largest distance from the submitted polyline (sampled every `step` px) to the GT polyline."""
    return max((closest_on_polyline(p, gt)[0] for p in resample(sub, step)), default=math.inf)


def offset_along_normal(pts: Sequence[Point], dist: float) -> list[Point]:
    """Translate a polyline by `dist` px along the unit normal of its first-to-last chord."""
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    L = math.hypot(x2 - x1, y2 - y1) or 1.0
    nx, ny = -(y2 - y1) / L, (x2 - x1) / L
    return [(x + nx * dist, y + ny * dist) for x, y in pts]


def x_at_y(pts: Sequence[Point], y: float) -> float | None:
    """Row-anchor target: x where the polyline crosses image row y (linear), or None."""
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        lo, hi = min(y1, y2), max(y1, y2)
        if lo <= y <= hi and y1 != y2:
            return x1 + (y - y1) * (x2 - x1) / (y2 - y1)
        if y1 == y2 == y:
            return (x1 + x2) / 2
    return None


# --------------------------------------------------------------------------- curves
def sample_bezier(vertices: Sequence[Point], types: str, n: int = 8) -> list[Point]:
    """Flatten a BDD100K poly2d (types 'L' vertex / 'C' cubic control point) into a polyline."""
    if not types or "C" not in types:
        return [tuple(map(float, v)) for v in vertices]
    out: list[Point] = [tuple(map(float, vertices[0]))]
    i = 0
    while i < len(vertices) - 1:
        if i + 3 < len(vertices) and types[i + 1 : i + 3] == "CC":
            p0, p1, p2, p3 = vertices[i : i + 4]
            for k in range(1, n + 1):
                t = k / n
                u = 1 - t
                out.append(
                    (
                        u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                        u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
                    )
                )
            i += 3
        else:
            out.append(tuple(map(float, vertices[i + 1])))
            i += 1
    return out


def convex_hull(points: Iterable[Point]) -> list[Point]:
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o: Point, a: Point, b: Point) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Point] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[Point] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


# --------------------------------------------------------------------------- polygons (scanline)
def _row_intervals(poly: Sequence[Point], y: float) -> list[Interval]:
    xs: list[float] = []
    n = len(poly)
    for i in range(n):
        (x1, y1), (x2, y2) = poly[i], poly[(i + 1) % n]
        if (y1 <= y < y2) or (y2 <= y < y1):
            xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
    xs.sort()
    return [(xs[k], xs[k + 1]) for k in range(0, len(xs) - 1, 2)]


def _merge(iv: list[Interval]) -> list[Interval]:
    iv = sorted(iv)
    out: list[Interval] = []
    for a, b in iv:
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def _length(iv: list[Interval]) -> float:
    return sum(b - a for a, b in iv)


def _intersect_len(a: list[Interval], b: list[Interval]) -> float:
    i = j = 0
    tot = 0.0
    while i < len(a) and j < len(b):
        lo, hi = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if hi > lo:
            tot += hi - lo
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return tot


def union_overlap(polys_a: Sequence[Sequence[Point]], polys_b: Sequence[Sequence[Point]], dy: float = 1.0) -> tuple[float, float, float]:
    """(area of union A, area of union B, area of A∩B), by scanline at row centres every `dy` px."""
    allp = [p for poly in list(polys_a) + list(polys_b) for p in poly]
    if not allp:
        return 0.0, 0.0, 0.0
    y0 = math.floor(min(p[1] for p in allp))
    y1 = math.ceil(max(p[1] for p in allp))
    area_a = area_b = inter = 0.0
    y = y0 + dy / 2
    while y < y1:
        ia = _merge([iv for poly in polys_a if len(poly) >= 3 for iv in _row_intervals(poly, y)])
        ib = _merge([iv for poly in polys_b if len(poly) >= 3 for iv in _row_intervals(poly, y)])
        area_a += _length(ia) * dy
        area_b += _length(ib) * dy
        inter += _intersect_len(ia, ib) * dy
        y += dy
    return area_a, area_b, inter


def polygon_iou_spill(gt: Sequence[Sequence[Point]], sub: Sequence[Sequence[Point]]) -> tuple[float, float]:
    """(IoU of the unions, spill = share of the submitted area that lies outside GT)."""
    ag, asub, inter = union_overlap(gt, sub)
    union = ag + asub - inter
    iou = 1.0 if union == 0 else inter / union
    spill = 0.0 if asub == 0 else (asub - inter) / asub
    return iou, spill


# --------------------------------------------------------------------------- boxes
def box_norm(pts: Sequence[Point]) -> tuple[float, float, float, float]:
    (x1, y1), (x2, y2) = pts[0], pts[1]
    return min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)


def box_iou(a: Sequence[Point], b: Sequence[Point]) -> float:
    ax1, ay1, ax2, ay2 = box_norm(a)
    bx1, by1, bx2, by2 = box_norm(b)
    iw, ih = max(0.0, min(ax2, bx2) - max(ax1, bx1)), max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return 0.0 if union <= 0 else inter / union


def box_height(pts: Sequence[Point]) -> float:
    _, y1, _, y2 = box_norm(pts)
    return y2 - y1
