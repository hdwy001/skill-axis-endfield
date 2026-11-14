# -*- coding: utf-8 -*-
"""应用装配：把监听、手柄、播放器、编辑器、悬浮窗接在一起。"""
import ctypes
import os
import queue
import time
import tkinter as tk

from . import fonts, paths, theme
from .editor import Editor
from .gamepad import GamepadListener, button_name
from .icons import IconStore
from .keys import MODIFIER_VKS
from .listener import KeyListener
from .model import Store
from .overlay import Overlay
from .padrouter import PadRouter
from .player import FINISHED, IGNORED, MATCH, WRONG, Player
from .testpanel import TestPanel

user32 = ctypes.WinDLL("user32", use_last_error=True)

try:
    import winsound
except Exception:  # pragma: no cover
    winsound = None


class Application:
    def __init__(self):
        self.root = tk.Tk()
        fonts.setup()
        self.root.title("技能轴提示器 · 明日方舟：终末地")
        self.root.geometry("1320x880")
        self.root.minsize(1180, 780)
        self.root.configure(bg=theme.BG)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        base = paths.base_dir()
        self.store = Store(base)
        self.store.defer_save = True        # 改动先记账，防抖后自动落盘
        self.store.on_change = self._schedule_save
        self._save_job = None
        self.last_save_time = None          # 最后一次落盘的时刻
        # 首次启动：把示例数据立刻落盘
        if not os.path.exists(self.store.axes_path):
            self.store.commit()
            self.last_save_time = time.time()
        self.settings = self.store.settings
        self.icons = IconStore(base)

        self.events = queue.Queue()
        self.player = Player(rotation=self.store.active_rotation(),
                             store=self.store, settings=self.settings)

        self.listener = KeyListener(self._on_listener_event,
                                    watch_mouse=self.settings.watch_mouse)
        self.gamepad = GamepadListener(self.events)
        self.pad_connected = False

        self.overlay = None
        self.test_panel = None
        self._bind_cb = None
        self._pad_bind_cb = None
        self._hold_start = {}       # 数字键按下时刻，用于长按判定
        self.pad_router = PadRouter(self.settings, self._press_vk)

        self.editor = Editor(self)

        self.listener.start()
        if self.settings.gamepad_enabled:
            self.gamepad.start()
        self.root.after(25, self._drain)

    # ================= 自动保存 =================
    SAVE_DELAY_MS = 800

    def _schedule_save(self):
        """有改动后延迟落盘；期间再来改动就重新计时。"""
        try:
            if self._save_job is not None:
                self.root.after_cancel(self._save_job)
                self._save_job = None
        except (tk.TclError, ValueError):
            self._save_job = None
        try:
            self._save_job = self.root.after(self.SAVE_DELAY_MS, self._do_save)
        except tk.TclError:
            self._save_job = None

    def _do_save(self):
        self._save_job = None
        try:
            if self.store.dirty:
                self.store.commit()
                self._mark_saved()
        except Exception:
            pass

    def _mark_saved(self):
        self.last_save_time = time.time()
        ed = getattr(self, "editor", None)
        if ed is not None:
            try:
                ed.show_last_save(self.last_save_time)
            except (tk.TclError, AttributeError):
                pass

    def flush_save(self):
        """立刻落盘（切换编队、退出时用）。"""
        try:
            if self._save_job is not None:
                self.root.after_cancel(self._save_job)
                self._save_job = None
        except (tk.TclError, ValueError):
            self._save_job = None
        try:
            if self.store.flush():
                self._mark_saved()
        except Exception:
            pass

    # ================= 事件 =================
    def _on_listener_event(self, ev):
        self.events.put(ev)

    def _drain(self):
        try:
            while True:
                item = self.events.get_nowait()
                self._dispatch(item)
        except queue.Empty:
            pass
        try:
            self.root.after(20, self._drain)
        except tk.TclError:
            pass

    def _dispatch(self, item):
        if isinstance(item, tuple):
            kind = item[0]
            if kind == "pad":
                self._handle_pad(item[1], item[2])
            elif kind == "gamepad":
                self.pad_connected = (item[1] == "connected")
                if self.editor is not None:
                    try:
                        self.editor._sync_settings_widgets()
                    except (tk.TclError, AttributeError):
                        pass
            return
        self._handle_event(item)

    def _handle_pad(self, phase, bit):
        # 绑定手柄
        if self._pad_bind_cb is not None:
            if phase == "down":
                cb, self._pad_bind_cb = self._pad_bind_cb, None
                cb(bit)
            return

        if not self.gamepad.enabled:
            # 关掉手柄监听时仍然记账，免得重新打开后按住的键状态不对
            self.pad_router.feed(phase, bit, active=False)
            return

        if self.test_panel is not None and phase == "down":
            try:
                self.test_panel.push_pad(bit)
            except tk.TclError:
                self.test_panel = None

        # 判定规则在 app/padrouter.py（两种终结技方式都在那里）
        self.pad_router.feed(phase, bit)

    def _press_vk(self, vk, hold=False):
        """把手柄动作换算成「等价的键盘按键」交给播放器。

        这样手柄和键盘共用同一套判定（数字键=队伍位，长按=终结技），
        不用维护两份匹配逻辑。
        """
        if vk is None:
            return
        if self.player.state not in ("running", "paused"):
            return
        if not self.is_overlay_visible():
            return
        if self.settings.only_game_focus and not self._game_in_focus():
            return
        result, info = self.player.press(vk=vk, hold=hold)
        self._after_press(result, info)

    def _handle_event(self, ev):
        from .model import SLOT_VKS

        # 1) 绑定键盘（最优先：数字键 1~4 也要能绑）
        if self._bind_cb is not None:
            if ev.mouse or not ev.down or ev.vk in MODIFIER_VKS:
                return
            cb, self._bind_cb = self._bind_cb, None
            cb(ev)
            return

        # 2) 测试面板实时显示（数字键也要能看到，否则会以为监听失效）
        if self.test_panel is not None and ev.down:
            try:
                self.test_panel.push(ev)
            except tk.TclError:
                self.test_panel = None

        # 3) 数字键 1~4：要等松开才知道是短按还是长按
        if ev.vk in SLOT_VKS and not ev.mouse:
            if ev.down:
                # 按住时系统会不断重复发送按下事件，只记第一次，
                # 否则长按会被反复重置成短按
                if ev.vk not in self._hold_start:
                    self._hold_start[ev.vk] = time.monotonic()
                return
            started = self._hold_start.pop(ev.vk, None)
            if started is None:
                # 没记录到按下（例如程序启动时就按住），按短按处理，别丢键
                self._press_maybe(ev, hold=False)
                return
            elapsed = (time.monotonic() - started) * 1000.0
            self._press_maybe(ev, hold=elapsed >= float(self.settings.hold_ms))
            return

        if not ev.down:
            return

        # 4) 全局快捷键
        s = self.settings
        if ev.vk == s.hotkey_visible:
            self.toggle_overlay()
            return
        if ev.vk == s.hotkey_through:
            self.toggle_through()
            return
        if ev.vk == s.hotkey_reset:
            self.player.reset()
            self.refresh_overlay()
            return
        if ev.vk == s.hotkey_start:
            self.toggle_player()
            return

        self._press_maybe(ev)

    def _press_maybe(self, ev, hold=False):
        """把一次输入交给播放器判定。"""
        if self._bind_cb is not None:
            return
        if self.player.state not in ("running", "paused"):
            return
        if not self.is_overlay_visible():
            return
        s = self.settings
        if s.only_game_focus and not self._game_in_focus():
            return
        result, info = self.player.press(vk=ev.vk, hold=hold)
        self._after_press(result, info)

    def _after_press(self, result, info):
        if result == MATCH:
            self.refresh_overlay()
            if self.player.state == "finished":
                self._beep(880, 160)
        elif result == WRONG:
            cur = info[0]
            self.refresh_overlay()
            self.overlay_show_hint("顺序不对：现在应放「%s」" % (cur.skill or "当前技能"))
        elif result == FINISHED:
            pass

    # ================= 播放 =================
    def rebuild_player(self):
        rot = self.store.active_rotation()
        self.player.set_rotation(rot)
        self.refresh_overlay()

    def toggle_player(self):
        if not self.is_overlay_visible():
            self.show_overlay()
        p = self.player
        if p.state == "running":
            p.pause()
        elif p.state == "paused":
            p.resume()
        else:
            p.set_rotation(self.store.active_rotation())
            p.start()
        self.refresh_overlay()

    def show_overlay(self):
        if self.overlay is None:
            self.overlay = Overlay(self)
            self.overlay.set_click_through(self.settings.click_through)
            try:
                self.overlay.show()
            except Exception:
                pass
        else:
            self.overlay.show()
        self.refresh_overlay()

    def hide_overlay(self):
        if self.overlay is not None:
            self.overlay.hide()
        self.player.reset()

    def toggle_overlay(self):
        if self.is_overlay_visible():
            self.hide_overlay()
        else:
            self.show_overlay()

    def is_overlay_visible(self):
        if self.overlay is None:
            return False
        return self.overlay.visible()

    def refresh_overlay(self):
        if self.is_overlay_visible():
            self.overlay.redraw()

    def overlay_show_hint(self, text):
        if self.is_overlay_visible():
            self.overlay.show_hint(text)

    def set_overlay_opacity(self, value, persist=True):
        """设置悬浮窗底色的不透明度（只影响背景层，文字不淡）。"""
        if self.overlay is None:
            return
        self.overlay.set_opacity(value, persist=persist)

    def toggle_through(self):
        self.settings.click_through = not self.settings.click_through
        if self.overlay is not None:
            self.overlay.set_click_through(self.settings.click_through)
        self.persist_settings()
        self.refresh_overlay()

    # ================= 绑定 =================
    def begin_bind(self, callback):
        self._bind_cb = callback

    def begin_pad_bind(self, callback):
        if not self.gamepad.available:
            from tkinter import messagebox
            messagebox.showwarning("手柄不可用", "系统里没有找到 XInput 库", parent=self.root)
            return
        if not self.gamepad._thread:
            self.gamepad.start()
        self._pad_bind_cb = callback

    def set_gamepad_enabled(self, enabled):
        self.gamepad.enabled = enabled
        if not enabled:
            self.pad_router.reset()
        elif not self.gamepad._thread:
            self.gamepad.start()

    # ================= 面板 =================
    def open_test_panel(self):
        if self.test_panel is not None:
            try:
                self.test_panel.win.deiconify()
                self.test_panel.win.lift()
                self.test_panel.refresh_status()
                return
            except tk.TclError:
                self.test_panel = None
        self.test_panel = TestPanel(self)
        self.root.after(600, self._refresh_panel_status)

    def _refresh_panel_status(self):
        if self.test_panel is not None:
            try:
                self.test_panel.refresh_status()
            except tk.TclError:
                self.test_panel = None

    # ================= 持久化 =================
    def persist(self):
        self.store.save_axes()

    def persist_settings(self):
        self.store.save_settings()

    # ================= 杂项 =================
    def _fg_title(self):
        try:
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 2)
            user32.GetWindowTextW(hwnd, buf, length + 2)
            return buf.value
        except Exception:
            return ""

    def _game_in_focus(self):
        kw = (self.settings.game_keyword or "").strip().lower()
        if not kw:
            return True
        return kw in self._fg_title().lower()

    def _beep(self, freq=880, ms=140):
        if winsound is None:
            return
        try:
            winsound.Beep(freq, ms)
        except Exception:
            pass

    def on_close(self):
        try:
            # 关软件时无条件保存一次
            try:
                if self._save_job is not None:
                    self.root.after_cancel(self._save_job)
                    self._save_job = None
            except (tk.TclError, ValueError):
                self._save_job = None
            try:
                self.store.commit()
            except Exception:
                pass
            try:
                self.store.save_settings()
            except Exception:
                pass
            self.listener.stop()
            self.gamepad.stop()
            try:
                self.root.destroy()
            except tk.TclError:
                pass
        except Exception:
            pass


def run():
    app = Application()
    app.root.mainloop()
