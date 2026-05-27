#!/usr/bin/env python3

import wx
from wx.lib.floatcanvas import FloatCanvas, GUIMode
import hpgl
import numpy

# fix broken reference to float_ in wxPython 4.2.0
FloatCanvas.float_ = numpy.float64

HPGL2MM = hpgl.hpgl2mm(1)
ZOOM_FACTOR = 1.3
PAN_STEP = 50  # pixels per cursor-key press


def XYPlotterScale(center):
    # Invert the Y axis so the canvas matches HPGL coordinates (Y increases
    # upward), rather than screen coordinates (Y increases downward).
    # center is unused; FloatCanvas requires this signature.
    return (-1.0, 1.0)


class HPGLPreview(wx.Frame):

    def __init__(self, hpgldata, title="HPGL preview", size=(1200, 700), dialog=False, *args, **kwargs):
        super(HPGLPreview, self).__init__(parent=None, title=title, size=size, *args, **kwargs)
        self.checked = False
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

        last = (0, 0)
        for line in hpgldata.getPaths():
            self.Canvas.AddLine(line)
            self.Canvas.AddLine([last, line[0]], LineColor="blue")
            last = line[-1]
        self.Canvas.AddLine([last, (0, 0)], LineColor="green")
        m, mm = hpgldata.getBoundingBox()
        self.Canvas.AddRectangle((0, 0), (mm[0] + m[0], mm[1] + m[1]), LineColor="orange")

        # GUIMove: left-drag pans, mouse wheel zooms (via ZoomWithMouseWheel mixin).
        # No additional bindings needed for either behaviour.
        self.Canvas.SetMode(GUIMode.GUIMove())

        self.btn_zoom_in.Bind(wx.EVT_BUTTON,  lambda e: self.Canvas.Zoom(ZOOM_FACTOR))
        self.btn_zoom_out.Bind(wx.EVT_BUTTON, lambda e: self.Canvas.Zoom(1.0 / ZOOM_FACTOR))
        self.btn_fit.Bind(wx.EVT_BUTTON,      lambda e: self.Canvas.ZoomToBB())

        # EVT_MOTION is also bound internally by FloatCanvas; event.Skip() lets that run too.
        self.Canvas.Bind(wx.EVT_MOTION, self.OnMove)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_CHAR_HOOK, self.OnKeyDown)

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
    args = parser.parse_args()

    hpglfile = hpgl.HPGL(args.file)

    dialog = HPGLPreview(hpglfile)

    dialog.ShowModal()
