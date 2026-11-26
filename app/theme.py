# -*- coding: utf-8 -*-
"""配色与字号。整体按《明日方舟：终末地》的工业冷色 + 琥珀高光来做。"""

from . import fonts
from .iconart import ELEMENT_CN  # 元素中文名，界面多处要用

BG = "#0b0e13"
BG_2 = "#0e1218"
PANEL = "#12161d"
PANEL_2 = "#171c25"
PANEL_3 = "#1e2530"
PANEL_4 = "#252d3a"
BORDER = "#2a3240"
BORDER_LIGHT = "#394455"

TEXT = "#e8edf4"
TEXT_DIM = "#9aa5b4"
TEXT_MUTED = "#6b7686"

# 琥珀色，终末地的主强调色
ACCENT = "#f5c451"
ACCENT_SOFT = "#c99a33"
ACCENT_DARK = "#4a3a14"

# 技能轴类型
CHARGE = "#f5c451"      # 充能轴 —— 黄
BURST = "#e05c4a"       # 爆发轴 —— 红

CYAN = "#57c8d8"
GREEN = "#7ee787"

OK = "#57c8d8"
WARN = "#f5a15c"
BAD = "#e05c4a"

PALETTE = [
    "#4dd0e1", "#f0b429", "#7ee787", "#c084fc", "#ff8a5c",
    "#57c8d8", "#e05c4a", "#a5bd00", "#9b6dd6", "#8b9199",
]

# 字号层级
F_TITLE = 18
F_SECTION = 13
F_BODY = 11
F_SMALL = 10
F_TINY = 9


def font(size, bold=False, light=False):
    """兼容旧代码：统一走 fonts.font（MiSans）。"""
    return fonts.font(size, bold, light)


def text(cv, x, y, s, size, fill, anchor="nw", max_width=None,
         bold=False, light=False, tags=()):
    """画文字，可选自动截断。"""
    return fonts.draw(cv, x, y, s, size, fill, anchor=anchor,
                      max_width=max_width, bold=bold, light=light, tags=tags)
