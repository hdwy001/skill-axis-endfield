# -*- coding: utf-8 -*-
"""编辑器：左侧编队播放顺序 / 中间队伍 + 技能 + 技能轴。"""
import copy
import json
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from . import dpi, fonts, theme
from .keys import vk_label
from .model import (KIND_CN, KIND_COMBO, KIND_SKILL, KINDS, KIND_ULT,
                    ROLE_BURST, ROLE_CHARGE, ROLE_CN, Axis, Node, Team)
from .opspicker import OperatorPicker
from .scaledcanvas import ScaledCanvas
from .textdialog import ask_text
from .widgets import rounded_rect, truncate

# 布局
LEFT_W = 316
AXIS_ROW_H = 56
ROT_CHIP_H = 30
ROT_CHIP_GAP = 6
TEAM_CARD_W = 96
TEAM_CARD_H = 112
SKILL_CARD_W = 104
SKILL_CARD_H = 104
NODE_W = 84
NODE_H = 104
NODE_GAP = 10
AVATAR = 34


def _btn(parent, text, command, kind="normal"):
    styles = {
        "normal": (theme.PANEL_3, theme.TEXT, theme.PANEL_4),
        "primary": (theme.ACCENT, "#221a06", theme.ACCENT_SOFT),
        "danger": (theme.PANEL_3, theme.BAD, theme.PANEL_4),
        "ghost": (theme.PANEL, theme.TEXT_DIM, theme.PANEL_2),
    }
    bg, fg, active = styles.get(kind, styles["normal"])
    return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                     activebackground=active, activeforeground=fg,
                     relief="flat", bd=0, highlightthickness=0, cursor="hand2",
                     font=theme.font(theme.F_SMALL), padx=dpi.S(12), pady=dpi.S(5))


def _section(parent, title, sub=None):
    f = tk.Frame(parent, bg=theme.BG)
    tk.Label(f, text=title, bg=theme.BG, fg=theme.TEXT,
             font=theme.font(theme.F_SECTION, True)).pack(side="left")
    if sub:
        tk.Label(f, text=sub, bg=theme.BG, fg=theme.TEXT_MUTED,
                 font=theme.font(theme.F_TINY)).pack(side="left", padx=dpi.Spair((8, 0)))
    return f


class Editor:
    def __init__(self, app):
        self.app = app
        self.root = app.root
        self.store = app.store
        self.icons = app.icons

        self.current_axis_id = None
        self.selected_member = ""
        self._drag = None
        self._ghost = None
        self._pending_drop = None
        self._rename_entry = None
        self._rot_rects = []        # 编队（标签）位置，算拖放插入点在用

        self._build()
        if self.store.axes:
            self.current_axis_id = self.store.axes[0].id
        self.refresh_all()

    # ================= 骨架 =================
    def _build(self):
        self.root.configure(bg=theme.BG)
        self._build_header()

        body = tk.Frame(self.root, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=dpi.S(14), pady=dpi.Spair((10, 12)))

        self.left = tk.Frame(body, bg=theme.BG, width=dpi.S(LEFT_W))
        self.left.pack(side="left", fill="y")
        self.left.pack_propagate(False)

        self.center = tk.Frame(body, bg=theme.BG)
        self.center.pack(side="left", fill="both", expand=True, padx=dpi.Spair((12, 0)))

        self._build_left()
        self._build_center()

    def _build_header(self):
        head = tk.Frame(self.root, bg=theme.BG_2)
        head.pack(fill="x")

        title = tk.Frame(head, bg=theme.BG_2)
        title.pack(side="left", padx=dpi.S(20), pady=dpi.Spair((12, 12)))
        tk.Label(title, text="技能轴提示器", bg=theme.BG_2, fg=theme.TEXT,
                 font=theme.font(theme.F_TITLE, True)).pack(anchor="w")
        tk.Label(title, text="明日方舟：终末地 · 编队编排", bg=theme.BG_2,
                 fg=theme.TEXT_MUTED, font=theme.font(theme.F_TINY)).pack(anchor="w")

        right = tk.Frame(head, bg=theme.BG_2)
        right.pack(side="right", padx=dpi.S(18), pady=dpi.S(16))

        # 权限状态：非管理员时提示（游戏里收不到按键多半是这个原因）
        self.perm_label = tk.Label(head, bg=theme.BG_2, cursor="hand2",
                                   font=theme.font(theme.F_TINY))
        self.perm_label.pack(side="right", padx=dpi.Spair((0, 14)))
        self.perm_label.bind("<Button-1>", lambda e: self._on_perm_click())
        self._refresh_perm_label()

        _btn(right, "打开悬浮窗", self.app.show_overlay, "primary").pack(
            side="left", padx=dpi.S(4))
        _btn(right, "按键测试", self.app.open_test_panel, "ghost").pack(
            side="left", padx=dpi.S(4))
        _btn(right, "导入", self.do_import, "ghost").pack(
            side="left", padx=dpi.S(4))
        _btn(right, "导出", self.do_export, "ghost").pack(
            side="left", padx=dpi.S(4))
        _btn(right, "设置", self.open_settings, "ghost").pack(
            side="left", padx=dpi.S(4))

        tk.Frame(self.root, bg=theme.BORDER, height=dpi.S(1)).pack(fill="x")

    def open_settings(self):
        from .settingsdialog import SettingsDialog
        SettingsDialog(self.app)

    # ---------- 权限状态 ----------
    def _refresh_perm_label(self):
        from .elevation import is_admin
        admin = is_admin()
        if admin:
            self.perm_label.configure(text="管理员模式", fg=theme.GREEN)
        else:
            self.perm_label.configure(
                text="非管理员 · 游戏里可能收不到按键（点这里提权）", fg=theme.WARN)

    def _on_perm_click(self):
        from tkinter import messagebox
        from .elevation import is_admin, relaunch_as_admin
        if is_admin():
            messagebox.showinfo("当前已是管理员", "程序已经以管理员身份运行。",
                                parent=self.root)
            return
        ok = relaunch_as_admin()
        if ok:
            self.app.on_close()
        else:
            messagebox.showwarning(
                "提权失败",
                "没能以管理员身份重启。\n\n可以手动操作：右键程序 → 以管理员身份运行。",
                parent=self.root)

    # ---------- 左栏 ----------
    def _build_left(self):
        wrap = self.left

        head = tk.Frame(wrap, bg=theme.BG)
        head.pack(fill="x", pady=dpi.Spair((4, 4)))
        tk.Label(head, text="编队", bg=theme.BG, fg=theme.TEXT,
                 font=theme.font(theme.F_SECTION, True)).pack(side="left")
        tk.Label(head, text="单击切换 · 拖动排序 · 双击改名", bg=theme.BG,
                 fg=theme.TEXT_MUTED,
                 font=theme.font(theme.F_TINY)).pack(side="right")

        # 编队标签块：一个编队一个标签，横向排，多了自动换行
        self.rot_canvas = ScaledCanvas(wrap, bg=theme.BG, highlightthickness=0,
                                    bd=0, height=ROT_CHIP_H + 6)
        self.rot_canvas.pack(fill="x")

        # 队伍阵容头像（整个编队共用）
        self.roster_canvas = ScaledCanvas(wrap, bg=theme.BG, highlightthickness=0,
                                       bd=0, height=AVATAR + 12)
        self.roster_canvas.pack(fill="x", pady=dpi.Spair((8, 0)))

        head = tk.Frame(wrap, bg=theme.BG)
        head.pack(fill="x", pady=dpi.Spair((10, 4)))
        tk.Label(head, text="播放顺序", bg=theme.BG, fg=theme.TEXT_DIM,
                 font=theme.font(theme.F_TINY)).pack(side="left")
        tk.Label(head, text="双击改名 · 拖动整行排序", bg=theme.BG,
                 fg=theme.TEXT_MUTED, font=theme.font(theme.F_TINY)).pack(side="right")

        self.order_canvas = ScaledCanvas(wrap, bg=theme.BG, highlightthickness=0, bd=0)
        self.order_canvas.pack(fill="both", expand=True)

        btns = tk.Frame(wrap, bg=theme.BG)
        btns.pack(fill="x", pady=dpi.Spair((8, 2)))

        self.save_label = tk.Label(btns, text=self._last_save_text(),
                                   bg=theme.BG, fg=theme.TEXT_MUTED,
                                   font=theme.font(theme.F_TINY), anchor="w")
        self.save_label.pack(fill="x", pady=dpi.Spair((0, 4)))

        grid = tk.Frame(btns, bg=theme.BG)
        grid.pack(fill="x", pady=dpi.S(2))
        grid.columnconfigure(0, weight=1, uniform="btn")
        grid.columnconfigure(1, weight=1, uniform="btn")

        _btn(grid, "＋ 新建技能轴", self.new_axis, "ghost").grid(
            row=0, column=0, sticky="ew", padx=dpi.Spair((0, 3)), pady=dpi.S(3))
        _btn(grid, "＋ 新建编队", self.new_rotation, "ghost").grid(
            row=0, column=1, sticky="ew", padx=dpi.Spair((3, 0)), pady=dpi.S(3))
        _btn(grid, "删除此技能轴", self.delete_axis, "danger").grid(
            row=1, column=0, sticky="ew", padx=dpi.Spair((0, 3)), pady=dpi.S(3))
        _btn(grid, "删除编队", self.delete_rotation, "danger").grid(
            row=1, column=1, sticky="ew", padx=dpi.Spair((3, 0)), pady=dpi.S(3))

    # ---------- 中间 ----------
    def _build_center(self):
        c = self.center

        team_wrap = tk.Frame(c, bg=theme.PANEL, padx=dpi.S(14), pady=dpi.S(12))
        team_wrap.pack(fill="x")
        _section(team_wrap, "队伍",
                 "单击选中 · 双击更换 · 拖动换位（位置决定按键 1~4）").pack(fill="x")
        self.team_canvas = ScaledCanvas(team_wrap, bg=theme.PANEL, highlightthickness=0,
                                     bd=0, height=TEAM_CARD_H + 8)
        self.team_canvas.pack(fill="x", pady=dpi.Spair((8, 0)))

        skill_wrap = tk.Frame(c, bg=theme.PANEL, padx=dpi.S(14), pady=dpi.S(12))
        skill_wrap.pack(fill="x", pady=dpi.Spair((10, 0)))
        _section(skill_wrap, "技能", "拖到下方技能轴，或点一下加到末尾").pack(fill="x")
        self.skill_canvas = ScaledCanvas(skill_wrap, bg=theme.PANEL, highlightthickness=0,
                                      bd=0, height=SKILL_CARD_H + 8)
        self.skill_canvas.pack(fill="x", pady=dpi.Spair((8, 0)))

        tl_wrap = tk.Frame(c, bg=theme.BG)
        tl_wrap.pack(fill="both", expand=True, pady=dpi.Spair((10, 0)))
        head = tk.Frame(tl_wrap, bg=theme.BG)
        head.pack(fill="x")
        self.tl_title = tk.Label(head, text="技能轴", bg=theme.BG, fg=theme.TEXT,
                                 font=theme.font(theme.F_SECTION, True))
        self.tl_title.pack(side="left")
        tk.Label(head, text="拖动节点改顺序 · 拖出删除", bg=theme.BG,
                 fg=theme.TEXT_MUTED, font=theme.font(theme.F_TINY)).pack(
            side="left", padx=dpi.S(10))
        _btn(head, "复制节点", self.duplicate_node, "ghost").pack(
            side="right", padx=dpi.S(3))
        _btn(head, "删除节点", self.delete_node, "danger").pack(
            side="right", padx=dpi.S(3))

        self.timeline = ScaledCanvas(tl_wrap, bg=theme.BG_2, highlightthickness=0, bd=0,
                                  height=NODE_H + 40)
        self.timeline.pack(fill="both", expand=True, pady=dpi.Spair((6, 0)))
        self.timeline.bind("<Button-1>", lambda e: self._select_node(None))

    # ================= 刷新 =================
    def refresh_all(self):
        # 先确保有一个选中干员，技能区才有内容
        if not self.selected_member:
            for m in self.current_team().normalized():
                if m:
                    self.selected_member = m
                    break
        self.refresh_rotation()
        self.refresh_roster()
        self.refresh_order()
        self.refresh_skills()
        self.refresh_team()
        self.refresh_timeline()

    def current_axis(self):
        axis = self.store.axis_by_id(self.current_axis_id)
        if axis is None and self.store.axes:
            axis = self.store.axes[0]
            self.current_axis_id = axis.id
        return axis

    def current_rotation(self):
        return self.store.active_rotation()

    def _order(self):
        """当前编队的播放顺序：充能轴们 + 爆发轴。"""
        rot = self.current_rotation()
        if not rot:
            return []
        out = [self.store.axis_by_id(i) for i in rot.charge_axes]
        out = [a for a in out if a is not None]
        burst = self.store.axis_by_id(rot.burst_axis)
        if burst is not None:
            out.append(burst)
        return out

    # ---------- 编队 ----------
    def refresh_rotation(self):
        """画编队标签：当前编队高亮，点击切换、拖动改顺序、双击改名。"""
        cv = self.rot_canvas
        cv.delete("all")
        self._rot_rects = []
        rots = self.store.rotations
        if not rots:
            cv.create_text(4, 15, anchor="w",
                           text="还没有编队，点下面「＋ 新建编队」",
                           fill=theme.TEXT_MUTED, font=theme.font(theme.F_TINY))
            cv.configure(height=ROT_CHIP_H + 6,
                         scrollregion=(0, 0, LEFT_W, ROT_CHIP_H + 6))
            return

        rot_now = self.current_rotation()
        active_id = rot_now.id if rot_now else ""
        max_x = LEFT_W - 4
        x, y = 0, 2
        for rot in rots:
            label = truncate(rot.name, 12)
            w = max(56, min(fonts.measure(label, theme.F_SMALL) + 24, max_x))
            if x > 0 and x + w > max_x:
                x, y = 0, y + ROT_CHIP_H + ROT_CHIP_GAP
            active = rot.id == active_id
            tag = "rot_%s" % rot.id
            rounded_rect(cv, x, y, x + w, y + ROT_CHIP_H, r=8,
                         fill=theme.PANEL_3 if active else theme.PANEL_2,
                         outline=theme.ACCENT if active else theme.BORDER,
                         width=2 if active else 1, tags=(tag,))
            cv.create_text(x + w / 2.0, y + ROT_CHIP_H / 2.0, text=label,
                           fill=theme.TEXT if active else theme.TEXT_DIM,
                           font=theme.font(theme.F_SMALL, active), tags=(tag,))
            cv.tag_bind(tag, "<Button-1>",
                        lambda e, r=rot: self._rot_press(r))
            cv.tag_bind(tag, "<Double-Button-1>",
                        lambda e, r=rot: self.rot_rename(r))
            self._rot_rects.append((x, y, x + w, y + ROT_CHIP_H, rot))
            x += w + ROT_CHIP_GAP

        h = y + ROT_CHIP_H + 6
        cv.configure(height=h, scrollregion=(0, 0, LEFT_W, h))

    def _rot_press(self, rot):
        """点一下切过去；按住拖动则等松手时改顺序。"""
        self._pick_rotation(rot.name)
        self._begin_drag({"type": "rot", "rotation": rot}, rot.name)

    def _rot_drop_index(self, e):
        """鼠标位置 -> 编队插入下标（按移动前的列表算）。"""
        pos = self._in_canvas(self.rot_canvas, e)
        if pos is None:
            return None
        px, py = pos
        idx = 0
        for (x1, y1, x2, y2, _rot) in self._rot_rects:
            if py > y2:
                idx += 1
                continue
            if py < y1:
                return idx
            if px < (x1 + x2) / 2.0:
                return idx
            idx += 1
        return idx

    def _draw_rot_indicator(self, idx):
        cv = self.rot_canvas
        cv.delete("drop_ind")
        if idx is None or not self._rot_rects:
            return
        if idx >= len(self._rot_rects):
            _x1, y1, x2, y2, _r = self._rot_rects[-1]
            x = x2 + ROT_CHIP_GAP / 2.0
        else:
            x1, y1, _x2, y2, _r = self._rot_rects[idx]
            x = x1 - ROT_CHIP_GAP / 2.0
        cv.create_line(x, y1 + 2, x, y2 - 2, fill=theme.ACCENT, width=3,
                       tags=("drop_ind",))

    def _reorder_rotation(self, rot, idx):
        if self.store.move_rotation(rot.id, idx):
            self.refresh_rotation()

    def save_changes(self):
        # 保留给外部调用（例如菜单里的「立即保存」）
        self.app.flush_save()

    # ---------- 保存时间 ----------
    def _last_save_text(self):
        ts = getattr(self.app, "last_save_time", None)
        if not ts:
            return "尚未保存"
        return "最后保存 %s" % time.strftime("%H:%M:%S", time.localtime(ts))

    def show_last_save(self, ts=None):
        """更新左栏底部的保存时间。"""
        if ts is not None:
            self.app.last_save_time = ts
        if not hasattr(self, "save_label"):
            return
        self.save_label.configure(text=self._last_save_text())

    def _confirm_unsaved(self, action="切换"):
        """自动保存模式下没有未保存提示，直接放行并落盘。"""
        self.app.flush_save()
        return True

    def _pick_rotation(self, name):
        target = None
        for r in self.store.rotations:
            if r.name == name:
                target = r
                break
        if target is None:
            return
        if target.id == self.store.settings.active_rotation:
            return
        # 自动保存：切换前先把当前改动落盘
        self.app.flush_save()
        self.store.settings.active_rotation = target.id
        self.store.save_settings()
        self.selected_member = ""
        self.current_axis_id = None
        order = self._order()
        if order:
            self.current_axis_id = order[0].id
        self.refresh_all()
        self.app.rebuild_player()

    def rename_rotation(self, rot=None):
        rot = rot or self.current_rotation()
        if not rot:
            return
        name = ask_text(self.app, "编队改名", "编队名称", rot.name)
        if not name:
            return
        rot.name = name
        self.store.touch()
        self.refresh_rotation()

    def rot_rename(self, rot=None):
        """双击标签改名：先把可能进行中的拖动结束掉，再弹输入框。"""
        self._end_drag()
        rot = rot or self.current_rotation()
        if not rot:
            return
        self._pick_rotation(rot.name)
        self.rename_rotation(rot)

    def delete_rotation(self):
        rot = self.current_rotation()
        if not rot:
            return
        if len(self.store.rotations) <= 1:
            messagebox.showinfo("不能删除", "至少要保留一个编队。", parent=self.root)
            return
        if not messagebox.askyesno(
                "删除编队",
                "确定删除「%s」？\n\n只会删掉这个编队，技能轴本身不会被删除。"
                % rot.name, parent=self.root):
            return
        self.store.delete_rotation(rot.id)
        left = self.store.rotations[0] if self.store.rotations else None
        self.store.settings.active_rotation = left.id if left else ""
        self.store.save_settings()
        self.selected_member = ""
        self.current_axis_id = None
        order = self._order()
        if order:
            self.current_axis_id = order[0].id
        self.refresh_all()
        self.app.rebuild_player()

    def new_rotation(self):
        if not self._confirm_unsaved("新建"):
            return
        name = ask_text(self.app, "新建编队", "给这个编队起个名字",
                        "新编队", ok_text="创建")
        if not name:
            return
        rot = self.store.add_rotation(name)
        self.store.settings.active_rotation = rot.id
        self.store.save_settings()
        self.selected_member = ""
        self.current_axis_id = None
        order = self._order()
        if order:
            self.current_axis_id = order[0].id
        self.refresh_all()
        self.app.rebuild_player()

    # ---------- 阵容头像 ----------
    def refresh_roster(self):
        cv = self.roster_canvas
        cv.delete("all")
        members = [m for m in self.current_team().normalized() if m]
        if not members:
            cv.create_text(2, 18, anchor="w", text="队伍还没选干员",
                           fill=theme.TEXT_MUTED, font=theme.font(theme.F_TINY))
            return
        x = 2
        for op in members:
            photo = self.icons.render_portrait(op, AVATAR)
            if photo is not None:
                cv.create_image(x + AVATAR / 2, 2 + AVATAR / 2, image=photo)
            cv.tag_bind("roster_%s" % op, "<Button-1>", lambda e: None)
            x += AVATAR + 8

    # ---------- 播放顺序 ----------
    def refresh_order(self):
        cv = self.order_canvas
        cv.delete("all")
        order = self._order()
        if not order:
            cv.create_text(6, 24, anchor="w",
                           text="还没有技能轴，点下面「＋ 新建技能轴」",
                           fill=theme.TEXT_MUTED, font=theme.font(theme.F_SMALL))
            cv.configure(scrollregion=(0, 0, LEFT_W, 80))
            return

        rot = self.current_rotation()
        charge_ids = rot.charge_axes if rot else []
        y = 2
        for idx, axis in enumerate(order):
            self._order_row(cv, axis, idx, y, charge_ids)
            y += AXIS_ROW_H
        cv.configure(scrollregion=(0, 0, LEFT_W, y + 8))

    def _order_row(self, cv, axis, idx, y, charge_ids):
        is_burst = axis.role == ROLE_BURST
        color = theme.BURST if is_burst else theme.CHARGE
        active = axis.id == self.current_axis_id
        tag = "row_%s" % axis.id

        rounded_rect(cv, 2, y, LEFT_W - 6, y + AXIS_ROW_H - 8, r=9,
                     fill=theme.PANEL_3 if active else theme.PANEL_2,
                     outline=theme.ACCENT if active else theme.BORDER,
                     width=2 if active else 1, tags=(tag,))
        rounded_rect(cv, 6, y + 8, 11, y + AXIS_ROW_H - 16, r=2, fill=color,
                     outline=color, tags=(tag,))

        cv.create_text(22, y + 13, anchor="nw", text=axis.name, fill=theme.TEXT,
                       font=theme.font(theme.F_BODY, True), tags=(tag,))

        badge = "爆发轴" if is_burst else "充能轴 %d/%d" % (
            charge_ids.index(axis.id) + 1 if axis.id in charge_ids else idx + 1,
            len(charge_ids))
        bw = fonts.measure(badge, theme.F_TINY, True) + 18
        bx = LEFT_W - 14 - bw
        rounded_rect(cv, bx, y + 11, bx + bw, y + 31, r=5,
                     fill=theme.PANEL_4, outline=color, tags=(tag,))
        cv.create_text(bx + bw / 2, y + 21, text=badge, fill=color,
                       font=theme.font(theme.F_TINY, True), tags=(tag,))

        cv.tag_bind(tag, "<Button-1>", lambda e, a=axis: self._row_press(a, e))
        cv.tag_bind(tag, "<Double-Button-1>",
                    lambda e, a=axis: self._begin_rename(a, e))

    def _row_press(self, axis, e):
        self.select_axis(axis.id)
        self._begin_drag({"type": "reorder", "axis": axis}, axis.name)

    def select_axis(self, axis_id):
        self.current_axis_id = axis_id
        self.refresh_order()
        self.refresh_timeline()

    # ---------- 技能轴改名 ----------
    def _begin_rename(self, axis, e):
        cv = self.order_canvas
        order = self._order()
        try:
            idx = order.index(axis)
        except ValueError:
            return
        y = 2 + idx * AXIS_ROW_H
        self._end_rename()
        ent = tk.Entry(cv, bg=theme.PANEL_4, fg=theme.TEXT, relief="flat", bd=0,
                       highlightthickness=1, highlightbackground=theme.ACCENT,
                       insertbackground=theme.TEXT,
                       font=theme.font(theme.F_BODY, True))
        ent.insert(0, axis.name)
        ent.select_range(0, "end")
        cv.create_window(20, y + 14, window=ent, anchor="nw", width=LEFT_W - 120,
                         tags=("rename",))
        ent.focus_set()
        self._rename_entry = (ent, axis)

        def commit(_ev=None):
            txt = ent.get().strip()
            if txt and self._rename_entry and self._rename_entry[1] is axis:
                axis.name = txt
                self.store.save_axes()
            self._end_rename()
            self.refresh_all()
            self.app.rebuild_player()

        ent.bind("<Return>", commit)
        ent.bind("<FocusOut>", commit)
        ent.bind("<Escape>", lambda _e: self._end_rename())

    def _end_rename(self):
        if not self._rename_entry:
            return
        ent, _axis = self._rename_entry
        self._rename_entry = None
        try:
            ent.destroy()
        except tk.TclError:
            pass
        try:
            self.order_canvas.delete("rename")
        except tk.TclError:
            pass

    # ---------- 技能轴增删 ----------
    def new_axis(self):
        rot = self.current_rotation()
        axis = self.store.add_axis(ROLE_CHARGE)
        if rot:
            rot.charge_axes.append(axis.id)
            self.store.save_rotations()
        self.current_axis_id = axis.id
        self.refresh_all()
        self.app.rebuild_player()

    def delete_axis(self):
        axis = self.current_axis()
        if not axis:
            return
        if not messagebox.askyesno("删除技能轴", "确定删除「%s」？" % axis.name,
                                   parent=self.root):
            return
        self.store.delete_axis(axis.id)
        self.current_axis_id = self.store.axes[0].id if self.store.axes else None
        self.refresh_all()
        self.app.rebuild_player()

    def current_team(self):
        """当前编队的队伍。"""
        return self.store.rotation_team(self.current_rotation())

    def set_current_team(self, members):
        rot = self.current_rotation()
        if rot is None:
            self.store.team = Team(members=list(members))
            self.store.touch()
            return
        rot.team = Team(members=list(members))
        self.store.touch()

    # ---------- 队伍 ----------
    def refresh_team(self):
        cv = self.team_canvas
        cv.delete("all")
        members = self.current_team().normalized()
        if not self.selected_member:
            for m in members:
                if m:
                    self.selected_member = m
                    break
        x = 2
        for i, cn in enumerate(members):
            tag = "tm_%d" % i
            active = bool(cn) and cn == self.selected_member
            rounded_rect(cv, x, 4, x + TEAM_CARD_W, 4 + TEAM_CARD_H, r=10,
                         fill=theme.PANEL_3 if active else theme.PANEL_2,
                         outline=theme.ACCENT if active else theme.BORDER,
                         width=2 if active else 1, tags=(tag,))
            if cn:
                photo = self.icons.render_portrait(cn, 60)
                if photo is not None:
                    cv.create_image(x + TEAM_CARD_W / 2, 4 + 42, image=photo,
                                    tags=(tag,))
                cv.create_text(x + TEAM_CARD_W / 2, 4 + 82, text=cn, fill=theme.TEXT,
                               font=theme.font(theme.F_SMALL, True), tags=(tag,))
                elem = self.icons.element_of(cn)
                cv.create_text(x + TEAM_CARD_W / 2, 4 + 98,
                               text=theme.ELEMENT_CN.get(elem, elem),
                               fill=theme.TEXT_MUTED,
                               font=theme.font(theme.F_TINY), tags=(tag,))
            else:
                cv.create_text(x + TEAM_CARD_W / 2, 4 + 46, text="＋",
                               fill=theme.TEXT_MUTED, font=theme.font(26, True),
                               tags=(tag,))
                cv.create_text(x + TEAM_CARD_W / 2, 4 + 80, text="选择干员",
                               fill=theme.TEXT_MUTED,
                               font=theme.font(theme.F_TINY), tags=(tag,))
            cv.tag_bind(tag, "<Button-1>",
                        lambda e, idx=i: self._on_slot_press(idx))
            cv.tag_bind(tag, "<Double-Button-1>",
                        lambda e, idx=i: self._on_slot_change(idx))
            x += TEAM_CARD_W + 10

    def _on_slot_press(self, idx):
        """点一下选中；按住拖动则等松手时换位置（位置 = 按键 1~4）。"""
        members = self.current_team().normalized()
        cn = members[idx]
        if not cn:
            self._on_slot_change(idx)
            return
        if cn != self.selected_member:
            self.selected_member = cn
            self.refresh_team()
            self.refresh_skills()
        self._begin_drag({"type": "member", "index": idx}, cn)

    def _member_drop_index(self, e):
        """鼠标位置 -> 队伍插入下标（0..4）。"""
        pos = self._in_canvas(self.team_canvas, e)
        if pos is None:
            return None
        x, _y = pos
        for i in range(4):
            cx = 2 + i * (TEAM_CARD_W + 10) + TEAM_CARD_W / 2.0
            if x < cx:
                return i
        return 4

    def _draw_member_indicator(self, idx):
        cv = self.team_canvas
        cv.delete("drop_ind")
        if idx is None:
            return
        x = 2 + idx * (TEAM_CARD_W + 10) - 5
        cv.create_line(x, 10, x, 6 + TEAM_CARD_H, fill=theme.ACCENT, width=3,
                       tags=("drop_ind",))

    def _move_member(self, src, dst):
        """把第 src 位干员拖到 dst 之前（下标按移前算）。"""
        if dst is None:
            return False
        ms = self.current_team().normalized()
        if not (0 <= src < len(ms)) or not ms[src]:
            return False
        name = ms.pop(src)
        if dst > src:
            dst -= 1
        dst = max(0, min(int(dst), len(ms)))
        if dst == src:
            ms.insert(src, name)
            return False
        ms.insert(dst, name)
        self.set_current_team(ms[:4])
        self.refresh_team()
        self.refresh_skills()
        self.refresh_roster()
        self.refresh_order()
        self.refresh_timeline()
        self.app.rebuild_player()
        return True

    def _on_slot_change(self, idx):
        self._end_drag()
        members = self.current_team().normalized()
        used = [m for j, m in enumerate(members) if m and j != idx]

        def apply(cn):
            ms = self.current_team().normalized()
            ms[idx] = cn
            self.set_current_team(ms)
            self.selected_member = cn
            self.refresh_team()
            self.refresh_skills()
            self.refresh_roster()
            self.refresh_order()
            self.refresh_timeline()
    
        OperatorPicker(self.app, apply, current=members[idx], used=used)

    # ---------- 按键提示 ----------
    def key_hint(self, node):
        """返回该节点对应的按键提示文本。"""
        s = self.store.settings
        if node.kind == KIND_COMBO:
            return vk_label(s.combo_key) if s.combo_key else "—"
        members = self.current_team().normalized()
        try:
            slot = members.index(node.operator)
        except ValueError:
            return "—"
        digit = s.slot_key(slot)
        if digit is None:
            return "—"
        label = vk_label(digit)
        return ("长按 " + label) if node.kind == KIND_ULT else label

    def kind_key_hint(self, kind, operator=None):
        s = self.store.settings
        if kind == KIND_COMBO:
            return vk_label(s.combo_key) if s.combo_key else "—"
        members = self.current_team().normalized()
        op = operator or self.selected_member
        try:
            slot = members.index(op)
        except ValueError:
            return "—"
        digit = s.slot_key(slot)
        if digit is None:
            return "—"
        label = vk_label(digit)
        return ("长按 " + label) if kind == KIND_ULT else label

    # ---------- 技能 ----------
    def refresh_skills(self):
        cv = self.skill_canvas
        cv.delete("all")
        cn = self.selected_member
        if not cn:
            cv.create_text(6, 30, anchor="w", text="先在队伍里选干员",
                           fill=theme.TEXT_MUTED, font=theme.font(theme.F_SMALL))
            return
        files = self.icons.skills_of(cn)
        x = 2
        for kind in KINDS:
            file = files.get(kind, "")
            tag = "sk_%s" % kind
            rounded_rect(cv, x, 4, x + SKILL_CARD_W, 4 + SKILL_CARD_H, r=10,
                         fill=theme.PANEL_2, outline=theme.BORDER, tags=(tag,))
            photo = self.icons.render(file, 56) if file else None
            if photo is not None:
                cv.create_image(x + SKILL_CARD_W / 2, 4 + 36, image=photo, tags=(tag,))
            else:
                cv.create_text(x + SKILL_CARD_W / 2, 4 + 36, text="无图",
                               fill=theme.TEXT_MUTED,
                               font=theme.font(theme.F_TINY), tags=(tag,))
            cv.create_text(x + SKILL_CARD_W / 2, 4 + 76, text=KIND_CN[kind],
                           fill=theme.TEXT, font=theme.font(theme.F_SMALL, True),
                           tags=(tag,))
            cv.create_text(x + SKILL_CARD_W / 2, 4 + 92,
                           text=self.kind_key_hint(kind, cn),
                           fill=theme.ACCENT,
                           font=theme.font(theme.F_TINY), tags=(tag,))
            cv.tag_bind(tag, "<Button-1>",
                        lambda e, k=kind: self._skill_press(k))
            x += SKILL_CARD_W + 10

    def _skill_press(self, kind):
        if not self.selected_member:
            return
        self._begin_drag({"type": "new", "kind": kind}, KIND_CN[kind])

    # ---------- 技能轴 ----------
    def refresh_timeline(self):
        cv = self.timeline
        cv.delete("all")
        axis = self.current_axis()
        if not axis:
            cv.create_text(10, 20, anchor="nw", text="左侧新建一条技能轴",
                           fill=theme.TEXT_MUTED, font=theme.font(theme.F_SMALL))
            return

        color = theme.BURST if axis.role == ROLE_BURST else theme.CHARGE
        cv.create_rectangle(0, 0, 4000, 5, fill=color, outline="")

        x = 8
        y = 18
        for node in axis.nodes:
            self._node_card(cv, node, x, y)
            x += NODE_W + NODE_GAP

        # 放置区
        for sx0 in range(x, x + NODE_W, 12):
            cv.create_line(sx0, y, min(sx0 + 7, x + NODE_W), y, fill=theme.BORDER,
                           width=2)
            cv.create_line(sx0, y + NODE_H, min(sx0 + 7, x + NODE_W), y + NODE_H,
                           fill=theme.BORDER, width=2)
        for sy0 in range(y, y + NODE_H, 12):
            cv.create_line(x, sy0, x, min(sy0 + 7, y + NODE_H), fill=theme.BORDER,
                           width=2)
            cv.create_line(x + NODE_W, sy0, x + NODE_W, min(sy0 + 7, y + NODE_H),
                           fill=theme.BORDER, width=2)
        cv.create_text(x + NODE_W / 2, y + 44, text="＋", fill=theme.TEXT_DIM,
                       font=theme.font(16))
        cv.create_text(x + NODE_W / 2, y + 66, text="拖技能", fill=theme.TEXT_MUTED,
                       font=theme.font(theme.F_TINY))
        cv.create_text(x + NODE_W / 2, y + 78, text="到这里", fill=theme.TEXT_MUTED,
                       font=theme.font(theme.F_TINY))

        cv.configure(scrollregion=(0, 0, max(x + NODE_W + 24, cv.winfo_width()),
                                   NODE_H + 40))
        self.tl_title.configure(text="技能轴 · %s" % axis.name, fg=color)

    def _node_card(self, cv, node, x, y):
        tag = "nd_%s" % node.id
        rounded_rect(cv, x, y, x + NODE_W, y + NODE_H, r=10,
                     fill=theme.PANEL_2, outline=theme.BORDER, tags=(tag,))
        photo = self.icons.render(node.icon, 52) if node.icon else None
        if photo is not None:
            cv.create_image(x + NODE_W / 2, y + 34, image=photo, tags=(tag,))
        else:
            cv.create_text(x + NODE_W / 2, y + 34, text="无", fill=theme.TEXT_MUTED,
                           font=theme.font(theme.F_TINY), tags=(tag,))
        cv.create_text(x + NODE_W / 2, y + 70, text=node.operator[:6], fill=theme.TEXT,
                       font=theme.font(theme.F_SMALL, True), tags=(tag,))
        cv.create_text(x + NODE_W / 2, y + 86,
                       text="%s · %s" % (KIND_CN.get(node.kind, ""),
                                         self.key_hint(node)),
                       fill=theme.TEXT_MUTED, font=theme.font(theme.F_TINY), tags=(tag,))
        cv.tag_bind(tag, "<Button-1>", lambda e, n=node: self._node_press(n, e))

    def _node_press(self, node, e):
        self._begin_drag({"type": "move", "node": node}, node.operator or "节点")

    def _select_node(self, node_id):
        pass

    def add_node(self, operator, kind, index=None):
        axis = self.current_axis()
        if not axis or not operator:
            return
        file = self.icons.icon_for(operator, kind) or ""
        node = Node(operator=operator, kind=kind, icon=file)
        if index is None:
            axis.nodes.append(node)
        else:
            axis.nodes.insert(max(0, min(index, len(axis.nodes))), node)
        self.store.save_axes()
        self.refresh_timeline()

    def duplicate_node(self):
        axis = self.current_axis()
        if not axis or not axis.nodes:
            return
        clone = copy.deepcopy(axis.nodes[-1])
        clone.id = Node().id
        axis.nodes.append(clone)
        self.store.save_axes()
        self.refresh_timeline()

    def delete_node(self):
        axis = self.current_axis()
        if not axis or not axis.nodes:
            return
        axis.nodes.pop()
        self.store.save_axes()
        self.refresh_timeline()

    # ---------- 拖拽 ----------
    def _begin_drag(self, payload, label):
        self._end_drag()
        self._drag = dict(payload)
        self._drag["moved"] = False
        self._pending_drop = None
        try:
            ghost = tk.Toplevel(self.root)
            ghost.overrideredirect(True)
            ghost.attributes("-topmost", True)
            ghost.configure(bg=theme.ACCENT)
            tk.Label(ghost, text=label, bg=theme.PANEL_3, fg=theme.TEXT,
                     font=theme.font(theme.F_SMALL),
                     padx=dpi.S(10), pady=dpi.S(6)).pack(padx=dpi.S(2),
                                                         pady=dpi.S(2))
            ghost.geometry("+%d+%d" % (self.root.winfo_pointerx() + dpi.S(12),
                                       self.root.winfo_pointery() + dpi.S(8)))
            self._ghost = ghost
        except tk.TclError:
            self._ghost = None
        self.root.bind_all("<B1-Motion>", self._drag_motion, add="+")
        self.root.bind_all("<ButtonRelease-1>", self._drag_release, add="+")

    def _drag_motion(self, e):
        if not self._drag:
            return
        self._drag["moved"] = True
        if self._ghost is not None:
            try:
                self._ghost.geometry("+%d+%d" % (e.x_root + dpi.S(12),
                                          e.y_root + dpi.S(8)))
            except tk.TclError:
                self._ghost = None
        if self._drag.get("type") == "reorder":
            self._pending_drop = self._order_drop_index(e)
            self._draw_reorder_indicator(self._pending_drop)
        elif self._drag.get("type") == "rot":
            self._pending_drop = self._rot_drop_index(e)
            self._draw_rot_indicator(self._pending_drop)
        elif self._drag.get("type") == "member":
            self._pending_drop = self._member_drop_index(e)
            self._draw_member_indicator(self._pending_drop)
        else:
            self._pending_drop = self._timeline_drop_index(e)
            self._draw_drop_indicator(self._pending_drop)

    def _in_canvas(self, cv, e):
        try:
            rx, ry = cv.winfo_rootx(), cv.winfo_rooty()
            rw, rh = cv.winfo_width(), cv.winfo_height()
        except tk.TclError:
            return None
        x, y = dpi.unS(e.x_root - rx), dpi.unS(e.y_root - ry)
        if 0 <= x <= rw and 0 <= y <= rh:
            return x, y
        return None

    def _order_drop_index(self, e):
        pos = self._in_canvas(self.order_canvas, e)
        if pos is None:
            return None
        _x, y = pos
        idx = int((y - 2 + AXIS_ROW_H / 2) // AXIS_ROW_H)
        return max(0, min(idx, len(self._order())))

    def _timeline_drop_index(self, e):
        pos = self._in_canvas(self.timeline, e)
        if pos is None:
            return None
        x, _y = pos
        axis = self.current_axis()
        total = len(axis.nodes) if axis else 0
        idx = int((x - 8 + (NODE_W + NODE_GAP) / 2) // (NODE_W + NODE_GAP))
        return max(0, min(idx, total))

    def _draw_reorder_indicator(self, idx):
        cv = self.order_canvas
        cv.delete("drop_ind")
        if idx is None:
            return
        y = 2 + idx * AXIS_ROW_H - 3
        cv.create_line(6, y, LEFT_W - 10, y, fill=theme.ACCENT, width=3,
                       tags=("drop_ind",))

    def _draw_drop_indicator(self, idx):
        cv = self.timeline
        cv.delete("drop_ind")
        if idx is None:
            return
        x = 8 + idx * (NODE_W + NODE_GAP) - NODE_GAP / 2
        cv.create_line(x, 16, x, 18 + NODE_H, fill=theme.ACCENT, width=3,
                       tags=("drop_ind",))

    def _drag_release(self, e):
        drag = self._drag
        if not drag:
            return
        idx = self._pending_drop
        moved = drag.get("moved")
        self._end_drag()

        if drag.get("type") == "reorder":
            if not moved or idx is None:
                return
            self._reorder_axis(drag["axis"], idx)
            return

        if drag.get("type") == "rot":
            if not moved or idx is None:
                return
            self._reorder_rotation(drag["rotation"], idx)
            return

        if drag.get("type") == "member":
            if not moved or idx is None:
                return
            self._move_member(drag["index"], idx)
            return

        if not moved:
            if drag.get("type") == "new":
                self.add_node(self.selected_member, drag["kind"])
            return

        if drag.get("type") == "new":
            if idx is not None:
                self.add_node(self.selected_member, drag["kind"], idx)
        elif drag.get("type") == "move":
            node = drag["node"]
            if idx is None:
                self._remove_node(node)
            else:
                self._move_node(node, idx)

    def _end_drag(self):
        self._drag = None
        self._pending_drop = None
        if self._ghost is not None:
            try:
                self._ghost.destroy()
            except tk.TclError:
                pass
            self._ghost = None
        try:
            self.root.unbind_all("<B1-Motion>")
            self.root.unbind_all("<ButtonRelease-1>")
        except tk.TclError:
            pass
        for cv in (self.timeline, self.order_canvas, self.rot_canvas,
                   self.team_canvas):
            try:
                cv.delete("drop_ind")
            except tk.TclError:
                pass

    def _reorder_axis(self, axis, idx):
        rot = self.current_rotation()
        if not rot or axis.role == ROLE_BURST:
            return
        if axis.id not in rot.charge_axes:
            return
        charges = list(rot.charge_axes)
        old = charges.index(axis.id)
        charges.remove(axis.id)
        if idx > old:
            idx -= 1
        idx = max(0, min(idx, len(charges)))
        charges.insert(idx, axis.id)
        rot.charge_axes = charges
        self.store.save_rotations()
        self.refresh_order()
        self.app.rebuild_player()

    def _move_node(self, node, idx):
        axis = self.current_axis()
        if not axis or node not in axis.nodes:
            return
        old = axis.nodes.index(node)
        axis.nodes.remove(node)
        if idx > old:
            idx -= 1
        idx = max(0, min(idx, len(axis.nodes)))
        axis.nodes.insert(idx, node)
        self.store.save_axes()
        self.refresh_timeline()

    def _remove_node(self, node):
        axis = self.current_axis()
        if not axis or node not in axis.nodes:
            return
        axis.nodes.remove(node)
        self.store.save_axes()
        self.refresh_timeline()

    # ---------- 导入导出 ----------
    def do_export(self):
        path = filedialog.asksaveasfilename(
            parent=self.root, title="导出配置", defaultextension=".json",
            initialfile="终末地技能轴.json",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.store.export_dict(), f, ensure_ascii=False, indent=2)
        except OSError as e:
            messagebox.showerror("导出失败", str(e), parent=self.root)
            return
        messagebox.showinfo("导出成功", "已保存到：\n%s" % path, parent=self.root)

    def do_import(self):
        path = filedialog.askopenfilename(
            parent=self.root, title="导入配置",
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            messagebox.showerror("读取失败", str(e), parent=self.root)
            return
        merge = messagebox.askyesno(
            "导入方式", "要把导入的内容追加到现有配置里吗？\n\n是 = 追加\n否 = 替换全部",
            parent=self.root)
        ok, msg = self.store.import_dict(data, merge=merge)
        if not ok:
            messagebox.showerror("导入失败", msg, parent=self.root)
            return
        self.current_axis_id = self.store.axes[0].id if self.store.axes else None
        self.refresh_all()
        self.app.rebuild_player()
        messagebox.showinfo("导入成功", msg, parent=self.root)
