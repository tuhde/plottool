#!/usr/bin/env python3

import math
import wx
from wx.lib.floatcanvas import FloatCanvas, GUIMode
import hpgl
import numpy

# fix broken reference to float_ in wxPython 4.2.0
FloatCanvas.float_ = numpy.float64

HPGL2MM = hpgl.hpgl2mm(1)
ZOOM_FACTOR = 1.3
PAN_STEP = 50  # pixels per cursor-key press
ARROW_SIZE = 50  # HPGL units (~1.25 mm)


_MARKER_N = 20  # polygon sides used to approximate circles

def _marker_pts(pt, radius):
    return [(pt[0] + radius * math.cos(2 * math.pi * i / _MARKER_N),
             pt[1] + radius * math.sin(2 * math.pi * i / _MARKER_N))
            for i in range(_MARKER_N)]

def _draw_start_marker(canvas, pt, color, radius):
    """Filled polygon (pen-down / start of cut)."""
    canvas.AddPolygon(_marker_pts(pt, radius), LineColor=color, FillColor=color)

def _draw_end_marker(canvas, pt, color, radius):
    """Circle outline polygon (pen-up / end of cut)."""
    pts = _marker_pts(pt, radius)
    pts.append(pts[0])  # close the loop
    canvas.AddLine(pts, LineColor=color, LineWidth=2)

