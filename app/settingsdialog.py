# -*- coding: utf-8 -*-
"""设置对话框：运行设置 + 键位映射。"""
import tkinter as tk

from . import dpi, theme
from .gamepad import button_name
from .model import KIND_CN, KINDS
from .widgets import center_window


class SettingsDialog:
    def __init__(self, app):
        self.app = app
        self.store = app.store
        self.s = self.store.settings

        self.win = tk.Toplevel(app.root)
        self.win.title("设置")
        self.win.configure(bg=theme.BG)
        self.win.transient(app.root)
        self.win.grab_set()

        self._build()
        center_window(self.win, app.root, 520, 730)

    # ---------- 界面 ----------
    def _build(self):
        head = tk.Frame(self.win, bg=theme.BG, padx=dpi.S(20), pady=dpi.S(16))
        head.pack(fill="x")
        tk.Label(head, text="设置", bg=theme.BG, fg=theme.TEXT,
                 font=theme.font(theme.F_TITLE, True)).pack(side="left")

        body = tk.Frame(self.win, bg=theme.BG, padx=dpi.S(20))
        body.pack(fill="both", expand=True)

        # ---- 运行设置 ----
        box1, _sub1 = self._card(body, "运行设置")
        self.mode_var = tk.StringVar(value=self.s.mode)
        for val, label in (("strict", "必须按对键才推进"), ("any", "任意键推进")):
            tk.Radiobutton(
                box1, text=label, value=val, variable=self.mode_var,
                command=self._on_mode, bg=theme.PANEL, fg=theme.TEXT_DIM,
                selectcolor=theme.PANEL_2, activebackground=theme.PANEL,
                activeforeground=theme.TEXT, relief="flat", bd=0,
                highlightthickness=0, anchor="w",
                font=theme.font(theme.F_BODY)).pack(fill="x", padx=dpi.S(8))

        self.focus_var = tk.BooleanVar(value=bool(self.s.only_game_focus))
        tk.Checkbutton(
            box1, text="仅当游戏窗口在前台时响应", variable=self.focus_var,
            command=self._on_focus, bg=theme.PANEL, fg=theme.TEXT_DIM,
            selectcolor=theme.PANEL_2, activebackground=theme.PANEL,
            activeforeground=theme.TEXT, relief="flat", bd=0,
            highlightthickness=0, anchor="w",
            font=theme.font(theme.F_BODY)).pack(fill="x", padx=dpi.S(8))

        self.pad_var = tk.BooleanVar(value=bool(self.s.gamepad_enabled))
        tk.Checkbutton(
            box1, text="启用手柄监听", variable=self.pad_var,
            command=self._on_pad, bg=theme.PANEL, fg=theme.TEXT_DIM,
            selectcolor=theme.PANEL_2, activebackground=theme.PANEL,
            activeforeground=theme.TEXT, relief="flat", bd=0,
            highlightthickness=0, anchor="w",
            font=theme.font(theme.F_BODY)).pack(fill="x", padx=dpi.S(8))

        # ---- 键位规则（只保留长按判定）----
        box2, _sub2 = self._card(body, "键位规则")

        row2 = tk.Frame(box2, bg=theme.PANEL)
        row2.pack(fill="x", padx=dpi.S(8), pady=dpi.S(3))
        tk.Label(row2, text="长按判定", bg=theme.PANEL, fg=theme.TEXT_DIM, width=8,
                 anchor="w", font=theme.font(theme.F_SMALL)).pack(side="left")
        self.hold_var = tk.StringVar(value=str(self.s.hold_ms))
        sp = tk.Spinbox(row2, from_=80, to=1200, increment=20, width=7,
                        textvariable=self.hold_var, command=self._on_hold,
                        bg=theme.PANEL_2, fg=theme.TEXT,
                        buttonbackground=theme.PANEL_3, relief="flat", bd=0,
                        highlightthickness=1, highlightbackground=theme.BORDER,
                        font=theme.font(theme.F_SMALL))
        sp.pack(side="left", ipady=dpi.S(2))
        sp.bind("<KeyRelease>", lambda e: self._on_hold())
        tk.Label(row2, text="毫秒（默认 280）", bg=theme.PANEL, fg=theme.TEXT_MUTED,
                 font=theme.font(theme.F_TINY)).pack(side="left", padx=dpi.Spair((8, 0)))

        # ---- 手柄（长按/终结键两种方式）----
        box3, pad_sub = self._card(body, "手柄", self._pad_rule_text())
        self.pad_sub = pad_sub

        self.pad_btns = {}

        # 终结技方式（对应游戏内「终结技施放动作 2」开关）
        row_ult = tk.Frame(box3, bg=theme.PANEL)
        row_ult.pack(fill="x", padx=dpi.S(8), pady=dpi.Spair((2, 4)))
        tk.Label(row_ult, text="终结技方式", bg=theme.PANEL, fg=theme.TEXT_DIM,
                 width=8, anchor="w",
                 font=theme.font(theme.F_SMALL)).pack(side="left")
        self.ult_mode_var = tk.StringVar(value=self.s.pad_ult_mode)
        for val, label in (("hold", "长按战技键"), ("alt", "终结键 + 按键")):
            tk.Radiobutton(
                row_ult, text=label, value=val, variable=self.ult_mode_var,
                command=self._on_ult_mode, bg=theme.PANEL, fg=theme.TEXT_DIM,
                selectcolor=theme.PANEL_2, activebackground=theme.PANEL,
                activeforeground=theme.TEXT, relief="flat", bd=0,
                highlightthickness=0,
                font=theme.font(theme.F_SMALL)).pack(side="left", padx=dpi.Spair((0, 6)))

        def add_row(key, label, value):
            r = tk.Frame(box3, bg=theme.PANEL)
            r.pack(fill="x", padx=dpi.S(8), pady=dpi.S(3))
            tk.Label(r, text=label, bg=theme.PANEL, fg=theme.TEXT_DIM,
                     width=8, anchor="w",
                     font=theme.font(theme.F_SMALL)).pack(side="left")
            pb = tk.Button(r, text=value, bg=theme.PANEL_2, fg=theme.TEXT,
                           activebackground=theme.PANEL_3,
                           activeforeground=theme.TEXT, relief="flat", bd=0,
                           highlightthickness=1, highlightbackground=theme.BORDER,
                           disabledforeground=theme.TEXT_MUTED,
                           cursor="hand2", font=theme.font(theme.F_SMALL),
                           command=lambda k=key: self._bind_pad_key(k))
            pb.pack(side="left", padx=dpi.Spair((6, 0)), ipady=dpi.S(2), expand=True, fill="x")
            self.pad_btns[key] = pb

        add_row("modifier", "修饰键", self._pad_name(self.s.pad_modifier))
        add_row("combo", "连携技", self._pad_name(self.s.pad_combo))
        add_row("ult", "终结键", self._pad_name(self.s.pad_ult_modifier))
        for _i in range(4):
            add_row("slot%d" % _i, "槽位 %d" % (_i + 1),
                    self._pad_name(self.s.pad_slot_key(_i)))

        self._sync_ult_row()

        self.hint = tk.Label(body, text="点按钮后按下对应的键即可重新绑定",
                             bg=theme.BG, fg=theme.TEXT_MUTED,
                             font=theme.font(theme.F_TINY), anchor="w")
        self.hint.pack(fill="x", pady=dpi.Spair((6, 0)))

        # ---- 底部 ----
        foot = tk.Frame(self.win, bg=theme.BG, padx=dpi.S(20), pady=dpi.S(14))
        foot.pack(fill="x", side="bottom")
        tk.Button(foot, text="完成", command=self.close, bg=theme.ACCENT,
                  fg="#221a06", activebackground=theme.ACCENT_SOFT,
                  activeforeground="#221a06", relief="flat", bd=0,
                  highlightthickness=0, cursor="hand2",
                  font=theme.font(theme.F_BODY, True),
                  padx=dpi.S(20), pady=dpi.S(6)).pack(side="right")

        self.win.bind("<Escape>", lambda e: self.close())

    def _card(self, parent, title, sub=None):
        f = tk.Frame(parent, bg=theme.BG)
        f.pack(fill="x", pady=dpi.Spair((12, 6)))
        tk.Label(f, text=title, bg=theme.BG, fg=theme.TEXT,
                 font=theme.font(theme.F_SECTION, True)).pack(side="left")
        sub_lbl = None
        if sub:
            sub_lbl = tk.Label(f, text=sub, bg=theme.BG, fg=theme.TEXT_MUTED,
                               font=theme.font(theme.F_TINY))
            sub_lbl.pack(side="left", padx=dpi.Spair((8, 0)))
        box = tk.Frame(parent, bg=theme.PANEL, padx=dpi.S(4), pady=dpi.S(6))
        box.pack(fill="x")
        return box, sub_lbl

    # ---------- 文案 ----------
    def _pad_rule_text(self):
        combo = self._pad_name(self.s.pad_combo)
        mod = self._pad_name(self.s.pad_modifier)
        if self.s.pad_ult_mode == "alt":
            ult = self._pad_name(self.s.pad_ult_modifier)
            return "连携 = %s　战技 = %s + 键　终结 = %s + 键" % (combo, mod, ult)
        return "连携 = %s　战技/终结 = %s + 键（长按）" % (combo, mod)

    def _sync_ult_row(self):
        """方式一（长按）下，终结键不可绑定。"""
        pb = self.pad_btns.get("ult")
        if pb is not None:
            alt = self.s.pad_ult_mode == "alt"
            pb.configure(state="normal" if alt else "disabled",
                         cursor="hand2" if alt else "arrow")
        if getattr(self, "pad_sub", None) is not None:
            try:
                self.pad_sub.configure(text=self._pad_rule_text())
            except tk.TclError:
                pass
    def _pad_name(self, bit):
        return button_name(bit, self.s.gamepad_scheme) if bit else "未设置"

    def _refresh_buttons(self):
        for key, pb in self.pad_btns.items():
            if key == "modifier":
                pb.configure(text=self._pad_name(self.s.pad_modifier))
            elif key == "combo":
                pb.configure(text=self._pad_name(self.s.pad_combo))
            elif key == "ult":
                pb.configure(text=self._pad_name(self.s.pad_ult_modifier))
            elif key.startswith("slot"):
                idx = int(key[4:])
                pb.configure(text=self._pad_name(self.s.pad_slot_key(idx)))
        self._sync_ult_row()

    # ---------- 动作 ----------
    def _on_hold(self):
        try:
            val = int(self.hold_var.get())
        except ValueError:
            return
        self.s.hold_ms = max(80, min(1200, val))
        self.store.save_settings()

    def _bind_pad_key(self, key):
        pb = self.pad_btns.get(key)
        if pb is None:
            return
        pb.configure(text="按下手柄键…", fg=theme.ACCENT)

        def on_pad(bit):
            if key == "modifier":
                self.s.pad_modifier = bit
            elif key == "combo":
                self.s.pad_combo = bit
            elif key == "ult":
                self.s.pad_ult_modifier = bit
            elif key.startswith("slot"):
                idx = int(key[4:])
                self.s.pad_slots[idx] = bit
            self.store.save_settings()
            pb.configure(fg=theme.TEXT)
            self._refresh_buttons()

        self.app.begin_pad_bind(on_pad)

    def _on_ult_mode(self):
        self.s.pad_ult_mode = self.ult_mode_var.get()
        self.store.save_settings()
        self._sync_ult_row()

    def _on_mode(self):
        self.s.mode = self.mode_var.get()
        self.store.save_settings()

    def _on_focus(self):
        self.s.only_game_focus = bool(self.focus_var.get())
        self.store.save_settings()

    def _on_pad(self):
        self.s.gamepad_enabled = bool(self.pad_var.get())
        self.store.save_settings()
        self.app.set_gamepad_enabled(self.pad_var.get())

    def close(self):
        try:
            self.win.grab_release()
        except tk.TclError:
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass
