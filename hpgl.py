#!/usr/bin/env python3
# HPGL parser, path manipulation, and optimization library.
# Coordinates are in HPGL machine units throughout (convert with mm2hpgl/hpgl2mm).
from __future__ import annotations

import re
import math
from typing import Callable, Optional


Point = tuple[float, float]
Path = list[Point]

HPGL_GOTO = "PU%s,%s;"
HPGL_CUTTO = "PD%s,%s;"
HPGL_CUTTO_STR = "PD%s;"
HPGL_INIT = "IN:;"          # colon variant for Cogi compatibility; parser accepts both IN and IN:
HPGL_SELECT_PEN = "SP%s;"
HPGL_PEN_ABSOLUTE = "PA;"

# HPGL standard: 1016 machine units per inch (≈ 40 units/mm).
def mm2hpgl(value: float) -> float:
    return value / 25.4 * 1016.0


def hpgl2mm(value: float) -> float:
    return round(value, 0) / 1016.0 * 25.4


def vecDot(a: Point, b: Point) -> float:
    return sum(map(lambda i: i[0] * i[1], zip(a, b)))


def vecLen(a: Point) -> float:
    return math.sqrt(vecDot(a, a))


def vecAngle(a: Point, b: Point, c: Point) -> float:
    v0 = (a[0] - b[0], a[1] - b[1])
    v1 = (c[0] - b[0], c[1] - b[1])
    if a == c:
        return 0
    r = vecDot(v0, v1) / (vecLen(v0) * vecLen(v1))
    if r >= -1 and r <= 1:  # clamp before acos: floating-point errors can push r slightly outside [-1, 1]
        return math.acos(r)
    return math.pi


def vecDist(a: Point, b: Point) -> float:
    return vecLen((a[0] - b[0], a[1] - b[1]))


def vecExtend(a: Point, b: Point, x: float) -> Point:
    return a[0] + x * (b[0] - a[0]), a[1] + x * (b[1] - a[1])


def _seg_intersect_t(p1: Point, p2: Point, p3: Point, p4: Point) -> Optional[float]:
    """Return t∈[0,1] where segment p1→p2 crosses segment p3→p4, or None."""
    dx = p2[0] - p1[0];  dy = p2[1] - p1[1]
    dx2 = p4[0] - p3[0]; dy2 = p4[1] - p3[1]
    denom = dx * dy2 - dy * dx2
    if abs(denom) < 1e-10:
        return None
    dx3 = p3[0] - p1[0]; dy3 = p3[1] - p1[1]
    t = (dx3 * dy2 - dy3 * dx2) / denom
    u = (dx3 * dy  - dy3 * dx)  / denom
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return t
    return None


def _line_bbox_clip(p1: Point, p2: Point,
                    x0: float, y0: float, x1: float, y1: float) -> Optional[tuple[Point, Point]]:
    """Clip the infinite line through p1→p2 to the axis-aligned bbox [x0,x1]×[y0,y1]."""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    t_min, t_max = -math.inf, math.inf
    if abs(dx) < 1e-10:
        if p1[0] < x0 or p1[0] > x1:
            return None
    else:
        ta, tb = (x0 - p1[0]) / dx, (x1 - p1[0]) / dx
        if ta > tb:
            ta, tb = tb, ta
        t_min = max(t_min, ta)
        t_max = min(t_max, tb)
    if abs(dy) < 1e-10:
        if p1[1] < y0 or p1[1] > y1:
            return None
    else:
        ta, tb = (y0 - p1[1]) / dy, (y1 - p1[1]) / dy
        if ta > tb:
            ta, tb = tb, ta
        t_min = max(t_min, ta)
        t_max = min(t_max, tb)
    if t_min >= t_max:
        return None
    return (p1[0] + t_min * dx, p1[1] + t_min * dy), \
           (p1[0] + t_max * dx, p1[1] + t_max * dy)


def _point_parity(p: Point, routes: list[Path]) -> int:
    """Return 1 if p is inside an odd number of path regions (even-odd rule), else 0.
    Casts a leftward ray from p and counts crossings with all route segments."""
    py = p[1] + 0.001  # tiny nudge avoids hitting vertices or horizontal segments exactly
    count = 0
    for path in routes:
        for a, b in zip(path, path[1:]):
            ay, by_ = a[1] - py, b[1] - py
            if (ay > 0) == (by_ > 0):
                continue  # segment doesn't straddle the ray's y level
            cx = a[0] + ay / (ay - by_) * (b[0] - a[0])
            if cx < p[0]:
                count += 1
    return count % 2


def _adaptive_clip(p1: Point, p2: Point, routes: list[Path]) -> list[tuple[Point, Point]]:
    """Split segment p1→p2 at every crossing with routes.
    Keep sub-segments whose midpoint lies outside all design paths (even-odd rule).
    Each midpoint is tested independently, avoiding cumulative parity corruption
    from odd crossings with open paths."""
    ts: list[float] = []
    for path in routes:
        for a, b in zip(path, path[1:]):
            t = _seg_intersect_t(p1, p2, a, b)
            if t is not None and 1e-9 < t < 1.0 - 1e-9:
                ts.append(t)
    ts.sort()
    deduped: list[float] = []
    for t in ts:
        if not deduped or t - deduped[-1] > 1e-6:
            deduped.append(t)
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    pts = [p1] + [(p1[0] + t * dx, p1[1] + t * dy) for t in deduped] + [p2]
    return [
        (pts[i], pts[i + 1])
        for i in range(len(pts) - 1)
        if _point_parity(((pts[i][0] + pts[i + 1][0]) / 2,
                          (pts[i][1] + pts[i + 1][1]) / 2), routes) == 0
    ]


