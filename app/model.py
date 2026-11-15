# -*- coding: utf-8 -*-
"""数据模型与本地存储。

结构：
    Axis      单条技能轴，role 区分「充能轴 / 爆发轴」
    Rotation  编队 = 若干个充能轴（有序）+ 1 个爆发轴，永远无限循环
    Team      队伍，固定 4 名干员

节点只记「哪个干员 + 哪个技能」，键位由设置里的统一映射决定。
"""
import json
import os
import re
import time
from .brand import APP_TITLE as APP_NAME, APP_VERSION
import uuid
from dataclasses import dataclass, field

ROLE_CHARGE = "charge"
ROLE_BURST = "burst"
ROLE_ROUTE = "route"       # 分支路线轴：不进播放顺序，只被分支点引用

ROLE_CN = {ROLE_CHARGE: "充能轴", ROLE_BURST: "爆发轴", ROLE_ROUTE: "路线轴"}

# 技能种类
KIND_SKILL = "skill"
KIND_COMBO = "combo"
KIND_ULT = "ult"
KIND_BRANCH = "branch"     # 分支点节点（不在 KINDS 里：它不是技能，没有图标）
KINDS = (KIND_SKILL, KIND_COMBO, KIND_ULT)
KIND_CN = {KIND_SKILL: "战技", KIND_COMBO: "连携", KIND_ULT: "终结",
           KIND_BRANCH: "分支"}

# 技能键位规则（游戏内默认，可在设置里自定义）：
#   技能   = 1/2/3/4，对应队伍第 1~4 位，短按
#   连携   = E，所有干员共用
#   终结技 = 长按该干员的 1/2/3/4，超过 hold_ms 判定为长按
SLOT_VKS = (0x31, 0x32, 0x33, 0x34)   # 1 2 3 4
DEFAULT_COMBO_KEY = 0x45              # E
DEFAULT_SLOT_VKS = SLOT_VKS           # 键盘：队伍 1~4 的出厂键位
DEFAULT_HOLD_MS = 280

# 合法虚拟键码范围（鼠标键是 0x1000 起的高位编码，不在此范围）
VK_MIN, VK_MAX = 0x08, 0xFF


def _as_vk(value, fallback=None):
    """把一个值收成合法虚拟键码；不合法就回落（fallback 为 None 时返回 None）。"""
    try:
        vk = int(value)
    except (TypeError, ValueError):
        return fallback
    if VK_MIN <= vk <= VK_MAX:
        return vk
    return fallback


def normalize_slot_vks(value):
    """键盘槽位键：收成 4 个合法键码，缺位/坏值用默认补（老存档兼容）。"""
    items = list(value or [])
    out = []
    for i, default in enumerate(DEFAULT_SLOT_VKS):
        raw = items[i] if i < len(items) else default
        out.append(_as_vk(raw, default))
    return tuple(out)

# 默认手柄映射（XInput 位掩码）：X=技能、Y=连携、B=终结
DEFAULT_PAD = {KIND_SKILL: 0x4000, KIND_COMBO: 0x8000, KIND_ULT: 0x2000}


# 手柄（XInput 位掩码）
PAD_A = 0x1000
PAD_B = 0x2000
PAD_X = 0x4000
PAD_Y = 0x8000
PAD_LB = 0x0100
PAD_RB = 0x0200

# 手柄默认键位（按游戏内设置复刻）：
#   连携技        = RB
#   施放战技/终结技 = LB + X/Y/A/B（短按=战技，长按=终结技）
DEFAULT_PAD_COMBO = PAD_RB
DEFAULT_PAD_MODIFIER = PAD_LB
DEFAULT_PAD_SLOTS = {0: PAD_X, 1: PAD_Y, 2: PAD_A, 3: PAD_B}

# 终结技的两种触发风格 —— 游戏内「设置 → 手柄」里选的是哪一种，这边就要跟着切：
#   hold  ：LB + 面键，长按 = 终结技，短按 = 战技
#   chord ：LB + RB + 面键 = 终结技，不用长按
PAD_ULT_HOLD = "hold"
PAD_ULT_CHORD = "chord"
PAD_ULT_MODES = (
    (PAD_ULT_HOLD, "LB + 长按面键"),
    (PAD_ULT_CHORD, "LB + RB + 面键"),
)


def pad_ult_mode_label(mode):
    for val, label in PAD_ULT_MODES:
        if val == mode:
            return label
    return PAD_ULT_MODES[0][1]