def _draw_arrow(canvas, path, color):
    """Draw a small V-shaped direction arrowhead at the midpoint of path."""
    mid = max(1, len(path) // 2)
    p1, p2 = path[mid - 1], path[mid]
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    ln = math.hypot(dx, dy)
    if ln < ARROW_SIZE * 0.5:
        return
    mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    ux, uy = dx / ln, dy / ln
    ca, sa = math.cos(math.radians(30)), math.sin(math.radians(30))
    bx, by = -ux * ARROW_SIZE, -uy * ARROW_SIZE
    w1 = (mx + ca * bx - sa * by, my + sa * bx + ca * by)
    w2 = (mx + ca * bx + sa * by, my - sa * bx + ca * by)
    canvas.AddLine([w1, (mx, my), w2], LineColor=color)


def XYPlotterScale(center):
    # Invert the Y axis so the canvas matches HPGL coordinates (Y increases
    # upward), rather than screen coordinates (Y increases downward).
    # center is unused; FloatCanvas requires this signature.
    return (-1.0, 1.0)


class HPGLPreview(wx.Frame):

    def __init__(self, hpgldata, title="HPGL preview", size=(1600, 900), dialog=False,
                 show_endpoints=True, show_points=False, *args, **kwargs):
        super(HPGLPreview, self).__init__(parent=None, title=title, size=size, *args, **kwargs)
        self.checked = False
        self._hpgl_paths = list(hpgldata.getPaths())
        self.CreateStatusBar()

        self.sizer = wx.BoxSizer(wx.VERTICAL)

        # Toolbar: zoom in/out and fit-to-view.
        # Pan is always active via left-drag (GUIMove mode), so no pan button needed.
        # Wheel zoom is also always active because GUIMove inherits ZoomWithMouseWheel.
        tb = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_zoom_in  = wx.Button(self, label="+",   size=(30, 28))
        self.btn_zoom_out = wx.Button(self, label="−",   size=(30, 28))
        self.btn_fit      = wx.Button(self, label="Fit", size=(40, 28))
        for btn in (self.btn_zoom_in, self.btn_zoom_out, self.btn_fit):
            tb.Add(btn, 0, wx.LEFT | wx.TOP | wx.BOTTOM, 2)
        self.sizer.Add(tb, 0, wx.ALL, 0)

        self.Canvas = FloatCanvas.FloatCanvas(self, -1, ProjectionFun=XYPlotterScale, BackgroundColor="white")
        self.sizer.Add(self.Canvas, 1, wx.ALL | wx.EXPAND)

        # summary bar
        w, h = hpgldata.getSize()
        travel, draw = hpgldata.getLength()
        n_paths = len(hpgldata.getPaths())
        summary = (
            "Size: {:.1f} × {:.1f} mm  |  Area: {:.1f} cm²  |  "
            "Paths: {}  |  Cut: {:.1f} cm  |  Travel: {:.1f} cm"
        ).format(w, h, w / 10 * h / 10, n_paths, draw / 10, travel / 10)
        self.summary_label = wx.StaticText(self, label=summary, style=wx.ALIGN_CENTER)
        self.sizer.Add(self.summary_label, 0, wx.ALL | wx.EXPAND, 4)

        hpgl_row = wx.BoxSizer(wx.HORIZONTAL)
        hpgl_row.Add(wx.StaticText(self, label="Path HPGL:"), 0, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 4)
        self.hpgl_field = wx.TextCtrl(self, style=wx.TE_READONLY | wx.TE_PROCESS_ENTER, size=(-1, -1))
        hpgl_row.Add(self.hpgl_field, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 4)
        self.sizer.Add(hpgl_row, 0, wx.ALL | wx.EXPAND, 2)

        self.bsizer = wx.BoxSizer(wx.HORIZONTAL)
        if dialog:
            self.btn_ok = wx.Button(self, wx.ID_OK, label="OK")
            self.btn_cancel = wx.Button(self, wx.ID_CANCEL, label="Cancel")
            self.bsizer.AddStretchSpacer(1)
            self.bsizer.Add(self.btn_ok, 0, wx.EXPAND | wx.RIGHT, 5)
            self.bsizer.Add(self.btn_cancel, 0, wx.EXPAND | wx.LEFT, 5)
            self.btn_ok.Bind(wx.EVT_BUTTON, self.OnOK)
            self.btn_cancel.Bind(wx.EVT_BUTTON, self.OnCancel)
            self.bsizer.AddStretchSpacer(1)
            self.sizer.Add(self.bsizer, 0, wx.ALL | wx.EXPAND, 2)

        self.SetSizer(self.sizer)

        travel_pen = wx.Pen("blue", 1, wx.PENSTYLE_USER_DASH)
        travel_pen.SetDashes([2, 12])  # 1:6 dot:gap ratio in pixels

        last = (0, 0)
        for line in hpgldata.getPaths():
            self.Canvas.AddLine(line)
            _draw_arrow(self.Canvas, line, "black")
            if show_points:
                for pt in line:
                    _draw_start_marker(self.Canvas, pt, "LightBlue", ARROW_SIZE * 0.35)
            travel = [last, line[0]]
            travel_obj = self.Canvas.AddLine(travel, LineColor="blue")
            travel_obj.Pen = travel_pen
            _draw_arrow(self.Canvas, travel, "blue")
            if show_endpoints:
                _draw_start_marker(self.Canvas, line[0],  "SteelBlue", ARROW_SIZE * 0.6)
                _draw_end_marker(  self.Canvas, line[-1], "DarkBlue",  ARROW_SIZE)
            last = line[-1]
        home = [last, (0, 0)]
        self.Canvas.AddLine(home, LineColor="green")
        _draw_arrow(self.Canvas, home, "green")
        m, mm = hpgldata.getBoundingBox()
        self.Canvas.AddRectangle((0, 0), (mm[0] + m[0], mm[1] + m[1]), LineColor="orange")
        if hasattr(hpgldata, '_design_bbox'):
            dm, dmm = hpgldata._design_bbox
            self.Canvas.AddRectangle((dm[0], dm[1]), (dmm[0] - dm[0], dmm[1] - dm[1]),
                                     LineColor="green")

        # GUIMove: left-drag pans, mouse wheel zooms (via ZoomWithMouseWheel mixin).
        # No additional bindings needed for either behaviour.
        self.Canvas.SetMode(GUIMode.GUIMove())

        self.btn_zoom_in.Bind(wx.EVT_BUTTON,  lambda e: self.Canvas.Zoom(ZOOM_FACTOR))
        self.btn_zoom_out.Bind(wx.EVT_BUTTON, lambda e: self.Canvas.Zoom(1.0 / ZOOM_FACTOR))
        self.btn_fit.Bind(wx.EVT_BUTTON,      lambda e: self.Canvas.ZoomToBB())

        # EVT_MOTION is also bound internally by FloatCanvas; event.Skip() lets that run too.
        self.Canvas.Bind(wx.EVT_MOTION, self.OnMove)
        self.Canvas.Bind(wx.EVT_RIGHT_DOWN, self.OnCanvasRightClick)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_CHAR_HOOK, self.OnKeyDown)

    def _segment_dist(self, px, py, ax, ay, bx, by):
        """Minimum distance from point (px,py) to segment (ax,ay)-(bx,by)."""
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    def _nearest_path_index(self, wx_coord, wy_coord):
        best_idx, best_dist = 0, float('inf')
        for i, path in enumerate(self._hpgl_paths):
            for j in range(len(path) - 1):
                d = self._segment_dist(wx_coord, wy_coord,
                                       path[j][0], path[j][1],
                                       path[j + 1][0], path[j + 1][1])
                if d < best_dist:
                    best_dist, best_idx = d, i
        return best_idx

    @staticmethod
    def _path_to_hpgl(path):
        first = path[0]
        rest = path[1:]
        coords = ",".join("{:d},{:d}".format(int(round(x)), int(round(y))) for x, y in rest)
        return "PU{:d},{:d};PD{};".format(int(round(first[0])), int(round(first[1])), coords)

    def OnCanvasRightClick(self, event):
        world = self.Canvas.PixelToWorld(event.GetPosition())
        idx = self._nearest_path_index(world[0], world[1])
        self.hpgl_field.SetValue(self._path_to_hpgl(self._hpgl_paths[idx]))
        self.hpgl_field.SelectAll()
        event.Skip()

    def OnKeyDown(self, event):
        key = event.GetKeyCode()
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.OnOK(event)
        elif key == wx.WXK_ESCAPE:
            self.OnCancel(event)
        elif key in (ord('+'), ord('='), wx.WXK_NUMPAD_ADD):
            self.Canvas.Zoom(ZOOM_FACTOR)
        elif key in (ord('-'), wx.WXK_NUMPAD_SUBTRACT):
            self.Canvas.Zoom(1.0 / ZOOM_FACTOR)
        elif key in (ord('f'), ord('F')):
            self.Canvas.ZoomToBB()
        elif key == wx.WXK_LEFT:
            self.Canvas.MoveImage((-PAN_STEP, 0), 'Pixel')
        elif key == wx.WXK_RIGHT:
            self.Canvas.MoveImage((PAN_STEP, 0), 'Pixel')
        elif key == wx.WXK_UP:
            self.Canvas.MoveImage((0, -PAN_STEP), 'Pixel')
        elif key == wx.WXK_DOWN:
            self.Canvas.MoveImage((0, PAN_STEP), 'Pixel')
        else:
            event.Skip()

    def OnOK(self, event):
        self.checked = True
        self.Close()

    def OnCancel(self, event):
        self.Close()

    def OnMove(self, event):
        coords = self.Canvas.PixelToWorld(event.GetPosition())
        self.SetStatusText("%.2f mm, %.2f mm" % (coords[0] * HPGL2MM, coords[1] * HPGL2MM))
        event.Skip()

    def OnClose(self, event):
        self.eventLoop.Exit()

    def ShowModal(self):
        if hasattr(self, "MakeModal"):
            self.MakeModal()  # removed in wxPython 4.x; present on older versions
        self.Show()
        self.Canvas.ZoomToBB()

        # wx.Frame has no native modal loop; run a GUIEventLoop manually to
        # block the caller until OnClose exits it (simulating a modal dialog).
        self.eventLoop = wx.GUIEventLoop()
        self.eventLoop.Run()
        self.Destroy()
        return self.checked


