# -*- coding: utf-8 -*-
"""悬浮窗内部排版 4 种方案对比图。

输出 preview/overlay_layout_options.png
"""
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from PIL import Image, ImageDraw  # noqa: E402

from app import fonts, theme  # noqa: E402
from app.iconart import ELEMENT_RGB  # noqa: E402
from app.icons import IconStore  # noqa: E402

K = 1.15
BOOST = 1.2
W, H = int(480 * K), int(392 * K)

OUT = os.path.join(BASE, "preview", "overlay_layout_options.png")

icons = IconStore(BASE)


def rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def blend(c1, c2, t):
    a, b = rgb(c1), rgb(c2)
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# ---------- 素材：造一条 6 个技能的序列 ----------
with open(os.path.join(BASE, "data", "icons", "index.json"), encoding="utf-8") as f:
    manifest = json.load(f)

by_op = {}
for e in manifest:
    by_op.setdefault(e["cn"], {})[e["kind"]] = e

SEQUENCE = []
want = [("佩丽卡", "skill", "1"), ("管理员", "combo", "E"),
        ("陈千语", "skill", "3"), ("余烬", "ult", "长按 4"),
        ("佩丽卡", "ult", "长按 1"), ("管理员", "skill", "2")]
for op, kind, key in want:
    e = by_op.get(op, {}).get(kind)
    if e:
        SEQUENCE.append({"op": op, "kind": kind, "icon": e["file"],
                         "key": key, "element": e.get("element", ""),
                         "label": {"skill": "技能", "combo": "连携",
                                   "ult": "终结"}[kind]})
INDEX = 2          # 当前进行到第 3 个