# 新建对象的默认命名规则（用户 2026-11-14 定）：
#   编队   -> 编队 · 1 / 编队 · 2 …
#   充能轴 -> 充能轴 · 1 / 充能轴 · 2 …
#   路线轴 -> 路线 · 1 / 路线 · 2 …
#   爆发轴 -> 爆发轴（固定，不编号）
DEFAULT_PREFIX = {ROLE_CHARGE: "充能轴", ROLE_ROUTE: "路线", ROLE_BURST: "爆发轴",
                  "rotation": "编队"}


def next_numbered_name(existing_names, prefix):
    """按 "前缀 · N" 找下一个可用编号（已有 3 就给 4，删除不影响已用号）。"""
    pat = re.compile(re.escape(prefix) + r"\s*·\s*(\d+)\s*$")
    nums = []
    for name in existing_names:
        m = pat.match(str(name or "").strip())
        if m:
            nums.append(int(m.group(1)))
    return "%s · %d" % (prefix, (max(nums) + 1) if nums else 1)


def new_id():
    return uuid.uuid4().hex[:12]


# 分支选项（2026-11-14 改成「卡片化」）：
#   trigger  触发卡：下一次按的这颗技能决定走这条分支   {"operator","kind","stage"}
#   nodes    这条分支自己的技能卡（直接内嵌在分支里，不再引用路线轴）
#   next     走完去哪："" = 顺着主线继续；否则是目标轴的 id（可以是爆发轴）
def option_trigger(option):
    trig = (option or {}).get("trigger") or {}
    return {
        "operator": str(trig.get("operator") or (option or {}).get("operator") or ""),
        "kind": (trig.get("kind") if trig.get("kind") in KINDS
                 else ((option or {}).get("kind") if (option or {}).get("kind") in KINDS
                       else KIND_SKILL)),
        "stage": max(1, min(9, int(trig.get("stage") or 1))),
    }


def option_nodes(option):
    return list((option or {}).get("nodes") or [])


def option_to_dict(option):
    return {
        "trigger": dict(option_trigger(option)),
        "nodes": [n.to_dict() for n in option_nodes(option)],
        "next": str((option or {}).get("next") or ""),
    }


def option_from_dict(d):
    """兼容两代格式：旧 {operator, kind, axis, merge} 与新 {trigger, nodes, next}。"""
    if "trigger" in d or "nodes" in d or "next" in d:
        nodes = []
        for raw in d.get("nodes") or []:
            if isinstance(raw, dict):
                nodes.append(Node.from_dict(raw))
        return {
            "trigger": option_trigger(d),
            "nodes": nodes,
            "next": str(d.get("next") or ""),
        }
    return {
        "trigger": option_trigger(d),
        "nodes": [],                                   # 旧路线轴的内容由 Store 迁移
        "next": "",
        "_legacy_axis": str(d.get("axis") or ""),
    }


def blank_option(operator="", kind=KIND_SKILL, stage=1):
    return {"trigger": {"operator": operator, "kind": kind, "stage": stage},
            "nodes": [], "next": ""}


@dataclass
class Node:
    id: str = field(default_factory=new_id)
    operator: str = ""
    kind: str = KIND_SKILL
    icon: str = ""
    # 多段技能：第几段（1 起）。同一颗键按两次就是两段，判定只看 operator+kind。
    stage: int = 1
    # 分支点专用：可选路线列表
    #   [{"operator": 触发干员, "kind": 触发种类, "axis": 路线轴 id, "merge": 是否汇合}]
    options: list = field(default_factory=list)

    @property
    def label(self):
        base = KIND_CN.get(self.kind, "战技")
        try:
            n = int(self.stage or 1)
        except (TypeError, ValueError):
            n = 1
        return base if n <= 1 else "%s %d" % (base, n)

    def to_dict(self):
        out = {
            "id": self.id,
            "operator": self.operator,
            "kind": self.kind,
            "icon": self.icon,
            "stage": max(1, int(self.stage or 1)),
        }
        if self.options:
            out["options"] = [option_to_dict(o) for o in self.options]
        return out

    @staticmethod
    def from_dict(d):
        kind = d.get("kind")
        if kind not in KINDS and kind != KIND_BRANCH:
            # 兼容旧数据：按图标名推断
            icon = d.get("icon", "") or ""
            if "连携" in icon:
                kind = KIND_COMBO
            elif "终结" in icon:
                kind = KIND_ULT
            else:
                kind = KIND_SKILL
        try:
            stage = max(1, min(9, int(d.get("stage") or 1)))
        except (TypeError, ValueError):
            stage = 1
        opts = []
        for o in d.get("options") or []:
            if not isinstance(o, dict):
                continue
            opts.append(option_from_dict(o))
        return Node(
            id=d.get("id") or new_id(),
            operator=d.get("operator", ""),
            kind=kind,
            icon=d.get("icon", ""),
            stage=stage,
            options=opts,
        )


