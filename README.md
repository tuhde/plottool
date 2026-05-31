plottool
========

A tool for sending HPGL files to a plotter or cutting plotter connected over a
serial port. Includes path optimization, blade offset compensation, tiling, and
a graphical preview window.

Tested with a Cogi CT-630 cutting plotter @ Stratum0:
https://stratum0.org/wiki/Cogi_CT-630

Also works on macOS, but less reliably — prepare for occasional job cancellation.

> This project is being actively extended with the help of
> [Claude Code](https://claude.ai/code) (Anthropic AI).

What's new
----------

**Weeding lines** — after processing, add extra cut lines to the design to help
remove waste vinyl. Eight strategies are available:

| Strategy | Description |
|----------|-------------|
| `grid` | Horizontal + vertical lines across the bbox |
| `horizontal` / `vertical` | Single-axis grid lines |
| `diagonal` | 45° lines across the bbox |
| `rombic` | Both diagonal families (diamond grid) |
| `frame` | Concentric equal-area rectangles stepping inward |
| `tick` | Short inward comb-teeth from each bbox edge |
| `radial` | Evenly-angled spokes from the bbox centre |

Line count is controlled by `--weed-size PCT` (max waste piece size as % of bbox
area, default 25). All strategies support **adaptive clipping** (default on):
weeding lines are split at design intersections and only waste-area segments are
kept. An outer frame rectangle (default 1 mm from the bbox) is added automatically.

See [WEEDING_LINES.md](WEEDING_LINES.md) for full strategy and parameter details.

**Improved preview** — the preview window now shows:
- Direction arrows on cut paths, travel moves, and the return-to-origin line
- Dotted travel (pen-up) lines
- Start-of-cut (filled blue dot) and end-of-cut (blue ring) markers at every pen transition
- The design bounding box before weeding lines are added (green rectangle)

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
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `-p`, `--port PORT` | `/dev/ttyUSB0` | Serial port |
| `-b`, `--baud BAUD` | `9600` | Serial baud rate |
| `-m`, `--magic` | off | Enable auto-optimize (optimize + blade offset + reroute xy) |
| `-w`, `--width WIDTH` | — | Scale design to WIDTH mm wide |
| `-v`, `--preview` | off | Show preview window before plotting |
| `-o`, `--output FILE` | — | Save processed HPGL to FILE before plotting |
| `--mirror` | off | Mirror on X-axis (for inverted cuts, e.g. T-shirts) |
| `--pen` | off | Disable blade offset compensation (use for pen plotters) |
| `--blade-offset MM` | `0.25` | Blade trailing offset in mm (ignored with `--pen`) |
| `--reroute {xy,nearest,none}` | `xy` | Reroute paths: `xy` = boustrophedon rows, `nearest` = greedy nearest-neighbour, `none` = keep original order |
| `--repeat-x N` | `1` | Tile the design N times along the X axis |
| `--repeat-y N` | `1` | Tile the design N times along the Y axis |
| `--gap MM` | `5` | Gap between tiles in mm |
| `--weed STRATEGY` | — | Add weeding lines (grid, horizontal, vertical, diagonal, rombic, frame, tick, radial) |
| `--weed-size PCT` | `25` | Max waste piece size as % of bbox area |
| `--weed-small-size PCT` | auto | Radial inner circle area as % of bbox (default: weed-size/10) |
| `--weed-min-size PCT` | auto | Drop weeding lines creating waste pieces smaller than this (default: weed-small-size/10) |
| `--weed-margin MM` | `2` | Extend weeding lines beyond bbox in mm |
| `--weed-frame-distance MM` | `1` | Distance of outer frame from bbox |
| `--no-weed-frame` | — | Suppress the automatic outer frame |
| `--no-weed-adaptive` | — | Disable adaptive clipping |

On macOS, tty devices follow a different naming convention — look for something
like `/dev/tty.usbserial-14430` or `/dev/cu.usbserial-14430`.

Usage — hpgl.py
----------------

Process an HPGL file without plotting (convert, optimise, export):

```
./hpgl.py file.hpgl -o out.hpgl -p preview.svg
```

**Options:**

| Flag | Default | Description |
|------|---------|-------------|
| `-p`, `--preview SVG` | — | Export an SVG preview |
| `-o`, `--output HPGL` | — | Write processed HPGL to file |
| `-m`, `--magic` | off | Enable auto-optimize |
| `-w`, `--width WIDTH` | — | Scale to WIDTH mm wide |
| `--mirror` | off | Mirror on X-axis |
| `--pen` | off | Disable blade offset compensation |
| `--blade-offset MM` | `0.25` | Blade trailing offset in mm (ignored with `--pen`) |
| `--reroute {xy,nearest,none}` | `xy` | Reroute paths (`xy` default) |
| `--repeat-x N` | `1` | Tile N times along X |
| `--repeat-y N` | `1` | Tile N times along Y |
| `--gap MM` | `5` | Gap between tiles in mm |
| `--weed STRATEGY` | — | Add weeding lines (see strategies above) |
| `--weed-size PCT` | `25` | Max waste piece size as % of bbox area |
| `--weed-small-size PCT` | auto | Radial inner circle area as % of bbox (default: weed-size/10) |
| `--weed-min-size PCT` | auto | Drop weeding lines creating waste pieces smaller than this (default: weed-small-size/10) |
| `--weed-margin MM` | `2` | Extend weeding lines beyond bbox in mm |
| `--weed-frame-distance MM` | `1` | Distance of outer frame from bbox |
| `--no-weed-frame` | — | Suppress the automatic outer frame |
| `--no-weed-adaptive` | — | Disable adaptive clipping |

Preview window
--------------

The preview window (`-v` / `--preview`) shows the processed paths before
sending to the plotter.

| Input | Action |
|-------|--------|
| Left-drag | Pan |
| Scroll wheel | Zoom (centred on cursor) |
| `+` / `=` | Zoom in |
| `-` | Zoom out |
| `f` | Fit view |
| Arrow keys | Pan |
| Enter | Confirm (dialog mode) |
| Esc | Cancel |
