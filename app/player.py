# -*- coding: utf-8 -*-
"""播放逻辑：编队 = 若干充能轴 → 1 个爆发轴，然后整体重复。

状态机对外只暴露：
    state   idle / running / paused / finished
    current()      当前节点
    current_axis() 当前所在技能轴（悬浮窗据此显示「充能轴 / 爆发轴」）
"""

import time

MATCH = "match"
WRONG = "wrong"
JUMP = "jump"          # 容错：按到本段后面的技能，自动追到该节点之后
IGNORED = "ignored"
FINISHED = "finished"

IDLE = "idle"

from .model import KIND_COMBO, KIND_SKILL, KIND_ULT  # noqa: E402


class Segment:
    """编队里的一段 = 一条技能轴。"""

    def __init__(self, axis, role, charge_index, charge_total):
        self.axis = axis
        self.role = role
        self.charge_index = charge_index      # 第几个充能轴（1 起），爆发轴为 0
        self.charge_total = charge_total


class Player:
    def __init__(self, rotation=None, store=None, settings=None):
        self.store = store
        self.settings = settings
        self.rotation = rotation
        self.state = IDLE
        self.cycle = 0              # 第几轮
        self.segment = 0            # 当前是第几段
        self.index = 0              # 段内第几个节点
        self.done = set()
        self._segments = []
        # 输入容错：过滤按键自动重复、手柄抖动和很短时间内的重复多按。
        # 120ms 足以覆盖硬件/系统重复，又不会妨碍正常技能节奏。
        self.duplicate_window = 0.12
        self.clock = time.monotonic
        self._last_input = None
        self._last_input_at = 0.0
        self.rebuild()

    # ---------- 结构 ----------
    def set_rotation(self, rotation):
        self.rotation = rotation
        self.rebuild()
        self.reset()

    def rebuild(self):
        """把编队展开成 [充能轴..., 爆发轴] 的段列表。"""
        self._segments = []
        if not self.rotation or not self.store:
            return
        charges = [self.store.axis_by_id(a) for a in self.rotation.charge_axes]
        charges = [a for a in charges if a is not None]
        total = len(charges)
        for i, axis in enumerate(charges, 1):
            self._segments.append(Segment(axis, "charge", i, total))
        burst = self.store.axis_by_id(self.rotation.burst_axis)
        if burst is not None:
            self._segments.append(Segment(burst, "burst", 0, total))

    @property
    def segments(self):
        return self._segments

    def current_segment(self):
        if 0 <= self.segment < len(self._segments):
            return self._segments[self.segment]
        return None

    def current_axis(self):
        seg = self.current_segment()
        return seg.axis if seg else None

    # ---------- 生命周期 ----------
    def start(self):
        self.reset()
        if self._segments and any(s.axis.nodes for s in self._segments):
            self.state = "running"
        return self.state

    def pause(self):
        if self.state == "running":
            self.state = "paused"

    def resume(self):
        if self.state == "paused":
            self.state = "running"

    def toggle(self):
        if self.state == "running":
            self.pause()
        elif self.state == "paused":
            self.resume()
        else:
            self.start()

    def reset(self):
        self.state = IDLE
        self.cycle = 0
        self.segment = 0
        self.index = 0
        self.done = set()
        self._last_input = None
        self._last_input_at = 0.0
        self._skip_empty()

    def _skip_empty(self):
        """跳过没有节点的段，避免卡住。"""
        guard = 0
        while self.segment < len(self._segments) and not self._segments[self.segment].axis.nodes:
            self.segment += 1
            self.index = 0
            guard += 1
            if guard > 64:
                break

    # ---------- 查询 ----------
    @property
    def total(self):
        axis = self.current_axis()
        return len(axis.nodes) if axis else 0

    def current(self):
        axis = self.current_axis()
        if not axis or self.index >= len(axis.nodes):
            return None
        return axis.nodes[self.index]

    def upcoming(self):
        axis = self.current_axis()
        if not axis or self.index + 1 >= len(axis.nodes):
            return None
        return axis.nodes[self.index + 1]

    def nodes_of_segment(self):
        axis = self.current_axis()
        return list(axis.nodes) if axis else []

    @property
    def cycle_repeat(self):
        """永远无限循环。"""
        return 0

    # ---------- 推进 ----------
    def press(self, vk=None, button=None, hold=False):
        """收到一次输入。

        vk     键盘键码
        button 手柄位掩码
        hold   True 表示这是一次长按（用于终结技）
        """
        if self.state != "running":
            return IGNORED, None
        node = self.current()
        if node is None:
            return FINISHED, None

        # 同一输入在极短时间内重复出现，视为按键自动重复、手柄抖动或多按。
        # 在循环刚回到开头时也保留这个保护，避免最后一个技能的重复输入
        # 误触发下一轮第一个同键技能。
        signature = (vk, button, bool(hold))
        now = self.clock()
        if (signature == self._last_input
                and now - self._last_input_at < self.duplicate_window):
            self._last_input_at = now
            return IGNORED, ("duplicate", node)
        self._last_input = signature
        self._last_input_at = now

        s = self.settings
        any_key = getattr(s, "mode", "strict") == "any"
        if any_key or self._matches(node, vk, button, hold):
            self.done.add(self.index)
            self._advance()
            return MATCH, node

        forgive = bool(getattr(s, "forgive_hold", False))

        # 容错一：技能节点被长按（手抖按住超过阈值）——按同一颗键，照样算这个技能。
        if forgive and hold and node.kind == KIND_SKILL:
            if self._matches(node, vk, button, False):
                self.done.add(self.index)
                self._advance()
                return MATCH, node

        # 容错二：按到了本段后面的技能，自动跳过中间节点并继续循环。
        # 只在当前技能轴内追赶，避免一次误按跨过整条轴或整轮循环。
        axis = self.current_axis()
        old_index = self.index
        for i in range(old_index + 1, len(axis.nodes)):
            n = axis.nodes[i]
            ok = self._matches(n, vk, button, hold)
            if not ok and forgive and hold and n.kind == KIND_SKILL:
                ok = self._matches(n, vk, button, False)
            if ok:
                skipped = i - old_index
                self._skip_to(i)
                return JUMP, (n, skipped)

        # 其它误按、虚按、多按只反馈，不改变进度，更不会暂停循环。
        # 即使它碰巧属于后面的技能轴，也留在当前节点继续等待正确输入。
        for seg in self._segments[self.segment + 1:]:
            for i, n in enumerate(seg.axis.nodes):
                if self._matches(n, vk, button, hold):
                    return WRONG, (node, n, i)
        return IGNORED, ("noise", node)

    def _team_members(self):
        """当前编队的队伍；编队没有队伍时退回全局默认。"""
        if self.rotation is not None and self.rotation.team:
            members = self.rotation.team.normalized()
            if any(members):
                return members
        if self.store is not None:
            return self.store.team.normalized()
        return []

    def _slot_of(self, node):
        """节点干员在队伍里的位置（0 起），找不到返回 None。"""
        try:
            return self._team_members().index(node.operator)
        except (ValueError, AttributeError):
            return None

    def _matches(self, node, vk, button, hold=False):
        s = self.settings
        if not s:
            return False

        if node.kind == KIND_COMBO:
            # 连携：所有干员统一一个键，不分长按
            want = s.combo_key
            if vk is not None and want is not None and vk == want:
                return True
            pad = s.pad_for(KIND_COMBO)
            return button is not None and pad is not None and button == pad

        slot = self._slot_of(node)
        digit = s.slot_key(slot)

        if node.kind == KIND_SKILL:
            # 技能：短按该干员的数字键
            if vk is not None and not hold and digit is not None and vk == digit:
                return True
            pad = s.pad_for(KIND_SKILL)
            return button is not None and pad is not None and button == pad

        if node.kind == KIND_ULT:
            # 终结技：长按该干员的数字键
            if vk is not None and hold and digit is not None and vk == digit:
                return True
            pad = s.pad_for(KIND_ULT)
            return button is not None and pad is not None and button == pad

        return False

    def skip(self):
        if self.state != "running" or self.current() is None:
            return False
        self.done.add(self.index)
        self._advance()
        return True

    def _skip_to(self, index):
        """把当前段推进到第 index 个节点之后（含它），用于自动追轴。"""
        seg = self.segment
        guard = 0
        while self.segment == seg and self.index <= index and guard < 512:
            self.done.add(self.index)
            self._advance()
            guard += 1

    def restart(self):
        """回到第一段第一个技能，并保持原来的运行/暂停状态（「重置」用）。"""
        state = self.state
        self.reset()
        has_nodes = any(seg.axis.nodes for seg in self._segments)
        if not has_nodes:
            return self.state
        if state == "running":
            self.state = "running"
        elif state == "paused":
            self.state = "paused"
        return self.state

    def _advance(self):
        axis = self.current_axis()
        self.index += 1
        if axis and self.index < len(axis.nodes):
            return

        # 本段走完 -> 下一段
        self.segment += 1
        self.index = 0
        self.done = set()
        if self.segment < len(self._segments):
            self._skip_empty()
            if self.segment < len(self._segments):
                return

        # 一轮走完 -> 无限循环，直接回到第一段
        self.cycle += 1
        self.segment = 0
        self.index = 0
        self.done = set()
        self._skip_empty()
        if self.segment >= len(self._segments):
            self.state = "finished"
