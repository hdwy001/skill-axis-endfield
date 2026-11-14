# -*- coding: utf-8 -*-
"""界面小工具：颜色混合、圆角矩形、文字截断。

图标绘制已迁到 app/iconart.py（用 Pillow 合成，质量更好）。
"""


def blend(c1, c2, t):
    """按 t (0~1) 混合两个 #rrggbb 颜色。"""
    try:
        a = tuple(int(c1[i:i + 2], 16) for i in (1, 3, 5))
        b = tuple(int(c2[i:i + 2], 16) for i in (1, 3, 5))
        return "#%02x%02x%02x" % tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
    except (ValueError, IndexError, TypeError):
        return c1


def rounded_rect(cv, x1, y1, x2, y2, r=12, **kw):
    """在 Canvas 上画圆角矩形（用平滑多边形近似）。"""
    r = max(0, min(r, (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    pts = [
        x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r,
        x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2,
        x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y2 - r,
        x1, y1 + r, x1, y1 + r, x1, y1, x1 + r, y1,
    ]
    return cv.create_polygon(pts, smooth=True, **kw)


def truncate(text, limit):
    if not text:
        return ""
    return text if len(text) <= limit else text[: max(1, limit - 1)] + "…"


def center_window(win, parent=None, width=None, height=None):
    """把窗口放到父窗口正中（没有父窗口就放屏幕正中），并夹在屏幕内。

    width / height 用**逻辑像素**传，内部按 DPI 换成物理像素。
    """
    from . import dpi
    try:
        win.update_idletasks()
        if width is not None:
            width = dpi.S(width)
        if height is not None:
            height = dpi.S(height)
        if width is None:
            width = max(win.winfo_reqwidth(), 200)
        if height is None:
            height = max(win.winfo_reqheight(), 120)
        if parent is not None and parent.winfo_exists():
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        else:
            px = py = 0
            pw = win.winfo_screenwidth()
            ph = win.winfo_screenheight()
        x = px + (pw - width) // 2
        y = py + (ph - height) // 2
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x = max(20, min(x, sw - width - 20))
        y = max(20, min(y, sh - height - 40))
        win.geometry("%dx%d+%d+%d" % (int(width), int(height), int(x), int(y)))
    except Exception:
        pass
