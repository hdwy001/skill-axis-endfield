# -*- coding: utf-8 -*-
"""悬浮窗：长条流水线形态。

要点：
    · 图标全部等大，横向一条排队
    · 当前技能用「只包住图标的描边框」标记，不压下面的键位文字
    · 已按过的只变暗，不画对勾
    · 窗口宽度 = 技能数量决定（自适应），高度按等比例
    · 整窗等比缩放：拖边框/四角，保持长宽比

渲染方式：Pillow 合成 RGBA → UpdateLayeredWindow 逐像素贴图，
底色 alpha 跟透明度走，文字/图标恒为不透明。
"""
import ctypes
import time
import tkinter as tk

from PIL import Image, ImageDraw

from . import dpi, fonts, layeredwin, theme
from .gamepad import button_name
from .keys import vk_label
from .model import KIND_COMBO, KIND_ULT

# 基准尺寸（scale = 1.0 时）
B_ICON = 44
B_GAP = 6
B_PAD = 14
B_HEADER = 32
B_HEIGHT = 136

MIN_SCALE = 0.6
MAX_SCALE = 2.2
SS = 2                      # 超采样

EDGE = 8                    # 边框拖拽感应宽度
MIN_W = 430                 # 顶栏需要的最小宽度，太窄会挤坏布局


def _rgb(hexcolor):
    hexcolor = hexcolor.lstrip("#")
    return tuple(int(hexcolor[i:i + 2], 16) for i in (0, 2, 4))


def _rgba(hexcolor, alpha):
    r, g, b = _rgb(hexcolor)
    return (r, g, b, max(0, min(255, int(round(alpha)))))


