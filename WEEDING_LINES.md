# Weeding Lines

After cutting, vinyl must be **weeded**: the waste material around and between the design
elements is peeled off.  Large blank areas are hard to grip.  Weeding lines are extra cut
lines added to break up those areas into manageable pieces.

---

## Vocabulary

### Part
A region of vinyl that **stays** after cutting — the design element you keep.  Its boundary
is formed by one or more cut paths (not necessarily closed); the cut path may be open, with
the sheet/bbox edge completing the enclosure.  The material *outside* parts is waste.

### Edge
One straight side of the bounding box of the original motif (top, bottom, left, right).

### Motif
The sum of all parts — the complete design that remains on the carrier medium after weeding.

### Visibility
Part A is **visible** to part B if a straight line can be drawn between them without crossing
or touching any third part.

### Bridge
A weeding line connecting two mutually visible parts, or a part and an edge.

### Interior
A waste space enclosed *within* a part — a hole inside the part's boundary.  Like a part,
it is not necessarily enclosed by a closed path.

---

## Strategies

| Name | Description |
|------|-------------|
| `grid` | Horizontal + vertical lines across the bbox |
| `horizontal` | Horizontal lines only |
| `vertical` | Vertical lines only |
| `diagonal` | 45° lines across the bbox |
| `rombic` | Both 45° diagonal families (diamond grid) |
| `frame` | Concentric equal-area rectangles from the bbox edge inward |
| `tick` | Short inward comb-teeth from each bbox edge |
| `radial` | Evenly-angled spokes from the bbox centre |

---

## Parameters

| CLI flag | Default | Applies to | Meaning |
|----------|---------|------------|---------|
| `--weed STRATEGY` | — | all | Strategy name (see table above) |
| `--weed-size PCT` | `25` | all | Max waste piece size as % of bbox area |
| `--weed-small-size PCT` | `weed-size/10` | `radial` | Inner circle area as % of bbox area |
| `--weed-min-size PCT` | `weed-small-size/10` | all | Drop weeding lines that create waste pieces smaller than this |
| `--weed-min-x MM` | `1` | grid-family | Min spacing between vertical weeding lines |
| `--weed-max-x MM` | ∞ | grid-family | Max spacing between vertical weeding lines |
| `--weed-min-y MM` | `1` | grid-family | Min spacing between horizontal weeding lines |
| `--weed-max-y MM` | ∞ | grid-family | Max spacing between horizontal weeding lines |
| `--weed-margin MM` | `2` | all | Extend weeding lines beyond bbox |
| `--weed-tick-length MM` | `5` | `tick` | Tooth length |
| `--weed-frame-distance MM` | `1` | all | Distance of the outer frame from the bbox |
| `--no-weed-frame` | — | all | Suppress the automatic outer frame rectangle |
| `--no-weed-adaptive` | — | all | Disable adaptive clipping |

`--weed-size` drives the line count for all strategies:

| Strategy | Derived count |
|----------|---------------|
| `grid` / `diagonal` / `rombic` / `tick` | `ceil(sqrt(100 / weed_size))` lines per axis |
| `horizontal` / `vertical` | `ceil(100 / weed_size)` lines |
| `frame` | rings at scale `sqrt(1 − k × weed_size/100)` until the ring collapses |
| `radial` | `round(effective_area / (bbox_area × weed_size/100))` spokes |

---

## Adaptive Clipping

Each generated weeding line is split at every intersection with existing design paths.
Sub-segments whose midpoint lies *inside* a part (even-odd rule) are discarded; only
waste-area segments are kept.  This prevents double-cutting through the design and avoids
cutting through part material.

Enabled by default; disable with `--no-weed-adaptive`.

---

## Strategy Details

### `frame`

Concentric rectangles scaled so each ring encloses equal area.  Scale factor for ring *k*:

```
s_k = sqrt(1 − k × weed_size / 100)
```

Rings are emitted until `s_k ≤ 0` or the rectangle degenerates.

### `radial`

Spokes radiate from the bbox centre at equal angular intervals.

**Spoke count** is derived from area:

```
n_spokes = round(effective_area / (bbox_area × weed_size / 100))
```

where `effective_area = bbox_area − π × inner_r²`.

**Inner circle** — when the centre lies in waste and is enclosed by a route:

- *Large interior* (enclosing route's bbox area ≥ `weed_size`% of bbox): an inner circle of
  area `weed_small_size`% of bbox is added; spokes start from the circle boundary.
- *Small interior* (enclosing route's bbox area < `weed_size`%): no circle; spokes start
  from the interior boundary so no segment falls inside the hole.

