# -*- coding: utf-8 -*-
"""干员选择器：立绘网格，带元素色标签。"""
import json
import os

import tkinter as tk

from . import dpi, theme
from .scaledcanvas import ScaledCanvas
from .widgets import center_window, rounded_rect

CELL_W = 104
CELL_H = 132
IMG = 64


class OperatorPicker:
    def __init__(self, app, on_pick, current=None, used=()):
        self.app = app
        self.on_pick = on_pick
        self.current = current or ""
        self.used = set(u for u in used if u)
        self.ops = self._load_operators()

        self.win = tk.Toplevel(app.root)
        self.win.title("选择干员")
        self.win.configure(bg=theme.BG)
        self.win.transient(app.root)
        self._build()
        center_window(self.win, app.root, 760, 600)

    # ---------- 数据 ----------
    def _load_operators(self):
        path = os.path.join(self.app.icons.dir, "index.json")
        data = []
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f) or []
        except (OSError, ValueError):
            return []
        ops = {}
        for e in data:
            cn = e.get("cn")
            if not cn:
                continue
            item = ops.setdefault(cn, {"cn": cn, "element": e.get("element", ""),
                                       "kind_cn": {}, "icons": {}})
            item["icons"][e.get("kind")] = e.get("file")
        return sorted(ops.values(), key=lambda x: x["cn"])

    # ---------- 界面 ----------
    def _build(self):
        head = tk.Frame(self.win, bg=theme.BG, padx=dpi.S(18), pady=dpi.S(14))
        head.pack(fill="x")
        tk.Label(head, text="选择干员", bg=theme.BG, fg=theme.TEXT,
                 font=theme.font(theme.F_TITLE, True)).pack(side="left")

        self.query_var = tk.StringVar()
        entry = tk.Entry(head, textvariable=self.query_var, bg=theme.PANEL_2,
                         fg=theme.TEXT, insertbackground=theme.TEXT, relief="flat",
                         highlightthickness=1, highlightbackground=theme.BORDER,
                         highlightcolor=theme.ACCENT, font=theme.font(theme.F_BODY),
                         width=16)
        entry.pack(side="right", ipady=dpi.S(4))
        self.query_var.trace_add("write", lambda *_: self.redraw())

        wrap = tk.Frame(self.win, bg=theme.BG, padx=dpi.S(18))
        wrap.pack(fill="both", expand=True)
        self.cv = ScaledCanvas(wrap, bg=theme.BG, highlightthickness=0, bd=0)
        self.cv.pack(side="left", fill="both", expand=True)
        bar = tk.Scrollbar(wrap, command=self.cv.yview, bg=theme.BG,
                           troughcolor=theme.PANEL_2, relief="flat")
        bar.pack(side="right", fill="y")
        self.cv.configure(yscrollcommand=bar.set)
        self.cv.bind("<MouseWheel>",
                     lambda e: self.cv.yview_scroll(int(-e.delta / 120), "units"))
        self.cv.bind("<Configure>", lambda e: self.redraw())

        foot = tk.Frame(self.win, bg=theme.PANEL, padx=dpi.S(18), pady=dpi.S(10))
        foot.pack(fill="x", side="bottom")
        self.status = tk.Label(foot, text="", bg=theme.PANEL, fg=theme.TEXT_MUTED,
                               font=theme.font(theme.F_TINY), anchor="w")
        self.status.pack(side="left")

        self.win.bind("<Escape>", lambda e: self.close())
        self.redraw()

    # ---------- 绘制 ----------
    def filtered(self):
        q = self.query_var.get().strip().lower()
        if not q:
            return self.ops
        return [o for o in self.ops if q in o["cn"].lower()]

    def redraw(self):
        cv = self.cv
        cv.delete("all")
        items = self.filtered()
        width = max(cv.winfo_width(), 400)
        cols = max(1, (width - 6) // CELL_W)
        if not items:
            cv.create_text(width / 2, 60, text="没有匹配的干员",
                           fill=theme.TEXT_MUTED, font=theme.font(theme.F_BODY))
            cv.configure(scrollregion=(0, 0, width, 120))
            return
        for i, op in enumerate(items):
            row, col = divmod(i, cols)
            self._cell(col * CELL_W, row * CELL_H, op)
        rows = (len(items) + cols - 1) // cols
        cv.configure(scrollregion=(0, 0, width, rows * CELL_H + 10))
        self.status.configure(text="共 %d 名干员" % len(items))

    def _cell(self, x, y, op):
        cv = self.cv
        cn = op["cn"]
        tag = "op_%s_%d_%d" % (cn, x, y)
        selected = cn == self.current
        used = cn in self.used and cn != self.current

        fill = theme.PANEL_2 if not selected else theme.PANEL_3
        outline = theme.ACCENT if selected else theme.BORDER
        rounded_rect(cv, x + 4, y + 4, x + CELL_W - 4, y + CELL_H - 6, r=10,
                     fill=fill, outline=outline, width=2 if selected else 1,
                     tags=(tag,))

        photo = self.app.icons.render_portrait(cn, IMG)
        if photo is not None:
            cv.create_image(x + CELL_W / 2, y + 44, image=photo, tags=(tag,))
        else:
            cv.create_text(x + CELL_W / 2, y + 44, text="?", fill=theme.TEXT_MUTED,
                           font=theme.font(22, True), tags=(tag,))

        color = theme.TEXT_MUTED if used else theme.TEXT
        cv.create_text(x + CELL_W / 2, y + 90, text=cn, fill=color,
                       font=theme.font(theme.F_BODY, True), tags=(tag,))
        cv.create_text(x + CELL_W / 2, y + 108,
                       text=theme.ELEMENT_CN.get(op["element"], op["element"]),
                       fill=theme.TEXT_MUTED, font=theme.font(theme.F_TINY), tags=(tag,))
        if used:
            cv.create_text(x + CELL_W / 2, y + 120, text="已在队伍", fill=theme.WARN,
                           font=theme.font(theme.F_TINY), tags=(tag,))

        cv.tag_bind(tag, "<Button-1>", lambda e: self.pick(cn))

    # ---------- 动作 ----------
    def pick(self, cn):
        self.on_pick(cn)
        self.close()

    def close(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass
