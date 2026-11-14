# -*- coding: utf-8 -*-
"""按 DPI 自动缩放的 Canvas。

界面代码仍然按「逻辑像素」画：create_text(10, 20, ...) 里的 10/20
就是设计稿上的位置；本类在交给 Tk 前统一乘上 dpi 因子，
回调时再把事件坐标除回去，于是布局代码完全不用管 DPI。

用法：把 tk.Canvas(...) 换成 ScaledCanvas(...)，其余照旧。
"""

import tkinter as tk

from . import dpi

# 这些 create_* 的前 4 个参数是坐标
_XY4 = ("create_rectangle", "create_oval", "create_arc")
# 前 2 个参数是坐标
_XY2 = ("create_text", "create_image", "create_line")


class ScaledEvent:
    """把 Tk 事件的坐标换算回逻辑像素。"""

    __slots__ = ("_e", "_f")

    def __init__(self, e, f):
        self._e = e
        self._f = f

    @property
    def x(self):
        return self._e.x / self._f

    @property
    def y(self):
        return self._e.y / self._f

    def __getattr__(self, name):
        return getattr(self._e, name)


class ScaledCanvas(tk.Canvas):
    def __init__(self, master=None, cnf={}, **kw):
        f = dpi.factor()
        for k in ("width", "height"):
            v = kw.get(k)
            if v:
                kw[k] = int(round(v * f))
        super().__init__(master, cnf, **kw)

    # ---------- 坐标缩放 ----------
    def _s(self, v):
        return v * dpi.factor()

    def _scale_pts(self, args):
        f = dpi.factor()
        out = []
        for v in args:
            try:
                out.append(v * f)
            except TypeError:
                out.append(v)          # 例如 None
        return tuple(out)

    @staticmethod
    def _scale_kw(kw):
        f = dpi.factor()
        for k in ("width", "height", "dash", "dashoffset", "offset"):
            v = kw.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                kw[k] = v * f
        return kw

    # ---------- create_* ----------
    def create_text(self, x, y, **kw):
        return super().create_text(self._s(x), self._s(y), **kw)

    def create_image(self, x, y, **kw):
        return super().create_image(self._s(x), self._s(y), **kw)

    def create_line(self, *args, **kw):
        return super().create_line(*self._scale_pts(args),
                                   **self._scale_kw(kw))

    def create_polygon(self, *args, **kw):
        if len(args) == 1 and isinstance(args[0], (list, tuple)):
            pts = self._scale_pts(args[0])
        else:
            pts = self._scale_pts(args)
        return super().create_polygon(pts, **self._scale_kw(kw))

    def create_rectangle(self, x1, y1, x2, y2, **kw):
        return super().create_rectangle(self._s(x1), self._s(y1),
                                        self._s(x2), self._s(y2),
                                        **self._scale_kw(kw))

    def create_oval(self, x1, y1, x2, y2, **kw):
        return super().create_oval(self._s(x1), self._s(y1),
                                   self._s(x2), self._s(y2),
                                   **self._scale_kw(kw))

    def create_arc(self, x1, y1, x2, y2, **kw):
        return super().create_arc(self._s(x1), self._s(y1),
                                  self._s(x2), self._s(y2),
                                  **self._scale_kw(kw))

    def create_window(self, x, y, **kw):
        for k in ("width", "height"):
            v = kw.get(k)
            if isinstance(v, (int, float)):
                kw[k] = int(round(v * dpi.factor()))
        return super().create_window(self._s(x), self._s(y), **kw)

    def coords(self, *args):
        if len(args) == 1 and isinstance(args[0], (list, tuple)):
            return super().coords(args[0], *self._scale_pts(args[1:]))
        item, rest = args[0], args[1:]
        return super().coords(item, *self._scale_pts(rest))

    # ---------- 其它 ----------
    def configure(self, cnf=None, **kw):
        f = dpi.factor()
        for k in ("height", "width"):
            v = kw.get(k)
            if isinstance(v, (int, float)):
                kw[k] = int(round(v * f))
        sr = kw.get("scrollregion")
        if isinstance(sr, (list, tuple)):
            kw["scrollregion"] = tuple(int(round(v * f)) for v in sr)
        return super().configure(cnf, **kw)

    config = configure

    def itemconfigure(self, tagOrId, cnf=None, **kw):
        for k in ("width",):
            v = kw.get(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                kw[k] = v * dpi.factor()
        return super().itemconfigure(tagOrId, cnf, **kw)

    itemconfig = itemconfigure

    def winfo_width(self):
        return int(round(super().winfo_width() / dpi.factor()))

    def winfo_height(self):
        return int(round(super().winfo_height() / dpi.factor()))

    def canvasx(self, screenx, gridspacing=None):
        return super().canvasx(screenx, gridspacing) / dpi.factor()

    def canvasy(self, screeny, gridspacing=None):
        return super().canvasy(screeny, gridspacing) / dpi.factor()

    def bbox(self, *args):
        box = super().bbox(*args)
        if not box:
            return box
        f = dpi.factor()
        return tuple(int(round(v / f)) for v in box)

    # ---------- 事件坐标换算 ----------
    def bind(self, sequence=None, func=None, add=None):
        if func is not None:
            f = dpi.factor()
            raw = func

            def wrapped(e, _raw=raw, _f=f):
                return _raw(ScaledEvent(e, _f))
            wrapped.__name__ = getattr(raw, "__name__", "handler")
            func = wrapped
        return super().bind(sequence, func, add)

    def tag_bind(self, tagOrId, sequence=None, func=None, add=None):
        if func is not None:
            f = dpi.factor()
            raw = func

            def wrapped(e, _raw=raw, _f=f):
                return _raw(ScaledEvent(e, _f))
            wrapped.__name__ = getattr(raw, "__name__", "handler")
            func = wrapped
        return super().tag_bind(tagOrId, sequence, func, add)
