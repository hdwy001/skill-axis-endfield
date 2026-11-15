# -*- coding: utf-8 -*-
"""播放逻辑：编队 = 若干充能轴 → 1 个爆发轴，然后整体重复。

状态机对外只暴露：
    state   idle / running / paused / finished
    current()      当前节点
    current_axis() 当前所在技能轴（悬浮窗据此显示「充能轴 / 爆发轴」）
"""

MATCH = "match"
WRONG = "wrong"
JUMP = "jump"          # 容错：按到本段后面的技能，自动追到该节点之后继续
IGNORED = "ignored"
FINISHED = "finished"

IDLE = "idle"

import time  # noqa: E402

from .model import (KIND_BRANCH, KIND_COMBO, KIND_SKILL, KIND_ULT,  # noqa: E402
                    Node)


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
        self.repeat_done = 0        # 当前这一段已经重复走过几遍（充能轴循环用）
        # 输入容错：过滤按键自动重复、手柄抖动和很短时间内的重复多按。
        # 120ms 足以覆盖硬件/系统重复，又不会妨碍正常技能节奏。
        self.duplicate_window = 0.12
        self.clock = time.monotonic
        self._last_input = None
        self._last_input_at = 0.0
        # 分支：走到分支点后选的路线（None 表示在主线）
        #   {"axis": Axis, "nodes": [...], "index": 0, "merge": bool, "name": str}
        self.route = None
        self.rebuild()

    # ---------- 结构 ----------
    def set_rotation(self, rotation):
        self.rotation = rotation
        self.rebuild()
        self.reset()

    def rebuild(self):
        """把编队顺序展开成段列表：充能轴和爆发轴可以是任意顺序、任意多条。"""
        self._segments = []
        if not self.rotation or not self.store:
            return
        ids = self.rotation.sequence()
        axes = [self.store.axis_by_id(a) for a in ids]
        axes = [a for a in axes if a is not None]
        total_charge = sum(1 for a in axes if a.role == "charge")
        charge_no = 0
        for axis in axes:
            if axis.role == "burst":
                self._segments.append(Segment(axis, "burst", 0, total_charge))
            else:
                charge_no += 1
                self._segments.append(Segment(axis, "charge", charge_no,
                                              total_charge))

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
        self.repeat_done = 0
        self.route = None
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
        if self.route is not None:
            nodes = self.route["nodes"]
            i = self.route["index"]
            return nodes[i] if 0 <= i < len(nodes) else None
        axis = self.current_axis()
        if not axis or self.index >= len(axis.nodes):
            return None
        return axis.nodes[self.index]

    def upcoming(self):
        if self.route is not None:
            nodes = self.route["nodes"]
            i = self.route["index"] + 1
            return nodes[i] if 0 <= i < len(nodes) else None
        axis = self.current_axis()
        if not axis or self.index + 1 >= len(axis.nodes):
            return None
        return axis.nodes[self.index + 1]

    @property
    def view_index(self):
        """当前该高亮的序号：分支里是分支自己的下标，主线上是主轴下标。"""
        if self.route is not None:
            return self.route["index"]
        return self.index

    def view_total(self):
        return len(self.nodes_of_segment())

    def nodes_of_segment(self):
        if self.route is not None:
            return list(self.route["nodes"])
        axis = self.current_axis()
        return list(axis.nodes) if axis else []

    def current_axis_obj(self):
        """悬浮窗显示用：在路线里就是那条路线轴。"""
        if self.route is not None:
            return self.route.get("axis")
        return self.current_axis()

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

        # 分支点：等一个「预设键」，按到哪条就走哪条
        if node.kind == KIND_BRANCH:
            opt = self._match_branch(node, vk, button, hold)
            if opt is None:
                return IGNORED, None
            self._start_route(node, opt)
            return MATCH, node

        any_key = getattr(self.settings, "mode", "strict") == "any"
        if any_key or self._matches(node, vk, button, hold):
            self.done.add(self.index)
            self._advance()
            return MATCH, node

        # 容错一：技能节点被长按（手抖按住超过阈值）——按同一颗键，照样算这个技能
        if (bool(getattr(self.settings, "forgive_hold", False)) and hold
                and node.kind == KIND_SKILL
                and self._matches(node, vk, button, False)):
            self.done.add(self.index)
            self._advance()
            return MATCH, node

        # 容错二：按到本段后面的技能，自动跳过中间节点并继续（只在当前轴内追赶，
        # 避免一次误按跨过整条轴或整轮循环）
        if self.route is None:
            axis = self.current_axis()
            for i in range(self.index + 1, len(axis.nodes)):
                n = axis.nodes[i]
                ok = self._matches(n, vk, button, hold)
                if (not ok and bool(getattr(self.settings, "forgive_hold", False))
                        and hold and n.kind == KIND_SKILL):
                    ok = self._matches(n, vk, button, False)
                if ok:
                    skipped = i - self.index
                    self._skip_to(i)
                    return JUMP, (n, skipped)

        # 也检查后面几段：按到「更后面的轴」的键同样算顺序错（只提示，不打断循环）
        for seg in self._segments[self.segment + 1:]:
            for i, n in enumerate(seg.axis.nodes):
                if self._matches(n, vk, button, hold):
                    return WRONG, (node, n, i)
        return IGNORED, None

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
        node = self.current()
        if node.kind == KIND_BRANCH and node.options:
            # 跳过分支点：默认走第一条
            self._start_route(node, node.options[0])
            return True
        self.done.add(self.index)
        self._advance()
        return True

    # ---------- 分支 ----------
    def _match_branch(self, node, vk, button, hold):
        """返回第一个命中的分支选项（触发卡与普通节点同一套按键判定）。"""
        from .model import option_trigger
        for opt in node.options or []:
            trig = option_trigger(opt)
            op = str(trig.get("operator") or "")
            if not op:
                continue
            probe = Node(operator=op, kind=trig.get("kind") or KIND_SKILL)
            if self._matches(probe, vk, button, hold):
                return opt
        return None

    def _start_route(self, branch_node, opt):
        """按到触发卡：进入这条分支，后面就是它自己的卡片。"""
        from .model import option_nodes
        self.done.add(self.index)
        nodes = [n for n in option_nodes(opt) if n is not None]
        self.route = {
            "axis": None,
            "nodes": nodes,
            "index": 0,
            "next": str((opt or {}).get("next") or ""),
            "name": "分支",
        }
        self._skip_empty_route()

    def _skip_empty_route(self):
        """分支可能还没排卡片：直接当作走完。"""
        route = self.route
        if route is not None and route["index"] >= len(route["nodes"]):
            self._finish_route()

    def _finish_route(self):
        next_id = str((self.route or {}).get("next") or "")
        self.route = None
        if next_id:
            # 走完直接跳到指定轴（可以是爆发轴）
            for i, seg in enumerate(self._segments):
                if seg.axis.id == next_id:
                    self.segment = i
                    self.index = 0
                    self.done = set()
                    self.repeat_done = 0
                    self._skip_empty()
                    return
            # 目标轴找不到：退回顺着走
        self.index += 1
        axis = self.current_axis()
        if axis is not None and self.index < len(axis.nodes):
            return
        self._advance_segment(after_route=True)

    def _skip_to(self, index):
        """把当前段推进到第 index 个节点之后（含它），用于自动追轴。"""
        seg = self.segment
        guard = 0
        while self.segment == seg and self.index <= index and guard < 512:
            self.done.add(self.index)
            self._advance()
            guard += 1

    def _advance(self):
        # 路线里推进：走完再看要不要汇合
        if self.route is not None:
            self.route["index"] += 1
            if self.route["index"] < len(self.route["nodes"]):
                return
            self._finish_route()
            return

        axis = self.current_axis()
        self.index += 1
        if axis and self.index < len(axis.nodes):
            return

        # 本段走完：充能轴如果设了「走 N 遍」，先原地重来，别急着往后
        if axis is not None and self.current_segment() is not None \
                and self.current_segment().role == "charge":
            try:
                want = int(axis.repeat)
            except (TypeError, ValueError):
                want = 1
            if want > 1 and self.repeat_done + 1 < want:
                self.repeat_done += 1
                self.index = 0
                self.done = set()
                return

        self._advance_segment()

    def _advance_segment(self, after_route=False):
        """本段结束：进下一段，或整轮结束回到第一段。"""
        self.segment += 1
        self.index = 0
        self.done = set()
        self.repeat_done = 0
        if self.segment < len(self._segments):
            self._skip_empty()
            if self.segment < len(self._segments):
                return

        # 一轮走完 -> 无限循环，直接回到第一段
        self.cycle += 1
        self.segment = 0
        self.index = 0
        self.done = set()
        self.repeat_done = 0
        self._skip_empty()
        if self.segment >= len(self._segments):
            self.state = "finished"
