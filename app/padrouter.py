# -*- coding: utf-8 -*-
"""手柄按键 -> 动作的判定（纯逻辑，不碰窗口，方便自测）。

游戏内有两套终结技施放方式（设置里叫「终结技施放动作 2」）：

    hold（动作 2 关，默认）  战技 = LB + 槽位键（短按）；终结 = 长按同一个键
    alt （动作 2 开）        战技 = LB + 槽位键（按下即算）；
                             终结 = 终结键 + 槽位键（默认终结键 = RB）

alt 方式下终结键通常就是连携键（RB）：按住它再按字母 = 终结技，
不按字母直接松开 = 连携技。
"""
import time


class PadRouter:
    """把 XInput 的按键事件翻成「放哪个技能」。"""

    def __init__(self, settings, press, clock=None):
        self.settings = settings
        self.press = press              # press(vk, hold=False)
        self.clock = clock or time.monotonic
        self.down = set()               # 当前按住的手柄键
        self.hold_start = {}            # 槽位键按下时刻（方式一用）
        self.ult_used = False           # 终结键按住期间是否已经放过终结技

    # ---------- 属性 ----------
    @property
    def alt(self):
        return getattr(self.settings, "pad_ult_mode", "hold") == "alt"

    @property
    def ult_modifier(self):
        return int(getattr(self.settings, "pad_ult_modifier", 0) or 0)

    def reset(self):
        self.down.clear()
        self.hold_start.clear()
        self.ult_used = False

    # ---------- 主入口 ----------
    def feed(self, phase, bit, active=True):
        """处理一次手柄事件（phase = "down" / "up"）。"""
        if phase == "down":
            self.down.add(bit)
        else:
            self.down.discard(bit)

        if not active:
            return

        s = self.settings
        alt = self.alt
        ult_mod = self.ult_modifier

        # ---- 终结键（方式二）----
        if alt and ult_mod and bit == ult_mod:
            if phase == "down":
                self.ult_used = False
            else:
                used = self.ult_used
                self.ult_used = False
                # 按住期间没放终结技，且这个键兼作连携键 -> 放连携
                if not used and ult_mod == int(s.pad_combo or 0):
                    self.press(s.combo_key, hold=False)
            return

        # ---- 连携技：单独一个键（默认 RB）----
        if bit == int(s.pad_combo or 0):
            if phase == "down":
                self.press(s.combo_key, hold=False)
            return

        # ---- 槽位字母 X/Y/A/B ----
        slot = s.pad_slot_of(bit)
        if slot is None:
            return
        digit = s.slot_key(slot)
        if digit is None:
            return

        # 方式二：终结键 + 槽位键（按下即算，不用长按）
        if alt and ult_mod in self.down:
            if phase == "down":
                self.ult_used = True
                self.press(digit, hold=True)
            return

        # 方式一：修饰键（LB）+ 槽位键，短按 = 战技，长按 = 终结技
        if phase == "down":
            if int(s.pad_modifier or 0) in self.down:
                self.hold_start[bit] = self.clock()
            else:
                self.hold_start[bit] = None     # 没按 LB，不算技能
            return

        started = self.hold_start.pop(bit, None)
        if started is None:
            return
        elapsed = (self.clock() - started) * 1000.0
        if alt:
            # 方式二下长按战技键不再等于终结技，避免误触
            self.press(digit, hold=False)
        else:
            self.press(digit, hold=elapsed >= float(getattr(s, "hold_ms", 280)))