# ---------- 通用绘制 ----------
class Pen:
    def __init__(self, img, d):
        self.img = img
        self.d = d

    def S(self, v):
        return int(round(v * K))

    def F(self, size):
        return max(8, int(round(size * K * BOOST)))

    def shape(self, box, r=12, fill=None, outline=None, width=1, alpha=255):
        a = int(alpha)
        self.d.rounded_rectangle(
            [self.S(box[0]), self.S(box[1]), self.S(box[2]), self.S(box[3])],
            radius=self.S(r),
            fill=(rgb(fill) + (a,)) if fill else None,
            outline=(rgb(outline) + (a,)) if outline else None,
            width=max(1, self.S(width)))

    def oval(self, x1, y1, x2, y2, fill=None, outline=None, width=1, alpha=255):
        a = int(alpha)
        self.d.ellipse([self.S(x1), self.S(y1), self.S(x2), self.S(y2)],
                       fill=(rgb(fill) + (a,)) if fill else None,
                       outline=(rgb(outline) + (a,)) if outline else None,
                       width=max(1, self.S(width)))

    def line(self, x1, y1, x2, y2, color, width=1, alpha=255):
        self.d.line([self.S(x1), self.S(y1), self.S(x2), self.S(y2)],
                    fill=(rgb(color) + (int(alpha),)), width=max(1, self.S(width)))

    def text(self, x, y, s, size, color, anchor="la", bold=False, max_w=None,
             alpha=255):
        if not s:
            return
        if max_w is not None:
            s = fonts.pil_fit(s, self.F(size), self.S(max_w), bold)
            if not s:
                return
        self.d.text((self.S(x), self.S(y)), s, font=fonts.pil_font(self.F(size), bold),
                    fill=(rgb(color) + (int(alpha),)),
                    anchor={"la": "la", "lm": "lm", "mm": "mm", "rm": "rm",
                            "ra": "ra"}.get(anchor, "la"))

    def icon(self, name, cx, cy, size, alpha=255):
        im = icons.render_pil(name, self.S(size))
        if im is None:
            return
        if alpha < 255:
            im = im.copy()
            r, g, b, a = im.split()
            a = a.point(lambda v: int(v * alpha / 255))
            im = Image.merge("RGBA", (r, g, b, a))
        self.img.alpha_composite(im, (self.S(cx) - im.width // 2,
                                      self.S(cy) - im.height // 2))


def base_shell(p):
    """外框 + 顶部 + 底部（各方案通用）。"""
    p.shape((1, 1, 480 - 1, 392 - 1), r=14, fill=theme.BG,
            outline=theme.BORDER, width=2)
    p.oval(444, 8, 470, 34, fill=theme.PANEL_2, outline=theme.BORDER, width=1)
    p.text(457, 21, "✕", theme.F_SMALL, theme.TEXT_DIM, anchor="mm", bold=True)

    p.text(16, 14, "示例编队", theme.F_BODY, theme.TEXT, bold=True, max_w=300)
    p.text(436, 14, "第 1 轮", theme.F_TINY, theme.TEXT_MUTED, anchor="rm")

    badge = "充能轴 1/2"
    bw = fonts.pil_text_width(badge, p.F(theme.F_TINY), True) / K + 22
    p.shape((16, 34, 16 + bw, 58), r=6, fill=theme.PANEL_2,
            outline=theme.CHARGE, width=2)
    p.text(16 + bw / 2, 46, badge, theme.F_TINY, theme.CHARGE, anchor="mm",
           bold=True)
    p.text(480 - 16, 46, "充能 · 第一轮", theme.F_TINY, theme.TEXT_MUTED,
           anchor="rm", max_w=230)
    p.line(16, 66, 480 - 16, 66, theme.BORDER)

    # 底部：透明度 + 状态
    ty = 340
    p.text(16, ty, "透明度", theme.F_TINY, theme.TEXT_MUTED, anchor="lm")
    p.line(92, ty, 250, ty, theme.BORDER, width=4)
    pos = 92 + 158 * 0.93
    p.line(92, ty, pos, ty, theme.ACCENT, width=4)
    p.oval(pos - 7, ty - 7, pos + 7, ty + 7, fill=theme.ACCENT)
    p.text(266, ty, "95%", theme.F_TINY, theme.ACCENT, anchor="lm", bold=True)

    p.text(16, 376, "进行中", theme.F_SMALL, theme.ACCENT, anchor="lm", bold=True)
    p.text(480 - 16, 376, "F7 开始  F8 重置  F9 隐藏  F10", theme.F_TINY,
           theme.TEXT_MUTED, anchor="rm", max_w=300)


# ---------- 方案 1：卡片 + 队列（现在） ----------
def layout_card():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    p = Pen(img, ImageDraw.Draw(img))
    base_shell(p)
    cur = SEQUENCE[INDEX]
    accent = "#%02x%02x%02x" % ELEMENT_RGB.get(cur["element"], (150, 150, 150))

    p.shape((12, 76, 480 - 12, 214), r=12, fill=theme.PANEL_2,
            outline=accent, width=2)
    p.icon(cur["icon"], 56, 145, 76)
    p.text(108, 96, cur["op"], theme.F_SMALL, theme.TEXT_DIM)
    p.text(108, 118, cur["label"], 20, theme.TEXT, bold=True)
    p.text(108, 152, "键盘 %s" % cur["key"], theme.F_SMALL, theme.ACCENT,
           bold=True)
    p.text(480 - 24, 90, "%02d / %02d" % (INDEX + 1, len(SEQUENCE)),
           theme.F_TINY, theme.TEXT_MUTED, anchor="rm")

    p.text(16, 228, "下一个", theme.F_TINY, theme.TEXT_MUTED, anchor="lm")
    nx = SEQUENCE[INDEX + 1]
    p.icon(nx["icon"], 90, 233, 32)
    p.text(114, 233, "%s · %s" % (nx["op"], nx["label"]), theme.F_SMALL,
           theme.TEXT_DIM, anchor="lm", max_w=320)

    x = 16
    for i, s in enumerate(SEQUENCE[:8]):
        dim = 110 if i < INDEX else 255
        p.icon(s["icon"], x + 17, 279, 34, alpha=dim)
        if i == INDEX:
            p.oval(x - 2, 260, x + 36, 298, outline=theme.ACCENT, width=2)
        x += 41
    return img


# ---------- 方案 2：横向流水线（当前放大 + 箭头） ----------
def layout_filmstrip():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    p = Pen(img, ImageDraw.Draw(img))
    base_shell(p)

    start = max(0, min(INDEX - 2, len(SEQUENCE) - 5))
    shown = SEQUENCE[start:start + 5]
    x = 24
    for i, s in enumerate(shown):
        idx = start + i
        big = idx == INDEX
        size = 68 if big else 48
        cy = 128 if big else 132
        dim = 90 if idx < INDEX else 255
        if big:
            p.shape((x - 10, 88, x + size + 10, 88 + size + 44), r=12,
                    fill=theme.PANEL_2, outline=theme.ACCENT, width=2)
        p.icon(s["icon"], x + size / 2, cy, size, alpha=dim)
        p.text(x + size / 2, 196, s["key"], theme.F_SMALL,
               theme.ACCENT if big else theme.TEXT_MUTED, anchor="mm", bold=True)
        p.text(x + size / 2, 210, s["op"], theme.F_TINY, theme.TEXT_DIM,
               anchor="mm", alpha=dim)
        if idx < INDEX:
            p.text(x + size / 2, cy, "✓", 18, theme.GREEN, anchor="mm", bold=True)
        x += size + (34 if big else 22)

    cur = SEQUENCE[INDEX]
    p.line(16, 240, 480 - 16, 240, theme.BORDER)
    p.text(16, 258, "现在按", theme.F_TINY, theme.TEXT_MUTED, anchor="lm")
    p.text(76, 258, cur["key"], 26, theme.ACCENT, anchor="lm", bold=True)
    p.text(160, 258, "%s · %s" % (cur["op"], cur["label"]), theme.F_BODY,
           theme.TEXT, anchor="lm", max_w=300)

    p.text(16, 300, "后面依次", theme.F_TINY, theme.TEXT_MUTED, anchor="lm")
    seq = "  →  ".join("%s %s" % (s["op"], s["key"]) for s in SEQUENCE[INDEX + 1:])
    p.text(88, 300, seq or "— 已是最后一个 —", theme.F_SMALL, theme.TEXT_DIM,
           anchor="lm", max_w=380)
    return img


# ---------- 方案 3：大图标 + 竖排清单 ----------
def layout_list():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    p = Pen(img, ImageDraw.Draw(img))
    base_shell(p)
    cur = SEQUENCE[INDEX]

    p.shape((12, 76, 260, 320), r=12, fill=theme.PANEL_2,
            outline=theme.ACCENT, width=2)
    p.icon(cur["icon"], 136, 150, 104)
    p.text(136, 224, cur["op"], theme.F_BODY, theme.TEXT, anchor="mm", bold=True)
    p.text(136, 246, cur["label"], theme.F_SMALL, theme.TEXT_DIM, anchor="mm")
    p.shape((66, 262, 206, 300), r=8, fill=theme.PANEL_3, outline=theme.ACCENT,
            width=2)
    p.text(136, 281, cur["key"], theme.F_BODY, theme.ACCENT, anchor="mm",
           bold=True)

    p.text(274, 88, "接下来", theme.F_TINY, theme.TEXT_MUTED)
    y = 108
    for i, s in enumerate(SEQUENCE[INDEX + 1:INDEX + 5]):
        p.shape((272, y, 480 - 12, y + 40), r=8, fill=theme.PANEL_2,
                outline=theme.BORDER)
        p.icon(s["icon"], 296, y + 20, 30)
        p.text(320, y + 12, "%s · %s" % (s["op"], s["label"]), theme.F_TINY,
               theme.TEXT, max_w=110)
        p.text(468, y + 20, s["key"], theme.F_TINY, theme.ACCENT, anchor="rm",
               bold=True)
        y += 46
    return img


# ---------- 方案 4：大序号条（强调按哪个键） ----------
def layout_numbers():
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    p = Pen(img, ImageDraw.Draw(img))
    base_shell(p)

    p.text(16, 88, "当前要按", theme.F_SMALL, theme.TEXT_MUTED)
    cur = SEQUENCE[INDEX]
    p.shape((16, 104, 152, 200), r=12, fill=theme.PANEL_2,
            outline=theme.ACCENT, width=2)
    p.text(84, 152, cur["key"].replace("长按 ", "长按\n"), 26, theme.ACCENT,
           anchor="mm", bold=True)

    p.icon(cur["icon"], 208, 152, 88)
    p.text(266, 132, cur["op"], theme.F_BODY, theme.TEXT, bold=True)
    p.text(266, 156, cur["label"], theme.F_SMALL, theme.TEXT_DIM)
    p.text(266, 180, "第 %d / %d 个" % (INDEX + 1, len(SEQUENCE)),
           theme.F_TINY, theme.TEXT_MUTED)

    p.line(16, 216, 480 - 16, 216, theme.BORDER)
    p.text(16, 232, "整条顺序", theme.F_TINY, theme.TEXT_MUTED)

    x = 16
    for i, s in enumerate(SEQUENCE):
        w = 72
        done = i < INDEX
        fill = theme.PANEL if done else theme.PANEL_2
        outline = theme.BORDER if not (i == INDEX) else theme.ACCENT
        p.shape((x, 250, x + w, 250 + 76), r=8, fill=fill, outline=outline,
                width=2 if i == INDEX else 1)
        p.text(x + 8, 258, "%d" % (i + 1), theme.F_TINY,
               theme.TEXT_MUTED if done else theme.ACCENT, bold=True)
        p.icon(s["icon"], x + w / 2, 292, 34, alpha=90 if done else 255)
        p.text(x + w / 2, 316, s["key"], theme.F_TINY,
               theme.TEXT_MUTED if done else theme.TEXT, anchor="mm", bold=True)
        x += w + 8
    return img


def main():
    variants = [
        ("A 卡片 + 队列（现在）", layout_card()),
        ("B 横向流水线", layout_filmstrip()),
        ("C 大图标 + 竖排清单", layout_list()),
        ("D 大序号条", layout_numbers()),
    ]

    pad = 24
    cap = 30
    cols = 2
    cell_w = W
    cell_h = H
    total_w = pad * (cols + 1) + cell_w * cols
    rows = (len(variants) + cols - 1) // cols
    total_h = 44 + rows * (cell_h + cap) + pad

    canvas = Image.new("RGB", (total_w, total_h), rgb(theme.BG))
    d = ImageDraw.Draw(canvas)
    d.text((pad, 12), "悬浮窗内部排版 4 种方案（同一组数据，同一尺寸 552×451）",
           font=fonts.pil_font(15, True), fill=rgb(theme.TEXT) + (255,))

    for i, (title, im) in enumerate(variants):
        r, c = divmod(i, cols)
        x = pad + c * (cell_w + pad)
        y = 44 + r * (cell_h + cap)
        canvas.paste(im, (x, y), im)
        d.text((x, y + cell_h + 6), title,
               font=fonts.pil_font(12, True), fill=rgb(theme.ACCENT) + (255,))

    canvas.save(OUT)
    print("saved", OUT, canvas.size)


if __name__ == "__main__":
    main()