TEAM_SIZE = 4


def move_item(seq, src, gap):
    """把 seq[src] 挪到 gap 这个「插入缝」，其余元素整体让位。

    gap 是缝的编号（0..len(seq)）：拖到第 3 个元素前面就是 gap=2。
    这是拖拽换序的统一语义（编队行 / 技能轴节点 / 队伍卡片都用它），
    比「两两互换」更符合直觉：拖过去是插入，不是对调。
    """
    items = list(seq or [])
    n = len(items)
    try:
        src = int(src)
        gap = int(gap)
    except (TypeError, ValueError):
        return items
    if not (0 <= src < n):
        return items
    gap = max(0, min(gap, n))

    rest = items[:src] + items[src + 1:]
    to = gap if gap <= src else gap - 1
    to = max(0, min(to, len(rest)))
    rest.insert(to, items[src])
    return rest


def assign_member(members, idx, cn, size=TEAM_SIZE):
    """把 cn 放到第 idx 位，返回新的队伍列表。

    队伍里同一位干员只能出现一次，所以 cn 已经在别的位时不是「复制一份」，
    而是**两个位置互换**：cn 去 idx 位，idx 位原来的人去 cn 原来的位。
    这是用户 2026-11-14 定下的规则，改之前先看交接摘要。
    """
    ms = list(members or [])[:size]
    while len(ms) < size:
        ms.append("")
    try:
        idx = int(idx)
    except (TypeError, ValueError):
        return ms
    if not (0 <= idx < size):
        return ms

    if not cn:
        ms[idx] = ""
        return ms

    for j, m in enumerate(ms):
        if m == cn and j != idx:
            ms[j], ms[idx] = ms[idx], cn     # 已在队伍 -> 换位，不产生重复
            return ms
    ms[idx] = cn
    return ms


@dataclass
class Team:
    members: list = field(default_factory=lambda: ["", "", "", ""])

    def normalized(self):
        """补齐/裁到 4 位，并把重复干员（后出现的那个）清空。

        正常操作走 assign_member 不会产生重复；这里是给旧存档、
        外部导入、手改 JSON 兜底，保证界面永远看不到一队两个同名。
        """
        m = ["" if x is None else str(x) for x in list(self.members)[:TEAM_SIZE]]
        while len(m) < TEAM_SIZE:
            m.append("")
        seen = set()
        out = []
        for x in m:
            if x and x in seen:
                out.append("")
                continue
            if x:
                seen.add(x)
            out.append(x)
        return out

    def to_dict(self):
        return {"members": self.normalized()}

    @staticmethod
    def from_dict(d):
        return Team(members=(d or {}).get("members", []))


@dataclass
class Axis:
    id: str = field(default_factory=new_id)
    name: str = "新技能轴"
    role: str = ROLE_BURST
    nodes: list = field(default_factory=list)
    # 充能轴可以单独设「这条走几遍」（1 = 只走一遍），走完再接着往下
    repeat: int = 1

    def repeat_count(self):
        try:
            n = int(self.repeat)
        except (TypeError, ValueError):
            return 1
        return max(1, min(99, n))

    @property
    def is_burst(self):
        return self.role == ROLE_BURST

    @property
    def role_cn(self):
        return ROLE_CN.get(self.role, "技能轴")

    def operators(self):
        """这条技能轴用到哪些干员（去重，保持出场顺序）。"""
        out = []
        for n in self.nodes:
            if n.operator and n.operator not in out:
                out.append(n.operator)
        return out

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "repeat": self.repeat_count(),
            "nodes": [n.to_dict() for n in self.nodes],
        }

    @staticmethod
    def from_dict(d):
        return Axis(
            id=d.get("id") or new_id(),
            name=d.get("name", "技能轴"),
            role=d.get("role") or ROLE_BURST,
            repeat=max(1, min(99, int(d.get("repeat") or 1))),
            nodes=[Node.from_dict(x) for x in d.get("nodes", [])],
        )


@dataclass
class Rotation:
    """编队 = 一串有序技能轴（充能轴 / 爆发轴可以混排、都可以有多条），无限循环。

    `order` 是唯一可信的播放顺序；`charge_axes` / `burst_axis` 只保留给旧数据和
    旧代码读取（保存时会按 order 重新推导）。
    """
    id: str = field(default_factory=new_id)
    name: str = "新编队"
    charge_axes: list = field(default_factory=list)
    burst_axis: str = ""
    team: Team = field(default_factory=Team)
    order: list = field(default_factory=list)

    def sequence(self):
        """播放顺序（轴 id 列表）。旧数据没有 order 时按「充能轴 + 爆发轴」兜底。"""
        if self.order:
            return [x for x in self.order if x]
        ids = [a for a in self.charge_axes if a]
        if self.burst_axis:
            ids.append(self.burst_axis)
        return ids

    def set_sequence(self, ids):
        self.order = [x for x in (ids or []) if x]
        self.sync_legacy()

    def sync_legacy(self, axis_lookup=None):
        """从 order 推导旧的 charge_axes / burst_axis 字段（保存前调用）。"""
        if not self.order:
            return
        if axis_lookup is None:
            return
        charges, bursts = [], []
        for aid in self.order:
            axis = axis_lookup(aid)
            if axis is None:
                continue
            if axis.role == ROLE_BURST:
                bursts.append(aid)
            else:
                charges.append(aid)
        self.charge_axes = charges
        self.burst_axis = bursts[-1] if bursts else ""

    def axis_ids(self):
        return self.sequence()

    def members(self):
        return self.team.normalized() if self.team else ["", "", "", ""]

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "order": self.sequence(),
            "charge_axes": list(self.charge_axes),
            "burst_axis": self.burst_axis,
            "team": self.team.to_dict() if self.team else Team().to_dict(),
        }

    @staticmethod
    def from_dict(d):
        order = [x for x in (d.get("order") or []) if x]
        rot = Rotation(
            id=d.get("id") or new_id(),
            name=d.get("name", "循环"),
            charge_axes=[x for x in d.get("charge_axes", []) if x],
            burst_axis=d.get("burst_axis", ""),
            team=Team.from_dict(d.get("team") or {}),
            order=order,
        )
        return rot


