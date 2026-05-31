plottool
========

A tool for sending HPGL files to a plotter or cutting plotter connected over a
serial port. Includes path optimization, blade offset compensation, scaling,
rotation, tiling, weeding lines, config profiles, and a graphical preview window.

Tested with a Cogi CT-630 cutting plotter @ Stratum0:
https://stratum0.org/wiki/Cogi_CT-630

Also works on macOS, but less reliably — prepare for occasional job cancellation.

> This project is being actively extended with the help of
> [Claude Code](https://claude.ai/code) (Anthropic AI).


Dependencies
------------

For Debian-based Linux distributions (Ubuntu, Mint):

```
sudo apt-get install python3-serial python3-wxgtk4.0 python3-numpy
```

For Arch Linux:

```
sudo pacman -S python-numpy python-pyserial python-wxpython
```

For macOS (homebrew + pip):

```
pip install numpy pyserial && brew install wxpython
```

Or install via pip from the repository root:

```
pip install .
```


Usage — plottool.py
--------------------

Send an HPGL file to the plotter:

```
./plottool.py file.hpgl
./plottool.py file.hpgl -m --width 200
./plottool.py file.hpgl --profile vinyl
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `--profile NAME` | — | Load a config profile (see Config file) |
| `-p`, `--port PORT` | `/dev/ttyUSB0` | Serial port |
| `-b`, `--baud BAUD` | `9600` | Serial baud rate |
| `-m`, `--magic` | off | Auto-optimize: point reduction + blade offset + reroute |
| `-w`, `--width MM` | — | Scale to width in mm (mutually exclusive with `-H`, `-s`) |
| `-H`, `--height MM` | — | Scale to height in mm (mutually exclusive with `-w`, `-s`) |
| `-s`, `--scale FACTOR` | — | Scale by factor, e.g. `0.5` for half size (mutually exclusive with `-w`, `-H`) |
| `--mirror` | off | Flip left-right (for inverted cuts, e.g. T-shirts) |
| `--flip` | off | Flip top-bottom |
| `--rotate DEG` | — | Rotate counter-clockwise by DEG degrees (uses axis swaps at multiples of 90°) |
| `-v`, `--preview` | off | Show preview window before plotting |
| `-o`, `--output FILE` | — | Save processed HPGL to FILE before plotting |
| `--pen` | off | Disable blade offset compensation (use for pen plotters) |
| `--blade-offset MM` | `0.25` | Blade trailing offset in mm (ignored with `--pen`) |
| `--no-blade-prep` | off | Skip the 2 mm seating cut at origin |
| `--reroute {xy,nearest,none}` | `xy` | Path order: `xy` = boustrophedon rows, `nearest` = greedy nearest-neighbour, `none` = original |
| `--repeat-x N` | `1` | Tile the design N times along X |
| `--repeat-y N` | `1` | Tile the design N times along Y |
| `--gap MM` | `5` | Gap between tiles (both axes) |
| `--gap-x MM` | — | Gap along X, overrides `--gap` (negative = overlap) |
| `--gap-y MM` | — | Gap along Y, overrides `--gap` (negative = overlap) |
| `--offset-x MM` | `0` | X offset per Y-step (stagger rows) |
| `--offset-y MM` | `0` | Y offset per X-step (stagger columns) |
| `--weed STRATEGY` | — | Add weeding lines (see Weeding lines) |
| `--weed-size PCT` | `25` | Max waste piece size as % of bbox area |
| `--weed-min-x MM` | `1` | Min spacing between vertical weeding lines |
| `--weed-max-x MM` | — | Max spacing between vertical weeding lines |
| `--weed-min-y MM` | `1` | Min spacing between horizontal weeding lines |
| `--weed-max-y MM` | — | Max spacing between horizontal weeding lines |
| `--weed-margin MM` | `2` | Extend weeding lines beyond bbox |
| `--weed-tick-length MM` | `5` | Tick/comb tooth length |
| `--weed-small-size PCT` | auto | Radial inner circle area (default: weed-size/10) |
| `--weed-min-size PCT` | auto | Drop lines creating waste pieces smaller than this |
| `--weed-frame-distance MM` | `1` | Distance of outer frame from bbox |
| `--no-weed-frame` | — | Suppress the automatic outer frame |
| `--no-weed-adaptive` | — | Disable adaptive clipping at design intersections |

On macOS, serial devices follow a different naming convention — look for something
like `/dev/tty.usbserial-14430` or `/dev/cu.usbserial-14430`.


Usage — hpgl.py
----------------

Process an HPGL file without plotting (convert, optimise, preview, export):

```
./hpgl.py file.hpgl -o out.hpgl -p preview.svg
./hpgl.py file.hpgl -m --rotate 90 -o out.hpgl
```

Supports all flags from `plottool.py` except `--port`, `--baud`, and `--preview`
(which is `-p SVG` here, exporting to an SVG file instead of opening a window).


Processing pipeline
-------------------

When multiple options are active, they are applied in this order:

1. **Scale** (`--width` / `--height` / `--scale`)
2. **Rotate** (`--rotate`)
3. **Mirror** (`--mirror`) — flip left-right
4. **Flip** (`--flip`) — flip top-bottom
5. **Optimize** (`--magic`) — remove redundant points, fit to origin
6. **Blade offset** (`--magic`) — overshoot correction at corners
7. **Tile** (`--repeat-x` / `--repeat-y`)
8. **Weeding lines** (`--weed`)
9. **Reroute** (`--reroute`) — reorder paths for travel efficiency
10. **Blade prep cut** — 2 mm seating cut prepended at origin (disable with `--no-blade-prep`)


Weeding lines
-------------

Add cut lines to help remove waste vinyl after cutting. Select a strategy with
`--weed STRATEGY`:

| Strategy | Description |
|----------|-------------|
| `grid` | Horizontal + vertical lines across the bbox |
| `horizontal` | Horizontal lines only |
| `vertical` | Vertical lines only |
| `diagonal` | 45° lines across the bbox |
| `rombic` | Both diagonal families (diamond grid) |
| `frame` | Concentric equal-area rectangles stepping inward |
| `tick` | Short inward comb-teeth from each bbox edge |
| `radial` | Evenly-angled spokes from the bbox centre |

Line density is controlled by `--weed-size PCT` (max waste piece size as % of bbox
area, default 25). All strategies support **adaptive clipping** (default on): weeding
lines are split at design intersections so only waste-area segments are kept. An outer
frame rectangle (1 mm from bbox by default) is added automatically.

See [WEEDING_LINES.md](WEEDING_LINES.md) for full parameter details.


Config file
-----------

Settings can be stored in `~/.plottoolrc` (global) or `plottool.conf` in the current
directory (local, takes precedence). The format is INI:

```ini
[default]
magic = true
blade-offset = 0.3

[vinyl]
width = 300
reroute = nearest

[shirt]
mirror = true
width = 300

[pen]
pen = true
no-blade-prep = true
```

The `[default]` section always applies. Use `--profile NAME` to also apply a named
section on top. Command-line arguments always override config values. See
`plottool.conf.example` for a full annotated example.


Preview window
--------------

The preview window (`-v` in `plottool.py`, `-p SVG` exports to file in `hpgl.py`)
shows the processed paths with:

- Direction arrows on cut paths, travel moves, and the return-to-origin line
- Dotted travel (pen-up) lines
- Start-of-cut (filled blue dot) and end-of-cut (blue ring) markers at every pen transition
- The design bounding box before weeding lines are added (green rectangle)

Interactive controls (plottool.py preview window):

| Input | Action |
|-------|--------|
| Left-drag | Pan |
| Scroll wheel | Zoom (centred on cursor) |
| `+` / `=` | Zoom in |
| `-` | Zoom out |
| `f` | Fit view |
| Arrow keys | Pan |
| Enter | Confirm and proceed to plot |
| Esc | Cancel |
