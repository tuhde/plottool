# Plan: Weeding Lines Feature

## Context

Vinyl cutting requires a "weeding" step: removing waste material around/between the cut shapes. Large blank areas are hard to grip and peel. Weeding lines are extra cut lines added to break up those blank areas into manageable strips or zones.

Strategies requested: grid, diagonal/diamond, tick/comb, radial/star, bridge. Adaptive clipping (split at design intersections) on by default. Configurable margin beyond bounding box.

---

## Strategies

| Name | Description |
|------|-------------|
| `grid` | Full horizontal + vertical lines across bbox |
| `horizontal` | Horizontal lines only |
| `vertical` | Vertical lines only |
| `diagonal` | 45° lines, clipped to bbox |
| `diamond` | Both 45° and 135° diagonals |
| `frame` | Single cut rectangle around bbox |
| `cross` | One H + one V line through bbox centre |
| `tick` | Short inward comb-teeth from bbox edges |
| `radial` | Lines from bbox centre to edge at evenly-spaced angles |
| `bridge` | Short lines between nearest-point pairs of closed paths, and closed paths to bbox edge |

---

## Parameters

### Spacing parameters

| Parameter | CLI flag | Default | Meaning |
|-----------|----------|---------|---------|
| `edge_count` | `--weed-edge-count N` | 4 | Target number of weeding lines crossing each bounding box edge (i.e. each edge is divided into N segments). Used to compute an initial spacing relative to the design size. |
| `min_spacing_x` | `--weed-min-x MM` | 5.0 | Minimum distance between weeding lines in the X direction (vertical lines). Overrides `edge_count` if it would produce tighter spacing. |
| `max_spacing_x` | `--weed-max-x MM` | 50.0 | Maximum distance between weeding lines in the X direction. Overrides `edge_count` if it would produce wider spacing. |
| `min_spacing_y` | `--weed-min-y MM` | 5.0 | Minimum distance between weeding lines in the Y direction (horizontal lines). |
| `max_spacing_y` | `--weed-max-y MM` | 50.0 | Maximum distance between weeding lines in the Y direction. |

**Computed spacing:**
```
spacing_x = clamp(bbox_width  / edge_count, min_spacing_x, max_spacing_x)
spacing_y = clamp(bbox_height / edge_count, min_spacing_y, max_spacing_y)
```
All in mm, then converted to HPGL units.

For `diagonal`/`diamond`: use `(spacing_x + spacing_y) / 2` as the perpendicular distance between lines.
For `radial`: `edge_count` is the number of rays (ignores min/max).
For `tick`: `edge_count` is the number of ticks on each edge.

### Other parameters

| Parameter | CLI flag | Default | Meaning |
|-----------|----------|---------|---------|
| `margin` | `--weed-margin MM` | 2.0 | Extend weeding lines beyond bbox in mm |
| `tick_length` | `--weed-tick-length MM` | 5.0 | Length of tick/comb teeth (`tick` strategy only) |
| `adaptive` | `--no-weed-adaptive` | True | Split lines at design intersections (see below) |

---

## Adaptive Clipping

Each generated weeding line segment is split at every intersection with existing design paths. Each resulting sub-segment becomes its own route (pen-up between them), preventing double-cutting at design crossings.

---

## New Geometry Helpers (in `hpgl.py`)

```python
def _seg_intersect_t(p1, p2, p3, p4) -> Optional[tuple[float, float]]:
    """Return (t, u) where p1+t*(p2-p1) meets p3+u*(p4-p3), or None."""

def _line_bbox_clip(p1, p2, x0, y0, x1, y1) -> Optional[tuple[Point, Point]]:
    """Parametric clip of the infinite line through p1→p2 to the given bbox."""

def _adaptive_clip(p1: Point, p2: Point, routes: list[Path]) -> list[tuple[Point, Point]]:
    """Return sub-segments of p1→p2 split at all intersections with routes."""
```

---

## New `HPGL` method

```python
def addWeedingLines(
    self,
    strategy: str = 'grid',
    edge_count: int = 4,
    min_spacing_x: float = 5.0,
    max_spacing_x: float = 50.0,
    min_spacing_y: float = 5.0,
    max_spacing_y: float = 50.0,
    margin: float = 2.0,
    tick_length: float = 5.0,
    adaptive: bool = True,
) -> None:
```

- Compute bbox + margin in HPGL units
- Compute `spacing_x` and `spacing_y` from `edge_count` clamped to min/max
- Dispatch to `_weed_<strategy>(...)` which returns `list[Path]` (each path is 2 points)
- If adaptive: run each returned path through `_adaptive_clip` against the original routes
- Append resulting paths to `self.routes`

