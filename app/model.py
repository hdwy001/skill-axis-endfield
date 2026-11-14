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
import uuid
from dataclasses import dataclass, field

ROLE_CHARGE = "charge"
ROLE_BURST = "burst"

ROLE_CN = {ROLE_CHARGE: "充能轴", ROLE_BURST: "爆发轴"}

# 技能种类
KIND_SKILL = "skill"
KIND_COMBO = "combo"
KIND_ULT = "ult"
KINDS = (KIND_SKILL, KIND_COMBO, KIND_ULT)
KIND_CN = {KIND_SKILL: "技能", KIND_COMBO: "连携", KIND_ULT: "终结"}

# 技能键位规则（游戏内默认）：
#   技能   = 1/2/3/4，对应队伍第 1~4 位，短按
#   连携   = E，所有干员共用
#   终结技 = 长按该干员的 1/2/3/4，超过 hold_ms 判定为长按
SLOT_VKS = (0x31, 0x32, 0x33, 0x34)   # 1 2 3 4
DEFAULT_COMBO_KEY = 0x45              # E
DEFAULT_HOLD_MS = 280

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

# 终结技施放方式（对应游戏内「终结技施放动作 2」开关）：
#   hold = 长按战技键（动作 2 关，游戏默认）
#   alt  = 终结键 + 槽位键（动作 2 开，默认用 RB，避免误触战技）
PAD_ULT_HOLD = "hold"
PAD_ULT_ALT = "alt"
PAD_ULT_MODES = (PAD_ULT_HOLD, PAD_ULT_ALT)
DEFAULT_PAD_ULT_MODE = PAD_ULT_HOLD
DEFAULT_PAD_ULT_MODIFIER = PAD_RB


def new_id():
    return uuid.uuid4().hex[:12]


@dataclass
class Node:
    id: str = field(default_factory=new_id)
    operator: str = ""
    kind: str = KIND_SKILL
    icon: str = ""

    @property
    def label(self):
        return KIND_CN.get(self.kind, "技能")

    def to_dict(self):
        return {
            "id": self.id,
            "operator": self.operator,
            "kind": self.kind,
            "icon": self.icon,
        }

    @staticmethod
    def from_dict(d):
        kind = d.get("kind")
        if kind not in KINDS:
            # 兼容旧数据：按图标名推断
            icon = d.get("icon", "") or ""
            if "连携" in icon:
                kind = KIND_COMBO
            elif "终结" in icon:
                kind = KIND_ULT
            else:
                kind = KIND_SKILL
        return Node(
            id=d.get("id") or new_id(),
            operator=d.get("operator", ""),
            kind=kind,
            icon=d.get("icon", ""),
        )


@dataclass
class Team:
    members: list = field(default_factory=lambda: ["", "", "", ""])

    def normalized(self):
        m = list(self.members)[:4]
        while len(m) < 4:
            m.append("")
        return m

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
            "nodes": [n.to_dict() for n in self.nodes],
        }

    @staticmethod
    def from_dict(d):
        return Axis(
            id=d.get("id") or new_id(),
            name=d.get("name", "技能轴"),
            role=d.get("role") or ROLE_BURST,
            nodes=[Node.from_dict(x) for x in d.get("nodes", [])],
        )


@dataclass
class Rotation:
    """编队：先按顺序打完所有充能轴，再打爆发轴，然后无限重复。

    每个编队有自己独立的队伍。
    """
    id: str = field(default_factory=new_id)
    name: str = "新编队"
    charge_axes: list = field(default_factory=list)
    burst_axis: str = ""
    team: Team = field(default_factory=Team)

    def axis_ids(self):
        ids = [a for a in self.charge_axes if a]
        if self.burst_axis:
            ids.append(self.burst_axis)
        return ids

    def members(self):
        return self.team.normalized() if self.team else ["", "", "", ""]

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "charge_axes": list(self.charge_axes),
            "burst_axis": self.burst_axis,
            "team": self.team.to_dict() if self.team else Team().to_dict(),
        }

    @staticmethod
    def from_dict(d):
        return Rotation(
            id=d.get("id") or new_id(),
            name=d.get("name", "循环"),
            charge_axes=[x for x in d.get("charge_axes", []) if x],
            burst_axis=d.get("burst_axis", ""),
            team=Team.from_dict(d.get("team") or {}),
        )


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
    # 长按判定阈值（毫秒）
    hold_ms: int = DEFAULT_HOLD_MS
    # 手柄映射：技能种类 -> 位掩码（旧版，保留兼容）
    pad: dict = field(default_factory=lambda: dict(DEFAULT_PAD))
    # 手柄组合键规则（照游戏内设置）
    pad_modifier: int = DEFAULT_PAD_MODIFIER     # LB
    pad_combo: int = DEFAULT_PAD_COMBO           # RB = 连携技
    pad_slots: dict = field(default_factory=lambda: dict(DEFAULT_PAD_SLOTS))
    # 终结技施放方式：hold = 长按战技键；alt = 终结键 + 槽位键
    pad_ult_mode: str = DEFAULT_PAD_ULT_MODE
    pad_ult_modifier: int = DEFAULT_PAD_ULT_MODIFIER   # alt 方式下的终结键（默认 RB）

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
        """队伍第 slot 位（0 起）对应的键盘键。"""
        if slot is None or not (0 <= slot < len(SLOT_VKS)):
            return None
        return SLOT_VKS[slot]

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
        if s.pad_ult_mode not in PAD_ULT_MODES:
            s.pad_ult_mode = DEFAULT_PAD_ULT_MODE
        s.pad_ult_modifier = int(s.pad_ult_modifier or DEFAULT_PAD_ULT_MODIFIER)
        s.hold_ms = max(60, int(s.hold_ms or DEFAULT_HOLD_MS))
        s.combo_key = int(s.combo_key or DEFAULT_COMBO_KEY)
        return s


