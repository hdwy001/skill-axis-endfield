# -*- coding: utf-8 -*-
"""全局按键监听：底层钩子 + 轮询双路，纯 ctypes 实现，不拦截任何按键。

设计要点：
* 钩子回调永远调用 CallNextHookEx，绝不吞键，游戏照常收到输入。
* 轮询用 GetAsyncKeyState 兜底，钩子被环境挡住时仍有机会工作。
* 两路事件按时间窗去重，避免同一次按键触发两次推进。
"""
import ctypes
import ctypes.wintypes as wt
import threading
import time

from .keys import MOUSE_BASE

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14

WM_KEYDOWN = 0x0100
WM_SYSKEYDOWN = 0x0104
WM_KEYUP = 0x0101
WM_SYSKEYUP = 0x0105
WM_MOUSE_DOWNS = {0x0201: 1, 0x0204: 2, 0x0207: 3, 0x020B: 4, 0x020C: 5}

DEDUPE_WINDOW = 0.06


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wt.POINT), ("mouseData", wt.DWORD), ("flags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wt.WPARAM, wt.LPARAM)

user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wt.DWORD]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]


class KeyEvent:
    __slots__ = ("vk", "source", "mouse", "down")

    def __init__(self, vk, source="hook", down=True):
        self.vk = vk
        self.source = source
        self.down = bool(down)
        self.mouse = vk is not None and vk >= MOUSE_BASE

    def __repr__(self):
        return f"<KeyEvent vk={self.vk} {self.source} {'down' if self.down else 'up'}>"


class KeyListener:
    def __init__(self, on_event=None, watch_mouse=True):
        self.on_event = on_event
        self.watch_mouse = watch_mouse
        self._last = {}
        self._pressed = set()       # 键盘按下边沿；过滤系统自动重复 KEYDOWN
        self._lock = threading.Lock()
        self.hook_ok = False
        self.mouse_hook_ok = False
        self.poll_ok = False
        self.running = False
        self._kb_proc = HOOKPROC(self._kb_callback)
        self._ms_proc = HOOKPROC(self._ms_callback)
        self._kb_hook = None
        self._ms_hook = None

    # ---------- 对外 ----------
    def start(self):
        if self.running:
            return
        self.running = True
        threading.Thread(target=self._kb_thread, daemon=True).start()
        if self.watch_mouse:
            threading.Thread(target=self._ms_thread, daemon=True).start()
        threading.Thread(target=self._poll_thread, daemon=True).start()

    def stop(self):
        self.running = False
        with self._lock:
            self._pressed.clear()

    # ---------- 去重与分发 ----------
    def _emit(self, vk, source, down=True):
        now = time.monotonic()
        key = (vk, bool(down))
        with self._lock:
            # 鼠标钩子目前只发 down，继续使用时间窗去重；键盘则维护真实
            # 按下集合，只让 up -> down 边沿通过，长按自动重复不会再次触发。
            if vk < MOUSE_BASE:
                if down:
                    if vk in self._pressed:
                        return
                    self._pressed.add(vk)
                else:
                    self._pressed.discard(vk)
            if now - self._last.get(key, 0.0) < DEDUPE_WINDOW:
                return
            self._last[key] = now
        cb = self.on_event
        if cb:
            try:
                cb(KeyEvent(vk, source, down))
            except Exception:
                pass

    # ---------- 键盘钩子 ----------
    def _kb_callback(self, nCode, wParam, lParam):
        if nCode == 0:
            down = wParam in (WM_KEYDOWN, WM_SYSKEYDOWN)
            up = wParam in (WM_KEYUP, WM_SYSKEYUP)
            if down or up:
                try:
                    kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    self._emit(kb.vkCode, "hook", down)
                except Exception:
                    pass
        return user32.CallNextHookEx(self._kb_hook, nCode, wParam, lParam)

    def _kb_thread(self):
        self._kb_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kb_proc, None, 0)
        self.hook_ok = bool(self._kb_hook)
        if not self._kb_hook:
            return
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    # ---------- 鼠标钩子 ----------
    def _ms_callback(self, nCode, wParam, lParam):
        if nCode == 0 and wParam in WM_MOUSE_DOWNS:
            self._emit(MOUSE_BASE + WM_MOUSE_DOWNS[wParam], "mouse-hook")
        return user32.CallNextHookEx(self._ms_hook, nCode, wParam, lParam)

    def _ms_thread(self):
        self._ms_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._ms_proc, None, 0)
        self.mouse_hook_ok = bool(self._ms_hook)
        if not self._ms_hook:
            return
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    # ---------- 轮询兜底 ----------
    def _poll_thread(self):
        time.sleep(0.15)          # 让钩子先装上，避免重复触发
        prev = {}
        self.poll_ok = True
        while self.running:
            for vk in range(0x08, 0xFF):
                state = user32.GetAsyncKeyState(vk)
                down = bool(state & 0x8000)
                if down and not prev.get(vk, False):
                    self._emit(vk, "poll", True)
                elif not down and prev.get(vk, False):
                    self._emit(vk, "poll", False)
                prev[vk] = down
            time.sleep(0.022)
