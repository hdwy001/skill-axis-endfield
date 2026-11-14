# -*- coding: utf-8 -*-
"""高 DPI 支持。

Windows 默认会把「没声明 DPI 感知」的程序整窗按比例位图放大
（150% 缩放 = 先画 1320×880 再拉到 1980×1320），字和图标全糊。

这里的做法：
    · 开窗前声明系统级 DPI 感知 -> 不会再有位图拉伸
    · 布局代码继续按「逻辑像素」写，用 S() 换到物理像素
    · Canvas 统一走 app/scaledcanvas.py，坐标/事件自动换算

所以：**不要在界面代码里直接写物理像素**，需要尺寸就 S(逻辑值)。
"""

import ctypes

_factor = None

LOGPIXELSX = 88


def enable():
    """声明 DPI 感知。必须在创建任何窗口之前调用。返回缩放因子。"""
    global _factor
    if _factor is not None:
        return _factor
    try:
        # 1 = PROCESS_SYSTEM_DPI_AWARE（Win8.1+）
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    _factor = _query()
    return _factor


def _query():
    try:
        user32 = ctypes.windll.user32
        dc = user32.GetDC(0)
        try:
            dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, LOGPIXELSX)
        finally:
            user32.ReleaseDC(0, dc)
        if dpi and 72 <= dpi <= 480:
            return round(dpi / 96.0, 4)
    except Exception:
        pass
    return 1.0


def factor():
    """当前缩放因子（96 DPI = 1.0，150% = 1.5）。"""
    return _factor if _factor else 1.0


def is_high():
    return factor() > 1.001


def S(v):
    """逻辑像素 -> 物理像素。"""
    return int(round(float(v) * factor()))


def Spair(v):
    """(x, y) 或单个数字 -> 物理像素元组/数字，给 padx/pady 用。"""
    if isinstance(v, (tuple, list)):
        return tuple(S(x) for x in v)
    return S(v)


def unS(v):
    """物理像素 -> 逻辑像素（鼠标坐标换算用）。"""
    return float(v) / factor()