def hpgl_goto(match):
    x = int(match.group(1))
    y = int(match.group(2))
    return HPGL_GOTO, (x, y)


def hpgl_pen_up(match):
    x = None
    y = None
    return HPGL_GOTO, (x, y)


def hpgl_cutto(match):
    x = int(match.group(1))
    y = int(match.group(2))
    return HPGL_CUTTO, (x, y)


def hpgl_cutto2(match):
    coords = list(map(int, match.groups()[0].split(",")))
    xy = list(zip(coords[0::2], coords[1::2]))
    return HPGL_CUTTO, xy


def hpgl_init(match):
    return HPGL_INIT, None


def hpgl_pen_absolute(match):
    return HPGL_PEN_ABSOLUTE, None


def hpgl_select_pen(match):
    pen = int(match.group(1))
    return HPGL_SELECT_PEN, (pen,)


def path_start_stop(path: Path) -> tuple[Point, Point]:
    return path[0], path[-1]


def path_center(path: Path) -> tuple[Point, Point]:
    xvals, yvals = zip(*path)
    max_x = max(xvals)
    max_y = max(yvals)
    min_x = min(xvals)
    min_y = min(yvals)

    start = (min_x + (max_x - min_x) / 2, min_y + (max_y - min_y) / 2)
    return start, start


