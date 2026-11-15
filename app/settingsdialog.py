# -*- coding: utf-8 -*-
"""设置对话框：运行设置 + 键位映射。

键位全部可自定义（2026-11-15）：
  * 键盘：队伍 1~4（短按战技 / 长按终结）、连携技、四个全局快捷键
  * 手柄：连携键、修饰键、队伍 1~4 的面键
点右侧按钮后按一下目标键即可换绑；和已有功能撞车会提示，不会静默覆盖。
"""
import tkinter as tk
from tkinter import messagebox

from . import theme
from .brand import APP_PUBLISHER, APP_VERSION_CN
from .gamepad import button_name
from .keys import vk_label
from .model import (DEFAULT_COMBO_KEY, DEFAULT_PAD_COMBO, DEFAULT_PAD_MODIFIER,
                    DEFAULT_PAD_SLOTS, DEFAULT_SLOT_VKS, PAD_ULT_CHORD,
                    PAD_ULT_MODES)
from .widgets import center_window

# 键盘卡片里的项：(key, 显示名, 说明)
KEY_ROWS = (
    ("slot0", "队伍 1", "短按战技 / 长按终结"),
    ("slot1", "队伍 2", "短按战技 / 长按终结"),
    ("slot2", "队伍 3", "短按战技 / 长按终结"),
    ("slot3", "队伍 4", "短按战技 / 长按终结"),
    ("combo", "连携技", "单独一个键"),
)

HOTKEY_ROWS = (
    ("hotkey_start", "开始/暂停", ""),
    ("hotkey_reset", "重置", ""),
    ("hotkey_visible", "显示/隐藏", ""),
    ("hotkey_through", "点击穿透", ""),
)

HOTKEY_DEFAULTS = {"hotkey_start": 0x76, "hotkey_reset": 0x77,
                   "hotkey_visible": 0x78, "hotkey_through": 0x79}

# 手柄卡片里的项：(key, 显示名, 说明)
PAD_ROWS = (
    ("combo", "连携键", "单独按"),
    ("modifier", "修饰键", "组合键的前半段"),
    ("slot0", "队伍 1", "面键"),
    ("slot1", "队伍 2", "面键"),
    ("slot2", "队伍 3", "面键"),
    ("slot3", "队伍 4", "面键"),
)


