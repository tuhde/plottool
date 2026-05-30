#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = "doommaster"

import sys
import argparse
from hpgl import HPGL, apply_args
try:
    import serial
except ImportError:
    print("You need to install pyserial. "
          "On Debian/Ubuntu try "
          "sudo apt-get install python3-serial")
    sys.exit(1)


parser = argparse.ArgumentParser(description="Process all arguments ")
parser.add_argument("-p", "--port", metavar="PORT", type=str, help="Serial port (default: /dev/ttyUSB0)", default="/dev/ttyUSB0")
parser.add_argument("-b", "--baud", metavar="BAUD", type=int, help="Serial baud rate (default: 9600)", default=9600)
parser.add_argument("-m", "--magic", action="store_true", help="Enable auto-optimize")
parser.add_argument("-w", "--width", metavar="WIDTH", type=int, help="Scale to width in mm")
parser.add_argument("-v", "--preview", action="store_true", help="Show preview window before plotting")
parser.add_argument("-o", "--output", metavar="FILE", type=str, help="Save processed HPGL to file before plotting")
parser.add_argument("--mirror", action="store_true", help="Mirror on X-axis for inverted cuts (T-Shirts etc.)")
parser.add_argument("--pen", action="store_true", help="Disable cut optimization for rotating knifes")
parser.add_argument("--blade-offset", metavar="MM", type=float, default=0.25, help="Blade offset in mm (default: 0.25, ignored with --pen)")
parser.add_argument("--reroute", choices=["xy", "nearest"], help="Reroute paths: xy (boustrophedon) or nearest (greedy)")
parser.add_argument("--repeat-x", metavar="N", type=int, default=1, help="Tile N times along X axis")
parser.add_argument("--repeat-y", metavar="N", type=int, default=1, help="Tile N times along Y axis")
parser.add_argument("--gap", metavar="MM", type=float, default=5.0, help="Gap between tiles in mm for both axes (default: 5)")
parser.add_argument("--gap-x", metavar="MM", type=float, default=None, help="Gap between tiles along X axis in mm; overrides --gap (negative = overlap)")
parser.add_argument("--gap-y", metavar="MM", type=float, default=None, help="Gap between tiles along Y axis in mm; overrides --gap (negative = overlap)")
parser.add_argument("--offset-x", metavar="MM", type=float, default=0.0, help="X offset per step when repeating along Y axis in mm (stagger rows)")
parser.add_argument("--offset-y", metavar="MM", type=float, default=0.0, help="Y offset per step when repeating along X axis in mm (stagger columns)")
parser.add_argument("file", type=str, help="the HPGL-file you want to plot")
weed_group = parser.add_argument_group("weeding lines")
weed_group.add_argument("--weed", metavar="STRATEGY",
                        choices=["grid", "horizontal", "vertical", "frame",
                                 "diagonal", "rombic", "tick", "radial"],
                        help="Add weeding lines (grid, horizontal, vertical, frame, "
                             "diagonal, rombic, tick, radial)")
weed_group.add_argument("--weed-edge-count", metavar="N", type=int, default=4,
                        help="Number of segments per bbox edge (default: 4)")
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
weed_group.add_argument("--no-weed-adaptive", action="store_true",
                        help="Disable splitting weeding lines at design intersections")
weed_group.add_argument("--no-weed-frame", action="store_true",
                        help="Disable the outer frame rectangle around the bbox")
weed_group.add_argument("--weed-frame-distance", metavar="MM", type=float, default=1.0,
                        help="Distance of outer frame from bbox in mm (default: 1)")
args = parser.parse_args()

try:
    HPGLinput = HPGL(args.file)
except Exception:
    print("no/wrong/empty file given in argument.")
    print("")
    raise


apply_args(HPGLinput, args)

if args.output:
    HPGLinput.exportHPGL(args.output)
    print("Saved processed HPGL to: {}".format(args.output))

print("Plotting file: " + args.file)
w, h = HPGLinput.getSize()
print("Plotting area is {width:.1f}cm x {height:.1f}cm".format(width=w / 10, height=h / 10))
print(" -> Total area:     {area:.1f} cm^2".format(area=w / 10 * h / 10))
travel, draw = HPGLinput.getLength()
print(" -> Travel distance: {:.1f} cm".format(travel / 10))
print(" ->   Cut distance: {:.1f} cm".format(draw / 10))

try:
    if args.preview:
        import hpglpreview
        import wx
        app = wx.App(False)
        dialog = hpglpreview.HPGLPreview(HPGLinput, dialog=True)
        if not dialog.ShowModal():
            sys.exit(1)
        cont = 'y'
    else:
        cont = input("continue? (y/n) ")
except KeyboardInterrupt:
    sys.exit(0)
if cont != "y":
    sys.exit(0)

print("Using port: {}".format(args.port))

HPGLdata = HPGLinput.getHPGL()
print("{} characters loaded".format(len(HPGLdata)))

try:
    with serial.Serial(
        port=args.port,
        baudrate=args.baud,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS,
        rtscts=True,   # hardware flow control is essential: the plotter has a small
        dsrdtr=True    # input buffer and will silently drop data without RTS/CTS throttling
    ) as port:
        # Send one command at a time; pyserial blocks on write() when the
        # plotter asserts CTS-not-ready, so flow control handles throttling.
        splitted = HPGLdata.split(";")
        total = len(splitted)

        sys.stdout.write("starting...")

        for i, command in enumerate(splitted):
            sys.stdout.write("\rsending... {percent:.1f}% done ({done}/{total})".format(percent=(i + 1) * 100.0 / total, done=i + 1, total=total))
            sys.stdout.flush()
            if not command:
                continue
            port.write(command.encode() + b";")
        port.write(b"PU0,0;SP0;SP0;")
        sys.stdout.write("\n")
except serial.serialutil.SerialException:
    print("Failed to open port {}.".format(args.port))