@dataclass
class Settings:
    overlay_x: int = 120
    overlay_y: int = 120
    overlay_scale: float = 1.0     # 悬浮窗等比缩放
    opacity: float = 0.95
    click_through: bool = False
    mode: str = "strict"
    watch_mouse: bool = True
    hotkey_start: int = 0x76
    hotkey_reset: int = 0x77
    hotkey_visible: int = 0x78
    hotkey_through: int = 0x79
    only_game_focus: bool = False
    game_keyword: str = "Endfield"
    gamepad_enabled: bool = True
    gamepad_scheme: str = "xbox"
    auto_elevate: bool = True      # 启动时自动以管理员身份重启（游戏常需管理员）
    active_rotation: str = ""
    # 连携技统一按键
    combo_key: int = DEFAULT_COMBO_KEY
    # 键盘：队伍 1~4 各自用哪个键（短按 = 战技，长按 = 终结技）
    slot_vks: tuple = DEFAULT_SLOT_VKS
    # 长按判定阈值（毫秒）
    hold_ms: int = DEFAULT_HOLD_MS
    # 手柄映射：技能种类 -> 位掩码（旧版，保留兼容）
    pad: dict = field(default_factory=lambda: dict(DEFAULT_PAD))
    # 手柄组合键规则（照游戏内设置）
    pad_modifier: int = DEFAULT_PAD_MODIFIER     # LB
    pad_combo: int = DEFAULT_PAD_COMBO           # RB = 连携技
    pad_slots: dict = field(default_factory=lambda: dict(DEFAULT_PAD_SLOTS))
    # 终结技触发风格：hold = LB+长按面键，chord = LB+RB+面键
    pad_ult_mode: str = PAD_ULT_HOLD

    def pad_ult_label(self):
        return pad_ult_mode_label(self.pad_ult_mode)

    def pad_slot_key(self, slot):
        """队伍第 slot 位对应的手柄按键位。"""
        try:
            return (self.pad_slots or {}).get(int(slot))
        except (TypeError, ValueError):
            return None

    def pad_slot_of(self, bit):
        """手柄按键位 -> 队伍槽位（0 起），找不到返回 None。"""
        for slot, b in (self.pad_slots or {}).items():
            if b == bit:
                try:
                    return int(slot)
                except (TypeError, ValueError):
                    return None
        return None

    def slot_key(self, slot):
        """队伍第 slot 位（0 起）对应的键盘键（可在设置里改）。"""
        keys = self.slot_vks or DEFAULT_SLOT_VKS
        try:
            slot = int(slot)
        except (TypeError, ValueError):
            return None
        if not (0 <= slot < len(keys)):
            return None
        return keys[slot]

    # ---------- 键位冲突查询（设置界面查重用）----------
    def keyboard_bindings(self):
        """[(功能名, 键码)]：键盘上所有可自定义的键。"""
        items = [("队伍 %d" % (i + 1), self.slot_key(i)) for i in range(4)]
        items += [
            ("连携技", self.combo_key),
            ("开始/暂停", self.hotkey_start),
            ("重置", self.hotkey_reset),
            ("显示/隐藏", self.hotkey_visible),
            ("点击穿透", self.hotkey_through),
        ]
        return items

    def keyboard_owner(self, vk, skip=None):
        """这个键盘键被谁占用了？没占用返回 None。skip = 忽略正在重绑的项。"""
        if vk is None:
            return None
        for name, key in self.keyboard_bindings():
            if name == skip:
                continue
            if key == vk:
                return name
        return None

    def pad_bindings(self):
        """[(功能名, 位掩码)]：手柄上所有可自定义的键。"""
        items = [("连携技", self.pad_combo), ("修饰键", self.pad_modifier)]
        items += [("队伍 %d" % (i + 1), self.pad_slot_key(i)) for i in range(4)]
        return items

    def pad_owner(self, bit, skip=None):
        """这个手柄键被谁占用了？没占用返回 None。"""
        if not bit:
            return None
        for name, key in self.pad_bindings():
            if name == skip:
                continue
            if key == bit:
                return name
        return None

    def pad_for(self, kind):
        return (self.pad or {}).get(kind)

    def to_dict(self):
        return self.__dict__.copy()

    @staticmethod
    def from_dict(d):
        s = Settings()
        for k, v in (d or {}).items():
            if hasattr(s, k) and v is not None:
                setattr(s, k, v)
        pad = dict(DEFAULT_PAD)
        pad.update({k: v for k, v in (s.pad or {}).items() if k in KINDS})
        s.pad = pad
        slots = dict(DEFAULT_PAD_SLOTS)
        for k, v in (s.pad_slots or {}).items():
            try:
                slots[int(k)] = int(v)
            except (TypeError, ValueError):
                continue
        s.pad_slots = slots
        s.pad_modifier = int(s.pad_modifier or DEFAULT_PAD_MODIFIER)
        s.pad_combo = int(s.pad_combo or DEFAULT_PAD_COMBO)
        if s.pad_ult_mode not in (PAD_ULT_HOLD, PAD_ULT_CHORD):
            s.pad_ult_mode = PAD_ULT_HOLD
        s.hold_ms = max(60, int(s.hold_ms or DEFAULT_HOLD_MS))
        s.combo_key = _as_vk(s.combo_key, DEFAULT_COMBO_KEY)
        s.slot_vks = normalize_slot_vks(s.slot_vks)
        return s


def make_demo_data():
    """首次启动的示例：编队 · 1 = 充能轴 · 1、充能轴 · 2、爆发轴 · 1（技能轴默认都为空）。"""
    c1 = Axis(name="充能轴 · 1", role=ROLE_CHARGE, nodes=[])
    c2 = Axis(name="充能轴 · 2", role=ROLE_CHARGE, nodes=[])
    burst = Axis(name="爆发轴 · 1", role=ROLE_BURST, nodes=[])
    team = Team(members=["佩丽卡", "管理员", "陈千语", "余烬"])
    rot = Rotation(name="编队 · 1", team=Team(members=list(team.members)))
    rot.set_sequence([c1.id, c2.id, burst.id])
    return [c1, c2, burst], [rot], team


def unique_name(existing, base):
    """在已有名字里找一个不重复的：base / base (2) / base (3) …"""
    base = str(base or "").strip() or "未命名"
    names = set(str(x or "") for x in existing)
    if base not in names:
        return base
    i = 2
    while "%s (%d)" % (base, i) in names:
        i += 1
    return "%s (%d)" % (base, i)