def path_median(path: Path) -> tuple[Point, Point]:
    xvals, yvals = zip(*path)
    min_x = min(xvals)
    min_y = min(yvals)
    xvals = list(map(lambda x: x - min_x, xvals))
    yvals = list(map(lambda y: y - min_y, yvals))
    xmedian = sorted(xvals)[int(math.ceil(len(xvals) // 2))]
    ymedian = sorted(yvals)[int(math.ceil(len(yvals) // 2))]

    start = (min_x + xmedian, min_y + ymedian)
    return start, start


def path_mean(path: Path) -> tuple[Point, Point]:
    xvals, yvals = zip(*path)
    min_x = min(xvals)
    min_y = min(yvals)
    xvals = list(map(lambda x: x - min_x, xvals))
    yvals = list(map(lambda y: y - min_y, yvals))
    xmean = sum(xvals) / len(xvals)
    ymean = sum(yvals) / len(yvals)

    start = (min_x + xmean, min_y + ymean)
    return start, start


def _weed_horizontal(x0: float, y0: float, x1: float, y1: float,
                     by0: float, by1: float, n: int) -> list[Path]:
    """n-1 horizontal lines that divide [by0, by1] into n equal segments; endpoints extend to x0/x1."""
    if n <= 1:
        return []
    h = by1 - by0
    return [[(x0, by0 + i * h / n), (x1, by0 + i * h / n)] for i in range(1, n)]


def _weed_vertical(x0: float, y0: float, x1: float, y1: float,
                   bx0: float, bx1: float, n: int) -> list[Path]:
    """n-1 vertical lines that divide [bx0, bx1] into n equal segments; endpoints extend to y0/y1."""
    if n <= 1:
        return []
    w = bx1 - bx0
    return [[(bx0 + i * w / n, y0), (bx0 + i * w / n, y1)] for i in range(1, n)]


def _weed_grid(x0: float, y0: float, x1: float, y1: float,
               bx0: float, by0: float, bx1: float, by1: float,
               n_x: int, n_y: int) -> list[Path]:
    return _weed_horizontal(x0, y0, x1, y1, by0, by1, n_y) + \
           _weed_vertical(x0, y0, x1, y1, bx0, bx1, n_x)


def _weed_frame(bx0: float, by0: float, bx1: float, by1: float, weed_size: float) -> list[Path]:
    """Concentric rectangular frames with equal-area rings.
    Frame k is scaled by s_k = sqrt(1 - k·weed_size/100) from the bbox centre,
    so each ring has area exactly weed_size% of the total bbox area."""
    lines = []
    w = bx1 - bx0
    h = by1 - by0
    k = 1
    while True:
        s2 = 1.0 - k * weed_size / 100.0
        if s2 <= 0.0:
            break
        s = math.sqrt(s2)
        xl = bx0 + w * (1.0 - s) / 2.0
        xr = bx1 - w * (1.0 - s) / 2.0
        yb = by0 + h * (1.0 - s) / 2.0
        yt = by1 - h * (1.0 - s) / 2.0
        if xl >= xr or yb >= yt:
            break
        lines += [
            [(xl, yb), (xr, yb)],
            [(xr, yb), (xr, yt)],
            [(xr, yt), (xl, yt)],
            [(xl, yt), (xl, yb)],
        ]
        k += 1
    return lines


def _diagonal_family(x0: float, y0: float, x1: float, y1: float,
                     c_ref: float, step: float, slope: int) -> list[Path]:
    """One family of parallel diagonal lines (slope ±1) clipped to the extended bbox."""
    if step <= 0:
        return []
    c_min = (y0 - x1) if slope == 1 else (y0 + x0)
    c_max = (y1 - x0) if slope == 1 else (y1 + x1)
    k_min = math.ceil((c_min - c_ref) / step)
    k_max = math.floor((c_max - c_ref) / step)
    lines = []
    for k in range(k_min, k_max + 1):
        c = c_ref + k * step
        p1 = (x0, slope * x0 + c)
        p2 = (x1, slope * x1 + c)
        seg = _line_bbox_clip(p1, p2, x0, y0, x1, y1)
        if seg:
            lines.append(list(seg))
    return lines


def _weed_diagonal(x0: float, y0: float, x1: float, y1: float,
                   bx0: float, by0: float, bx1: float, by1: float,
                   n_x: int, n_y: int) -> list[Path]:
    """45° diagonal lines (y−x = c) equally spaced across the bbox."""
    step = (bx1 - bx0) / n_x if n_x > 0 else 1.0
    return _diagonal_family(x0, y0, x1, y1, by0 - bx0, step, slope=1)


def _weed_rombic(x0: float, y0: float, x1: float, y1: float,
                 bx0: float, by0: float, bx1: float, by1: float,
                 n_x: int, n_y: int) -> list[Path]:
    """Both diagonal families (45° and 135°) forming a rhombic grid."""
    step = (bx1 - bx0) / n_x if n_x > 0 else 1.0
    return (_diagonal_family(x0, y0, x1, y1, by0 - bx0, step, slope=1) +
            _diagonal_family(x0, y0, x1, y1, by0 + bx0, step, slope=-1))


def _weed_tick(x0: float, y0: float, x1: float, y1: float,
               bx0: float, by0: float, bx1: float, by1: float,
               tick_hpgl: float, n_x: int, n_y: int) -> list[Path]:
    """Short inward comb-teeth from each bbox edge. n_x ticks on top/bottom, n_y on left/right."""
    lines = []
    for i in range(1, n_x):
        tx = bx0 + i * (bx1 - bx0) / n_x
        lines.append([(tx, y0), (tx, y0 + tick_hpgl)])
        lines.append([(tx, y1), (tx, y1 - tick_hpgl)])
    for i in range(1, n_y):
        ty = by0 + i * (by1 - by0) / n_y
        lines.append([(x0, ty), (x0 + tick_hpgl, ty)])
        lines.append([(x1, ty), (x1 - tick_hpgl, ty)])
    return lines


def _ray_bbox_intersect(cx: float, cy: float, dx: float, dy: float,
                        x0: float, y0: float, x1: float, y1: float) -> Optional[Point]:
    """First intersection of forward ray (cx,cy)+t*(dx,dy), t>0, with the bbox boundary."""
    t_best = math.inf
    for wx in (x0, x1):
        if abs(dx) > 1e-10:
            t = (wx - cx) / dx
            if t > 1e-9 and y0 <= cy + t * dy <= y1:
                t_best = min(t_best, t)
    for wy in (y0, y1):
        if abs(dy) > 1e-10:
            t = (wy - cy) / dy
            if t > 1e-9 and x0 <= cx + t * dx <= x1:
                t_best = min(t_best, t)
    return None if t_best == math.inf else (cx + t_best * dx, cy + t_best * dy)


def _weed_radial(x0: float, y0: float, x1: float, y1: float,
                 bx0: float, by0: float, bx1: float, by1: float,
                 weed_size: float, weed_small_size: float,
                 routes: list[Path]) -> list[Path]:
    """Spokes from the bbox centre at evenly-distributed angles (360°/n_spokes apart).

    If the centre lies in waste (not inside a part), all spokes would converge
    at one uncut spot which may tear the vinyl.  In that case a small inner circle
    of area weed_small_size% of bbox is added and spokes run from the circle boundary
    to the perimeter instead of from the centre.
    """
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    W, H = bx1 - bx0, by1 - by0

    center_in_part = bool(_point_parity((cx, cy), routes))
    enclosing_routes: list[Path] = []
    inner_r = 0.0
    circle_r = 0.0

    if not center_in_part:
        enclosing_routes = [r for r in routes if _point_parity((cx, cy), [r])]
        if enclosing_routes:
            interior_bbox_area = min(
                (max(p[0] for p in r) - min(p[0] for p in r)) *
                (max(p[1] for p in r) - min(p[1] for p in r))
                for r in enclosing_routes
            )
            if interior_bbox_area >= W * H * weed_size / 100.0:
                enclosing_routes = []
                inner_r = math.sqrt(W * H * weed_small_size / (100.0 * math.pi))
                circle_r = inner_r

    effective_area = W * H - math.pi * inner_r ** 2
    target_area = W * H * weed_size / 100.0
    n_spokes = max(1, round(effective_area / target_area))
    lines: list[Path] = []

    for i in range(n_spokes):
        angle = 2 * math.pi * i / n_spokes
        dx, dy = math.cos(angle), math.sin(angle)
        ep = _ray_bbox_intersect(cx, cy, dx, dy, x0, y0, x1, y1)
        if ep is None:
            continue
        if inner_r > 0:
            start: Point = (cx + inner_r * dx, cy + inner_r * dy)
        elif enclosing_routes:
            t_min = 1.0
            for route in enclosing_routes:
                for a, b in zip(route, route[1:]):
                    t = _seg_intersect_t((cx, cy), ep, a, b)
                    if t is not None and 1e-9 < t < t_min:
                        t_min = t
            start = (cx + t_min * (ep[0] - cx), cy + t_min * (ep[1] - cy))
        else:
            start = (cx, cy)
        lines.append([start, ep])

    if circle_r > 0:
        n = max(32, round(math.pi * circle_r / 20))
        pts = [
            (cx + circle_r * math.cos(2 * math.pi * i / n),
             cy + circle_r * math.sin(2 * math.pi * i / n))
            for i in range(n)
        ]
        pts.append(pts[0])
        lines.append(pts)

    return lines


def _point_to_seg_closest(p: Point, a: Point, b: Point) -> tuple[float, Point]:
    """Closest point on segment a→b to p, and the distance."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    len2 = dx * dx + dy * dy
    if len2 < 1e-12:
        return vecDist(p, a), a
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / len2))
    closest = (a[0] + t * dx, a[1] + t * dy)
    return vecDist(p, closest), closest


def _weed_small_piece_filter(
    segments: list[Path],
    routes: list[Path],
    x0: float, y0: float, x1: float, y1: float,
    bbox_area: float,
    weed_min_size: float,
) -> list[Path]:
    """Remove 2-point weeding segments that create waste pieces below weed_min_size% of bbox.

    For each segment the smallest waste strip it could bound is approximated as
    segment_length × min_clearance, where min_clearance is the minimum distance
    from any interior sample point on the segment to a design path or the bbox edge.
    Endpoints are excluded from sampling because adaptive clipping places them exactly
    on design paths (distance 0), which would falsely remove every segment.
    Multi-point paths (e.g. the radial inner circle) are passed through unchanged.
    """
    if weed_min_size <= 0:
        return segments
    threshold = bbox_area * weed_min_size / 100.0
    bbox_boundary: Path = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
    boundaries = list(routes) + [bbox_boundary]
    result: list[Path] = []
    for seg in segments:
        if len(seg) != 2:
            result.append(seg)
            continue
        a, b = seg[0], seg[1]
        length = vecDist(a, b)
        min_clearance = float('inf')
        for i in range(1, 5):          # t = 0.2, 0.4, 0.6, 0.8 — interior only
            t = i / 5.0
            p = (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1]))
            for boundary in boundaries:
                for ra, rb in zip(boundary, boundary[1:]):
                    d, _ = _point_to_seg_closest(p, ra, rb)
                    if d < min_clearance:
                        min_clearance = d
        if length * min_clearance >= threshold:
            result.append(seg)
    return result


HPGL_CMDS = {
    re.compile(r"^PU(-?\d+),(-?\d+)$"): hpgl_goto,
    re.compile(r"^PD(-?\d+),(-?\d+)$"): hpgl_cutto,
    re.compile(r"^PD((-?\d+,-?\d+,)+(-?\d+),(-?\d+))$"): hpgl_cutto2,
    re.compile(r"^PA$"): hpgl_pen_absolute,
    re.compile(r"^PU$"): hpgl_pen_up,
    re.compile(r"^IN:?$"): hpgl_init,
    re.compile(r"^SP(\d+)$"): hpgl_select_pen}


class HPGL:
    def __init__(self, fn: Optional[str]) -> None:
        self.routes: list[Path] = []
        if fn:
            with open(fn) as f:
                self.parse(f.read())

    def parse(self, hpgldata: str) -> None:
        commands = hpgldata.split(";")
        routes = []
        path = []
        for command in commands:
            command = command.strip()
            if not command:
                continue
            matched = False
            for CMD, func in HPGL_CMDS.items():
                match = CMD.match(command)
                if match:
                    cmd, params = func(match)
                    if cmd == HPGL_INIT:
                        pass
                    elif cmd == HPGL_SELECT_PEN:
                        pass
                    elif cmd == HPGL_PEN_ABSOLUTE:
                        pass
                    elif cmd == HPGL_GOTO:
                        if path:
                            if len(path) > 1:
                                routes.append(path)
                        path = [params, ]
                    elif cmd == HPGL_CUTTO:
                        if isinstance(params, list):
                            path.extend(params)
                        else:
                            if path[-1] != params:
                                path.append(params)
                    else:
                        raise Exception("what to do with \"" + cmd + "\" ?")

                    matched = True
                    break
            if not matched:
                print(repr(command))
        if path:
            if len(path) > 1:
                routes.append(path)
        self.routes = routes

    def getPaths(self) -> list[Path]:
        return self.routes

    def getBoundingBox(self) -> tuple[Point, Point]:
        max_x = None
        max_y = None
        min_x = None
        min_y = None
        for path in self.getPaths():
            for x, y in path:
                if max_x is None or x > max_x:
                    max_x = x
                if min_x is None or x < min_x:
                    min_x = x

                if max_y is None or y > max_y:
                    max_y = y
                if min_y is None or y < min_y:
                    min_y = y

        return ((min_x, min_y), (max_x, max_y))

    def bladeOffset(self, offset: float) -> None:
        # A rotating knife blade trails behind its pivot by `offset` mm.
        # At each sharp corner we extend the incoming segment past the corner
        # and start the outgoing segment slightly ahead of it, giving the blade
        # time to swing into the new direction before cutting begins.
        hpgl_offset = mm2hpgl(offset)

        def _blade_offset(path):
            new_path = []
            new_path.append(path[0])
            for prev, cur, next in zip(path[:-2], path[1:-1], path[2:]):
                angle = vecAngle(prev, cur, next)
                if angle < math.pi / 1.1:  # ~164°: only correct at meaningful corners; near-straight angles need no adjustment
                    d2 = vecDist(cur, next)
                    ext2 = (4 * hpgl_offset) / d2
                    if ext2 <= 1.0:
                        d1 = vecDist(prev, cur)
                        ext1 = 1 + hpgl_offset / d1
                        new_path.append(vecExtend(prev, cur, ext1))
                        new_path.append(vecExtend(cur, next, ext2))
                    else:
                        new_path.append(cur)
                else:
                    new_path.append(cur)
            new_path.append(path[-1])
            return new_path
        self.operate(_blade_offset)

    def optimize(self) -> None:
        # Two-pass: first remove duplicates/subpixel points (required so the
        # collinearity check in pass 2 doesn't fail on zero-length segments),
        # then drop points that lie exactly on a straight line between neighbours.
        def _optimize(path):
            new_path = []
            last = None
            for p in path:
                if p == last:
                    continue
                last = p
                new_path.append((int(round(p[0], 0)), int(round(p[1], 0))))
            path = new_path
            new_path = []
            new_path.append(path[0])
            prev = new_path[0]
            for cur, next in zip(path[1:-1], path[2:]):
                if cur == prev:
                    continue
                if cur == next:
                    continue
                angle = vecAngle(prev, cur, next)
                if angle == math.pi:
                    continue
                new_path.append(cur)
                prev = cur
            if new_path[-1] != path[-1]:
                new_path.append(path[-1])
            if len(new_path) == 1:
                return None
            if new_path[0] == new_path[-1]:
                angle = vecAngle(new_path[-2], new_path[0], new_path[1])
                if angle == math.pi:
                    new_path.pop(0)
                    new_path.pop(-1)
                    new_path.append(new_path[0])
            return new_path

        last = None
        paths = self.getPaths()
        self.routes = []
        for path in paths:
            if path[0] == last:
                self.routes[-1].extend(path)
            else:
                self.routes.append(path)
            last = path[-1]
        self.operate(_optimize)

    def optimizeCut(self, offset: float) -> None:
        # For closed paths, reposition the start/end seam to the midpoint of the
        # longest segment.  This gives the blade maximum run-up before reaching
        # the seam and a clean overcut exit, minimising the visible join mark.
        hpgl_offset = mm2hpgl(offset) * 2
        operations = []

        def _optimizeCut(path):
            if path[0] != path[-1]:
                return path
            index = None
            maxlen = None
            for j, coord in enumerate(zip(path[:-1], path[1:])):
                cur, next = coord
                l = vecDist(cur, next)
                if maxlen is None or maxlen < l:
                    maxlen = l
                    index = j
            a = vecExtend(path[index], path[index + 1], 0.5)
            d = vecDist(path[index], path[index + 1])
            b = vecExtend(path[index + 1], path[index], 0.5 - min(hpgl_offset / d, 0.5))
            pre = [a, b]
            if path[index + 1] == b:
                pre = [a]
            p = pre + path[index + 1:] + path[1:index + 1] + [a, b]
            return p

        self.operate(_optimizeCut)

    def operate(self, fn: Callable[[Path], Optional[Path]]) -> None:
        routes = []
        for path in self.routes:
            result = fn(path)
            if result:
                routes.append(result)
        self.routes = routes

    def operateXY(self, fn: Callable[[float, float], Point]) -> None:
        self.operate(lambda path: list(map(lambda xy: fn(xy[0], xy[1]), path)))

    def move(self, xoffset: float, yoffset: float) -> None:
        self.operateXY(lambda x, y: (x + xoffset, y + yoffset))

    def scale(self, xfactor: float, yfactor: Optional[float] = None) -> None:
        if yfactor is None:
            yfactor = xfactor
        self.operateXY(lambda x, y: (x * xfactor, y * yfactor))

    def fit(self) -> None:
        min_xy, max_xy = self.getBoundingBox()
        x, y = min_xy
        self.move(-x, -y)

    def scaleToWidth(self, width: float) -> None:
        new_width = mm2hpgl(width)

        self.fit()
        _, max_xy = self.getBoundingBox()
        x, y = max_xy
        factor = new_width / float(x)
        self.scale(factor)

    def exportSVG(self, filename: str) -> None:
        _, max_xy = self.getBoundingBox()
        x, y = max_xy
        svg = """<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg
	xmlns:dc="http://purl.org/dc/elements/1.1/"
	xmlns:cc="http://creativecommons.org/ns#"
	xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
	xmlns:svg="http://www.w3.org/2000/svg"
	xmlns="http://www.w3.org/2000/svg"
	units="mm"
	width="{width:.3f}mm"
	height="{height:.3f}mm"
	viewBox="0 0 {width:.3f} {height:.3f}">
""".format(width=hpgl2mm(x), height=hpgl2mm(y))
        last_x = 0
        last_y = 0
        for path in self.getPaths():
            svg += "<path style=\"stroke:#0000ff;stroke-opacity:.8;fill:none;stroke-width:0.1;\" d=\"M %.3f,%.3f L %.3f,%.3f\"></path>\n" % tuple(map(hpgl2mm, (last_x, last_y, path[0][0], path[0][1])))
            last_x = path[-1][0]
            last_y = path[-1][1]
            svg += "<path style=\"stroke:#ff0000;stroke-opacity:.8;fill:none;stroke-width:0.1;\" d=\""
            first = True
            for x, y in path:
                if first:
                    first = False
                    svg += "M %.3f,%.3f" % (hpgl2mm(x), hpgl2mm(y))
                else:
                    svg += " L %.3f,%.3f" % (hpgl2mm(x), hpgl2mm(y))

            svg += "\"></path>\n"
        svg += "<path style=\"stroke:#0000ff;stroke-opacity:.8;fill:none;stroke-width:0.1;\" d=\"M %.3f,%.3f L %.3f,%.3f\"></path>\n" % tuple(map(hpgl2mm, (last_x, last_y, 0, 0)))
        svg += "</svg>"
        with open(filename, "w") as f:
            f.write(svg)

    def mirrorX(self) -> None:
        min_xy, max_xy = self.getBoundingBox()
        self.scale(-1, 1)
        self.move(max_xy[0], 0)

    def mirrorY(self) -> None:
        min_xy, max_xy = self.getBoundingBox()
        self.scale(1, -1)
        self.move(0, max_xy[1])

    def addMargin(self, x: float, y: float) -> None:
        self.move(mm2hpgl(x), mm2hpgl(y))

    def getSize(self) -> tuple[float, float]:
        min_xy, max_xy = self.getBoundingBox()
        return tuple(map(hpgl2mm, (max_xy[0] - min_xy[0], max_xy[1] - min_xy[1])))

    def getLength(self) -> tuple[float, float]:
        movement = 0
        draw = 0
        last = (0, 0)
        for path in self.getPaths():
            movement += vecDist(last, path[0])
            draw += sum(map(lambda x: vecDist(x[0], x[1]), zip(path, path[1:])))
            last = path[-1]
        movement += vecDist(last, (0, 0))
        return hpgl2mm(movement), hpgl2mm(draw)

    def multiplyX(self, delta: float, m: int = 2, offset_y: float = 0.0, _step_x: Optional[float] = None) -> None:
        if m < 2:
            return
        deltaHPGL = mm2hpgl(delta)
        offsetHPGL = mm2hpgl(offset_y)
        original = self.getPaths()
        step_x = _step_x if _step_x is not None else self.getBoundingBox()[1][0]
        for i in range(m - 1):
            self.move(step_x + deltaHPGL, offsetHPGL)
            self.routes = original + self.routes

    def multiplyY(self, delta: float, m: int = 2, offset_x: float = 0.0, _step_y: Optional[float] = None) -> None:
        if m < 2:
            return
        deltaHPGL = mm2hpgl(delta)
        offsetHPGL = mm2hpgl(offset_x)
        original = self.getPaths()
        step_y = _step_y if _step_y is not None else self.getBoundingBox()[1][1]
        for i in range(m - 1):
            self.move(offsetHPGL, step_y + deltaHPGL)
            self.routes = original + self.routes

    def getHPGL(self) -> str:
        hpgl = HPGL_INIT
        hpgl += HPGL_PEN_ABSOLUTE
        for route in self.routes:
            route = tuple(map(lambda a: tuple(map(lambda b: int(round(b, 0)), a)), route))
            goto = route[0]
            route = ",".join(map(lambda a: "%d,%d" % a, route[1:]))
            hpgl += HPGL_GOTO % goto
            hpgl += HPGL_CUTTO_STR % route
        hpgl += HPGL_GOTO % (0, 0)
        hpgl += HPGL_SELECT_PEN % 0  # SP0 twice: some plotters only retract the blade/pen on the second command
        hpgl += HPGL_SELECT_PEN % 0
        return hpgl

    def exportHPGL(self, filename: str) -> None:
        with open(filename, "w") as f:
            f.write(self.getHPGL())

    def rerouteNearest(self, xweight: float = 1, yweight: float = 2,
                       pathfn: Callable[[Path], tuple[Point, Point]] = path_center) -> None:
        # Greedy nearest-neighbour reorder. yweight=2 by default because the
        # plotter carriage moves faster along X, so Y travel costs more time.
        last_p = (0, 0)
        paths = self.getPaths()
        self.routes = []
        distance = None
        next_path = None
        next_path_stop = None
        while paths:
            for path in paths:
                path_start, path_stop = pathfn(path)
                d = math.sqrt(((path_start[0] - last_p[0]) * xweight) ** 2 + ((path_start[1] - last_p[1]) * yweight) ** 2)
                if distance is None or distance > d:
                    distance = d
                    next_path = path
                    next_path_stop = path_stop
            if next_path:
                self.routes.append(next_path)
                paths.remove(next_path)
                last_p = next_path_stop
                next_path = None
                distance = None

    def rerouteXY(self, rowsize: int = 600,
                  pathfn: Callable[[Path], tuple[Point, Point]] = path_start_stop) -> None:
        # Boustrophedon (snake) order: sort paths into horizontal rows, then
        # alternate row direction so the pen reverses rather than returning to
        # the start of each row, minimising total pen-up travel.
        min_xy, max_xy = self.getBoundingBox()
        x, y = max_xy
        _, min_y = min_xy
        rows = [[] for i in range(int((y - min_y) // rowsize + 1))]
        for path in self.getPaths():
            start, stop = pathfn(path)
            x, y = start
            row = int((y - min_y) // rowsize)
            rows[row].append((start, path))
        reverse = False
        self.routes = []

        for row in rows:
            if row:
                self.routes.extend(map(lambda a: a[1], sorted(row, reverse=reverse)))
                reverse = not reverse

    def addWeedingLines(self, strategy: str = 'grid',
                        min_spacing_x: float = 1.0, max_spacing_x: float = math.inf,
                        min_spacing_y: float = 1.0, max_spacing_y: float = math.inf,
                        margin: float = 2.0, tick_length: float = 5.0,
                        adaptive: bool = True,
                        add_frame: bool = True, frame_distance: float = 1.0,
                        weed_size: float = 25.0, weed_small_size: float = 0.0,
                        weed_min_size: float = 0.0) -> None:
        min_xy, max_xy = self.getBoundingBox()
        mx = mm2hpgl(margin)
        x0, y0 = min_xy[0] - mx, min_xy[1] - mx
        x1, y1 = max_xy[0] + mx, max_xy[1] + mx

        bx0, by0 = min_xy[0], min_xy[1]
        bx1, by1 = max_xy[0], max_xy[1]

        if not hasattr(self, '_design_bbox'):
            self._design_bbox = (min_xy, max_xy)

        # 1D strategies: each strip ≤ weed_size% of total area  →  n = ⌈100/weed_size⌉
        # 2D strategies: each cell ≤ weed_size% of total area   →  n = ⌈√(100/weed_size)⌉
        n_1d = max(1, math.ceil(100.0 / weed_size))
        n_2d = max(1, math.ceil(math.sqrt(100.0 / weed_size)))

        def _clamp_n(n, size, min_sp, max_sp):
            if size <= 0:
                return 1
            if min_sp > 0:
                n = min(n, int(size / mm2hpgl(min_sp)))
            if max_sp < math.inf:
                n = max(n, math.ceil(size / mm2hpgl(max_sp)))
            return max(n, 1)

        n_x = _clamp_n(n_2d, bx1 - bx0, min_spacing_x, max_spacing_x)
        n_y = _clamp_n(n_2d, by1 - by0, min_spacing_y, max_spacing_y)

        original_routes = self.routes[:]
        if weed_small_size <= 0:
            weed_small_size = weed_size / 10.0
        if weed_min_size <= 0:
            weed_min_size = weed_small_size / 10.0

        dispatch = {
            'grid':       lambda: _weed_grid(x0, y0, x1, y1, bx0, by0, bx1, by1, n_x, n_y),
            'horizontal': lambda: _weed_horizontal(x0, y0, x1, y1, by0, by1, n_1d),
            'vertical':   lambda: _weed_vertical(x0, y0, x1, y1, bx0, bx1, n_1d),
            'frame':      lambda: _weed_frame(bx0, by0, bx1, by1, weed_size),
            'diagonal':   lambda: _weed_diagonal(x0, y0, x1, y1, bx0, by0, bx1, by1, n_x, n_y),
            'rombic':     lambda: _weed_rombic(x0, y0, x1, y1, bx0, by0, bx1, by1, n_x, n_y),
            'tick':       lambda: _weed_tick(x0, y0, x1, y1, bx0, by0, bx1, by1, mm2hpgl(tick_length), n_x, n_y),
            'radial':     lambda: _weed_radial(x0, y0, x1, y1, bx0, by0, bx1, by1, weed_size, weed_small_size, original_routes),
        }
        fn = dispatch.get(strategy)
        if fn is None:
            raise ValueError("Unknown weeding strategy {!r}. Available: {}".format(
                strategy, ', '.join(dispatch)))
        new_lines = fn()

        if adaptive:
            clipped = []
            for seg in new_lines:
                if len(seg) == 2:
                    for a, b in _adaptive_clip(seg[0], seg[1], original_routes):
                        if vecDist(a, b) > 1.0:
                            clipped.append([a, b])
                else:
                    # Multi-point polyline: clip each segment and chain consecutive kept pieces.
                    chain: list[Point] = []
                    for i in range(len(seg) - 1):
                        sub = _adaptive_clip(seg[i], seg[i + 1], original_routes)
                        for a, b in sub:
                            if vecDist(a, b) <= 1.0:
                                continue
                            if chain and vecDist(chain[-1], a) < 1.0:
                                chain.append(b)
                            else:
                                if len(chain) >= 2:
                                    clipped.append(chain)
                                chain = [a, b]
                        if not sub and chain:
                            clipped.append(chain)
                            chain = []
                    if len(chain) >= 2:
                        clipped.append(chain)
            new_lines = clipped

        if weed_min_size > 0:
            bbox_area = (bx1 - bx0) * (by1 - by0)
            new_lines = _weed_small_piece_filter(
                new_lines, original_routes, x0, y0, x1, y1, bbox_area, weed_min_size)

        self.routes.extend(new_lines)

        if add_frame:
            fd = mm2hpgl(frame_distance)
            fx0, fy0 = bx0 - fd, by0 - fd
            fx1, fy1 = bx1 + fd, by1 + fd
            self.routes += [
                [(fx0, fy0), (fx1, fy0)],
                [(fx1, fy0), (fx1, fy1)],
                [(fx1, fy1), (fx0, fy1)],
                [(fx0, fy1), (fx0, fy0)],
            ]


def apply_args(hpgl_obj: HPGL, args) -> None:
    blade_optimize = False
    optimize = False
    rotate180 = False
    mirror = args.mirror

    if args.magic:
        blade_optimize = True
        optimize = True
        rotate180 = True

    if args.width is not None:
        hpgl_obj.scaleToWidth(args.width)

    if getattr(args, 'pen', False):
        blade_optimize = False

    if rotate180:
        hpgl_obj.mirrorX()
        hpgl_obj.mirrorY()

    if mirror:
        hpgl_obj.mirrorX()

    if optimize:
        hpgl_obj.optimize()
        hpgl_obj.fit()

    if blade_optimize:
        blade_offset = getattr(args, 'blade_offset', 0.25) or 0.25
        hpgl_obj.optimizeCut(blade_offset)
        hpgl_obj.bladeOffset(blade_offset)

    repeat_x = getattr(args, 'repeat_x', 1) or 1
    repeat_y = getattr(args, 'repeat_y', 1) or 1
    gap = getattr(args, 'gap', 5.0)
    if gap is None:
        gap = 5.0
    gap_x = getattr(args, 'gap_x', None)
    gap_y = getattr(args, 'gap_y', None)
    if gap_x is None:
        gap_x = gap
    if gap_y is None:
        gap_y = gap
    offset_x = getattr(args, 'offset_x', 0.0) or 0.0
    offset_y = getattr(args, 'offset_y', 0.0) or 0.0
    if repeat_x > 1 or repeat_y > 1:
        _, (orig_max_x, orig_max_y) = hpgl_obj.getBoundingBox()
    if repeat_x > 1:
        hpgl_obj.multiplyX(gap_x, repeat_x, offset_y, _step_x=orig_max_x)
    if repeat_y > 1:
        hpgl_obj.multiplyY(gap_y, repeat_y, offset_x, _step_y=orig_max_y)

    weed = getattr(args, 'weed', None)
    if weed:
        hpgl_obj.addWeedingLines(
            strategy=weed,
            min_spacing_x=getattr(args, 'weed_min_x', 1.0) or 1.0,
            max_spacing_x=getattr(args, 'weed_max_x', None) or float('inf'),
            min_spacing_y=getattr(args, 'weed_min_y', 1.0) or 1.0,
            max_spacing_y=getattr(args, 'weed_max_y', None) or float('inf'),
            margin=getattr(args, 'weed_margin', 2.0) or 2.0,
            tick_length=getattr(args, 'weed_tick_length', 5.0) or 5.0,
            adaptive=not getattr(args, 'no_weed_adaptive', False),
            add_frame=not getattr(args, 'no_weed_frame', False),
            frame_distance=getattr(args, 'weed_frame_distance', 1.0) or 1.0,
            weed_size=getattr(args, 'weed_size', 25.0) or 25.0,
            weed_small_size=getattr(args, 'weed_small_size', 0.0),
            weed_min_size=getattr(args, 'weed_min_size', 0.0),
        )

    reroute = getattr(args, 'reroute', 'xy')
    if reroute == 'xy':
        hpgl_obj.rerouteXY()
    elif reroute == 'nearest':
        hpgl_obj.rerouteNearest()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser("HPGL modification/optimization tool")
    parser.add_argument("file", type=str, help="the HPGL-file to edit")
    parser.add_argument("-p", "--preview", type=str, help="Generate SVG preview file", metavar="SVG")
    parser.add_argument("-o", "--output", type=str, help="Output HPGL file", metavar="HPGL")
    parser.add_argument("-m", "--magic", action="store_true", help="Enable auto-optimize")
    parser.add_argument("-w", "--width", metavar="WIDTH", type=int, help="Scale to width in mm")
    parser.add_argument("--mirror", action="store_true", help="Mirror on X-axis for inverted cuts (T-Shirts etc.)")
    parser.add_argument("--pen", action="store_true", help="Disable cut optimization for rotating knifes")
    parser.add_argument("--blade-offset", metavar="MM", type=float, default=0.25, help="Blade offset in mm (default: 0.25, ignored with --pen)")
    parser.add_argument("--reroute", choices=["xy", "nearest", "none"], default="xy",
                        help="Reroute paths: xy (boustrophedon, default), nearest (greedy), none (keep original order)")
    parser.add_argument("--repeat-x", metavar="N", type=int, default=1, help="Tile N times along X axis")
    parser.add_argument("--repeat-y", metavar="N", type=int, default=1, help="Tile N times along Y axis")
    parser.add_argument("--gap", metavar="MM", type=float, default=5.0, help="Gap between tiles in mm for both axes (default: 5)")
    parser.add_argument("--gap-x", metavar="MM", type=float, default=None, help="Gap between tiles along X axis in mm; overrides --gap (negative = overlap)")
    parser.add_argument("--gap-y", metavar="MM", type=float, default=None, help="Gap between tiles along Y axis in mm; overrides --gap (negative = overlap)")
    parser.add_argument("--offset-x", metavar="MM", type=float, default=0.0, help="X offset per step when repeating along Y axis in mm (stagger rows)")
    parser.add_argument("--offset-y", metavar="MM", type=float, default=0.0, help="Y offset per step when repeating along X axis in mm (stagger columns)")
    weed_group = parser.add_argument_group("weeding lines")
    weed_group.add_argument("--weed", metavar="STRATEGY",
                            choices=["grid", "horizontal", "vertical", "frame",
                                     "diagonal", "rombic", "tick", "radial"],
                            help="Add weeding lines (grid, horizontal, vertical, frame, "
                                 "diagonal, rombic, tick, radial)")
    weed_group.add_argument("--weed-min-x", metavar="MM", type=float, default=1.0,
                            help="Min spacing between vertical weeding lines in mm (default: 1)")
    weed_group.add_argument("--weed-max-x", metavar="MM", type=float, default=None,
                            help="Max spacing between vertical weeding lines in mm (default: unlimited)")
    weed_group.add_argument("--weed-min-y", metavar="MM", type=float, default=1.0,
                            help="Min spacing between horizontal weeding lines in mm (default: 1)")
    weed_group.add_argument("--weed-max-y", metavar="MM", type=float, default=None,
                            help="Max spacing between horizontal weeding lines in mm (default: unlimited)")
    weed_group.add_argument("--weed-margin", metavar="MM", type=float, default=2.0,
                            help="Extend weeding lines beyond bbox in mm (default: 2)")
    weed_group.add_argument("--weed-tick-length", metavar="MM", type=float, default=5.0,
                            help="Tick/comb tooth length in mm (default: 5)")
    weed_group.add_argument("--weed-size", metavar="PCT", type=float, default=25.0,
                            help="Max waste piece size as %% of bbox area (default: 25)")
    weed_group.add_argument("--weed-small-size", metavar="PCT", type=float, default=0.0,
                            help="Radial inner circle area as %% of bbox area (default: weed-size/10)")
    weed_group.add_argument("--weed-min-size", metavar="PCT", type=float, default=0.0,
                            help="Remove weeding lines creating waste pieces smaller than PCT%% of bbox (default: weed-small-size/10)")
    weed_group.add_argument("--no-weed-adaptive", action="store_true",
                            help="Disable splitting weeding lines at design intersections")
    weed_group.add_argument("--no-weed-frame", action="store_true",
                            help="Disable the outer frame rectangle around the bbox")
    weed_group.add_argument("--weed-frame-distance", metavar="MM", type=float, default=1.0,
                            help="Distance of outer frame from bbox in mm (default: 1)")
    args = parser.parse_args()

    HPGLinput = HPGL(args.file)
    apply_args(HPGLinput, args)

    if args.preview is not None:
        HPGLinput.exportSVG(args.preview)
    if args.output is not None:
        HPGLinput.exportHPGL(args.output)
