plottool
========

A tool for sending HPGL files to a plotter or cutting plotter connected over a
serial port. Includes path optimization, blade offset compensation, tiling, and
a graphical preview window.

Tested with a Cogi CT-630 cutting plotter @ Stratum0:
https://stratum0.org/wiki/Cogi_CT-630

Also works on macOS, but less reliably — prepare for occasional job cancellation.

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
| `--reroute {xy,nearest}` | — | Reroute paths: `xy` = boustrophedon rows, `nearest` = greedy nearest-neighbour |
| `--repeat-x N` | `1` | Tile the design N times along the X axis |
| `--repeat-y N` | `1` | Tile the design N times along the Y axis |
| `--gap MM` | `5` | Gap between tiles in mm |

On macOS, tty devices follow a different naming convention — look for something
like `/dev/tty.usbserial-14430` or `/dev/cu.usbserial-14430`.

Usage — hpgl.py
----------------

Process an HPGL file without plotting (convert, optimise, export):

```
./hpgl.py file.hpgl -o out.hpgl -p preview.svg
```

**Options:**

| Flag | Description |
|------|-------------|
| `-p`, `--preview SVG` | Export an SVG preview |
| `-o`, `--output HPGL` | Write processed HPGL to file |
| `-m`, `--magic` | Enable auto-optimize |
| `-w`, `--width WIDTH` | Scale to WIDTH mm wide |
| `--mirror` | Mirror on X-axis |
| `--pen` | Disable blade offset compensation |
| `--reroute {xy,nearest}` | Reroute paths |
| `--repeat-x N` | Tile N times along X |
| `--repeat-y N` | Tile N times along Y |
| `--gap MM` | Gap between tiles in mm |