class Store:
    """轴、编队、队伍、设置都存在 data/ 下的 JSON 里，原子写入。"""

    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.data_dir = os.path.join(base_dir, "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.axes_path = os.path.join(self.data_dir, "axes.json")
        self.rotations_path = os.path.join(self.data_dir, "rotations.json")
        self.team_path = os.path.join(self.data_dir, "team.json")
        self.settings_path = os.path.join(self.data_dir, "settings.json")
        self.axes = []
        self.rotations = []
        self.team = Team()
        self.settings = Settings()
        # 改动先记账，防抖后自动落盘
        self.defer_save = False
        self.dirty = False
        self.on_change = None       # 有改动时回调（用于自动保存）
        self.load()

    # ---------- 载入 ----------
    def load(self):
        self.team = Team.from_dict(self._read_json(self.team_path, {}))
        self.axes = [Axis.from_dict(d) for d in self._read_json(self.axes_path, []) or []]
        self.rotations = [Rotation.from_dict(d)
                          for d in self._read_json(self.rotations_path, []) or []]
        self.settings = Settings.from_dict(self._read_json(self.settings_path, {}))
        if not self.axes or not self.rotations:
            axes, rots, team = make_demo_data()
            self.axes = self.axes or axes
            if not self.rotations:
                if self.axes:
                    # 有轴但没有编队（例如刚删光/手改文件）：按现有轴重建一个，
                    # 别用 demo 里那批新 id，否则编队会引用到不存在的轴
                    charges = [a for a in self.axes if a.role == ROLE_CHARGE]
                    bursts = [a for a in self.axes if a.role == ROLE_BURST]
                    rot = Rotation(name="编队 · 1")
                    rot.set_sequence([a.id for a in charges] +
                                     [b.id for b in bursts])
                    self.rotations = [rot]
                else:
                    self.rotations = rots
            if not self.team.members or not any(self.team.members):
                self.team = team
        self._migrate_team()
        self._migrate_orders()
        self._migrate_branches()
        self._migrate_axis_names()
        self.dirty = False

    def _migrate_axis_names(self):
        """旧示例里两条轴的名字统一一下（只改这两个旧名，自定义名字不动）。"""
        rename = {"RB测试": "充能轴", "爆发 · 开场": "爆发轴"}
        changed = False
        for axis in self.axes:
            new = rename.get(axis.name)
            if new:
                axis.name = new
                changed = True
        if changed:
            self.save_axes()

    def _migrate_orders(self):
        """旧编队只有 charge_axes + burst_axis：合成 order，并同步回旧字段。"""
        for rot in self.rotations:
            if not rot.order:
                rot.order = [x for x in (rot.charge_axes or []) if x]
                if rot.burst_axis:
                    rot.order.append(rot.burst_axis)
            rot.sync_legacy(self.axis_by_id)

    def _migrate_branches(self):
        """旧分支选项引用「路线轴」：把路线轴的节点搬进分支自身的 nodes。"""
        legacy_axes = {a.id: a for a in self.axes
                       if getattr(a, "role", "") == ROLE_ROUTE}
        for axis in self.axes:
            for node in axis.nodes:
                if getattr(node, "kind", "") != KIND_BRANCH:
                    continue
                for opt in node.options or []:
                    legacy_id = opt.pop("_legacy_axis", "") if isinstance(opt, dict) else ""
                    if not legacy_id:
                        continue
                    src = legacy_axes.get(legacy_id)
                    if src is not None:
                        opt["nodes"] = [Node.from_dict(n.to_dict()) for n in src.nodes]
                    opt.setdefault("trigger", {
                        "operator": "", "kind": KIND_SKILL, "stage": 1})
                    opt.setdefault("next", "")

    def _migrate_team(self):
        """旧数据里队伍是全局的，迁移到每个编队。"""
        fallback = self.team.normalized()
        for rot in self.rotations:
            members = rot.team.normalized() if rot.team else []
            if not any(members):
                rot.team = Team(members=list(fallback))

    def _read_json(self, path, default):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return default

    # ---------- 保存 ----------
    def touch(self):
        """标记有未保存改动。"""
        self.dirty = True
        self._notify()

    def _notify(self):
        cb = self.on_change
        if cb is None:
            return
        try:
            cb()
        except Exception:
            pass

    def _persist(self, path, obj):
        if self.defer_save:
            self.dirty = True
            self._notify()
            return
        self._write_json(path, obj)

    def save_axes(self):
        self._persist(self.axes_path, [a.to_dict() for a in self.axes])

    def save_rotations(self):
        self._persist(self.rotations_path, [r.to_dict() for r in self.rotations])

    def save_team(self):
        self._persist(self.team_path, self.team.to_dict())

    def save_settings(self):
        # 设置永远立即生效，不参与「保存」流程
        self._write_json(self.settings_path, self.settings.to_dict())

    def save_all(self):
        self.save_axes()
        self.save_rotations()
        self.save_team()
        self.save_settings()

    def commit(self):
        """把当前所有改动写盘。"""
        self.defer_save = False
        try:
            self.save_axes()
            self.save_rotations()
            self.save_team()
        finally:
            self.defer_save = True
        self.dirty = False

    def flush(self):
        """有改动就立刻写盘。返回是否真的写了。"""
        if not self.dirty:
            return False
        self.commit()
        return True

    def revert(self):
        """放弃未保存改动：从磁盘重新载入。"""
        self.load()

    def _write_json(self, path, obj):
        tmp = path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)
        except OSError:
            pass

    # ---------- 查询 ----------
    def axis_by_id(self, axis_id):
        for a in self.axes:
            if a.id == axis_id:
                return a
        return None

    def rotation_by_id(self, rid):
        for r in self.rotations:
            if r.id == rid:
                return r
        return None

    def charge_axes(self):
        return [a for a in self.axes if a.role == ROLE_CHARGE]

    def burst_axes(self):
        return [a for a in self.axes if a.role == ROLE_BURST]

    def active_rotation(self):
        r = self.rotation_by_id(self.settings.active_rotation)
        if r is None and self.rotations:
            r = self.rotations[0]
            self.settings.active_rotation = r.id
        return r

    # ---------- 增删 ----------
    def add_axis(self, role=ROLE_CHARGE, name=None):
        if name:
            axis_name = name
        elif role == ROLE_BURST:
            # 爆发轴可以有多条：爆发轴 · 1、· 2、· 3 …
            existing = [a for a in self.axes if a.role == ROLE_BURST]
            axis_name = "爆发轴 · %d" % (len(existing) + 1)
        else:
            prefix = DEFAULT_PREFIX.get(role, "技能轴")
            axis_name = next_numbered_name(
                [a.name for a in self.axes if a.role == role], prefix)
        axis = Axis(name=axis_name, role=role)
        self.axes.append(axis)
        self.save_axes()
        return axis

    def delete_axis(self, axis_id):
        self.axes = [a for a in self.axes if a.id != axis_id]
        for r in self.rotations:
            r.order = [x for x in r.order if x != axis_id]
            r.charge_axes = [x for x in r.charge_axes if x != axis_id]
            if r.burst_axis == axis_id:
                r.burst_axis = ""
            # 分支里「跳到某轴」的目标被删了：退回顺着走
            for axis in self.axes:
                for node in axis.nodes:
                    for opt in (getattr(node, "options", None) or []):
                        if isinstance(opt, dict) and opt.get("next") == axis_id:
                            opt["next"] = ""
        self.save_axes()
        self.save_rotations()

    def add_rotation(self, name=None):
        rot = Rotation(name=name or next_numbered_name(
            [r.name for r in self.rotations], "编队"))
        # 跟随示例编队的排版：充能轴、爆发轴各按现有结构克隆一份，
        # **新建独立轴**（新 id、空节点），这样改一个编队不会动到别的编队
        template = self.rotations[0] if self.rotations else None
        ids = template.sequence() if template else []
        new_ids = []
        for aid in ids:
            src = self.axis_by_id(aid)
            if src is None:
                continue
            clone = Axis.from_dict(src.to_dict())
            clone.id = new_id()
            clone.nodes = []                      # 技能轴默认空
            prefix = DEFAULT_PREFIX.get(src.role, "技能轴")
            clone.name = next_numbered_name(
                [a.name for a in self.axes if a.role == src.role], prefix)
            self.axes.append(clone)
            new_ids.append(clone.id)
        rot.set_sequence(new_ids)
        rot.sync_legacy(self.axis_by_id)
        active = self.active_rotation()
        rot.team = Team(members=list((active.members() if active
                                      else self.team.normalized())))
        self.rotations.append(rot)
        self.save_axes()
        self.save_rotations()
        return rot

    def rotation_team(self, rot=None):
        """当前编队的队伍。"""
        rot = rot or self.active_rotation()
        if rot is None:
            return self.team
        if not rot.team:
            rot.team = Team(members=list(self.team.normalized()))
        return rot.team

    def delete_rotation(self, rid):
        self.rotations = [r for r in self.rotations if r.id != rid]
        if self.settings.active_rotation == rid:
            self.settings.active_rotation = self.rotations[0].id if self.rotations else ""
            self.save_settings()
        self.save_rotations()

    # ---------- 导入导出 ----------
    def export_dict(self, rotation=None):
        """导出配置。

        不给 rotation：整份导出（轴、编队顺序、队伍、完整设置）。
        给 rotation  ：只导出这一个编队，连同它自己用的轴和队伍，
                       方便单独分享一套打法。
        """
        if rotation is not None:
            ids = list(rotation.sequence())
            axes = [a for a in self.axes if a.id in ids]
            rots = [rotation]
            scope = "rotation"
        else:
            axes = self.axes
            rots = self.rotations
            scope = "all"
        return {
            "format": "skill-axis",
            "version": 5,
            "app": APP_NAME,
            "app_version": APP_VERSION,
            "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "scope": scope,
            "counts": {"axes": len(axes), "rotations": len(rots)},
            "axes": [a.to_dict() for a in axes],
            "rotations": [r.to_dict() for r in rots],
            "team": self.team.to_dict(),
            "settings": self.settings.to_dict(),
        }

    def import_dict(self, data, mode="append"):
        """导入配置。

        mode = "replace"：覆盖当前所有编队（轴、编队、队伍、设置都用文件里的）
        mode = "append" ：在现有基础上添加（轴/编队都新建 id，重名自动区分）
        """
        if mode is True:
            mode = "append"
        elif mode is False:
            mode = "replace"
        if mode not in ("replace", "append"):
            mode = "append"
        if not isinstance(data, dict) or "axes" not in data:
            return False, "文件格式不对：缺少 axes"
        try:
            axes = [Axis.from_dict(d) for d in data.get("axes", [])]
            rots = [Rotation.from_dict(d) for d in data.get("rotations", [])]
        except Exception as e:
            return False, "解析失败：%s" % e
        if not axes:
            return False, "文件里没有技能轴"

        if mode == "replace":
            # 覆盖：内容全部来自文件（含设置），但名字要去重
            names = []
            for a in axes:
                a.name = unique_name(names, a.name)
                names.append(a.name)
            rnames = []
            for r in rots:
                r.name = unique_name(rnames, r.name)
                rnames.append(r.name)
            self.axes = axes
            self.rotations = rots or []
            if "team" in data:
                self.team = Team.from_dict(data["team"])
            id_map = {}
            # 编队顺序只保留文件里真实存在的轴
            for r in self.rotations:
                r.order = [x for x in r.sequence() if self.axis_by_id(x)]
                r.sync_legacy(self.axis_by_id)
        else:
            # 添加：导入的所有 id 重新发，避免和现有数据撞车
            id_map = {}
            existing_names = [a.name for a in self.axes]
            for a in axes:
                old = a.id
                a.id = new_id()
                id_map[old] = a.id
                a.name = unique_name(existing_names, a.name)
                existing_names.append(a.name)
            rnames = [r.name for r in self.rotations]
            for r in rots:
                old = r.id
                r.id = new_id()
                id_map[old] = r.id
                r.name = unique_name(rnames, r.name)
                rnames.append(r.name)
            for a in axes:
                for node in a.nodes:
                    for opt in (getattr(node, "options", None) or []):
                        if isinstance(opt, dict) and opt.get("next"):
                            opt["next"] = id_map.get(opt["next"], opt["next"])
            for r in rots:
                r.order = [id_map.get(x, x) for x in r.sequence()]
            self.axes.extend(axes)
            self.rotations.extend(rots)
            for r in rots:
                r.order = [x for x in r.order if self.axis_by_id(x)]
                r.sync_legacy(self.axis_by_id)

        # 设置跟随（两种模式都应用文件里有写的字段）
        imported = data.get("settings")
        if isinstance(imported, dict) and imported:
            try:
                fresh = Settings.from_dict(imported)
            except Exception:  # noqa: BLE001
                fresh = None
            if fresh is not None:
                for key, value in fresh.to_dict().items():
                    if key in imported:
                        setattr(self.settings, key, value)

        if not any(r.id == self.settings.active_rotation for r in self.rotations):
            self.settings.active_rotation = self.rotations[0].id if self.rotations else ""
        for r in self.rotations:
            r.order = [x for x in r.order if self.axis_by_id(x)]
            r.sync_legacy(self.axis_by_id)

        self.save_all()
        return True, "导入 %d 条技能轴、%d 个编队（%s）" % (
            len(axes), len(rots), "覆盖" if mode == "replace" else "添加")

    def _remap_references(self, id_map):
        """把编队顺序和分支跳转里的旧 id 换成新 id。"""
        for rot in self.rotations:
            rot.order = [id_map.get(x, x) for x in rot.sequence()]
        for axis in self.axes:
            for node in axis.nodes:
                for opt in (getattr(node, "options", None) or []):
                    if isinstance(opt, dict) and opt.get("next"):
                        opt["next"] = id_map.get(opt["next"], opt["next"])
        if self.settings.active_rotation:
            self.settings.active_rotation = id_map.get(
                self.settings.active_rotation, self.settings.active_rotation)
