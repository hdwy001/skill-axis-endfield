# -*- coding: utf-8 -*-
"""「检查更新」窗口：查 GitHub -> 只下改过的文件 -> 覆盖 -> 重启生效。"""

import os
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import dpi, paths, theme
from . import updater as up
from .widgets import center_window


class UpdateDialog:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.manifest = None
        self.plan = []
        self.busy = False

        self.win = tk.Toplevel(self.root)
        self.win.title("检查更新")
        self.win.configure(bg=theme.BG)
        self.win.transient(self.root)
        self.win.resizable(False, False)
        self.win.protocol("WM_DELETE_WINDOW", self.close)

        body = tk.Frame(self.win, bg=theme.BG, padx=dpi.S(20), pady=dpi.S(18))
        body.pack(fill="both", expand=True)

        tk.Label(body, text="软件更新", bg=theme.BG, fg=theme.TEXT,
                 font=theme.font(theme.F_SECTION, True)).pack(anchor="w")
        self.sub = tk.Label(body, text="当前版本 v%s" % up.local_version(),
                            bg=theme.BG, fg=theme.TEXT_MUTED,
                            font=theme.font(theme.F_TINY))
        self.sub.pack(anchor="w", pady=dpi.Spair((4, 10)))

        self.state = tk.Label(body, text="正在检查 GitHub…", bg=theme.PANEL,
                              fg=theme.TEXT, anchor="w", justify="left",
                              wraplength=dpi.S(400),
                              font=theme.font(theme.F_BODY),
                              padx=dpi.S(12), pady=dpi.S(10))
        self.state.pack(fill="x")

        self.bar = ttk.Progressbar(body, mode="determinate", maximum=100)
        self.bar.pack(fill="x", pady=dpi.Spair((10, 0)))

        btns = tk.Frame(body, bg=theme.BG)
        btns.pack(fill="x", pady=dpi.Spair((14, 0)))
        self.btn_go = self._btn(btns, "立即更新", self.do_update, "primary")
        self.btn_close = self._btn(btns, "关闭", self.close, "ghost")
        self.btn_go.pack(side="right", padx=dpi.Spair((6, 0)))
        self.btn_close.pack(side="right")
        self.btn_go.configure(state="disabled")

        center_window(self.win, self.root, 470, 250)
        self.win.lift()
        self.win.focus_force()
        self.start_check()

    # ---------- 小工具 ----------
    def _btn(self, parent, text, cmd, kind="ghost"):
        colors = {
            "primary": (theme.ACCENT, "#221a06", theme.ACCENT_SOFT),
            "ghost": (theme.PANEL_2, theme.TEXT, theme.PANEL_3),
        }
        bg, fg, active = colors[kind]
        return tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                         activebackground=active, activeforeground=fg,
                         relief="flat", bd=0, cursor="hand2",
                         highlightthickness=0, padx=dpi.S(14), pady=dpi.S(6),
                         font=theme.font(theme.F_SMALL))

    def _ui(self, fn, *args):
        """从子线程回到 Tk 主线程。"""
        try:
            self.root.after(0, lambda: fn(*args))
        except tk.TclError:
            pass

    def _set_state(self, text, color=theme.TEXT):
        try:
            self.state.configure(text=text, fg=color)
        except tk.TclError:
            pass

    # ---------- 检查 ----------
    def start_check(self):
        if self.busy:
            return
        self.busy = True
        self.bar.configure(mode="indeterminate")
        self.bar.start(18)
        self._set_state("正在检查 GitHub…")
        threading.Thread(target=self._check_worker, daemon=True).start()

    def _check_worker(self):
        try:
            manifest = up.fetch_manifest()
            todo = up.plan(manifest, paths.base_dir())
        except up.UpdateError as exc:
            self._ui(self._check_failed, str(exc))
            return
        self._ui(self._check_done, manifest, todo)

    def _check_failed(self, msg):
        self._stop_bar()
        self.busy = False
        self._set_state("检查失败：\n%s" % msg, theme.BAD)
        self.btn_go.configure(state="disabled", text="重试",
                              command=self.start_check)
        self.btn_go.configure(state="normal")

    def _check_done(self, manifest, todo):
        self._stop_bar()
        self.busy = False
        self.manifest = manifest
        self.plan = todo
        remote = manifest.get("version", "?")
        local = up.local_version()

        if not up.is_newer(remote, local):
            self._set_state("已是最新版本 v%s。" % local, theme.GREEN)
            self.btn_go.configure(state="disabled", text="立即更新")
            return
        if not todo:
            self._set_state(
                "GitHub 上是 v%s，但文件都一样（可能还没跑 make_manifest）。\n"
                "本地 v%s。" % (remote, local), theme.WARN)
            self.btn_go.configure(state="disabled", text="立即更新")
            return

        size = sum(int((i or {}).get("size", 0) or 0) for _r, i in todo)
        names = "、".join(r for r, _i in todo[:6])
        if len(todo) > 6:
            names += " 等"
        self._set_state(
            "发现新版本 v%s（本地 v%s）\n需要下载 %d 个文件，约 %.0f KB\n%s"
            % (remote, local, len(todo), size / 1024.0, names), theme.ACCENT)
        self.btn_go.configure(state="normal", text="立即更新",
                              command=self.do_update)

    def _stop_bar(self):
        try:
            self.bar.stop()
            self.bar.configure(mode="determinate", value=0)
        except tk.TclError:
            pass

    # ---------- 更新 ----------
    def do_update(self):
        if self.busy or not self.plan:
            return
        self.busy = True
        self.btn_go.configure(state="disabled")
        self.bar.configure(mode="determinate", maximum=len(self.plan),
                           value=0)
        self._set_state("正在下载…")
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _update_worker(self):
        def progress(i, total, rel):
            self._ui(self._on_progress, i, total, rel)

        try:
            written, backup = up.apply(self.plan, paths.base_dir(),
                                       on_progress=progress)
        except up.UpdateError as exc:
            self._ui(self._update_failed, str(exc))
            return
        except OSError as exc:
            self._ui(self._update_failed, "写入失败：%s" % exc)
            return
        self._ui(self._update_done, written, backup)

    def _on_progress(self, i, total, rel):
        try:
            self.bar.configure(value=i)
        except tk.TclError:
            return
        if rel:
            self._set_state("正在下载 %d/%d：%s" % (i + 1, total, rel))

    def _update_failed(self, msg):
        self.busy = False
        self._set_state("更新失败：\n%s\n（原文件已备份到 update_backup/）" % msg,
                        theme.BAD)
        self.btn_go.configure(state="normal", text="重试",
                              command=self.do_update)

    def _update_done(self, written, backup):
        self.busy = False
        self._set_state(
            "更新完成：写了 %d 个文件。\n重启程序后生效。\n备份：%s"
            % (written, backup), theme.GREEN)
        self.btn_go.configure(state="normal", text="立即重启",
                              command=self.restart_app)

    def restart_app(self):
        try:
            if paths.is_frozen():
                subprocess.Popen([sys.executable] + sys.argv[1:])
            else:
                subprocess.Popen([sys.executable, os.path.join(
                    paths.base_dir(), "main.py")])
        except OSError as exc:
            messagebox.showerror("重启失败", "请手动重启程序。\n%s" % exc,
                                 parent=self.win)
            return
        self.app.on_close()

    def close(self):
        if self.busy:
            if not messagebox.askyesno("更新中", "正在下载，确定要关掉吗？",
                                       parent=self.win):
                return
        try:
            self.win.destroy()
        except tk.TclError:
            pass