class Overlay:
    def __init__(self, app):
        self.app = app
        s = app.store.settings

        self.scale = float(getattr(s, "overlay_scale", 1.0) or 1.0)
        self.scale = max(MIN_SCALE, min(MAX_SCALE, self.scale))
        self.opacity = float(s.opacity) or 0.95
        self._pulse_on = False
        self._hint = ""
        self._hint_until = 0
        self._flash_until = 0.0
        self._flash_ok = True
        self._drag = None
        self._resize = None
        self._opacity_drag = False
        self._img = None
        self._W = 0
        self._H = 0
        self._u = dpi.factor()      # 高 DPI 下的物理像素倍数

        x, y = int(s.overlay_x), int(s.overlay_y)
        sw = app.root.winfo_screenwidth()
        sh = app.root.winfo_screenheight()
        if (x, y) in ((120, 120), (0, 0)):
            x = max(20, (sw - dpi.S(900)) // 2)
            y = max(20, sh - dpi.S(260))
        self._x, self._y = x, y

        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=theme.BG)
        self.win.geometry("+%d+%d" % (x, y))

        self.win.bind("<Button-1>", self._press)
        self.win.bind("<B1-Motion>", self._motion)
        self.win.bind("<ButtonRelease-1>", self._release)
        self.win.bind("<Motion>", self._hover)
        self.win.bind("<Escape>", lambda e: app.hide_overlay())

        self.redraw()
        self._tick()
        for d in (40, 120, 300):
            try:
                self.win.after(d, self.redraw)
            except tk.TclError:
                pass

    # ---------- 尺寸 ----------
    @property
    def _sc(self):
        """实际缩放 = 用户拖的缩放 × DPI 因子（绘制与命中区都用它）。"""
        return self.scale * self._u

    def _metrics(self):
        s = self._sc
        ic = max(16, int(round(B_ICON * s)))
        gap = max(2, int(round(B_GAP * s)))
        pad = max(6, int(round(B_PAD * s)))
        head = max(18, int(round(B_HEADER * s)))
        height = max(60, int(round(B_HEIGHT * s)))
        return ic, gap, pad, head, height

    def _nodes(self):
        p = self.app.player
        nodes = p.nodes_of_segment()
        if nodes:
            return nodes
        for seg in p.segments:
            if seg.axis.nodes:
                return list(seg.axis.nodes)
        return []

    def _layout(self):
        """算出窗口尺寸与可见区间。"""
        ic, gap, pad, head, height = self._metrics()
        nodes = self._nodes()
        n = max(1, len(nodes))
        slot = ic + gap

        content_w = pad * 2 + n * slot - gap
        max_w = int(self.win.winfo_screenwidth() * 0.92)
        min_w = max(MIN_W, int(round(MIN_W * self._sc)))

        visible = n
        if content_w > max_w:
            visible = max(3, (max_w - pad * 2 + gap) // slot)
            content_w = pad * 2 + visible * slot - gap

        W = max(min_w, min(content_w, max_w))
        return W, height, head, ic, slot, pad, nodes, visible

    def _min_width(self):
        return max(MIN_W, int(round(MIN_W * self._sc)))

    # ---------- 透明度 / 显隐 ----------
    def set_opacity(self, value, persist=True):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return
        self.opacity = max(0.25, min(1.0, value))
        if persist:
            s = self.app.store.settings
            s.opacity = self.opacity
            try:
                self.app.persist_settings()
            except Exception:
                pass
        self._safe_redraw()

    def set_scale(self, value, persist=True):
        self.scale = max(MIN_SCALE, min(MAX_SCALE, float(value)))
        if persist:
            s = self.app.store.settings
            s.overlay_scale = self.scale
            try:
                self.app.persist_settings()
            except Exception:
                pass
        self._safe_redraw()

    def _safe_redraw(self):
        try:
            self.redraw()
        except tk.TclError:
            pass

    def show(self):
        try:
            self.win.deiconify()
            self.win.lift()
        except tk.TclError:
            pass
        self.redraw()
        for d in (40, 120):
            try:
                self.win.after(d, self.redraw)
            except tk.TclError:
                pass

    def hide(self):
        try:
            self.win.withdraw()
        except tk.TclError:
            pass

    def visible(self):
        try:
            return bool(self.win.winfo_exists()) and bool(self.win.winfo_viewable())
        except tk.TclError:
            return False

    def exists(self):
        try:
            return bool(self.win.winfo_exists())
        except tk.TclError:
            return False

    def set_click_through(self, enabled):
        layeredwin.set_layered(self.win, layered=True, click_through=enabled)

    def show_hint(self, text):
        self._hint = text
        self._hint_until = time.time() + 2.0
        self.redraw()

    def flash(self, ok=False):
        """当前技能闪一下描边：对 = 绿，错 = 红。"""
        self._flash_ok = bool(ok)
        self._flash_until = time.time() + 0.75
        self._safe_redraw()
        for d in (90, 190, 300):
            try:
                self.win.after(d, self._safe_redraw)
            except tk.TclError:
                break

    def _flash_color(self):
        if time.time() < self._flash_until:
            return theme.OK if self._flash_ok else theme.BAD
        return ""

    def _tick(self):
        self._pulse_on = not self._pulse_on
        try:
            self.win.after(520, self._tick)
        except tk.TclError:
            return
        if self.app.player.state == "running":
            self.redraw()

    # ---------- 数据 ----------
    def team_members(self):
        rot = self.app.player.rotation or self.app.store.active_rotation()
        if rot is not None:
            return rot.members()
        return self.app.store.team.normalized()

    def key_hint(self, node):
        s = self.app.store.settings
        if node.kind == KIND_COMBO:
            return vk_label(s.combo_key) if s.combo_key else "—"
        try:
            slot = self.team_members().index(node.operator)
        except ValueError:
            return "?"
        digit = s.slot_key(slot)
        if digit is None:
            return "?"
        label = vk_label(digit)
        return ("长按" + label) if node.kind == KIND_ULT else label

    def _warn_text(self, nodes):
        """给出「为什么按了没反应」的可见提示。"""
        p = self.app.player
        if not nodes:
            return "这条技能轴还没有技能"
        if p.state in ("idle",):
            return "按 F7 开始提示 · F8 重置（当前未启动）"
        if p.state == "paused":
            return "已暂停 · F7 继续 · F8 重置"
        team = self.team_members()
        missing = []
        for n in nodes:
            if n.operator and n.operator not in team and n.operator not in missing:
                missing.append(n.operator)
        if missing:
            return "这些干员不在当前编队里：%s" % "、".join(missing[:3])
        return ""

    # ---------- 命中区 ----------
    def _zone(self, x, y):
        """返回拖拽区：move / n / s / e / w / ne / nw / se / sw。"""
        W, H = self._W, self._H
        if W <= 0 or H <= 0:
            return "move"
        edge = max(4, EDGE * self._sc)
        left, right = x <= edge, x >= W - edge
        top, bottom = y <= edge, y >= H - edge
        if top and left:
            return "nw"
        if top and right:
            return "ne"
        if bottom and left:
            return "sw"
        if bottom and right:
            return "se"
        if top:
            return "n"
        if bottom:
            return "s"
        if left:
            return "w"
        if right:
            return "e"
        return "move"

    _CURSORS = {"n": "sb_v_double_arrow", "s": "sb_v_double_arrow",
                "e": "sb_h_double_arrow", "w": "sb_h_double_arrow",
                "ne": "size_ne_sw", "sw": "size_ne_sw",
                "nw": "size_nw_se", "se": "size_nw_se",
                "move": "fleur"}

    def _hover(self, e):
        if self.app.store.settings.click_through:
            return
        z = self._zone(e.x, e.y)
        try:
            self.win.configure(cursor=self._CURSORS.get(z, "arrow"))
        except tk.TclError:
            pass

    def _btn_pos(self):
        """顶栏右上角两个圆钮的位置：(关闭 x, 重置 x, y, 半径)。"""
        s = self._sc
        head = max(18, int(round(B_HEADER * s)))
        ymid = head / 2.0
        ccx = self._W - 22 * s
        rcx = ccx - 30 * s
        return ccx, rcx, ymid, 11 * s

    def _in_close(self, x, y):
        s = self._sc
        m = max(4, int(round(4 * s)))
        cx, _rcx, cy, r = self._btn_pos()
        rr = r + m
        return (cx - rr) <= x <= (cx + rr) and (cy - rr) <= y <= (cy + rr)

    def _in_reset(self, x, y):
        s = self._sc
        m = max(4, int(round(4 * s)))
        _ccx, cx, cy, r = self._btn_pos()
        rr = r + m
        return (cx - rr) <= x <= (cx + rr) and (cy - rr) <= y <= (cy + rr)

    # ---------- 交互 ----------
    def _slider_rect(self):
        """透明度滑条的命中矩形（与绘制用同一套坐标）。"""
        s = self._sc
        W = self._W
        head = max(18, int(round(B_HEADER * s)))
        ymid = head / 2.0
        cr = 11 * s
        _ccx, rcx, _ymid, _r = self._btn_pos()
        sl_w = 62 * s
        sl_x2 = rcx - cr - 26 * s
        sl_x1 = sl_x2 - sl_w
        h = max(8, 9 * s)
        return sl_x1 - 2, sl_x2 + 2, ymid - h, ymid + h

    def _in_slider(self, x, y):
        x1, x2, y1, y2 = self._slider_rect()
        return x1 <= x <= x2 and y1 <= y <= y2

    def _apply_slider(self, x):
        x1, x2, _y1, _y2 = self._slider_rect()
        if x2 <= x1:
            return
        ratio = max(0.0, min(1.0, (x - x1) / float(x2 - x1)))
        self.opacity = 0.25 + ratio * 0.75
        self.redraw()

    def _press(self, e):
        if self.app.store.settings.click_through:
            return
        if self._in_close(e.x, e.y):
            self.app.hide_overlay()
            return
        if self._in_reset(e.x, e.y):
            self.app.reset_player()
            return
        if self._in_slider(e.x, e.y):
            self._opacity_drag = True
            self._apply_slider(e.x)
            return
        z = self._zone(e.x, e.y)
        if z != "move":
            self._resize = {"zone": z, "sx": e.x_root, "sy": e.y_root,
                            "w": self._W, "h": self._H, "scale": self.scale}
            return
        self._drag = (e.x_root - self.win.winfo_x(),
                      e.y_root - self.win.winfo_y())

    def _motion(self, e):
        if self._resize is not None:
            self._do_resize(e)
            return
        if self._opacity_drag:
            self._apply_slider(e.x)
            return
        if not self._drag:
            return
        dx, dy = self._drag
        try:
            self.win.geometry("+%d+%d" % (e.x_root - dx, e.y_root - dy))
        except tk.TclError:
            pass

    def _release(self, e):
        if self._opacity_drag:
            self._opacity_drag = False
            self.set_opacity(self.opacity)
            return
        if self._resize is not None:
            self._resize = None
            self.set_scale(self.scale)
            self.redraw()
            return
        if not self._drag:
            return
        self._drag = None
        s = self.app.store.settings
        s.overlay_x, s.overlay_y = self.win.winfo_x(), self.win.winfo_y()
        self.app.persist_settings()

    def _do_resize(self, e):
        """等比缩放：按拖动主轴换算比例。"""
        r = self._resize
        dx = e.x_root - r["sx"]
        dy = e.y_root - r["sy"]
        zone = r["zone"]

        if zone in ("e", "w"):
            delta, base = dx, r["w"]
        elif zone in ("n", "s"):
            delta, base = dy, r["h"]
        else:
            delta = dx if abs(dx) > abs(dy) else dy
            base = r["w"] if abs(dx) > abs(dy) else r["h"]

        if zone in ("w", "n", "nw", "sw"):
            delta = -delta

        if base <= 0:
            return
        new_scale = r["scale"] * (base + delta) / float(base)
        new_scale = max(MIN_SCALE, min(MAX_SCALE, new_scale))
        if abs(new_scale - self.scale) < 0.005:
            return
        self.scale = new_scale
        self.redraw()

    # ---------- 绘制 ----------
    def redraw(self):
        if not self.exists():
            return
        self._ensure_layered()

        W, H, head, ic, slot, pad, nodes, visible = self._layout()
        if W != self._W or H != self._H:
            self._W, self._H = W, H
            try:
                self.win.geometry("%dx%d+%d+%d"
                                  % (W, H, self.win.winfo_x(), self.win.winfo_y()))
            except tk.TclError:
                pass

        img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
        self._img_cur = img
        d = ImageDraw.Draw(img)
        self._d = d
        self._W, self._H = W, H
        self._a = self.opacity * 255.0

        self._frame(d, W, H)
        self._header(d, W, head, nodes)
        self._strip(d, W, H, head, ic, slot, pad, nodes, visible)

        warn = self._warn_text(nodes)
        if warn:
            self._text(d, W / 2, H - max(9, 9 * self._sc), warn,
                       theme.F_TINY, theme.WARN, anchor="mm", bold=True)

        if self._hint and time.time() < self._hint_until:
            self._text(d, W / 2, H - max(22, 22 * self._sc), self._hint,
                       theme.F_TINY, theme.BAD, anchor="mm", bold=True)
        elif self._hint:
            self._hint = ""

        out = img.resize((W, H), Image.LANCZOS)
        self._img = out
        layeredwin.blit(self.win, out)

    def _ensure_layered(self):
        try:
            hwnd = layeredwin.hwnd_of(self.win)
            if not hwnd:
                return
            style = layeredwin.user32.GetWindowLongW(
                ctypes.c_void_p(hwnd), layeredwin.GWL_EXSTYLE)
            if not (style & layeredwin.WS_EX_LAYERED):
                layeredwin.user32.SetWindowLongW(
                    ctypes.c_void_p(hwnd), layeredwin.GWL_EXSTYLE,
                    style | layeredwin.WS_EX_LAYERED)
        except Exception:
            pass

    # 单位换算
    def _S(self, v):
        return int(round(v * SS))

    def _fs(self, pt):
        return max(7, int(round(pt * self._sc)))

    def _shape(self, d, box, r=8, fill=None, outline=None, width=1):
        d.rounded_rectangle(
            [self._S(box[0]), self._S(box[1]), self._S(box[2]), self._S(box[3])],
            radius=self._S(r),
            fill=_rgba(fill, self._a) if fill else None,
            outline=_rgba(outline, self._a) if outline else None,
            width=max(1, self._S(width)))

    def _text(self, d, x, y, s, pt, color, anchor="la", bold=False,
              max_w=None):
        if not s:
            return
        size = self._fs(pt)
        if max_w is not None:
            s = fonts.pil_fit(s, size * SS, max_w * SS, bold)
            if not s:
                return
        d.text((self._S(x), self._S(y)), s, font=fonts.pil_font(size * SS, bold),
               fill=_rgba(color, 255),
               anchor={"la": "la", "lm": "lm", "mm": "mm", "rm": "rm",
                       "ra": "ra", "ls": "ls"}.get(anchor, "la"))

    def _paste(self, im, cx, cy):
        if im is None:
            return
        self._img_cur.alpha_composite(
            im, (int(self._S(cx) - im.width / 2), int(self._S(cy) - im.height / 2)))

    def _frame(self, d, W, H):
        r = max(6, int(round(10 * self._sc)))
        self._shape(d, (0.5, 0.5, W - 0.5, H - 0.5), r=r, fill=theme.BG,
                    outline=theme.BORDER, width=max(1, self._sc))

    def _header(self, d, W, head, nodes):
        s = self._sc
        p = self.app.player
        rot = p.rotation
        name = rot.name if rot else "未选择编队"
        ymid = head / 2.0

        # 右上角：重置 + 关闭（重置图标自己画，MiSans 里没有 ↻ 字形）
        cr = 11 * s
        ccx, rcx, ccy, _r = self._btn_pos()
        for bx in (rcx, ccx):
            d.ellipse([self._S(bx - cr), self._S(ccy - cr),
                       self._S(bx + cr), self._S(ccy + cr)],
                      fill=_rgba(theme.PANEL_2, self._a),
                      outline=_rgba(theme.BORDER, self._a),
                      width=max(1, self._S(1)))
        self._text(d, ccx, ccy, "×", theme.F_TINY, theme.TEXT, anchor="mm",
                   bold=True)
        # 重置图标用「重」字（MiSans 里没有 ↻ 字形，画弧又容易糊）
        self._text(d, rcx, ccy, "重", theme.F_TINY, theme.TEXT_DIM,
                   anchor="mm", bold=True)

        # 右侧：透明度（右边界让出「重置」圆钮）
        sl_w = 62 * s
        sl_x2 = rcx - cr - 26 * s
        sl_x1 = sl_x2 - sl_w
        self._text(d, sl_x1 - 6 * s, ymid, "透明度", theme.F_TINY,
                   theme.TEXT_MUTED, anchor="rm")
        d.line([self._S(sl_x1), self._S(ymid), self._S(sl_x2), self._S(ymid)],
               fill=_rgba(theme.BORDER, self._a), width=max(1, self._S(2)))
        pos = sl_x1 + (sl_x2 - sl_x1) * (
            (self.opacity - 0.25) / 0.75)
        d.line([self._S(sl_x1), self._S(ymid), self._S(pos), self._S(ymid)],
               fill=_rgba(theme.ACCENT, self._a), width=max(1, self._S(2)))
        kr = 4 * s
        d.ellipse([self._S(pos - kr), self._S(ymid - kr),
                   self._S(pos + kr), self._S(ymid + kr)],
                  fill=_rgba(theme.ACCENT, self._a))
        self._text(d, sl_x2 + 5 * s, ymid, "%d%%" % int(round(self.opacity * 100)),
                   theme.F_TINY, theme.ACCENT, anchor="lm", bold=True)

        # 编队名 + 徽章（进度放到左半边，别跟「透明度」挤在一起）
        name_right = sl_x1 - 42 * s
        nm = fonts.pil_fit(name, self._fs(theme.F_BODY) * SS,
                           max(60, name_right - 14 * s - 90 * s) * SS, True)
        self._text(d, 14 * s, ymid, nm, theme.F_BODY, theme.TEXT, anchor="lm",
                   bold=True)
        name_w = fonts.pil_text_width(nm, self._fs(theme.F_BODY) * SS, True) / SS
        bx = 14 * s + name_w + 10 * s

        seg = p.current_segment()
        if seg is None:
            return
        if seg.role == "burst":
            color, label = theme.BURST, "爆发轴"
        else:
            color = theme.CHARGE
            label = ("充能轴 %d/%d" % (seg.charge_index, seg.charge_total)
                     if seg.charge_total > 1 else "充能轴")
        bw = fonts.pil_text_width(label, self._fs(theme.F_TINY) * SS, True) / SS + 16 * s
        if bx + bw <= name_right:
            self._shape(d, (bx, ymid - 9 * s, bx + bw, ymid + 9 * s),
                        r=4 * s, fill=theme.PANEL_2, outline=color, width=1)
            self._text(d, bx + bw / 2, ymid, label, theme.F_TINY, color,
                       anchor="mm", bold=True)

            # 进度（只读）：紧跟在徽章后面，空间不够就不画
            idx = max(0, min(p.index, max(0, len(nodes) - 1)))
            prog = "%d / %d" % (idx + 1, len(nodes)) if nodes else "0 / 0"
            pw = fonts.pil_text_width(prog, self._fs(theme.F_TINY) * SS) / SS
            px = bx + bw + 10 * s
            if px + pw <= name_right:
                self._text(d, px, ymid, prog, theme.F_TINY, theme.TEXT_MUTED,
                           anchor="lm")

    def _strip(self, d, W, H, head, ic, slot, pad, nodes, visible):
        if not nodes:
            self._text(d, W / 2, head + (H - head) / 2, "这条轴还没有技能",
                       theme.F_SMALL, theme.TEXT_MUTED, anchor="mm")
            return

        p = self.app.player
        idx = max(0, min(p.index, len(nodes) - 1))

        start = 0
        if len(nodes) > visible:
            start = max(0, min(idx - visible // 2, len(nodes) - visible))
        shown = nodes[start:start + visible]

        top = head + 6 * self._sc
        icon_cy = top + ic / 2
        key_y = icon_cy + ic / 2 + 11 * self._sc

        # 窗口比内容宽时（顶栏需要最小宽度），内容居中
        gap = slot - ic
        content_w = pad * 2 + len(shown) * slot - gap
        x = (W - content_w) / 2.0 + pad
        for i, node in enumerate(shown):
            gi = start + i
            cur = gi == idx
            past = gi < idx
            cx = x + ic / 2

            if cur:
                k = 5 * self._sc
                flash = self._flash_color()
                if flash:
                    k2 = k + 3 * self._sc
                    self._shape(d, (cx - ic / 2 - k2, icon_cy - ic / 2 - k2,
                                    cx + ic / 2 + k2, icon_cy + ic / 2 + k2),
                                r=10 * self._sc, fill=None, outline=flash,
                                width=max(3, int(round(3 * self._sc))))
                self._shape(d, (cx - ic / 2 - k, icon_cy - ic / 2 - k,
                                cx + ic / 2 + k, icon_cy + ic / 2 + k),
                            r=8 * self._sc, fill=None, outline=theme.ACCENT,
                            width=2)

            im = self.app.icons.render_pil(node.icon, int(ic * SS)) if node.icon else None
            if im is not None and past:
                im = im.copy()
                r, g, b, a = im.split()
                a = a.point(lambda v: int(v * 0.35))
                im = Image.merge("RGBA", (r, g, b, a))
            self._paste(im, cx, icon_cy)

            col = theme.ACCENT if cur else (theme.TEXT_MUTED if past else theme.TEXT_DIM)
            self._text(d, cx, key_y, self.key_hint(node), theme.F_TINY, col,
                       anchor="mm", bold=cur, max_w=slot - 2)
            x += slot

        if len(nodes) > visible:
            side = "→" if start + visible < len(nodes) else ""
            if side:
                self._text(d, W - pad - 2, icon_cy, side, theme.F_BODY,
                           theme.TEXT_MUTED, anchor="rm")
