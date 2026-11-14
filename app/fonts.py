# -*- coding: utf-8 -*-
"""字体与文字排版工具。

统一用 MiSans。系统里没装时自动退回微软雅黑，不会崩。
所有需要画在 Canvas 上的文字都应该走 text()，它会测宽并自动截断，
避免文字互相压住或超出面板。
"""
import tkinter as tk
from tkinter import font as tkfont

from . import dpi

# 字重名（Tk 家族名）。MiSans 装了全套字重，用真字重而不是 bold 模拟。
FAMILY = "MiSans"
FAMILY_BOLD = "MiSans Demibold"
FAMILY_LIGHT = "MiSans Light"
FAMILY_FALLBACK = "Microsoft YaHei UI"

_ready = False
_has_misans = False
_cache = {}


def families():
    try:
        return set(tkfont.families())
    except tk.TclError:
        return set()


def setup():
    """检测 MiSans 是否可用。要在 Tk 根窗口建立之后调用。"""
    global _ready, _has_misans
    if _ready:
        return _has_misans
    fams = families()
    _has_misans = FAMILY in fams
    _ready = True
    return _has_misans


def family(bold=False, light=False):
    if _has_misans:
        if bold:
            return FAMILY_BOLD
        if light:
            return FAMILY_LIGHT
        return FAMILY
    return FAMILY_FALLBACK


def font(size, bold=False, light=False):
    """返回一个 tkfont.Font，按 (size, bold, light) 缓存。"""
    key = (int(size), bool(bold), bool(light))
    if key in _cache:
        return _cache[key]
    f = tkfont.Font(family=family(bold, light), size=int(size))
    _cache[key] = f
    return f


def measure(text, size, bold=False, light=False):
    """文字宽度（逻辑像素）。

    Tk 按 DPI 缩放后 measure 返回物理像素，这里除回去，
    这样调用方（布局/截断）永远只用一套逻辑坐标。
    """
    return font(size, bold, light).measure(text) / dpi.factor()


def fit(text, size, max_width, bold=False, light=False):
    """把文字截断到不超过 max_width，超出部分用省略号。"""
    if not text:
        return ""
    if max_width <= 0:
        return ""
    if measure(text, size, bold, light) <= max_width:
        return text
    ell = "…"
    ell_w = measure(ell, size, bold, light)
    if ell_w > max_width:
        return ""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if measure(text[:mid], size, bold, light) + ell_w <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + ell


def wrap(text, size, max_width, bold=False, light=False, max_lines=2):
    """按宽度折行，返回行列表。最多 max_lines 行，最后一行超长会截断。"""
    if not text:
        return []
    lines, cur = [], ""
    for ch in text:
        trial = cur + ch
        if measure(trial, size, bold, light) <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = ch
            if len(lines) >= max_lines:
                break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines:
        # 检查是否还有没排完的内容
        joined = "".join(lines)
        if len(joined) < len(text):
            lines[-1] = fit(lines[-1] + "…", size, max_width, bold, light)
    return lines


def draw(cv, x, y, text, size, fill, anchor="nw", max_width=None,
         bold=False, light=False, tags=()):
    """在 Canvas 上画一行文字，可选自动截断。返回 item id。"""
    if max_width is not None:
        text = fit(text, size, max_width, bold, light)
    if not text:
        return None
    return cv.create_text(x, y, text=text, fill=fill, anchor=anchor,
                          font=font(size, bold, light), tags=tags)


# ---------- Pillow 用的字体（逐像素透明绘制需要） ----------
_PIL_FILES = {
    False: ("MiSans-Regular.ttf", "MiSans-Light.ttf", "msyh.ttc"),
    True: ("MiSans-Demibold.ttf", "MiSans-Bold.ttf", "msyhbd.ttc"),
}
_pil_cache = {}


def pil_font(size, bold=False):
    """返回可给 PIL ImageDraw 用的字体。"""
    from PIL import ImageFont
    key = (int(size), bool(bold))
    if key in _pil_cache:
        return _pil_cache[key]
    import os
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for name in _PIL_FILES[bool(bold)]:
        path = os.path.join(windir, "Fonts", name)
        if os.path.isfile(path):
            try:
                f = ImageFont.truetype(path, int(size))
                _pil_cache[key] = f
                return f
            except OSError:
                continue
    try:
        f = ImageFont.load_default()
    except Exception:
        f = None
    _pil_cache[key] = f
    return f


def pil_text_width(text, size, bold=False):
    try:
        f = pil_font(size, bold)
        return f.getlength(text) if hasattr(f, "getlength") else len(text) * size // 2
    except Exception:
        return len(text) * size // 2


def pil_fit(text, size, max_width, bold=False):
    """按像素宽度截断（Pillow 版）。"""
    if not text or max_width <= 0:
        return ""
    if pil_text_width(text, size, bold) <= max_width:
        return text
    ell = "…"
    ew = pil_text_width(ell, size, bold)
    if ew > max_width:
        return ""
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if pil_text_width(text[:mid], size, bold) + ew <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + ell