def make_demo_data():
    """首次启动的示例：2 个充能轴 + 1 个爆发轴。"""
    c1 = Axis(name="充能 · 第一轮", role=ROLE_CHARGE, nodes=[
        Node(operator="佩丽卡", kind=KIND_SKILL, icon="佩丽卡_技能.png"),
        Node(operator="管理员", kind=KIND_COMBO, icon="管理员_连携.png"),
    ])
    c2 = Axis(name="充能 · 第二轮", role=ROLE_CHARGE, nodes=[
        Node(operator="陈千语", kind=KIND_SKILL, icon="陈千语_技能.png"),
        Node(operator="佩丽卡", kind=KIND_ULT, icon="佩丽卡_终结.png"),
    ])
    burst = Axis(name="爆发 · 开场", role=ROLE_BURST, nodes=[
        Node(operator="余烬", kind=KIND_ULT, icon="余烬_终结.png"),
        Node(operator="佩丽卡", kind=KIND_SKILL, icon="佩丽卡_技能.png"),
        Node(operator="陈千语", kind=KIND_ULT, icon="陈千语_终结.png"),
    ])
    rot = Rotation(name="示例编队", charge_axes=[c1.id, c2.id], burst_axis=burst.id,
                   team=Team(members=["佩丽卡", "管理员", "陈千语", "余烬"]))
    team = Team(members=["佩丽卡", "管理员", "陈千语", "余烬"])
    return [c1, c2, burst], [rot], team


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
            self.rotations = self.rotations or rots
            if not self.team.members or not any(self.team.members):
                self.team = team
        self._migrate_team()
        self.dirty = False

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
        axis = Axis(name=name or ("新充能轴" if role == ROLE_CHARGE else "新爆发轴"),
                    role=role)
        self.axes.append(axis)
        self.save_axes()
        return axis

    def delete_axis(self, axis_id):
        self.axes = [a for a in self.axes if a.id != axis_id]
        for r in self.rotations:
            r.charge_axes = [x for x in r.charge_axes if x != axis_id]
            if r.burst_axis == axis_id:
                r.burst_axis = ""
        self.save_axes()
        self.save_rotations()

    def add_rotation(self, name=None):
        rot = Rotation(name=name or "新编队")
        charges = self.charge_axes()
        bursts = self.burst_axes()
        rot.charge_axes = [charges[0].id] if charges else []
        rot.burst_axis = bursts[0].id if bursts else ""
        # 新编队组默认沿用当前队伍，方便接着改
        active = self.active_rotation()
        rot.team = Team(members=list((active.members() if active
                                      else self.team.normalized())))
        self.rotations.append(rot)
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

    def move_rotation(self, rid, before_index):
        """把编队移到 before_index 之前（下标按移动前的列表算）。

        返回 True 表示确实动了；顺序就是编队列表的显示顺序，也是下拉/拖动顺序。
        """
        old = None
        target = None
        for i, r in enumerate(self.rotations):
            if r.id == rid:
                old, target = i, r
                break
        if target is None:
            return False
        if before_index is None:
            return False
        try:
            before_index = int(before_index)
        except (TypeError, ValueError):
            return False
        self.rotations.pop(old)
        if before_index > old:
            before_index -= 1
        before_index = max(0, min(before_index, len(self.rotations)))
        if before_index == old:
            self.rotations.insert(old, target)      # 位置没变，放回去
            return False
        self.rotations.insert(before_index, target)
        self.save_rotations()
        return True

    # ---------- 导入导出 ----------
    def export_dict(self):
        return {
            "format": "skill-axis",
            "version": 3,
            "axes": [a.to_dict() for a in self.axes],
            "rotations": [r.to_dict() for r in self.rotations],
            "team": self.team.to_dict(),
            "settings": {"combo_key": self.settings.combo_key,
                         "hold_ms": self.settings.hold_ms,
                         "pad": dict(self.settings.pad)},
        }

    def import_dict(self, data, merge=False):
        if not isinstance(data, dict) or "axes" not in data:
            return False, "文件格式不对：缺少 axes"
        try:
            axes = [Axis.from_dict(d) for d in data.get("axes", [])]
            rots = [Rotation.from_dict(d) for d in data.get("rotations", [])]
        except Exception as e:
            return False, "解析失败：%s" % e
        if not axes:
            return False, "文件里没有技能轴"
        if merge:
            existing = {a.id for a in self.axes}
            for a in axes:
                if a.id in existing:
                    a.id = new_id()
            self.axes.extend(axes)
            existing_r = {r.id for r in self.rotations}
            for r in rots:
                if r.id in existing_r:
                    r.id = new_id()
            self.rotations.extend(rots)
        else:
            self.axes = axes
            self.rotations = rots or self.rotations
            if "team" in data:
                self.team = Team.from_dict(data["team"])
        self.save_all()
        return True, "导入 %d 条技能轴、%d 个编队" % (len(axes), len(rots))
