# -*- coding: utf-8 -*-
"""通用文本输入弹窗：居中显示，返回输入内容。"""
import tkinter as tk

from . import dpi, theme
from .widgets import center_window


class TextDialog:
    def __init__(self, app, title, label, initial="", ok_text="确定"):
        self.result = None
        self.win = tk.Toplevel(app.root)
        self.win.title(title)
        self.win.configure(bg=theme.BG)
        self.win.transient(app.root)
        self.win.resizable(False, False)
        self.win.grab_set()

        box = tk.Frame(self.win, bg=theme.BG, padx=dpi.S(22), pady=dpi.S(18))
        box.pack(fill="both", expand=True)

        tk.Label(box, text=label, bg=theme.BG, fg=theme.TEXT_DIM,
                 font=theme.font(theme.F_SMALL), anchor="w").pack(fill="x")

        self.var = tk.StringVar(value=initial)
        ent = tk.Entry(box, textvariable=self.var, bg=theme.PANEL_2, fg=theme.TEXT,
                       insertbackground=theme.TEXT, relief="flat", bd=0,
                       selectbackground=theme.ACCENT, selectforeground="#221a06",
                       highlightthickness=1, highlightbackground=theme.BORDER,
                       highlightcolor=theme.ACCENT, font=theme.font(theme.F_BODY))
        ent.pack(fill="x", pady=dpi.Spair((6, 14)), ipady=dpi.S(5))
        ent.icursor("end")
        ent.select_range(0, "end")
        ent.focus_set()

        bar = tk.Frame(box, bg=theme.BG)
        bar.pack(fill="x")
        tk.Button(bar, text=ok_text, command=self._ok, bg=theme.ACCENT,
                  fg="#221a06", activebackground=theme.ACCENT_SOFT,
                  activeforeground="#221a06", relief="flat", bd=0,
                  highlightthickness=0, cursor="hand2",
                  font=theme.font(theme.F_BODY, True),
                  padx=dpi.S(18), pady=dpi.S(5)).pack(side="right")
        tk.Button(bar, text="取消", command=self._cancel, bg=theme.PANEL_2,
                  fg=theme.TEXT_DIM, activebackground=theme.PANEL_3,
                  activeforeground=theme.TEXT, relief="flat", bd=0,
                  highlightthickness=0, cursor="hand2",
                  font=theme.font(theme.F_SMALL), padx=dpi.S(14), pady=dpi.S(5)).pack(side="right",
                                                                     padx=dpi.S(8))

        ent.bind("<Return>", lambda e: self._ok())
        self.win.bind("<Escape>", lambda e: self._cancel())

        center_window(self.win, app.root, 380, 170)
        self.win.wait_window()

    def _ok(self):
        self.result = self.var.get().strip()
        self._close()

    def _cancel(self):
        self.result = None
        self._close()

    def _close(self):
        try:
            self.win.grab_release()
        except tk.TclError:
            pass
        try:
            self.win.destroy()
        except tk.TclError:
            pass


def ask_text(app, title, label, initial="", ok_text="确定"):
    return TextDialog(app, title, label, initial, ok_text).result
