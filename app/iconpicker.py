# -*- coding: utf-8 -*-
"""图标库面板：缩略图网格 + 搜索 + 按技能类型筛选。"""
import tkinter as tk
from tkinter import filedialog

from . import dpi, theme
from .scaledcanvas import ScaledCanvas
from .widgets import center_window, rounded_rect, truncate

CELL_W = 92
CELL_H = 112
IMG = 58


def _btn(parent, text, command, active=False, small=True):
    return tk.Button(
        parent, text=text, command=command,
        bg=theme.ACCENT if active else theme.PANEL_2,
        fg="#20180a" if active else theme.TEXT,
        activebackground=theme.ACCENT_SOFT if active else theme.PANEL_3,
        activeforeground="#20180a" if active else theme.TEXT,
        relief="flat", bd=0, highlightthickness=0, cursor="hand2",
        font=theme.font(9, active), padx=dpi.S(10), pady=dpi.S(4),
    )


class IconPicker:
    def __init__(self, app, on_pick, current=None):
        self.app = app
        self.on_pick = on_pick
        self.current = current or ""
        self.kind = "all"
        self.entries = app.icons.manifest()

        self.win = tk.Toplevel(app.root)
        self.win.title("图标库")
        self.win.configure(bg=theme.BG)
        self.win.transient(app.root)

        self._build()
        center_window(self.win, app.root, 800, 620)
        self.redraw()

    # ---------- 界面 ----------
    def _build(self):
        head = tk.Frame(self.win, bg=theme.BG, padx=dpi.S(16), pady=dpi.S(12))
        head.pack(fill="x")

        tk.Label(head, text="图标库", bg=theme.BG, fg=theme.TEXT,
                 font=theme.font(14, True)).pack(side="left")

        self.query_var = tk.StringVar()
        entry = tk.Entry(head, textvariable=self.query_var, bg=theme.PANEL_2,
                         fg=theme.TEXT, insertbackground=theme.TEXT, relief="flat",
                         highlightthickness=1, highlightbackground=theme.BORDER,
                         highlightcolor=theme.ACCENT, font=theme.font(10), width=18)
        entry.pack(side="right", ipady=dpi.S(4), padx=dpi.Spair((8, 0)))
        tk.Label(head, text="搜索", bg=theme.BG, fg=theme.TEXT_MUTED,
                 font=theme.font(9)).pack(side="right")
        self.query_var.trace_add("write", lambda *_: self.redraw())

        bar = tk.Frame(self.win, bg=theme.BG, padx=dpi.S(16))
        bar.pack(fill="x", pady=dpi.Spair((0, 8)))
        self.filter_btns = {}
        for key, label in (("all", "全部"), ("skill", "技能"),
                           ("combo", "连携"), ("ult", "终结"), ("custom", "自定义")):
            b = _btn(bar, label, lambda k=key: self.set_kind(k), active=(key == "all"))
            b.pack(side="left", padx=dpi.Spair((0, 6)))
            self.filter_btns[key] = b

        wrap = tk.Frame(self.win, bg=theme.BG, padx=dpi.S(16))
        wrap.pack(fill="both", expand=True)
        self.canvas = ScaledCanvas(wrap, bg=theme.BG, highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        scroll = tk.Scrollbar(wrap, command=self.canvas.yview, bg=theme.BG,
                              troughcolor=theme.PANEL_2, relief="flat")
        scroll.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-e.delta / 120), "units"))
        self.canvas.bind("<Configure>", lambda e: self.redraw())

        foot = tk.Frame(self.win, bg=theme.PANEL, padx=dpi.S(16), pady=dpi.S(10))
        foot.pack(fill="x", side="bottom")
        self.status = tk.Label(foot, text="", bg=theme.PANEL, fg=theme.TEXT_DIM,
                               font=theme.font(9), anchor="w")
        self.status.pack(side="left")
        _btn(foot, "从文件选择…", self.browse_file).pack(side="right", padx=dpi.Spair((6, 0)))
        _btn(foot, "关闭", self.close).pack(side="right")

        self.win.bind("<Escape>", lambda e: self.close())

    def set_kind(self, kind):
        self.kind = kind
        for key, btn in self.filter_btns.items():
            active = key == kind
            btn.configure(bg=theme.ACCENT if active else theme.PANEL_2,
                          fg="#20180a" if active else theme.TEXT,
                          font=theme.font(9, active))
        self.redraw()

    # ---------- 数据筛选 ----------
    def filtered(self):
        q = self.query_var.get().strip().lower()
        out = []
        for e in self.entries:
            if self.kind != "all" and e.get("kind") != self.kind:
                continue
            if q:
                hay = " ".join(str(e.get(k, "")) for k in ("cn", "en", "skill", "file")).lower()
                if q not in hay:
                    continue
            out.append(e)
        return out

    # ---------- 绘制 ----------
    def redraw(self):
        cv = self.canvas
        cv.delete("all")
        items = self.filtered()
        width = max(cv.winfo_width(), 400)
        cols = max(1, (width - 4) // CELL_W)

        if not items:
            cv.create_text(width / 2, 60, text="没有匹配的图标",
                           fill=theme.TEXT_MUTED, font=theme.font(11))
            cv.configure(scrollregion=(0, 0, width, 120))
            self.status.configure(text="共 0 个")
            return

        for i, e in enumerate(items):
            row, col = divmod(i, cols)
            x = col * CELL_W
            y = row * CELL_H
            self._cell(x, y, e)

        rows = (len(items) + cols - 1) // cols
        cv.configure(scrollregion=(0, 0, width, rows * CELL_H + 8))
        self.status.configure(text=f"共 {len(items)} 个图标 · 图标目录 data/icons")

    def _cell(self, x, y, entry):
        cv = self.canvas
        tag = f"cell_{entry['file']}_{x}_{y}"
        selected = entry["file"] == self.current

        rounded_rect(cv, x + 4, y + 4, x + CELL_W - 4, y + CELL_H - 6, r=10,
                     fill=theme.PANEL_2 if not selected else theme.PANEL_3,
                     outline=theme.ACCENT if selected else theme.BORDER,
                     width=2 if selected else 1, tags=(tag,))

        photo = self.app.icons.render(entry["file"], 58)
        if photo is not None:
            cv.create_image(x + CELL_W / 2.0, y + 37, image=photo, tags=(tag,))

        label = entry.get("cn") or entry.get("file", "")
        cv.create_text(x + CELL_W / 2, y + 80, text=truncate(label, 8),
                       fill=theme.TEXT, font=theme.font(9, True), tags=(tag,))
        stars = "★" * int(entry.get("rarity") or 0)
        sub = entry.get("kind_cn", "")
        if stars:
            sub = f"{sub} {stars}"
        cv.create_text(x + CELL_W / 2, y + 96, text=sub,
                       fill=theme.TEXT_MUTED, font=theme.font(8), tags=(tag,))

        cv.tag_bind(tag, "<Button-1>", lambda e, f=entry["file"]: self.pick(f))

    # ---------- 动作 ----------
    def pick(self, filename):
        self.on_pick(filename)
        self.close()

    def browse_file(self):
        path = filedialog.askopenfilename(
            parent=self.win, title="选择图标文件", initialdir=self.app.icons.dir,
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.webp *.gif *.bmp"),
                       ("所有文件", "*.*")],
        )
        if path:
            self.pick(self.app.icons.store_name(path))

    def close(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass
