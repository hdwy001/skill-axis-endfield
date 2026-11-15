# -*- coding: utf-8 -*-
"""纯逻辑自测，不打开任何窗口。"""
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.model import (Axis, KIND_COMBO, KIND_SKILL, KIND_ULT,  # noqa: E402
                       Node, ROLE_BURST, ROLE_CHARGE, ROLE_ROUTE, Rotation,
                       Settings, Store, Team)
from app.player import FINISHED, IGNORED, JUMP, MATCH, WRONG, Player  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond), detail))


class FakeStore:
    def __init__(self, axes):
        self.axes = axes
        self.team = Team()

    def axis_by_id(self, axis_id):
        for a in self.axes:
            if a.id == axis_id:
                return a
        return None


def mk_axis(role, name, kinds):
    axis = Axis(name=name, role=role)
    axis.nodes = [Node(operator="干员%d" % i, kind=k) for i, k in enumerate(kinds, 1)]
    return axis


def mk_player(charge_kinds=((KIND_SKILL,), (KIND_COMBO,)),
              burst_kinds=(KIND_ULT,), team=("佩丽卡", "管理员", "陈千语", "余烬")):
    charges = [mk_axis(ROLE_CHARGE, "充能%d" % i, ks)
               for i, ks in enumerate(charge_kinds, 1)]
    burst = mk_axis(ROLE_BURST, "爆发", burst_kinds)
    rot = Rotation(name="测试编队", charge_axes=[c.id for c in charges],
                   burst_axis=burst.id)
    axes = charges + [burst]
    s = Settings()
    store = FakeStore(axes)
    store.team = Team(members=list(team))
    p = Player(rotation=rot, store=store, settings=s)
    # 让每个节点的干员都落在队伍里
    for axis in axes:
        for i, n in enumerate(axis.nodes):
            n.operator = team[i % len(team)]
    return p, rot, axes, s


# ---------- 结构 ----------
def test_segment_order():
    p, rot, axes, _s = mk_player()
    check("编队段数 = 充能2 + 爆发1", len(p.segments) == 3)
    check("段顺序：充能在前、爆发在后",
          [s.role for s in p.segments] == ["charge", "charge", "burst"])
    check("充能轴带序号", p.segments[0].charge_index == 1
          and p.segments[1].charge_index == 2)


def test_play_through():
    p, rot, axes, s = mk_player()
    p.start()
    check("开始时在第 1 个充能轴",
          p.current_segment().role == "charge"
          and p.current_segment().charge_index == 1)
    check("当前节点是技能类", p.current().kind == KIND_SKILL)

    node = p.current()
    slot = p.store.team.normalized().index(node.operator)
    p.press(vk=s.slot_key(slot), hold=False)
    check("充能1 打完进入充能2", p.current_segment().charge_index == 2)

    p.press(vk=s.combo_key)
    check("充能2 打完进入爆发轴", p.current_segment().role == "burst")

    node = p.current()
    slot = p.store.team.normalized().index(node.operator)
    p.press(vk=s.slot_key(slot), hold=True)
    check("一轮打完继续循环（不结束）", p.state == "running")
    check("回到第 1 个充能轴", p.current_segment().charge_index == 1)
    check("轮次 +1", p.cycle == 1)


def test_slot_mapping():
    """数字键按队伍顺序绑定。"""
    p, rot, axes, s = mk_player(charge_kinds=((KIND_SKILL, KIND_SKILL),),
                                team=("佩丽卡", "管理员"))
    now = [100.0]
    p.clock = lambda: now[0]
    p.start()
    n0 = p.current()
    slot0 = p.store.team.normalized().index(n0.operator)
    check("第 1 位对应键 1", s.slot_key(slot0) == 0x31)
    p.press(vk=0x34)          # 无关位次的键 -> 容错忽略，不推进
    check("按错位次的键不推进", p.index == 0)
    now[0] += 0.2
    p.press(vk=0x31)
    check("按对位次的键推进", p.index == 1)


def test_combo_key():
    """连携统一用 E，和干员无关。"""
    p, rot, axes, s = mk_player(charge_kinds=((KIND_COMBO,),))
    p.start()
    check("连携默认键是 E", s.combo_key == 0x45)
    r, _ = p.press(vk=0x45)
    check("按 E 触发连携", r == MATCH)


def test_ult_requires_hold():
    """终结技必须长按，短按不算。"""
    p, rot, axes, s = mk_player(charge_kinds=((KIND_ULT,),),
                                team=("佩丽卡",))
    p.start()
    slot = p.store.team.normalized().index(p.current().operator)
    digit = s.slot_key(slot)
    r1, _ = p.press(vk=digit, hold=False)
    check("短按不触发终结技", r1 != MATCH)
    r2, _ = p.press(vk=digit, hold=True)
    check("长按触发终结技", r2 == MATCH)


def test_hold_threshold_setting():
    s = Settings()
    check("默认长按阈值 280ms", s.hold_ms == 280)
    s2 = Settings.from_dict({"hold_ms": 500})
    check("阈值可持久化", s2.hold_ms == 500)


def test_hotdata_dirty_flow():
    """保存 / 放弃 的流程。"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp = os.path.join(base, "data", "_selftest_tmp5")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    store = Store(tmp)
    store.defer_save = True

    axis = store.add_axis(ROLE_CHARGE, "草稿技能轴")
    check("改动后标记为脏", store.dirty is True)

    store2 = Store(tmp)
    check("未保存时磁盘里没有草稿技能轴",
          not any(a.name == "草稿技能轴" for a in store2.axes))

    store.commit()
    store3 = Store(tmp)
    check("保存后磁盘里有草稿技能轴",
          any(a.name == "草稿技能轴" for a in store3.axes))
    check("保存后不再是脏", store.dirty is False)

    store.add_axis(ROLE_CHARGE, "丢弃技能轴")
    store.revert()
    check("放弃后回到磁盘状态",
          not any(a.name == "丢弃技能轴" for a in store.axes))
    check("放弃后不是脏", store.dirty is False)
    shutil.rmtree(tmp, ignore_errors=True)


def test_per_rotation_team():
    """每个编队有自己的队伍。"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp = os.path.join(base, "data", "_selftest_tmp6")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    store = Store(tmp)
    rot = store.active_rotation()
    rot.team = Team(members=["佩丽卡", "管理员", "陈千语", "余烬"])
    r2 = store.add_rotation("第二个编队")
    check("新建编队继承当前队伍", r2.members() == rot.members())

    r2.team = Team(members=["伊冯", "别礼", "卡缪", "大潘"])
    store.commit()

    store2 = Store(tmp)
    a = store2.rotation_by_id(rot.id)
    b = store2.rotation_by_id(r2.id)
    check("编队队伍各自持久化",
          a.members()[0] == "佩丽卡" and b.members()[0] == "伊冯")

    check("rotation_team 取对应编队的队伍",
          store2.rotation_team(b).normalized()[0] == "伊冯")
    shutil.rmtree(tmp, ignore_errors=True)