---

## Strategy Implementations

### `grid` / `horizontal` / `vertical`
Step y from `min_y − margin` to `max_y + margin` in `spacing_y` increments (horizontal lines).
Each line: `[(min_x − margin, y), (max_x + margin, y)]`.
Verticals use `spacing_x` and step in x. Omit the other axis for `horizontal`/`vertical`.

### `diagonal` / `diamond`
Parametrize 45° family as `y − x = c`. Step c at `spacing_diag` increments over the bbox + margin range.
Clip each line to bbox + margin with `_line_bbox_clip`.
`diamond` adds the 135° family (`y + x = c`).

### `frame`
Four two-point paths forming a rectangle at `(min_x − margin, min_y − margin)` → `(max_x + margin, max_y + margin)`.

### `cross`
Centre `(cx, cy)`. One horizontal path full-width, one vertical path full-height.

### `tick`
`edge_count` ticks per edge, evenly spaced along the edge.
Bottom: path from `(x, min_y − margin)` to `(x, min_y − margin + tick_hpgl)`.
Top: `(x, max_y + margin − tick_hpgl)` → `(x, max_y + margin)`.
Left/right: same logic with y steps.

### `radial`
Centre `(cx, cy)`. `edge_count` rays at angles `0, 360/N, 2*360/N, …`.
Each ray clipped to bbox + margin, emitted as `[(cx, cy), endpoint]`.

### `bridge`
1. Collect closed paths: `[p for p in self.routes if p[0] == p[-1]]`
2. For each closed path → each of the 4 bbox edges: find path point nearest the edge; emit perpendicular line from that point to the edge + margin.
3. For each pair of closed paths: brute-force nearest point pair; if distance < `spacing_hpgl` (average of x/y), emit a bridge line between them.

---

## CLI Arguments (add to both `hpgl.py __main__` and `plottool.py`)

```
--weed STRATEGY          Strategy: grid, horizontal, vertical, diagonal, diamond,
                         frame, cross, tick, radial, bridge
--weed-edge-count N      Lines crossing each bbox edge / number of radial lines / ticks per edge (default: 4)
--weed-min-x MM          Min spacing between vertical weeding lines in mm (default: 5)
--weed-max-x MM          Max spacing between vertical weeding lines in mm (default: 50)
--weed-min-y MM          Min spacing between horizontal weeding lines in mm (default: 5)
--weed-max-y MM          Max spacing between horizontal weeding lines in mm (default: 50)
--weed-margin MM         Extend lines beyond bbox in mm (default: 2)
--weed-tick-length MM    Tick/comb tooth length in mm (default: 5)
--no-weed-adaptive       Disable adaptive splitting (default: on)
```

---

## Wiring in `apply_args()` (at end, after tiling)

```python
weed = getattr(args, 'weed', None)
if weed:
    hpgl_obj.addWeedingLines(
        strategy=weed,
        edge_count=getattr(args, 'weed_edge_count', 4) or 4,
        min_spacing_x=getattr(args, 'weed_min_x', 5.0) or 5.0,
        max_spacing_x=getattr(args, 'weed_max_x', 50.0) or 50.0,
        min_spacing_y=getattr(args, 'weed_min_y', 5.0) or 5.0,
        max_spacing_y=getattr(args, 'weed_max_y', 50.0) or 50.0,
        margin=getattr(args, 'weed_margin', 2.0) or 2.0,
        tick_length=getattr(args, 'weed_tick_length', 5.0) or 5.0,
        adaptive=not getattr(args, 'no_weed_adaptive', False),
    )
```

---

## Files to Modify

| File | Changes |
|------|---------|
| `hpgl.py` | Add geometry helpers, `addWeedingLines` + strategy sub-functions, CLI args in `__main__`, weed block in `apply_args` |
| `plottool.py` | Add same CLI args |

## Ordering in `apply_args`

Weeding lines are added **last** (after tiling) so they cover the final layout.

---

## Verification

1. `python hpgl.py test.hpgl -p out.svg --weed grid` — inspect SVG for correct H+V lines.
2. Each strategy: inspect SVG output for correct geometry.
3. Adaptive clipping: verify weeding lines are split at design crossings (gaps visible at intersections in SVG).
4. `bridge` with a multi-letter design.
5. Tiling + weeding: weeding lines should cover the full tiled extent.
6. min/max clamping: use a very small design with `--weed-max-x 10` and confirm spacing is capped.
