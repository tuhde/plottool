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

    def multiplyX(self, delta: float, m: int = 2) -> None:
        if m < 2:
            return
        deltaHPGL = mm2hpgl(delta)
        original = self.getPaths()
        min_xy, max_xy = self.getBoundingBox()
        x, y = max_xy
        for i in range(m - 1):
            self.move(x + deltaHPGL, 0)
            self.routes = original + self.routes

    def multiplyY(self, delta: float, m: int = 2) -> None:
        if m < 2:
            return
        deltaHPGL = mm2hpgl(delta)
        original = self.getPaths()
        min_xy, max_xy = self.getBoundingBox()
        x, y = max_xy
        for i in range(m - 1):
            self.move(0, y + deltaHPGL)
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

    reroute = getattr(args, 'reroute', None)
    if reroute is None and args.magic:
        reroute = 'xy'
    if reroute == 'xy':
        hpgl_obj.rerouteXY()
    elif reroute == 'nearest':
        hpgl_obj.rerouteNearest()

    repeat_x = getattr(args, 'repeat_x', 1) or 1
    repeat_y = getattr(args, 'repeat_y', 1) or 1
    gap = getattr(args, 'gap', 5.0) or 5.0
    if repeat_x > 1:
        hpgl_obj.multiplyX(gap, repeat_x)
    if repeat_y > 1:
        hpgl_obj.multiplyY(gap, repeat_y)


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
    parser.add_argument("--reroute", choices=["xy", "nearest"], help="Reroute paths: xy (boustrophedon) or nearest (greedy)")
    parser.add_argument("--repeat-x", metavar="N", type=int, default=1, help="Tile N times along X axis")
    parser.add_argument("--repeat-y", metavar="N", type=int, default=1, help="Tile N times along Y axis")
    parser.add_argument("--gap", metavar="MM", type=float, default=5.0, help="Gap between tiles in mm (default: 5)")
    args = parser.parse_args()

    HPGLinput = HPGL(args.file)
    apply_args(HPGLinput, args)

    if args.preview is not None:
        HPGLinput.exportSVG(args.preview)
    if args.output is not None:
        HPGLinput.exportHPGL(args.output)