class SettingsDialog:
    def __init__(self, app):
        self.app = app
        self.store = app.store
        self.s = self.store.settings
        self.key_btns = {}
        self.pad_btns = {}
        self._binding = None          # 正在等按键的那一项，避免同时点两个

        self.win = tk.Toplevel(app.root)
        self.win.title("设置")
        self.win.configure(bg=theme.BG)
        self.win.transient(app.root)
        self.win.grab_set()

        self._build()
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        try:
            self.win.update_idletasks()
            need = self.win.winfo_reqheight()
        except tk.TclError:
            need = 760
        # 内容放不下时靠滚动条，窗口本身不无限拉高
        center_window(self.win, app.root, 560, max(620, min(900, need + 10)))

    # ---------- 界面 ----------
    def _build(self):
        self._subs = {}
        head = tk.Frame(self.win, bg=theme.BG, padx=20, pady=16)
        head.pack(fill="x")
        tk.Label(head, text="设置", bg=theme.BG, fg=theme.TEXT,
                 font=theme.font(theme.F_TITLE, True)).pack(side="left")

        # 底部先占位，保证「完成」永远看得见
        foot = tk.Frame(self.win, bg=theme.BG, padx=20, pady=14)
        foot.pack(fill="x", side="bottom")
        tk.Label(foot, text="版本 %s　发布者 %s" % (APP_VERSION_CN, APP_PUBLISHER),
                 bg=theme.BG, fg=theme.TEXT_MUTED,
                 font=theme.font(theme.F_TINY)).pack(side="left")
        tk.Button(foot, text="完成", command=self.close, bg=theme.ACCENT,
                  fg="#221a06", activebackground=theme.ACCENT_SOFT,
                  activeforeground="#221a06", relief="flat", bd=0,
                  highlightthickness=0, cursor="hand2",
                  font=theme.font(theme.F_BODY, True),
                  padx=20, pady=6).pack(side="right")

        body = self._scrolled_body()

        # ---- 运行设置 ----
        box1 = self._card(body, "运行设置")
        self.mode_var = tk.StringVar(value=self.s.mode)
        for val, label in (("strict", "必须按对键才推进"), ("any", "任意键推进")):
            tk.Radiobutton(
                box1, text=label, value=val, variable=self.mode_var,
                command=self._on_mode, bg=theme.PANEL, fg=theme.TEXT_DIM,
                selectcolor=theme.PANEL_2, activebackground=theme.PANEL,
                activeforeground=theme.TEXT, relief="flat", bd=0,
                highlightthickness=0, anchor="w",
                font=theme.font(theme.F_BODY)).pack(fill="x", padx=8)

        self.focus_var = tk.BooleanVar(value=bool(self.s.only_game_focus))
        tk.Checkbutton(
            box1, text="仅当游戏窗口在前台时响应", variable=self.focus_var,
            command=self._on_focus, bg=theme.PANEL, fg=theme.TEXT_DIM,
            selectcolor=theme.PANEL_2, activebackground=theme.PANEL,
            activeforeground=theme.TEXT, relief="flat", bd=0,
            highlightthickness=0, anchor="w",
            font=theme.font(theme.F_BODY)).pack(fill="x", padx=8)

        self.pad_var = tk.BooleanVar(value=bool(self.s.gamepad_enabled))
        tk.Checkbutton(
            box1, text="启用手柄监听", variable=self.pad_var,
            command=self._on_pad, bg=theme.PANEL, fg=theme.TEXT_DIM,
            selectcolor=theme.PANEL_2, activebackground=theme.PANEL,
            activeforeground=theme.TEXT, relief="flat", bd=0,
            highlightthickness=0, anchor="w",
            font=theme.font(theme.F_BODY)).pack(fill="x", padx=8)

        # ---- 键盘按键 ----
        box2 = self._card(body, "键盘按键",
                          "点右侧按钮，再按一下想用的键；同一键不能重复绑定")
        for key, label, hint in KEY_ROWS:
            row = self._row(box2, label)
            btn = self._bind_button(row, lambda k=key: self._start_key_bind(k))
            self.key_btns[key] = btn
            if hint:
                tk.Label(row, text=hint, bg=theme.PANEL, fg=theme.TEXT_MUTED,
                         font=theme.font(theme.F_TINY)).pack(side="left", padx=(8, 0))

        tk.Frame(box2, bg=theme.BORDER, height=1).pack(fill="x", padx=8, pady=(6, 4))
        tk.Label(box2, text="快捷键", bg=theme.PANEL, fg=theme.TEXT_MUTED,
                 font=theme.font(theme.F_TINY)).pack(anchor="w", padx=8)
        for key, label, _hint in HOTKEY_ROWS:
            row = self._row(box2, label)
            btn = self._bind_button(row, lambda k=key: self._start_key_bind(k))
            self.key_btns[key] = btn

        self._reset_button(box2, "键盘恢复默认", self._reset_keyboard)

        # ---- 手柄按键 ----
        box3 = self._card(body, "手柄按键", self._pad_rule_text())
        for key, label, hint in PAD_ROWS:
            row = self._row(box3, label)
            btn = self._bind_button(row, lambda k=key: self._start_pad_bind(k))
            self.pad_btns[key] = btn
            if hint:
                tk.Label(row, text=hint, bg=theme.PANEL, fg=theme.TEXT_MUTED,
                         font=theme.font(theme.F_TINY)).pack(side="left", padx=(8, 0))

        # 终结技触发风格（要跟游戏内设置选的那一种对齐）
        tk.Frame(box3, bg=theme.BORDER, height=1).pack(fill="x", padx=8, pady=(8, 4))
        row_ult = tk.Frame(box3, bg=theme.PANEL)
        row_ult.pack(fill="x", padx=8)
        tk.Label(row_ult, text="终结技方式", bg=theme.PANEL, fg=theme.TEXT_DIM,
                 anchor="w", font=theme.font(theme.F_SMALL)).pack(side="left")

        self.ult_var = tk.StringVar(value=self.s.pad_ult_mode)
        for val, label in PAD_ULT_MODES:
            tk.Radiobutton(
                row_ult, text=label, value=val, variable=self.ult_var,
                command=self._on_ult_mode, bg=theme.PANEL, fg=theme.TEXT_DIM,
                selectcolor=theme.PANEL_2, activebackground=theme.PANEL,
                activeforeground=theme.TEXT, relief="flat", bd=0,
                highlightthickness=0, anchor="w",
                font=theme.font(theme.F_SMALL)).pack(side="left", padx=(6, 0))

        # 这一行原来在 _on_ult_mode 里被 configure，但从来没创建过 —— 切风格就崩
        self.ult_note = tk.Label(box3, text=self._ult_note_text(), bg=theme.PANEL,
                                 fg=theme.TEXT_MUTED, justify="left",
                                 font=theme.font(theme.F_TINY))
        self.ult_note.pack(fill="x", padx=8, pady=(6, 2))

        self._reset_button(box3, "手柄恢复默认", self._reset_pad)

        # ---- 键位规则 ----
        box4 = self._card(body, "键位规则")
        row2 = tk.Frame(box4, bg=theme.PANEL)
        row2.pack(fill="x", padx=8, pady=3)
        tk.Label(row2, text="长按判定", bg=theme.PANEL, fg=theme.TEXT_DIM, width=8,
                 anchor="w", font=theme.font(theme.F_SMALL)).pack(side="left")
        self.hold_var = tk.StringVar(value=str(self.s.hold_ms))
        sp = tk.Spinbox(row2, from_=80, to=1200, increment=20, width=7,
                        textvariable=self.hold_var, command=self._on_hold,
                        bg=theme.PANEL_2, fg=theme.TEXT,
                        buttonbackground=theme.PANEL_3, relief="flat", bd=0,
                        highlightthickness=1, highlightbackground=theme.BORDER,
                        font=theme.font(theme.F_SMALL))
        sp.pack(side="left", ipady=2)
        sp.bind("<KeyRelease>", lambda e: self._on_hold())
        tk.Label(row2, text="毫秒（超过算长按 = 终结技）", bg=theme.PANEL,
                 fg=theme.TEXT_MUTED,
                 font=theme.font(theme.F_TINY)).pack(side="left", padx=(8, 0))

        self.win.bind("<Escape>", lambda e: self.close())
        self._refresh_buttons()

    # ---------- 滚动容器 ----------
    def _scrolled_body(self):
        holder = tk.Frame(self.win, bg=theme.BG)
        holder.pack(fill="both", expand=True)

        canvas = tk.Canvas(holder, bg=theme.BG, highlightthickness=0, bd=0)
        bar = tk.Scrollbar(holder, orient="vertical", command=canvas.yview,
                           width=10, bg=theme.PANEL, troughcolor=theme.BG,
                           relief="flat", bd=0)
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=theme.BG, padx=20)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfigure(win_id, width=e.width))

        def _wheel(ev):
            try:
                canvas.yview_scroll(int(-ev.delta / 120), "units")
            except tk.TclError:
                pass

        # 绑在 Toplevel 上：Tk 的 bindtags 里每个子控件都带顶层窗口，
        # 所以鼠标在卡片/按钮上也照样能滚（不用 Enter/Leave，那会在子控件间误触发）
        self.win.bind("<MouseWheel>", _wheel)
        self._canvas = canvas
        return inner

    def _unbind_wheel(self):
        try:
            self.win.unbind("<MouseWheel>")
        except tk.TclError:
            pass

    # ---------- 小部件 ----------
    def _card(self, parent, title, sub=None):
        f = tk.Frame(parent, bg=theme.BG)
        f.pack(fill="x", pady=(12, 6))
        tk.Label(f, text=title, bg=theme.BG, fg=theme.TEXT,
                 font=theme.font(theme.F_SECTION, True)).pack(side="left")
        if sub:
            lbl = tk.Label(f, text=sub, bg=theme.BG, fg=theme.TEXT_MUTED,
                           font=theme.font(theme.F_TINY), justify="left")
            lbl.pack(side="left", padx=(8, 0))
            self._subs[title] = lbl
        box = tk.Frame(parent, bg=theme.PANEL, padx=4, pady=6)
        box.pack(fill="x")
        return box

    def _row(self, parent, label, width=9):
        row = tk.Frame(parent, bg=theme.PANEL)
        row.pack(fill="x", padx=8, pady=2)
        tk.Label(row, text=label, bg=theme.PANEL, fg=theme.TEXT_DIM, width=width,
                 anchor="w", font=theme.font(theme.F_SMALL)).pack(side="left")
        return row

    def _bind_button(self, row, command):
        btn = tk.Button(row, text="", command=command, bg=theme.PANEL_2,
                        fg=theme.TEXT, activebackground=theme.PANEL_3,
                        activeforeground=theme.TEXT, relief="flat", bd=0,
                        highlightthickness=1, highlightbackground=theme.BORDER,
                        cursor="hand2", width=13, anchor="w",
                        font=theme.font(theme.F_SMALL), padx=8, pady=2)
        btn.pack(side="left")
        return btn

    def _reset_button(self, parent, text, command):
        row = tk.Frame(parent, bg=theme.PANEL)
        row.pack(fill="x", padx=8, pady=(6, 2))
        tk.Button(row, text=text, command=command, bg=theme.PANEL, fg=theme.TEXT_MUTED,
                  activebackground=theme.PANEL_2, activeforeground=theme.TEXT,
                  relief="flat", bd=0, highlightthickness=0, cursor="hand2",
                  font=theme.font(theme.F_TINY)).pack(side="left")

    # ---------- 文案 ----------
    def _pad_name(self, bit):
        return button_name(bit, self.s.gamepad_scheme) if bit else "未设置"

    def _pad_rule_text(self):
        """手柄卡片的副标题：跟着当前键位和终结技风格走。"""
        mod = self._pad_name(self.s.pad_modifier)
        combo = self._pad_name(self.s.pad_combo)
        if self.s.pad_ult_mode == PAD_ULT_CHORD:
            return "连携 = %s（单独按）　战技 = %s + 面键　终结 = %s + %s + 面键" % (
                combo, mod, mod, combo)
        return "连携 = %s　战技 = %s + 短按面键　终结 = %s + 长按面键" % (
            combo, mod, mod)

    def _ult_note_text(self):
        if self.s.pad_ult_mode == PAD_ULT_CHORD:
            return ("游戏里若把终结技设成「组合键」，就选这一项。\n"
                    "注意：按住 %s 时按下的 %s 属于终结技组合，不会推进连携。"
                    % (self._pad_name(self.s.pad_modifier),
                       self._pad_name(self.s.pad_combo)))
        return ("游戏里若把终结技设成「长按」，就选这一项。\n"
                "按住 %s 后面键按不满 %dms 算战技，超过算终结技。"
                % (self._pad_name(self.s.pad_modifier), int(self.s.hold_ms)))

    # ---------- 取值 / 刷新 ----------
    def _key_value(self, key):
        if key.startswith("slot"):
            return self.s.slot_key(int(key[4:]))
        if key == "combo":
            return self.s.combo_key
        return getattr(self.s, key, None)

    def _key_label(self, key):
        for k, label, _hint in KEY_ROWS:
            if k == key:
                return label
        for k, label, _hint in HOTKEY_ROWS:
            if k == key:
                return label
        return key

    def _pad_value(self, key):
        if key == "combo":
            return self.s.pad_combo
        if key == "modifier":
            return self.s.pad_modifier
        if key.startswith("slot"):
            return self.s.pad_slot_key(int(key[4:]))
        return None

    def _pad_label(self, key):
        for k, label, _hint in PAD_ROWS:
            if k == key:
                return label
        return key

    def _refresh_buttons(self):
        for key, btn in self.key_btns.items():
            btn.configure(text=vk_label(self._key_value(key)), fg=theme.TEXT)
        for key, btn in self.pad_btns.items():
            btn.configure(text=self._pad_name(self._pad_value(key)), fg=theme.TEXT)
        sub = self._subs.get("手柄按键")
        if sub is not None:
            sub.configure(text=self._pad_rule_text())

    # ---------- 键盘绑定 ----------
    def _start_key_bind(self, key):
        btn = self.key_btns.get(key)
        if btn is None or self._binding is not None:
            return
        self._binding = key
        btn.configure(text="按新键…", fg=theme.ACCENT)
        self.app.begin_bind(lambda ev: self._finish_key_bind(key, ev.vk))

    def _finish_key_bind(self, key, vk):
        self._binding = None
        if vk is None:
            self._refresh_buttons()
            return
        owner = self.s.keyboard_owner(vk, skip=self._key_label(key))
        if owner:
            messagebox.showwarning(
                "按键冲突",
                "「%s」已经用在「%s」上了，请换一个键。" % (vk_label(vk), owner),
                parent=self.win)
            self._refresh_buttons()
            return
        self._apply_key_bind(key, vk)
        self.store.save_settings()
        self._refresh_buttons()
        self._after_key_change()

    def _apply_key_bind(self, key, vk):
        if key.startswith("slot"):
            keys = list(self.s.slot_vks or DEFAULT_SLOT_VKS)
            keys[int(key[4:])] = vk
            self.s.slot_vks = tuple(keys)
        elif key == "combo":
            self.s.combo_key = vk
        else:
            setattr(self.s, key, vk)

    def _after_key_change(self):
        """键位变了：悬浮窗上的「按 X」提示要跟着换。"""
        try:
            self.app.refresh_overlay()
        except Exception:  # noqa: BLE001
            pass

    # ---------- 手柄绑定 ----------
    def _start_pad_bind(self, key):
        btn = self.pad_btns.get(key)
        if btn is None or self._binding is not None:
            return
        self._binding = key
        btn.configure(text="按手柄键…", fg=theme.ACCENT)
        self.app.begin_pad_bind(lambda bit: self._finish_pad_bind(key, bit))

    def _finish_pad_bind(self, key, bit):
        self._binding = None
        if not bit:
            self._refresh_buttons()
            return
        owner = self.s.pad_owner(bit, skip=self._pad_label(key))
        if owner:
            messagebox.showwarning(
                "按键冲突",
                "「%s」已经用在「%s」上了，请换一个键。" % (self._pad_name(bit), owner),
                parent=self.win)
            self._refresh_buttons()
            return
        self._apply_pad_bind(key, bit)
        self.store.save_settings()
        self._reset_pad_rules()
        self._refresh_buttons()
        self._after_key_change()

    def _apply_pad_bind(self, key, bit):
        if key == "combo":
            self.s.pad_combo = bit
        elif key == "modifier":
            self.s.pad_modifier = bit
        elif key.startswith("slot"):
            slots = dict(self.s.pad_slots or DEFAULT_PAD_SLOTS)
            slots[int(key[4:])] = bit
            self.s.pad_slots = slots

    def _reset_pad_rules(self):
        """清掉手柄按住状态，避免旧组合键的半截状态影响新键位。"""
        rules = getattr(self.app, "pad_rules", None)
        if rules is not None:
            try:
                rules.reset()
            except AttributeError:
                pass

    # ---------- 恢复默认 ----------
    def _reset_keyboard(self):
        if not messagebox.askyesno("恢复默认键盘键位",
                                   "把队伍键、连携键和快捷键都恢复成出厂设置？",
                                   parent=self.win):
            return
        self.s.slot_vks = tuple(DEFAULT_SLOT_VKS)
        self.s.combo_key = DEFAULT_COMBO_KEY
        for key, vk in HOTKEY_DEFAULTS.items():
            setattr(self.s, key, vk)
        self.store.save_settings()
        self._refresh_buttons()
        self._after_key_change()

    def _reset_pad(self):
        if not messagebox.askyesno("恢复默认手柄键位",
                                   "把手柄的连携键、修饰键和队伍面键恢复成出厂设置？",
                                   parent=self.win):
            return
        self.s.pad_modifier = DEFAULT_PAD_MODIFIER
        self.s.pad_combo = DEFAULT_PAD_COMBO
        self.s.pad_slots = dict(DEFAULT_PAD_SLOTS)
        self.store.save_settings()
        self._reset_pad_rules()
        self._refresh_buttons()
        self._after_key_change()

    # ---------- 动作 ----------
    def _on_hold(self):
        try:
            val = int(self.hold_var.get())
        except ValueError:
            return
        self.s.hold_ms = max(80, min(1200, val))
        self.store.save_settings()
        if getattr(self, "ult_note", None) is not None:
            self.ult_note.configure(text=self._ult_note_text())

    def _on_ult_mode(self):
        self.s.pad_ult_mode = self.ult_var.get()
        self.store.save_settings()
        self._reset_pad_rules()
        self._refresh_buttons()
        if getattr(self, "ult_note", None) is not None:
            self.ult_note.configure(text=self._ult_note_text())

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
        if self._binding is not None:
            # 关窗口时还在等按键：把绑定取消掉，别吞下一次输入
            self._binding = None
            try:
                self.app.end_bind()
            except AttributeError:
                pass
            try:
                self.app.end_pad_bind()
            except AttributeError:
                pass
        self._unbind_wheel()
        try:
            self.win.grab_release()
        except tk.TclError:
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass
