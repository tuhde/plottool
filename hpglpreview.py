#!/usr/bin/env python3


import wx
from wx.lib.floatcanvas import NavCanvas, FloatCanvas
import hpgl
import numpy

# fix broken reference to float_ in wxPython 4.2.0
FloatCanvas.float_ = numpy.float64

HPGL2MM = hpgl.hpgl2mm(1)


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

        self.Canvas = NavCanvas.NavCanvas(self, -1, ProjectionFun=XYPlotterScale, BackgroundColor="white")
        self.sizer.Add(self.Canvas, 1, wx.ALL | wx.EXPAND)
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
            self.Canvas.Canvas.AddLine(line)

            self.Canvas.Canvas.AddLine([last, line[0]], LineColor="blue")
            last = line[-1]
        self.Canvas.Canvas.AddLine([last, (0, 0)], LineColor="green")
        m, mm = hpgldata.getBoundingBox()

        self.Canvas.Canvas.AddRectangle((0, 0), (mm[0] + m[0], mm[1] + m[1]), LineColor="orange")

        self.Canvas.Canvas.Bind(wx.EVT_MOTION, self.OnMove)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(wx.EVT_CHAR_HOOK, self.OnKeyDown)

    def OnKeyDown(self, event):
        key = event.GetKeyCode()
        if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self.OnOK(event)
        elif key == wx.WXK_ESCAPE:
            self.OnCancel(event)
        else:
            event.Skip()

    def OnOK(self, event):
        self.checked = True
        self.Close()

    def OnCancel(self, event):
        self.Close()

    def OnMove(self, event):
        coords = self.Canvas.Canvas.PixelToWorld(event.GetPosition())
        self.SetStatusText("%.2f mm, %.2f mm" % (coords[0] * HPGL2MM, coords[1] * HPGL2MM))
        event.Skip()

    def OnClose(self, event):
        self.eventLoop.Exit()

    def ShowModal(self):
        if hasattr(self, "MakeModal"):
            self.MakeModal()  # removed in wxPython 4.x; present on older versions
        self.Show()
        self.Canvas.Canvas.ZoomToBB()

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