if __name__ == "__main__":
    import argparse
    app = wx.App(False)
    parser = argparse.ArgumentParser("HPGL preview")
    parser.add_argument("file", type=str, help="the HPGL-file to open")
    weed_group = parser.add_argument_group("weeding lines")
    weed_group.add_argument("--weed", metavar="STRATEGY",
                            choices=["grid", "horizontal", "vertical", "frame",
                                     "diagonal", "rombic", "tick", "radial", "bridge"],
                            help="Add weeding lines")
    weed_group.add_argument("--weed-edge-count", metavar="N", type=int, default=4)
    weed_group.add_argument("--weed-min-x", metavar="MM", type=float, default=1.0)
    weed_group.add_argument("--weed-max-x", metavar="MM", type=float, default=None)
    weed_group.add_argument("--weed-min-y", metavar="MM", type=float, default=1.0)
    weed_group.add_argument("--weed-max-y", metavar="MM", type=float, default=None)
    weed_group.add_argument("--weed-margin", metavar="MM", type=float, default=2.0)
    weed_group.add_argument("--weed-tick-length", metavar="MM", type=float, default=5.0)
    weed_group.add_argument("--no-weed-adaptive", action="store_true")
    weed_group.add_argument("--no-weed-frame", action="store_true")
    weed_group.add_argument("--weed-frame-distance", metavar="MM", type=float, default=1.0)
    args = parser.parse_args()

    hpglfile = hpgl.HPGL(args.file)
    hpgl.apply_args(hpglfile, args)

    dialog = HPGLPreview(hpglfile)

    dialog.ShowModal()
