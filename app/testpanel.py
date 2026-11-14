# -*- coding: utf-8 -*-
"""按键测试面板：用来确认监听是否真的生效。"""
import tkinter as tk

from . import dpi, theme
from .keys import vk_label
from .widgets import center_window


class TestPanel:
    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("按键测试")
        self.win.configure(bg=theme.BG)
        self.win.attributes("-topmost", True)

        wrap = tk.Frame(self.win, bg=theme.BG, padx=dpi.S(18), pady=dpi.S(16))
        wrap.pack(fill="both", expand=True)

        tk.Label(wrap, text="按键测试", bg=theme.BG, fg=theme.TEXT,
                 font=theme.font(15, True), anchor="w").pack(fill="x")
        tk.Label(wrap, text="在任意窗口（包括游戏里）按下按键，下面会实时显示。",
                 bg=theme.BG, fg=theme.TEXT_DIM, font=theme.font(10),
                 anchor="w").pack(fill="x", pady=dpi.Spair((2, 12)))

        status = tk.Frame(wrap, bg=theme.PANEL, padx=dpi.S(14), pady=dpi.S(12))
        status.pack(fill="x")
        self.lbl_hook = tk.Label(status, text="钩子：检测中…", bg=theme.PANEL,
                                 fg=theme.TEXT_DIM, font=theme.font(10), anchor="w")
        self.lbl_hook.pack(fill="x")
        self.lbl_poll = tk.Label(status, text="轮询：检测中…", bg=theme.PANEL,
                                 fg=theme.TEXT_DIM, font=theme.font(10), anchor="w")
        self.lbl_poll.pack(fill="x")
        self.lbl_mouse = tk.Label(status, text="鼠标：检测中…", bg=theme.PANEL,
                                  fg=theme.TEXT_DIM, font=theme.font(10), anchor="w")
        self.lbl_mouse.pack(fill="x")
        self.lbl_pad = tk.Label(status, text="手柄：检测中…", bg=theme.PANEL,
                                fg=theme.TEXT_DIM, font=theme.font(10), anchor="w")
        self.lbl_pad.pack(fill="x")

        self.lbl_admin = tk.Label(status, text="权限：检测中…", bg=theme.PANEL,
                                  fg=theme.TEXT_DIM, font=theme.font(10), anchor="w")
        self.lbl_admin.pack(fill="x")

        self.lbl_tip = tk.Label(wrap, text="", bg=theme.BG, fg=theme.WARN,
                                font=theme.font(10), anchor="w", justify="left",
                                wraplength=dpi.S(500))
        self.lbl_tip.pack(fill="x", pady=dpi.Spair((6, 0)))

        # 键位映射：让用户直接看到「按哪个键对应谁」
        self.lbl_map = tk.Label(wrap, text="", bg=theme.PANEL, fg=theme.TEXT_DIM,
                                font=theme.font(10), anchor="w", justify="left",
                                wraplength=dpi.S(500), padx=dpi.S(10), pady=dpi.S(8))
        self.lbl_map.pack(fill="x", pady=dpi.Spair((10, 0)))

        self.big = tk.Label(wrap, text="按下任意键…", bg=theme.BG, fg=theme.ACCENT,
                            font=theme.font(22, True), pady=dpi.S(18))
        self.big.pack(fill="x")

        tk.Label(wrap, text="最近收到的按键", bg=theme.BG, fg=theme.TEXT_MUTED,
                 font=theme.font(9), anchor="w").pack(fill="x")
        self.listbox = tk.Listbox(wrap, bg=theme.PANEL, fg=theme.TEXT,
                                  selectbackground=theme.PANEL_3, relief="flat",
                                  highlightthickness=0, font=theme.font(10), height=9)
        self.listbox.pack(fill="both", expand=True, pady=dpi.Spair((4, 10)))

        tk.Label(wrap, text="提示：如果这里能看到按键，但游戏里悬浮窗不推进，"
                            "通常是绑定键和实际技能键不一致。",
                 bg=theme.BG, fg=theme.TEXT_MUTED, font=theme.font(9),
                 anchor="w", wraplength=dpi.S(510), justify="left").pack(fill="x")

        self.refresh_status()
        center_window(self.win, app.root, 560, 470)

    def _mapping_text(self):
        from .gamepad import button_name
        app = self.app
        s = app.store.settings
        rot = app.store.active_rotation()
        team = rot.members() if rot else app.store.team.normalized()

        parts = []
        for i, op in enumerate(team[:4]):
            parts.append("%d→%s" % (i + 1, op or "(空)"))

        combo = vk_label(s.combo_key) if s.combo_key else "—"
        pmod = button_name(s.pad_modifier, s.gamepad_scheme)
        pcombo = button_name(s.pad_combo, s.gamepad_scheme)
        letters = " / ".join(
            button_name(s.pad_slot_key(i), s.gamepad_scheme) or "?"
            for i in range(4))
        if s.pad_ult_mode == "alt":
            pult = button_name(s.pad_ult_modifier, s.gamepad_scheme)
            pad_line = "手柄：连携 %s　战技 %s + %s　终结 %s + %s" % (
                pcombo, pmod, letters, pult, letters)
        else:
            pad_line = "手柄：连携 %s　战技/终结 %s + %s（长按）" % (
                pcombo, pmod, letters)
        return ("队伍映射：%s\n"
                "键盘：连携 %s　长按判定 %d ms\n%s"
                % (" · ".join(parts), combo, int(s.hold_ms), pad_line))

    def _verdict(self, vk):
        """这颗键在当前设置下是什么含义。"""
        app = self.app
        s = app.store.settings
        rot = app.store.active_rotation()
        team = rot.members() if rot else app.store.team.normalized()
        if s.combo_key and vk == s.combo_key:
            return "连携键"
        if vk in (0x31, 0x32, 0x33, 0x34):
            slot = vk - 0x31
            op = team[slot] if slot < len(team) else ""
            if not op:
                return "槽位 %d 为空" % (slot + 1)
            return "第%d位 %s（短按技能 / 长按终结）" % (slot + 1, op)
        return "非技能键"

    def refresh_status(self):
        lis = self.app.listener
        self.lbl_hook.configure(
            text=("钩子：已生效" if lis.hook_ok else "钩子：未生效"),
            fg=theme.GREEN if lis.hook_ok else theme.BAD)
        self.lbl_poll.configure(
            text=("轮询：已生效" if lis.poll_ok else "轮询：未生效"),
            fg=theme.GREEN if lis.poll_ok else theme.BAD)
        self.lbl_mouse.configure(
            text=("鼠标：已生效" if lis.mouse_hook_ok else "鼠标：未启用"),
            fg=theme.GREEN if lis.mouse_hook_ok else theme.TEXT_MUTED)
        pad = getattr(self.app, "pad_connected", False)
        self.lbl_pad.configure(
            text=("手柄：已连接" if pad else
                  ("手柄：未连接" if getattr(self.app.gamepad, "available", False)
                   else "手柄：XInput 不可用")),
            fg=theme.GREEN if pad else theme.TEXT_MUTED)
        try:
            self.lbl_map.configure(text=self._mapping_text())
        except tk.TclError:
            pass

        from .elevation import is_admin
        admin = is_admin()
        self.lbl_admin.configure(
            text=("权限：管理员（游戏里也能收到按键）" if admin
                  else "权限：普通用户"),
            fg=theme.GREEN if admin else theme.WARN)
        if admin:
            self.lbl_tip.configure(text="")
        else:
            self.lbl_tip.configure(
                text="如果桌面上能识别按键、切到游戏就没反应，"
                     "多半是游戏以管理员运行而本程序没有。"
                     "右键程序 → 以管理员身份运行。")

    def push(self, ev):
        name = vk_label(ev.vk)
        verdict = self._verdict(ev.vk)
        self.big.configure(text="%s   →  %s" % (name, verdict))
        self.listbox.insert(0, "%s  vk=%s  %s" % (name, ev.vk, verdict))
        if self.listbox.size() > 60:
            self.listbox.delete(59, tk.END)
        self.refresh_status()

    def push_pad(self, bit):
        from .gamepad import button_name
        from .model import KIND_CN
        s = self.app.store.settings
        scheme = s.gamepad_scheme
        name = "手柄 " + button_name(bit, scheme)

        if bit == s.pad_modifier:
            verdict = "修饰键（按住它再按字母才是取用技能）"
        elif bit == s.pad_combo:
            verdict = "连携技"
        else:
            slot = s.pad_slot_of(bit)
            if slot is None:
                verdict = "未映射"
            else:
                rot = self.app.store.active_rotation()
                team = rot.members() if rot else self.app.store.team.normalized()
                op = team[slot] if slot < len(team) else ""
                verdict = ("槽位 %d %s（短按战技 / 长按终结）"
                           % (slot + 1, op or "(空)"))

        self.big.configure(text="%s   →  %s" % (name, verdict))
        self.listbox.insert(0, "%s  bit=0x%04X  %s" % (name, bit, verdict))
        if self.listbox.size() > 60:
            self.listbox.delete(59, tk.END)
        self.refresh_status()

    def destroy(self):
        try:
            self.win.destroy()
        except tk.TclError:
            pass