def test_rotation_team_affects_keys():
    """不同编队同一干员的位置不同，按键也不同。"""
    p, rot, axes, s = mk_player(charge_kinds=((KIND_SKILL,),),
                                team=("佩丽卡", "管理员"))
    p.start()
    node = p.current()
    check("队伍第 1 位是佩丽卡", node.operator == "佩丽卡")
    check("佩丽卡技能对应键 1", s.slot_key(0) == 0x31)

    # 换一支队伍，佩丽卡排到第 3 位
    rot.team = Team(members=["余烬", "管理员", "佩丽卡", "陈千语"])
    p.rebuild()
    p.start()
    check("换了队伍后仍在技能节点", p.current().kind == KIND_SKILL)
    check("佩丽卡现在对应键 3", s.slot_key(2) == 0x33)
    r, _ = p.press(vk=0x31)
    check("按 1 不再触发（她已不在第1位）", r != MATCH)
    r2, _ = p.press(vk=0x33)
    check("按 3 触发", r2 == MATCH)


def test_rename_rotation():
    store = Store.__new__(Store)
    r = Rotation(name="旧名字")
    r.name = "新名字"
    check("编队可以改名", r.name == "新名字")
    check("改名后持久化字段正确", r.to_dict()["name"] == "新名字")


def test_infinite():
    p, rot, axes, s = mk_player()
    p.start()
    for _ in range(5):
        node = p.current()
        slot = p.store.team.normalized().index(node.operator)
        p.press(vk=s.slot_key(slot))
        p.press(vk=s.combo_key)
        node = p.current()
        slot = p.store.team.normalized().index(node.operator)
        p.press(vk=s.slot_key(slot), hold=True)
    check("永远不结束", p.state == "running")
    check("轮次累计 5", p.cycle == 5)


def test_wrong_key():
    p, rot, axes, s = mk_player()
    p.start()
    n = p.current()
    slot = p.store.team.normalized().index(n.operator)
    digit = s.slot_key(slot)
    r, _ = p.press(vk=digit, hold=True)   # 当前是技能，长按是终结技的写法
    check("技能节点遇到长按不推进", r != MATCH)
    check("不推进时仍在原位", p.index == 0)


def test_key_map():
    p, rot, axes, s = mk_player()
    s.combo_key = 0x51          # 改成 Q
    p.start()
    p.press(vk=0x31)            # 技能推进
    r1, _ = p.press(vk=0x45)    # 旧 E 不再有效
    check("改键后旧连携键无效", r1 != MATCH)
    r2, _ = p.press(vk=0x51)
    check("改键后新连携键有效", r2 == MATCH)


def test_any_mode():
    p, rot, axes, s = mk_player()
    s.mode = "any"
    p.start()
    r, _ = p.press(vk=0x99)
    check("任意键模式推进", r == MATCH and p.current_segment().charge_index == 2)


def test_gamepad():
    p, rot, axes, s = mk_player()
    p.start()
    bit = s.pad_for(KIND_SKILL)
    r, _ = p.press(button=bit)
    check("手柄按键能匹配", r == MATCH)


def test_pad_ult_modes():
    """终结技两种风格：LB+长按面键 / LB+RB+面键。"""
    from app.padrules import PadRules

    def mk(mode):
        s = Settings()
        s.pad_ult_mode = mode
        return s, PadRules(s)

    # ---- 风格一：LB + 长按面键 ----
    s, r = mk("hold")
    LB, RB, X = s.pad_modifier, s.pad_combo, s.pad_slot_key(0)
    check("默认终结技风格是长按", Settings().pad_ult_mode == "hold")
    check("单独按面键不算施放", r.handle("down", X, 0.0) is None)
    check("没按 LB 松开也不触发", r.handle("up", X, 0.05) is None)

    r = PadRules(s)
    r.handle("down", LB, 0.0)
    r.handle("down", X, 0.01)
    a = r.handle("up", X, 0.06)
    check("风格一：LB+短按面键 = 战技", a == ("press", 0x31, False), repr(a))

    r = PadRules(s)
    r.handle("down", LB, 0.0)
    r.handle("down", X, 0.02)
    a = r.handle("up", X, 0.42)
    check("风格一：LB+长按面键 = 终结技", a == ("press", 0x31, True), repr(a))

    r = PadRules(s)
    r.handle("down", LB, 0.0)
    a = r.handle("down", RB, 0.02)
    check("风格一：不按 LB 单按 RB 是连携", a == ("press", 0x45, False), repr(a))

    # ---- 风格二：LB + RB + 面键 ----
    s2, r2 = mk("chord")
    check("终结技风格二可读回", r2.mode() == "chord")
    check("风格二：单独 RB 仍算连携",
          PadRules(s2).handle("down", RB, 0.0) == ("press", 0x45, False))

    r2 = PadRules(s2)
    r2.handle("down", LB, 0.0)
    a = r2.handle("down", RB, 0.02)
    check("风格二：按住 LB 时 RB 不抢连携", a is None, repr(a))
    a = r2.handle("down", X, 0.05)
    check("风格二：LB+RB+面键 = 终结技", a == ("press", 0x31, True), repr(a))
    check("风格二：松开面键不重复触发", r2.handle("up", X, 0.30) is None)
    check("风格二：松开 RB 不误触连携", r2.handle("up", RB, 0.34) is None)

    r3 = PadRules(s2)
    r3.handle("down", LB, 0.0)
    r3.handle("down", X, 0.02)
    a = r3.handle("up", X, 0.60)
    check("风格二：光长按不放只算战技", a == ("press", 0x31, False), repr(a))

    # 切风格后残留的按住状态要清掉
    r4 = PadRules(s2)
    r4.handle("down", LB, 0.0)
    r4.reset()
    check("reset 清掉按住状态", not r4.held and r4.handle("up", X, 0.2) is None)

    # ---- 持久化 ----
    tmp_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "data", "_selftest_tmp5")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    os.makedirs(tmp_dir, exist_ok=True)
    store = Store(tmp_dir)
    store.settings.pad_ult_mode = "chord"
    store.save_settings()
    store2 = Store(tmp_dir)
    check("终结技风格持久化", store2.settings.pad_ult_mode == "chord")
    check("旧设置缺字段时默认长按",
          Settings.from_dict({"hold_ms": 300}).pad_ult_mode == "hold")
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_team_unique():
    """队伍不允许重复：已经在队里的干员再放进来 -> 两个位置互换。"""
    from app.model import Team, assign_member

    base = ["佩丽卡", "管理员", "陈千语", "余烬"]

    moved = assign_member(base, 3, "佩丽卡")
    check("重复加入变成互换", moved == ["余烬", "管理员", "陈千语", "佩丽卡"], repr(moved))
    check("互换后仍然 4 人且不重复",
          len(moved) == 4 and len(set(moved)) == 4)

    replaced = assign_member(base, 1, "新干员")
    check("换成队伍外的人直接替换",
          replaced == ["佩丽卡", "新干员", "陈千语", "余烬"], repr(replaced))

    to_empty = assign_member(["佩丽卡", "", "", ""], 2, "佩丽卡")
    check("拖到空位 = 移动（原位置清空）", to_empty == ["", "", "佩丽卡", ""],
          repr(to_empty))

    cleared = assign_member(base, 2, "")
    check("清空某个位置", cleared == ["佩丽卡", "管理员", "", "余烬"], repr(cleared))

    bad = assign_member(base, 9, "佩丽卡")
    check("越界索引不改动", bad == base, repr(bad))

    # 旧存档里已经重复的：显示时只保留第一次出现，后面清空
    dedup = Team(members=["佩丽卡", "管理员", "佩丽卡", "余烬"]).normalized()
    check("重复存档自动去重", dedup == ["佩丽卡", "管理员", "", "余烬"], repr(dedup))
    check("去重后长度仍是 4", len(dedup) == 4)


def test_move_item():
    """拖拽换序的统一语义：插入式整体挪位（不是两两互换）。"""
    from app.model import move_item

    base = ["A", "B", "C", "D"]
    check("拖到后面：整体前移", move_item(base, 0, 3) == ["B", "C", "A", "D"],
          repr(move_item(base, 0, 3)))
    check("拖到最前：整体后移", move_item(base, 3, 0) == ["D", "A", "B", "C"],
          repr(move_item(base, 3, 0)))
    check("拖到自己原位不变", move_item(base, 1, 1) == base, repr(move_item(base, 1, 1)))
    check("往后挪一格", move_item(base, 1, 3) == ["A", "C", "B", "D"],
          repr(move_item(base, 1, 3)))
    check("挪到末尾之后的缝", move_item(base, 0, 4) == ["B", "C", "D", "A"],
          repr(move_item(base, 0, 4)))
    check("越界索引原样返回", move_item(base, 9, 1) == base)
    check("元素数量不变", len(move_item(base, 2, 0)) == 4)


def test_axis_repeat():
    """充能轴可以单独走 N 遍，走完再往下走；爆发轴不受影响。"""
    from app.model import Axis, ROLE_CHARGE

    # 一条充能轴 + 一条爆发轴；充能轴设成 2 遍
    charge_kinds = ((KIND_SKILL,),)
    p, rot, axes, s = mk_player(charge_kinds=charge_kinds, burst_kinds=(KIND_ULT,))
    axis = axes[0]
    axis.role = ROLE_CHARGE
    axis.repeat = 2
    now = [200.0]
    p.clock = lambda: now[0]
    p.start()
    check("循环轴起始在第 1 段", p.segment == 0 and p.index == 0)

    # 第一遍：推进到段尾后应该原地重来，而不是进爆发轴
    p.press(vk=s.slot_key(0), hold=False)
    check("第一遍走完回到本段开头", p.segment == 0 and p.index == 0, repr(
        (p.segment, p.index, p.repeat_done)))
    check("记录已走遍数", p.repeat_done == 1)

    # 第二遍走完才进爆发轴（同一颗键，等过去重窗口再按）
    now[0] += 0.2
    p.press(vk=s.slot_key(0), hold=False)
    check("第二遍走完进入爆发轴", p.segment == 1, repr(p.segment))
    check("换段后遍数归零", p.repeat_done == 0)

    # 爆发轴不循环：走完直接回到第一段
    now[0] += 0.2
    p.press(vk=s.slot_key(0), hold=True)
    check("爆发轴走完回到第一段", p.segment == 0 and p.cycle == 1,
          repr((p.segment, p.cycle)))

    # 重复次数持久化 & 越界收敛
    a = Axis(name="循环轴", role=ROLE_CHARGE, repeat=3)
    check("循环次数持久化", Axis.from_dict(a.to_dict()).repeat == 3)
    check("循环次数下限 1", Axis(name="x", repeat=0).repeat_count() == 1)
    check("循环次数上限 99", Axis(name="x", repeat=500).repeat_count() == 99)
    check("旧数据缺 repeat 默认 1", Axis.from_dict({"name": "旧"}).repeat == 1)


def test_multi_stage():
    """多段技能：同一颗键分两段按，轴里是两个节点，判定只看干员+种类。"""
    from app.model import Axis, Node

    n1 = Node(operator="祀", kind=KIND_SKILL, stage=1)
    n2 = Node(operator="祀", kind=KIND_SKILL, stage=2)
    check("段号进 label", n1.label == "战技" and n2.label == "战技 2",
          repr((n1.label, n2.label)))
    check("段号持久化", Node.from_dict(n2.to_dict()).stage == 2)
    check("旧数据默认第 1 段", Node.from_dict({"operator": "祀"}).stage == 1)
    check("段号越界收敛", Node.from_dict({"stage": 99}).stage == 9)

    # 两段用同一颗键：连按两次应各推进一个节点
    rot_axes = [mk_axis(ROLE_CHARGE, "两段", (KIND_SKILL, KIND_SKILL))]
    rot = Rotation(name="t", charge_axes=[rot_axes[0].id], burst_axis="",
                   team=Team(members=["祀", "管理员", "陈千语", "余烬"]))
    p = Player(rotation=rot, store=FakeStore(rot_axes), settings=Settings())
    for n in rot_axes[0].nodes:
        n.operator = "祀"
    rot_axes[0].nodes[0].stage = 1
    rot_axes[0].nodes[1].stage = 2
    now = [300.0]
    p.clock = lambda: now[0]
    p.start()
    key = p.settings.slot_key(0)
    r1, _ = p.press(vk=key, hold=False)
    now[0] += 0.2            # 同一颗键要连着按两下，等过去重窗口再按第二下
    r2, _ = p.press(vk=key, hold=False)
    # 两段走完正好一轮结束、回到第一段，所以 cycle 加 1
    check("两段各按一次都推进",
          r1 == MATCH and r2 == MATCH and p.cycle == 1 and p.index == 0,
          repr((r1, r2, p.cycle, p.index)))

    # 段数与图标：祀 战技 2 段；诀 三类都 2 段
    from app import forms
    check("祀的战技登记为 3 段", forms.stages("祀", "skill") == 3)
    check("诀的终结登记为 2 段", forms.stages("诀", "ult") == 2)
    check("没登记的干员默认 1 段", forms.stages("佩丽卡", "skill") == 1)

    # 按名字区分形态（用户要求，别再用 ①②）
    check("诀第二段叫「战技·意诀」",
          forms.label_for("诀", "skill", 2) == "战技·意诀",
          repr(forms.label_for("诀", "skill", 2)))
    check("诀连携第二段叫「连携·意诀」",
          forms.label_for("诀", "combo", 2) == "连携·意诀")
    check("明河第二段叫「战技·连携后」",
          forms.label_for("明河", "skill", 2) == "战技·连携后")
    check("梨诺两段叫「战技·开 / 战技·关」",
          forms.label_for("梨诺", "skill", 1) == "战技·开"
          and forms.label_for("梨诺", "skill", 2) == "战技·关")
    check("噗切娜两段按第一段/第二段命名",
          forms.label_for("噗切娜", "skill", 2) == "战技·第二段")
    check("没登记名字时返回空（用兜底显示）",
          forms.label_for("佩丽卡", "skill", 1) == "")


def test_branch():
    """分支点：触发卡决定走哪条；分支自带卡片；走完可顺走或跳到指定轴。"""
    from app.model import KIND_BRANCH, blank_option

    team = ("佩丽卡", "管理员", "陈千语", "余烬")

    def build(next_to_burst=False):
        burst = Axis(name="爆发轴", role=ROLE_BURST,
                     nodes=[Node(operator="余烬", kind=KIND_ULT)])
        main = Axis(name="主线", role=ROLE_CHARGE)
        br = Node(kind=KIND_BRANCH, options=[
            {"trigger": {"operator": "佩丽卡", "kind": KIND_ULT, "stage": 1},
             "nodes": [Node(operator="余烬", kind=KIND_SKILL),
                       Node(operator="陈千语", kind=KIND_ULT)],
             "next": (burst.id if next_to_burst else "")},
            blank_option("余烬", KIND_COMBO),
        ])
        main.nodes = [Node(operator="佩丽卡", kind=KIND_SKILL), br,
                      Node(operator="管理员", kind=KIND_SKILL)]
        store = FakeStore([main, burst])
        store.team = Team(members=list(team))
        rot = Rotation(name="分支编队", team=Team(members=list(team)))
        rot.set_sequence([main.id, burst.id])
        p = Player(rotation=rot, store=store, settings=Settings())
        p.start()
        return p, burst

    p, burst = build()
    p.press(vk=0x31, hold=False)                 # 佩丽卡战技 -> 分支点
    check("走到分支点", p.current().kind == KIND_BRANCH, repr(p.current()))

    r, _ = p.press(vk=0x33, hold=False)          # 陈千语战技：不是任何触发卡
    check("分支点按错不选路", r == IGNORED and p.route is None, repr((r, p.route)))

    r, _ = p.press(vk=0x31, hold=True)           # 佩丽卡终结 = 第一条的触发卡
    check("按触发卡进入分支", r == MATCH and p.route is not None, repr(r))
    check("分支第一张卡", p.route is not None and p.current().operator == "余烬",
          repr(p.current()))

    p.press(vk=0x34, hold=False)
    check("分支内推进", p.current() is not None and p.current().operator == "陈千语",
          repr(p.current()))

    r, _ = p.press(vk=0x33, hold=True)
    check("顺走：回主线下一节点",
          r == MATCH and p.route is None and p.current().operator == "管理员",
          repr((r, p.route, p.current())))

    # 走完跳到爆发轴
    p2, burst2 = build(next_to_burst=True)
    p2.press(vk=0x31, hold=False)
    p2.press(vk=0x31, hold=True)
    p2.press(vk=0x34, hold=False)
    p2.press(vk=0x33, hold=True)
    check("走完直接跳到爆发轴",
          p2.route is None and p2.current_axis() is burst2,
          repr((p2.route, p2.current_axis() and p2.current_axis().name)))
    check("跳到爆发轴后从第一个节点开始",
          p2.current() is not None and p2.current().operator == "余烬",
          repr(p2.current()))

    # 空分支：立刻按「顺走」处理
    p3, _ = build()
    p3.press(vk=0x31, hold=False)
    p3.press(vk=0x45, hold=False)                # 余烬连携（E）-> 空分支
    check("空分支立即顺走", p3.route is None and p3.current().operator == "管理员",
          repr((p3.route, p3.current())))


def test_axis_order():
    """充能轴/爆发轴可以混排、多条爆发轴；顺序按 rot.order。"""
    main1 = Axis(name="充能轴 · 1", role=ROLE_CHARGE)
    burst1 = Axis(name="爆发轴", role=ROLE_BURST)
    main2 = Axis(name="充能轴 · 2", role=ROLE_CHARGE)
    burst2 = Axis(name="爆发轴 · 2", role=ROLE_BURST)
    for a in (main1, burst1, main2, burst2):
        a.nodes = [Node(operator="佩丽卡", kind=KIND_SKILL)]
    store = FakeStore([main1, burst1, main2, burst2])
    store.team = Team(members=["佩丽卡", "管理员", "陈千语", "余烬"])
    rot = Rotation(name="混排", team=Team(members=store.team.normalized()))
    rot.set_sequence([main1.id, burst1.id, main2.id, burst2.id])
    rot.sync_legacy(store.axis_by_id)
    check("编队顺序按 order", rot.sequence() == [main1.id, burst1.id, main2.id, burst2.id],
          repr(rot.sequence()))
    check("旧字段同步：充能轴只含充能",
          rot.charge_axes == [main1.id, main2.id], repr(rot.charge_axes))
    check("旧字段同步：burst_axis 取最后一条爆发轴",
          rot.burst_axis == burst2.id, repr(rot.burst_axis))

    p = Player(rotation=rot, store=store, settings=Settings())
    p.start()
    names = [s.axis.name for s in p.segments]
    check("段顺序 = 混排顺序",
          names == ["充能轴 · 1", "爆发轴", "充能轴 · 2", "爆发轴 · 2"], repr(names))
    check("爆发轴也能有多个段",
          sum(1 for s in p.segments if s.role == "burst") == 2)

    # 存盘再读回，顺序不丢
    tmp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "_selftest_tmp8")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    store2 = Store(tmp)
    store2.axes = [main1, burst1, main2, burst2]
    store2.rotations = [rot]
    store2.settings.active_rotation = rot.id
    store2.save_axes(); store2.save_rotations(); store2.save_settings()
    store3 = Store(tmp)
    rot3 = store3.active_rotation()
    check("混排顺序持久化", rot3.sequence() == [main1.id, burst1.id, main2.id, burst2.id],
          repr(rot3.sequence()))
    shutil.rmtree(tmp, ignore_errors=True)


def test_default_names():
    """默认命名：编队 · N / 充能轴 · N / 路线 · N / 爆发轴（固定）。"""
    from app.model import next_numbered_name

    check("编号顺延：1、2 -> 3",
          next_numbered_name(["充能轴 · 1", "充能轴 · 2"], "充能轴") == "充能轴 · 3")
    check("编号按最大值顺延（不看条数）",
          next_numbered_name(["充能轴 · 5"], "充能轴") == "充能轴 · 6")
    check("没有同名时从 1 开始",
          next_numbered_name(["别的轴"], "充能轴") == "充能轴 · 1")
    check("不误判前缀相近的名字",
          next_numbered_name(["充能轴测试"], "充能轴") == "充能轴 · 1")

    tmp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "_selftest_tmp7")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    store = Store(tmp)
    demo = {a.name for a in store.axes}
    check("示例数据充能轴叫「充能轴 · 1/2」",
          "充能轴 · 1" in demo and "充能轴 · 2" in demo, repr(demo))
    check("示例数据爆发轴叫「爆发轴 · 1」", "爆发轴 · 1" in demo, repr(demo))
    check("示例编队叫「编队 · 1」",
          store.rotations[0].name == "编队 · 1", repr(store.rotations[0].name))

    a1 = store.add_axis(ROLE_CHARGE)
    a2 = store.add_axis(ROLE_CHARGE)
    check("新建充能轴依次编号",
          a1.name == "充能轴 · 3" and a2.name == "充能轴 · 4",
          repr((a1.name, a2.name)))

    b1 = store.add_axis(ROLE_BURST)
    b2 = store.add_axis(ROLE_BURST)
    check("已有「爆发轴 · 1」时新建为「爆发轴 · 2」",
          b1.name == "爆发轴 · 2", repr(b1.name))
    check("再建一条为「爆发轴 · 3」", b2.name == "爆发轴 · 3", repr(b2.name))

    rot = store.add_rotation()
    check("新建编队依次编号", rot.name == "编队 · 2", repr(rot.name))
    shutil.rmtree(tmp, ignore_errors=True)


def test_skip():
    p, rot, axes, s = mk_player(charge_kinds=((KIND_SKILL, KIND_ULT),))
    p.start()
    ok = p.skip()
    check("跳过节点", ok and p.index == 1)


def test_empty_segment_skipped():
    charges = [mk_axis(ROLE_CHARGE, "空充能", ())]
    burst = mk_axis(ROLE_BURST, "爆发", (KIND_SKILL,))
    rot = Rotation(name="t", charge_axes=[charges[0].id], burst_axis=burst.id)
    p = Player(rotation=rot, store=FakeStore(charges + [burst]),
               settings=Settings())
    p.start()
    check("跳过没有节点的段", p.current_segment().role == "burst")


# ---------- 存储 ----------
def test_store_roundtrip():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp = os.path.join(base, "data", "_selftest_tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    store = Store(tmp)
    check("首次载入生成示例数据",
          len(store.axes) == 3 and len(store.rotations) == 1)

    axis = store.add_axis(ROLE_CHARGE, "我的充能")
    axis.nodes = [Node(operator="佩丽卡", kind=KIND_ULT, icon="佩丽卡_终结.png")]
    store.save_axes()

    store2 = Store(tmp)
    found = [a for a in store2.axes if a.name == "我的充能"]
    check("技能轴持久化", len(found) == 1)
    if found:
        check("节点 kind 持久化", found[0].nodes[0].kind == KIND_ULT)
        check("技能轴类型持久化", found[0].role == ROLE_CHARGE)

    rot = store2.active_rotation()
    check("编队持久化（示例 2 条 + 新增 1 条充能轴）",
          rot is not None and len(rot.charge_axes) == 3
          and axis.id in rot.sequence(), repr((rot.charge_axes if rot else None)))

    store2.team = Team(members=["A", "B", "C", "D"])
    store2.save_team()
    store3 = Store(tmp)
    check("队伍持久化", store3.team.normalized() == ["A", "B", "C", "D"])


def test_settings_keys():
    tmp_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "data", "_selftest_tmp4")
    shutil.rmtree(tmp_dir, ignore_errors=True)
    os.makedirs(tmp_dir, exist_ok=True)
    store = Store(tmp_dir)
    s = store.settings
    check("默认连携键是 E", s.combo_key == 0x45)
    check("默认长按阈值 280", s.hold_ms == 280)
    s.combo_key = 0x51
    s.hold_ms = 400
    s.pad[KIND_ULT] = 0x1000
    store.save_settings()
    store2 = Store(tmp_dir)
    check("连携键持久化", store2.settings.combo_key == 0x51)
    check("长按阈值持久化", store2.settings.hold_ms == 400)
    check("手柄映射持久化", store2.settings.pad_for(KIND_ULT) == 0x1000)
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_export_import():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp = os.path.join(base, "data", "_selftest_tmp2")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    store = Store(tmp)
    data = store.export_dict()
    check("导出包含 axes/rotations/team/settings",
          all(k in data for k in ("axes", "rotations", "team", "settings")))

    tmp2 = os.path.join(base, "data", "_selftest_tmp3")
    shutil.rmtree(tmp2, ignore_errors=True)
    os.makedirs(tmp2, exist_ok=True)
    store2 = Store(tmp2)
    before = len(store2.axes)
    ok, msg = store2.import_dict(data, mode="append")
    check("导入成功", ok, msg)
    check("追加模式技能轴数增加", len(store2.axes) > before)
    ok_bad, _ = store2.import_dict({"foo": 1})
    check("非法文件被拒绝", not ok_bad)
    shutil.rmtree(tmp2, ignore_errors=True)


def test_demo_and_clone():
    """示例编队排版 + 新建编队克隆独立轴（不串改别的编队）。"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp = os.path.join(base, "data", "_selftest_tmp11")
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    st = Store(tmp)
    names = [a.name for a in st.axes]
    check("示例：充能轴 · 1 / 充能轴 · 2", names[:2] == ["充能轴 · 1", "充能轴 · 2"],
          repr(names))
    check("示例：爆发轴 · 1", "爆发轴 · 1" in names, repr(names))
    check("示例技能轴默认是空的", all(not a.nodes for a in st.axes),
          repr([len(a.nodes) for a in st.axes]))
    check("示例编队叫「编队 · 1」", st.rotations[0].name == "编队 · 1")
    check("示例队伍不变", st.rotations[0].members()[:2] == ["佩丽卡", "管理员"],
          repr(st.rotations[0].members()))

    before_axes = len(st.axes)
    before_names = [a.name for a in st.axes]
    rot2 = st.add_rotation()
    check("新建编队序号顺延", rot2.name == "编队 · 2", repr(rot2.name))
    check("新建编队克隆同样排版（2 充能 + 1 爆发）",
          len(rot2.sequence()) == 3, repr(rot2.sequence()))
    check("克隆的轴是新 id（不和原编队共用）",
          not (set(rot2.sequence()) & set(st.rotations[0].sequence())))
    check("克隆的轴名字不重复",
          len({a.name for a in st.axes}) == len(st.axes),
          repr([a.name for a in st.axes]))
    check("克隆的轴默认空", all(not st.axis_by_id(x).nodes for x in rot2.sequence()))
    check("轴数量增加 3 条", len(st.axes) == before_axes + 3)
    check("原轴名字没被改", all(n in [a.name for a in st.axes] for n in before_names))

    # 改新编队里的轴，不能影响旧编队里的同名内容
    clone = st.axis_by_id(rot2.sequence()[0])
    clone.nodes = [Node(operator="别礼", kind=KIND_SKILL)]
    old = st.axis_by_id(st.rotations[0].sequence()[0])
    check("改新编队的轴不影响旧编队", old is not clone and not old.nodes)
    shutil.rmtree(tmp, ignore_errors=True)


def test_import_modes():
    """导入两种模式：覆盖 / 添加；名字重复要区分开。"""
    from app.model import unique_name

    check("unique_name 顺延后缀",
          unique_name(["编队 · 1"], "编队 · 1") == "编队 · 1 (2)")
    check("unique_name 跳过已占用",
          unique_name(["编队 · 1", "编队 · 1 (2)"], "编队 · 1") == "编队 · 1 (3)")

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ta = os.path.join(base, "data", "_selftest_tmp12")
    tb = os.path.join(base, "data", "_selftest_tmp13")
    for d in (ta, tb):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
    a = Store(ta)
    a.settings.hold_ms = 333
    data = a.export_dict()

    b = Store(tb)
    ok, _ = b.import_dict(data, mode="replace")
    check("覆盖导入成功", ok)
    check("覆盖导入后设置跟随", b.settings.hold_ms == 333)
    check("覆盖导入后编队数量等于文件", len(b.rotations) == len(a.rotations),
          repr((len(b.rotations), len(a.rotations))))
    check("覆盖导入后名字不重复",
          len({r.name for r in b.rotations}) == len(b.rotations))

    n0 = len(b.rotations)
    a0 = len(b.axes)
    ok2, _ = b.import_dict(data, mode="append")
    ok3, _ = b.import_dict(data, mode="append")
    check("追加导入成功", ok2 and ok3)
    check("追加后编队变多", len(b.rotations) == n0 * 3, repr(len(b.rotations)))
    check("追加后轴变多", len(b.axes) == a0 + 2 * len(a.axes))
    rnames = [r.name for r in b.rotations]
    check("追加后编队名字不重复", len(set(rnames)) == len(rnames), repr(rnames))
    anames = [x.name for x in b.axes]
    check("追加后轴名字不重复", len(set(anames)) == len(anames))
    alive = {x.id for x in b.axes}
    broken = [x for r in b.rotations for x in r.sequence() if x not in alive]
    check("追加后编队顺序都指向存在的轴", not broken, repr(broken[:3]))
    for d in (ta, tb):
        shutil.rmtree(d, ignore_errors=True)


def test_export_roundtrip():
    """导出/导入要带全所有内容：设置、循环次数、段号、分支卡片与跳转。"""
    from app.model import KIND_BRANCH
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    t1 = os.path.join(base, "data", "_selftest_tmp9")
    t2 = os.path.join(base, "data", "_selftest_tmp10")
    for d in (t1, t2):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)

    store = Store(t1)
    store.settings.hold_ms = 420
    store.settings.combo_key = 0x51
    store.settings.pad_ult_mode = "chord"
    store.settings.pad_modifier = 0x0200
    store.settings.opacity = 0.7

    charge = store.axes[0]
    charge.repeat = 3
    charge.nodes = [Node(operator="祀", kind=KIND_SKILL, stage=2)]
    burst = next(a for a in store.axes if a.role == ROLE_BURST)
    burst.nodes = [Node(kind=KIND_BRANCH, options=[{
        "trigger": {"operator": "管理员", "kind": KIND_ULT, "stage": 1},
        "nodes": [Node(operator="余烬", kind=KIND_SKILL)],
        "next": charge.id,
    }])]
    rot = store.active_rotation()
    rot.set_sequence([charge.id, burst.id])
    store.save_all()

    data = store.export_dict()
    check("导出带完整设置",
          data["settings"].get("hold_ms") == 420
          and data["settings"].get("pad_ult_mode") == "chord"
          and data["settings"].get("opacity") == 0.7, repr(data["settings"].get("hold_ms")))
    check("导出带循环次数", data["axes"][0]["repeat"] == 3
          if data["axes"][0].get("id") == charge.id else
          any(a.get("repeat") == 3 for a in data["axes"]))
    check("导出带段号", any(
        n.get("stage") == 2 for a in data["axes"] for n in a.get("nodes", [])))
    check("导出带分支卡片", any(
        n.get("kind") == KIND_BRANCH and n.get("options")
        and n["options"][0]["nodes"]
        for a in data["axes"] for n in a.get("nodes", [])))

    # 替换导入
    store2 = Store(t2)
    ok, msg = store2.import_dict(data, mode="replace")
    check("替换导入成功", ok, msg)
    check("导入后设置跟随", store2.settings.hold_ms == 420
          and store2.settings.pad_ult_mode == "chord"
          and store2.settings.opacity == 0.7,
          repr((store2.settings.hold_ms, store2.settings.pad_ult_mode)))
    r2 = store2.active_rotation()
    check("导入后顺序跟随", r2 is not None and r2.sequence() == [charge.id, burst.id],
          repr(r2.sequence() if r2 else None))
    a2 = store2.axis_by_id(charge.id)
    check("导入后循环次数跟随", a2 is not None and a2.repeat == 3)
    b2 = store2.axis_by_id(burst.id)
    check("导入后分支卡片跟随",
          b2 is not None and b2.nodes[0].kind == KIND_BRANCH
          and len(b2.nodes[0].options[0]["nodes"]) == 1
          and b2.nodes[0].options[0]["next"] == charge.id)

    # 合并导入：id 冲突要重映射，分支跳转不能断
    ok2, _ = store2.import_dict(data, mode="append")
    check("合并导入成功", ok2)
    alive = {a.id for a in store2.axes}
    broken = []
    for axis in store2.axes:
        for node in axis.nodes:
            for opt in (node.options or []):
                nxt = opt.get("next")
                if nxt and nxt not in alive:
                    broken.append(nxt)
    check("合并导入后分支跳转仍指向存在的轴", not broken, repr(broken))
    for d in (t1, t2):
        shutil.rmtree(d, ignore_errors=True)


def test_legacy_migration():
    axis = Axis.from_dict({
        "id": "old1", "name": "旧技能轴", "kind": "loop",
        "nodes": [{"operator": "佩丽卡", "icon": "佩丽卡_连携.png",
                   "vk": 0x31, "note": "旧备注"}],
    })
    check("旧数据可解析", axis.nodes[0].operator == "佩丽卡")
    check("旧图标推断出连携类型", axis.nodes[0].kind == KIND_COMBO)
    check("旧技能轴默认按爆发处理", axis.role == ROLE_BURST)


# ---------- 资源 ----------
def test_assets():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    icons = os.path.join(base, "data", "icons")
    portraits = os.path.join(base, "data", "portraits")
    n_icons = len([f for f in os.listdir(icons) if f.endswith(".png")]) \
        if os.path.isdir(icons) else 0
    n_portraits = len([f for f in os.listdir(portraits) if f.endswith(".png")]) \
        if os.path.isdir(portraits) else 0
    check("技能图标库存在", n_icons >= 100, "共 %d 张" % n_icons)
    check("干员立绘存在", n_portraits >= 30, "共 %d 张" % n_portraits)


def test_tolerant_progress():
    """误按不中断；按到后续技能自动追轴；短时间重复输入不多推进。"""
    p, rot, axes, s = mk_player(charge_kinds=((KIND_SKILL, KIND_SKILL, KIND_COMBO),),
                                team=("佩丽卡", "管理员", "陈千语"))
    now = [1000.0]
    p.clock = lambda: now[0]
    p.start()
    team = p.store.team.normalized()
    digit2 = s.slot_key(team.index(axes[0].nodes[1].operator))

    r, info = p.press(vk=digit2, hold=False)
    check("按到本段后面的技能会自动追轴", r == JUMP)
    check("追轴会报告跳过数量", info[0] is axes[0].nodes[1] and info[1] == 1)
    check("追轴后继续等待下一技能", p.state == "running" and p.index == 2)

    # 当前应按连携，误按一个绑定数字键：保持运行且不改变进度
    now[0] += 0.20
    r2, _ = p.press(vk=s.slot_key(0), hold=False)
    check("普通误按不会暂停循环", p.state == "running")
    check("普通误按不会乱推进", r2 in (WRONG, IGNORED) and p.index == 2)

    now[0] += 0.20
    r3, _ = p.press(vk=s.combo_key, hold=False)
    check("误按后按对仍能继续", r3 == MATCH and p.state == "running")

    # 两个连续节点故意使用同一个键：120ms 内的第二下视为抖动/多按
    p2, _r2, axes2, s2 = mk_player(charge_kinds=((KIND_SKILL, KIND_SKILL),),
                                   team=("佩丽卡", "管理员"))
    axes2[0].nodes[1].operator = axes2[0].nodes[0].operator
    now2 = [2000.0]
    p2.clock = lambda: now2[0]
    p2.start()
    same_key = s2.slot_key(0)
    first, _ = p2.press(vk=same_key, hold=False)
    now2[0] += 0.05
    duplicate, _ = p2.press(vk=same_key, hold=False)
    check("第一次输入正常推进", first == MATCH and p2.index == 1)
    check("短时间重复多按被吞掉", duplicate == IGNORED and p2.index == 1)
    now2[0] += 0.20
    next_real, _ = p2.press(vk=same_key, hold=False)
    check("超过容错窗口后同键可正常推进",
          next_real == MATCH and p2.state == "running")


def test_export_import_merge():
    """导出/导入：单编队导出带队伍，追加导入不破坏原有引用。"""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp = os.path.join(base, "data", "_selftest_export")
    import shutil as _sh
    _sh.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    store = Store(tmp)
    rot = store.active_rotation()
    data = store.export_dict(rot)
    check("单编队导出标记 scope", data.get("scope") == "rotation")
    check("单编队导出带上了队伍",
          data["rotations"][0]["team"]["members"][0] == rot.members()[0])
    ids = {a["id"] for a in data["axes"]}
    refs = set(data["rotations"][0].get("order") or [])
    check("单编队导出的引用都包含在 axes 里", refs <= ids)

    before_ids = [r.id for r in store.rotations]
    before_axis = list(store.rotations[0].sequence())
    ok, _msg = store.import_dict(data, mode="append")
    check("追加导入成功", ok)
    check("原有编队保持不变",
          [r.id for r in store.rotations][:len(before_ids)] == before_ids
          and store.rotations[0].sequence() == before_axis)
    _sh.rmtree(tmp, ignore_errors=True)


def test_updater_plan():
    """更新器只挑缺失或哈希不一致的文件，且挡掉越界路径。"""
    try:
        from app import updater as up
    except Exception as exc:  # noqa: BLE001
        check("更新器模块可导入", False, repr(exc))
        return
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tmp = os.path.join(base, "data", "_selftest_update")
    import shutil as _sh
    _sh.rmtree(tmp, ignore_errors=True)
    os.makedirs(tmp, exist_ok=True)
    same = os.path.join(tmp, "same.py")
    with open(same, "w", encoding="utf-8") as f:
        f.write("x = 1\n")
    digest = up.file_hash(same)
    manifest = {"version": "9.9.9", "files": {
        "same.py": {"sha256": digest, "size": 6},
        "missing.py": {"sha256": "0" * 64, "size": 10},
        "../evil.py": {"sha256": "0" * 64, "size": 1},
    }}
    names = [rel for rel, _info in up.plan(manifest, tmp)]
    check("哈希一致的文件不下载", "same.py" not in names)
    check("缺失的文件会下载", "missing.py" in names)
    check("越界路径被挡掉", all(".." not in n for n in names))
    check("safe_relpath 拒绝绝对路径",
          up.safe_relpath("/etc/passwd") is None
          and up.safe_relpath("C:/windows/x") is None)
    check("版本比较可用",
          up.is_newer("1.10.0", "1.9.9") and not up.is_newer("1.2.0", "1.3.0"))
    _sh.rmtree(tmp, ignore_errors=True)


def test_render():
    try:
        from app.iconart import compose, compose_combo, compose_portrait
    except Exception as exc:  # noqa: BLE001
        check("图标合成模块可导入", False, repr(exc))
        return
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    glyph = os.path.join(base, "data", "icons", "佩丽卡_技能.png")
    portrait = os.path.join(base, "data", "portraits", "佩丽卡.png")
    if not os.path.isfile(glyph):
        check("图标合成：素材存在", False)
        return
    for kind in ("skill", "ult"):
        im = compose(glyph, 96, "Electric", kind)
        check("合成 %s 正常" % kind, im.size == (96, 96) and im.mode == "RGBA")
    if os.path.isfile(portrait):
        im = compose_combo(portrait, glyph, 96, "Electric")
        check("合成连携图标正常", im.size == (96, 96) and im.mode == "RGBA")
        im2 = compose_portrait(portrait, 96, "Electric")
        check("合成纯头像正常", im2.size == (96, 96) and im2.mode == "RGBA")


def test_fonts():
    try:
        from app import fonts
    except Exception as exc:  # noqa: BLE001
        check("字体模块可导入", False, repr(exc))
        return
    check("字体模块有 fit 截断函数", callable(getattr(fonts, "fit", None)))
    check("字体模块有 wrap 折行函数", callable(getattr(fonts, "wrap", None)))


def main():
    for fn in (test_segment_order, test_play_through, test_slot_mapping,
               test_combo_key, test_ult_requires_hold, test_hold_threshold_setting,
               test_infinite, test_wrong_key, test_key_map, test_any_mode,
               test_gamepad, test_pad_ult_modes, test_team_unique, test_move_item,
               test_axis_repeat, test_multi_stage, test_branch, test_axis_order, test_default_names,
               test_tolerant_progress, test_export_import_merge, test_updater_plan,
               test_skip,
               test_empty_segment_skipped,
               test_hotdata_dirty_flow, test_per_rotation_team,
               test_rotation_team_affects_keys, test_rename_rotation,
               test_store_roundtrip, test_settings_keys, test_export_import, test_export_roundtrip, test_demo_and_clone, test_import_modes,
               test_legacy_migration, test_assets, test_render, test_fonts):
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            check(fn.__name__ + " 未抛异常", False, repr(exc))

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for d in ("_selftest_tmp", "_selftest_tmp2", "_selftest_tmp3",
              "_selftest_tmp4", "_selftest_tmp5", "_selftest_tmp6"):
        shutil.rmtree(os.path.join(base, "data", d), ignore_errors=True)

    failed = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(("PASS  " if ok else "FAIL  ") + name + ("   %s" % detail if detail else ""))
    print("-" * 60)
    print("共 %d 项，失败 %d 项" % (len(results), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
