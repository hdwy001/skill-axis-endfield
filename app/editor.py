# -*- coding: utf-8 -*-
"""编辑器：左侧技能轴顺序 / 中间队伍 + 技能 + 技能轴。"""
import copy
import json
import os
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from . import dragfx, forms, theme
from .brand import APP_SUB, APP_TITLE, icon_png
from .keys import vk_label
from .menu import NiceMenu
from .model import (KIND_BRANCH, KIND_CN, KIND_COMBO, KIND_SKILL, KINDS, KIND_ULT,
                    ROLE_BURST, ROLE_CHARGE, ROLE_CN, ROLE_ROUTE, Axis, Node, Team,
                    assign_member, move_item, next_numbered_name,
                    unique_name)
from .opspicker import OperatorPicker
from .textdialog import ask_text
from .widgets import center_window, rounded_rect

# 布局
LEFT_W = 316
AXIS_ROW_H = 56
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
                     font=theme.font(theme.F_SMALL), padx=12, pady=5)


def _section(parent, title, sub=None):
    f = tk.Frame(parent, bg=theme.BG)
    tk.Label(f, text=title, bg=theme.BG, fg=theme.TEXT,
             font=theme.font(theme.F_SECTION, True)).pack(side="left")
    if sub:
        tk.Label(f, text=sub, bg=theme.BG, fg=theme.TEXT_MUTED,
                 font=theme.font(theme.F_TINY)).pack(side="left", padx=(8, 0))
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
        self._ghost_photo = None
        self._pending_drop = None
        self._arm_job = None
        self._rename_entry = None

        self._build()
        # 每个 canvas 一个动画器：同时只跑一条，避免多条 after 循环叠加把卡片甩飞
        self._anim_team = dragfx.Animator(self.root, self.team_canvas)
        self._anim_timeline = dragfx.Animator(self.root, self.timeline)
        self._anim_order = dragfx.Animator(self.root, self.order_canvas)
        if self.store.axes:
            self.current_axis_id = self.store.axes[0].id
        self.refresh_all()

    # ================= 骨架 =================
    def _build(self):
        self.root.configure(bg=theme.BG)
        self._build_header()

        body = tk.Frame(self.root, bg=theme.BG)
        body.pack(fill="both", expand=True, padx=14, pady=(10, 12))

        self.left = tk.Frame(body, bg=theme.BG, width=LEFT_W)
        self.left.pack(side="left", fill="y")
        self.left.pack_propagate(False)

        self.center = tk.Frame(body, bg=theme.BG)
        self.center.pack(side="left", fill="both", expand=True, padx=(12, 0))

        self._build_left()
        self._build_center()

    def _resize_brand(self, avail):
        """图标/字号随左上角高度自适应（保持图标原比例，不拉伸）。"""
        try:
            win_w = int(self.root.winfo_width())
        except tk.TclError:
            win_w = 1200
        # 跟窗口宽度走：窄窗小一点、宽窗大一点，但不超出标题行
        h = int(max(22, min(34, win_w / 48.0)))
        if avail:
            h = min(h, max(20, int(avail)))
        if abs(h - getattr(self, "_brand_h", 0)) < 1 and self._brand_photo:
            return
        self._brand_h = h
        path = icon_png()
        try:
            from PIL import Image, ImageTk
            im = Image.open(path).convert("RGBA")
            im.thumbnail((h * 3, h * 3), Image.LANCZOS)   # 3x 供高 DPI
            photo = ImageTk.PhotoImage(im.resize((h, h), Image.LANCZOS))
            self._brand_photo = photo
            self.brand_icon.configure(image=photo, width=h, height=h)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.brand_name.configure(font=theme.font(max(11, int(h * 0.52)), True))
        except tk.TclError:
            pass

    def _build_header(self):
        head = tk.Frame(self.root, bg=theme.BG_2)
        head.pack(fill="x")

        title = tk.Frame(head, bg=theme.BG_2)
        title.pack(side="left", padx=20, pady=(10, 10))

        # 左上角：图标 + 软件名（图标按行高自适应，保持原比例不拉伸）
        brand = tk.Frame(title, bg=theme.BG_2)
        brand.pack(anchor="w")
        self.brand_icon = tk.Label(brand, bg=theme.BG_2, bd=0,
                                   highlightthickness=0)
        self.brand_icon.pack(side="left", padx=(0, 10))
        self.brand_name = tk.Label(brand, text=APP_TITLE, bg=theme.BG_2,
                                   fg=theme.TEXT, font=theme.font(theme.F_TITLE, True))
        self.brand_name.pack(side="left")
        tk.Label(title, text=APP_SUB, bg=theme.BG_2,
                 fg=theme.TEXT_MUTED, font=theme.font(theme.F_TINY)).pack(anchor="w",
                                                                        pady=(2, 0))
        self._brand_photo = None
        self._brand_h = 0
        brand.bind("<Configure>", lambda e: self._resize_brand(e.height))
        self.root.bind("<Configure>", lambda e: self._resize_brand(title.winfo_height() - 14),
                       add="+")
        self.root.after(30, lambda: self._resize_brand(title.winfo_height() - 14))

        right = tk.Frame(head, bg=theme.BG_2)
        right.pack(side="right", padx=18, pady=16)

        # 权限状态：非管理员时提示（游戏里收不到按键多半是这个原因）
        self.perm_label = tk.Label(head, bg=theme.BG_2, cursor="hand2",
                                   font=theme.font(theme.F_TINY))
        self.perm_label.pack(side="right", padx=(0, 14))
        self.perm_label.bind("<Button-1>", lambda e: self._on_perm_click())
        self._refresh_perm_label()

        _btn(right, "打开悬浮窗", self.app.show_overlay, "primary").pack(side="left", padx=4)
        _btn(right, "按键测试", self.app.open_test_panel, "ghost").pack(side="left", padx=4)
        _btn(right, "导入", self.do_import, "ghost").pack(side="left", padx=4)
        _btn(right, "导出", self.do_export, "ghost").pack(side="left", padx=4)
        _btn(right, "检查更新", self.app.open_update, "ghost").pack(side="left", padx=4)
        _btn(right, "设置", self.open_settings, "ghost").pack(side="left", padx=4)

        tk.Frame(self.root, bg=theme.BORDER, height=1).pack(fill="x")

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
        tk.Label(wrap, text="编队", bg=theme.BG, fg=theme.TEXT,
                 font=theme.font(theme.F_SECTION, True)).pack(anchor="w", pady=(4, 6))

        sel = tk.Frame(wrap, bg=theme.BG)
        sel.pack(fill="x")
        self.rot_btn = tk.Button(sel, text="—  ▾", bg=theme.PANEL_2, fg=theme.TEXT,
                                 activebackground=theme.PANEL_3,
                                 activeforeground=theme.TEXT, relief="flat", bd=0,
                                 highlightthickness=1,
                                 highlightbackground=theme.BORDER,
                                 cursor="hand2", anchor="w",
                                 font=theme.font(theme.F_BODY),
                                 command=self._open_rotation_menu,
                                 padx=10, pady=4)
        self.rot_btn.pack(side="left", fill="x", expand=True)
        _btn(sel, "改名", self.rename_rotation, "ghost").pack(side="left", padx=(6, 0))

        # 队伍阵容头像（整个编队共用）
        self.roster_canvas = tk.Canvas(wrap, bg=theme.BG, highlightthickness=0,
                                       bd=0, height=AVATAR + 12)
        self.roster_canvas.pack(fill="x", pady=(8, 0))

        head = tk.Frame(wrap, bg=theme.BG)
        head.pack(fill="x", pady=(10, 4))
        tk.Label(head, text="技能轴顺序", bg=theme.BG, fg=theme.TEXT_DIM,
                 font=theme.font(theme.F_TINY)).pack(side="left")
        tk.Label(head, text="双击改名 · 拖动整行排序", bg=theme.BG,
                 fg=theme.TEXT_MUTED, font=theme.font(theme.F_TINY)).pack(side="right")

        self.order_canvas = tk.Canvas(wrap, bg=theme.BG, highlightthickness=0, bd=0)
        self.order_canvas.pack(fill="both", expand=True)

        btns = tk.Frame(wrap, bg=theme.BG)
        btns.pack(fill="x", pady=(8, 2))

        self.save_label = tk.Label(btns, text=self._last_save_text(),
                                   bg=theme.BG, fg=theme.TEXT_MUTED,
                                   font=theme.font(theme.F_TINY), anchor="w")
        self.save_label.pack(fill="x", pady=(0, 4))

        grid = tk.Frame(btns, bg=theme.BG)
        grid.pack(fill="x", pady=2)
        grid.columnconfigure(0, weight=1, uniform="btn")
        grid.columnconfigure(1, weight=1, uniform="btn")

        _btn(grid, "＋ 新建（选类型）", self.new_axis_menu, "ghost").grid(
            row=0, column=0, sticky="ew", padx=(0, 3), pady=3)
        _btn(grid, "＋ 新建编队", self.new_rotation, "ghost").grid(
            row=0, column=1, sticky="ew", padx=(3, 0), pady=3)
        _btn(grid, "删除此技能轴", self.delete_axis, "danger").grid(
            row=1, column=0, sticky="ew", padx=(0, 3), pady=3)
        _btn(grid, "删除编队", self.delete_rotation, "danger").grid(
            row=1, column=1, sticky="ew", padx=(3, 0), pady=3)

    # ---------- 中间 ----------
    def _build_center(self):
        c = self.center

        team_wrap = tk.Frame(c, bg=theme.PANEL, padx=14, pady=12)
        team_wrap.pack(fill="x")
        _section(team_wrap, "队伍", "单击选中 · 双击更换 · 拖动换位").pack(fill="x")
        self.team_canvas = tk.Canvas(team_wrap, bg=theme.PANEL, highlightthickness=0,
                                     bd=0, height=TEAM_CARD_H + 8)
        self.team_canvas.pack(fill="x", pady=(8, 0))
        self.team_canvas.bind("<ButtonPress-1>", self._team_press)
        self.team_canvas.bind("<Double-Button-1>", self._team_double)

        skill_wrap = tk.Frame(c, bg=theme.PANEL, padx=14, pady=12)
        skill_wrap.pack(fill="x", pady=(10, 0))
        _section(skill_wrap, "战技 / 连携 / 终结",
                 "拖到下方技能轴，或点一下加到末尾").pack(fill="x")
        self.skill_canvas = tk.Canvas(skill_wrap, bg=theme.PANEL, highlightthickness=0,
                                      bd=0, height=SKILL_CARD_H + 8)
        self.skill_canvas.pack(fill="x", pady=(8, 0))

        tl_wrap = tk.Frame(c, bg=theme.BG)
        tl_wrap.pack(fill="both", expand=True, pady=(10, 0))
        head = tk.Frame(tl_wrap, bg=theme.BG)
        head.pack(fill="x")
        self.tl_title = tk.Label(head, text="技能轴", bg=theme.BG, fg=theme.TEXT,
                                 font=theme.font(theme.F_SECTION, True))
        self.tl_title.pack(side="left")
        tk.Label(head, text="拖动节点改顺序 · 拖出删除", bg=theme.BG,
                 fg=theme.TEXT_MUTED, font=theme.font(theme.F_TINY)).pack(side="left",
                                                                        padx=10)

        # 「这条轴走几遍」：只对充能轴有意义，爆发轴固定 1
        self.repeat_box = tk.Frame(head, bg=theme.BG)
        self.repeat_box.pack(side="left", padx=(6, 0))
        tk.Label(self.repeat_box, text="循环", bg=theme.BG, fg=theme.TEXT_MUTED,
                 font=theme.font(theme.F_TINY)).pack(side="left")
        self.repeat_minus = _btn(self.repeat_box, "－",
                                 lambda: self.bump_repeat(-1), "ghost")
        self.repeat_minus.pack(side="left", padx=(6, 0))
        self.repeat_label = tk.Label(self.repeat_box, text="×1", bg=theme.BG,
                                     fg=theme.ACCENT,
                                     font=theme.font(theme.F_SMALL, True), width=4)
        self.repeat_label.pack(side="left")
        self.repeat_plus = _btn(self.repeat_box, "＋",
                                lambda: self.bump_repeat(1), "ghost")
        self.repeat_plus.pack(side="left")

        _btn(head, "＋ 分支点", self.add_branch_node, "ghost").pack(side="right", padx=3)
        _btn(head, "复制节点", self.duplicate_node, "ghost").pack(side="right", padx=3)
        _btn(head, "删除节点", self.delete_node, "danger").pack(side="right", padx=3)

        tl_row = tk.Frame(tl_wrap, bg=theme.BG_2)
        tl_row.pack(fill="both", expand=True, pady=(6, 0))
        self.timeline = tk.Canvas(tl_row, bg=theme.BG_2, highlightthickness=0, bd=0,
                                  height=NODE_H + 40)
        self.tl_scroll = tk.Scrollbar(tl_row, command=self.timeline.yview,
                                      bg=theme.BG_2, troughcolor=theme.PANEL_2,
                                      relief="flat")
        self.timeline.configure(yscrollcommand=self.tl_scroll.set)
        self.timeline.pack(side="left", fill="both", expand=True)
        self.tl_scroll.pack(side="right", fill="y")
        self.timeline.bind("<MouseWheel>", self._timeline_wheel)
        self.timeline.bind("<Configure>", lambda e: self._clamp_timeline_scroll())
        # 注意：不要在这里绑「点空白收起分支」——它会先于松手执行，
        # 导致点菱形时先收起再展开，永远关不上。开合只由菱形自己切换。

        # 分支展开状态：存的是当前展开的分支节点 id（点菱形切换）
        self._expanded_branch = None

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
        """当前编队的播放顺序：按 rot.order，充能轴/爆发轴混排。"""
        rot = self.current_rotation()
        if not rot:
            return []
        out = [self.store.axis_by_id(i) for i in rot.sequence()]
        return [a for a in out if a is not None]

    def _set_order(self, ids):
        rot = self.current_rotation()
        if rot is None:
            return
        rot.set_sequence(ids)
        rot.sync_legacy(self.store.axis_by_id)
        self.store.save_rotations()

    # ---------- 编队 ----------
    def refresh_rotation(self):
        rot = self.current_rotation()
        try:
            self.rot_btn.configure(text="%s  ▾" % (rot.name if rot else "—"))
        except tk.TclError:
            pass

    def _open_rotation_menu(self):
        items = [(r.name, r.name) for r in self.store.rotations]
        NiceMenu(self.root, items, self._pick_rotation, width=260,
                 anchor=(self.rot_btn.winfo_rootx(),
                         self.rot_btn.winfo_rooty() + self.rot_btn.winfo_height() + 4))

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

    def rename_rotation(self):
        rot = self.current_rotation()
        if not rot:
            return
        name = ask_text(self.app, "编队改名", "编队名称", rot.name)
        if not name:
            return
        rot.name = name
        self.store.touch()
        self.refresh_rotation()

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
        default_name = next_numbered_name([r.name for r in self.store.rotations],
                                         "编队")
        name = ask_text(self.app, "新建编队", "给这个编队起个名字",
                        default_name, ok_text="创建")
        if not name:
            name = default_name
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

    # ---------- 技能轴顺序 ----------
    def refresh_order(self):
        cv = self.order_canvas
        self._anim_order.cancel()
        cv.delete("all")
        order = self._order()
        if not order:
            cv.create_text(6, 24, anchor="w",
                           text="还没有技能轴，点下面「＋ 新建」",
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

        if is_burst:
            burst_no = [a for a in self._order() if a.role == ROLE_BURST]
            badge = ("爆发轴 %d/%d" % (burst_no.index(axis) + 1, len(burst_no))
                     if len(burst_no) > 1 else "爆发轴")
        else:
            badge = "充能轴 %d/%d" % (
                charge_ids.index(axis.id) + 1 if axis.id in charge_ids else idx + 1,
                len(charge_ids))
        if axis.repeat_count() > 1:
            badge += " · ×%d" % axis.repeat_count()
        bw = theme.font(theme.F_TINY, True).measure(badge) + 18
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
        self.close_branch_panel()      # 切轴就收起分支设置
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
    def new_axis(self, role=ROLE_CHARGE):
        """新建轴：先让用户填名字，填了才创建。"""
        prefix = "充能轴" if role == ROLE_CHARGE else "爆发轴"
        default = next_numbered_name(
            [a.name for a in self.store.axes if a.role == role], prefix)
        name = ask_text(self.app, "新建技能轴", "给这条技能轴起个名字",
                        default, ok_text="创建")
        if not name or not name.strip():
            return
        name = name.strip()
        if any(a.name == name for a in self.store.axes):
            name = unique_name([a.name for a in self.store.axes], name)
        rot = self.current_rotation()
        axis = self.store.add_axis(role, name)
        if rot:
            ids = rot.sequence()
            ids.append(axis.id)
            self._set_order(ids)
        self.current_axis_id = axis.id
        self.refresh_all()
        self.app.rebuild_player()

    def new_axis_menu(self):
        """「＋ 新建」：选建充能轴还是爆发轴（自绘菜单）。"""
        NiceMenu(self.root, [
            ("充能轴", ROLE_CHARGE),
            ("爆发轴", ROLE_BURST),
        ], lambda role: self.new_axis(role))

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
        self._anim_team.cancel()      # 先停动画，免得旧动画去搬重建出来的同名 tag
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
                         width=2 if active else 1,
                         tags=(tag, "tmrect_%d" % i))
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
                        lambda e, idx=i: self._on_slot_select(idx))
            x += TEAM_CARD_W + 10

    def _team_double(self, e):
        """双击换人。用坐标算位置：refresh_team 会重建 item，按 item 绑定会失手。"""
        idx = self._team_index_at(e.x, e.y)
        if idx is None:
            return
        self._on_slot_change(idx)

    def _on_slot_select(self, idx):
        cn = self.current_team().normalized()[idx]
        if not cn:
            self._on_slot_change(idx)
            return
        self.selected_member = cn
        self.refresh_team()
        self.refresh_skills()

    # ---------- 队伍拖拽换位（插入式：拖过去整体挪位） ----------
    def _team_index_at(self, x, y):
        """canvas 坐标 -> 队伍位（0~3）；落在卡片区外返回 None。"""
        if y is None or not (0 <= y <= TEAM_CARD_H + 8):
            return None
        total = 2 + TEAM_CARD_W * 4 + 10 * 3
        if x < 0 or x > total + 10:
            return None
        idx = int((x - 2) // (TEAM_CARD_W + 10))
        if idx < 0:
            return None
        return min(3, idx)

    def _team_gap_at(self, x, y):
        """canvas 坐标 -> 插入缝（0~4）。缝 i 表示「插到第 i 张卡前面」。"""
        if y is None or not (0 <= y <= TEAM_CARD_H + 8):
            return None
        total = 2 + TEAM_CARD_W * 4 + 10 * 3
        if x < 0 or x > total + 10:
            return None
        # 每张卡的中心把区间分成 4 段，边界就是缝
        center = 2 + TEAM_CARD_W / 2.0
        idx = 0
        while idx < 4 and x > center + idx * (TEAM_CARD_W + 10):
            idx += 1
        return idx

    def _team_ghost_image(self, cn):
        try:
            return self.icons.render_portrait(cn, 56)
        except Exception:  # noqa: BLE001
            return None

    def _team_press(self, e):
        idx = self._team_index_at(e.x, e.y)
        if idx is None:
            return
        cn = self.current_team().normalized()[idx]
        if not cn:
            return                    # 空位没有东西可拖，交给单击开选择器
        self._begin_drag({"type": "team", "from": idx}, cn,
                         image=self._team_ghost_image(cn))

    # ---------- 拖动时的实时让位 ----------
    def _preview_shift(self, anim, items, from_idx, gap, tag_of, base, step,
                       vertical=False, fixed=4):
        """拖动中预演落点：被拖的隐藏，其余整体挪开/收回。

        偏移量在 dragfx 上膛时已量好（bbox 与理论位置的固有差），
        所以来回拖动都能准确回到原位。
        """
        if not items:
            return
        if gap is None:
            gap = from_idx
        try:
            preview = move_item(items, from_idx, gap)
        except (TypeError, ValueError):
            return

        offs = (self._drag or {}).get("offs") or {}
        targets = []
        for i, it in enumerate(items):
            if i == from_idx:
                continue
            try:
                j = preview.index(it)
            except ValueError:
                continue
            tag = tag_of(i, it)
            off = offs.get(tag, (0, 0))
            if isinstance(off, (int, float)):
                ox, oy = off, 0
            else:
                ox, oy = off
            pos = base + j * step + (oy if vertical else ox)
            targets.append((tag, fixed, pos) if vertical else (tag, pos, fixed))
        anim.move_to(targets)

    def _preview_new_target(self, target):
        """技能栏拖进来的实时预览：主线让位 / 分支行让位 / 触发卡不动。

        每次都给**所有**主轴与分支卡片算目标，来回拖也不会留下上次的残影。
        """
        axis = self.current_axis()
        if axis is None:
            return
        step = NODE_W + NODE_GAP
        row_start = 10 + NODE_W + NODE_GAP
        offs = (self._drag or {}).get("offs") or {}
        targets = []

        def add(tag, x, y):
            off = offs.get(tag, (0, 0))
            ox, oy = off if isinstance(off, tuple) else (off, 0)
            targets.append((tag, x + ox, y + oy))

        main_idx = target[1] if target and target[0] == "main" else None
        b_oi = target[1] if target and target[0] == "branch" else None
        b_gap = target[2] if target and target[0] == "branch" else None

        for i, node in enumerate(axis.nodes):
            j = i + (1 if main_idx is not None and i >= main_idx else 0)
            add("nd_%s" % node.id, 8 + j * step, 18)

        geom = self._branch_row_geometry()
        for oi, opt in enumerate(self._branch_option_list()):
            ry = geom.get(oi, (18 + NODE_H + 18, 0))[0]
            for j, node in enumerate(opt.get("nodes") or []):
                k = j + (1 if b_oi == oi and j >= b_gap else 0)
                add("br_%d_%d" % (oi, j), row_start + k * step, ry)

        # 末尾虚线框也跟着走：往主线插一张，它整体右移一格
        last_branch = bool(axis.nodes and
                           getattr(axis.nodes[-1], "kind", "") == KIND_BRANCH)
        slot_x = 8 + (len(axis.nodes) - (1 if last_branch else 0)) * step
        if main_idx is not None:
            slot_x += step
        targets.append(("tl_slot", slot_x, 18))
        self._anim_timeline.move_to(targets)

    def _preview_insert(self, anim, count, gap, tag_of, base, step, fixed=18):
        """新项目要插进来：gap 之后的项目整体后移一格，腾出位置。"""
        if gap is None:
            return
        gap = max(0, min(int(gap), count))
        offs = self._drag.setdefault("offs", {})
        if not offs:
            for i in range(count):
                tag = tag_of(i)
                try:
                    box = anim.canvas.bbox(tag)
                except tk.TclError:
                    continue
                if box:
                    offs[tag] = box[0] - (base + i * step)
        targets = []
        for i in range(count):
            if i < gap:
                continue
            tag = tag_of(i)
            off = offs.get(tag, (0, 0))
            ox = off[0] if isinstance(off, tuple) else off
            targets.append((tag, base + (i + 1) * step + ox, fixed))
        anim.move_to(targets)

    def _hide_dragged(self, cv, tag):
        try:
            cv.itemconfigure(tag, state="hidden")
            return True
        except tk.TclError:
            return False

    def _team_drop(self, from_slot, gap, members_before):
        """松手：把卡片插进 gap 这条缝。拖动时已经让好位了，这里只落数据。"""
        new_members = move_item(members_before, from_slot, gap)
        if new_members == members_before:
            self.refresh_team()
            return
        self.set_current_team(new_members)
        self._after_team_change()

    def _after_team_change(self):
        if self.selected_member and \
                self.selected_member not in self.current_team().normalized():
            self.selected_member = ""
        self.refresh_team()
        self.refresh_skills()
        self.refresh_roster()
        self.refresh_order()
        self.refresh_timeline()

    def _assign_slot(self, idx, cn):
        """把 cn 放进第 idx 位；已在队伍别的位置就互换，绝不出现重复。"""
        members = assign_member(self.current_team().normalized(), idx, cn)
        self.set_current_team(members)
        self.selected_member = cn
        self._after_team_change()

    def _on_slot_change(self, idx):
        members = self.current_team().normalized()
        used = [m for j, m in enumerate(members) if m and j != idx]

        def apply(cn):
            self._assign_slot(idx, cn)

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
        files = self.icons.forms_of(cn)
        x = 2
        for kind in KINDS:
            stages = max(forms.stages(cn, kind), len(files.get(kind, [])))
            for stage in range(1, stages + 1):
                file = self.icons.icon_for(cn, kind, stage)
                tag = "sk_%s_%d" % (kind, stage)
                label = self._form_label(cn, kind, stage, stages)
                rounded_rect(cv, x, 4, x + SKILL_CARD_W, 4 + SKILL_CARD_H, r=10,
                             fill=theme.PANEL_2, outline=theme.BORDER, tags=(tag,))
                photo = self.icons.render(file, 56) if file else None
                if photo is not None:
                    cv.create_image(x + SKILL_CARD_W / 2, 4 + 36, image=photo,
                                    tags=(tag,))
                else:
                    cv.create_text(x + SKILL_CARD_W / 2, 4 + 36, text="无图",
                                   fill=theme.TEXT_MUTED,
                                   font=theme.font(theme.F_TINY), tags=(tag,))
                cv.create_text(x + SKILL_CARD_W / 2, 4 + 76, text=label,
                               fill=theme.TEXT, font=theme.font(theme.F_SMALL, True),
                               tags=(tag,))
                cv.create_text(x + SKILL_CARD_W / 2, 4 + 92,
                               text=self.kind_key_hint(kind, cn),
                               fill=theme.ACCENT,
                               font=theme.font(theme.F_TINY), tags=(tag,))
                cv.tag_bind(tag, "<Button-1>",
                            lambda e, k=kind, st=stage: self._skill_press(k, st))
                x += SKILL_CARD_W + 10

    def _skill_press(self, kind, stage=1):
        if not self.selected_member:
            return
        self._begin_drag({"type": "new", "kind": kind, "stage": stage},
                         self._stage_label(kind, stage))

    def _stage_label(self, kind, stage):
        n = self._stage_count(self.selected_member, kind)
        return self._form_label(self.selected_member, kind, stage, n)

    def _form_label(self, operator, kind, stage, stages=None):
        """技能卡/节点的显示名：优先用 forms.json 里登记的名字。"""
        base = KIND_CN.get(kind, "战技")
        name = forms.label_for(operator, kind, stage, fallback="")
        if name:
            return name
        n = stages if stages is not None else self._stage_count(operator, kind)
        return base if n <= 1 else "%s %s" % (base, forms.stage_suffix(stage))

    def _stage_count(self, operator, kind):
        files = self.icons.forms_of(operator).get(kind, [])
        return max(forms.stages(operator, kind), len(files))

    # ---------- 技能轴 ----------
    # ---------- 单条技能轴循环次数 ----------
    def bump_repeat(self, delta):
        axis = self.current_axis()
        if axis is None or axis.role != ROLE_CHARGE:
            return
        axis.repeat = max(1, min(99, axis.repeat_count() + delta))
        self.store.save_axes()
        self._sync_repeat_controls(axis)
        self.refresh_order()
        self.app.refresh_overlay()

    def _sync_repeat_controls(self, axis):
        if axis is None:
            return
        is_charge = axis.role == ROLE_CHARGE
        n = axis.repeat_count() if is_charge else 1
        try:
            self.repeat_label.configure(
                text=("×%d" % n) if is_charge else "×1",
                fg=theme.ACCENT if (is_charge and n > 1) else theme.TEXT_MUTED)
            state = "normal" if is_charge else "disabled"
            self.repeat_minus.configure(state=state)
            self.repeat_plus.configure(state=state)
        except tk.TclError:
            pass

    def _clamp_timeline_scroll(self):
        """窗口尺寸变化时把滚动区域收紧，别留可上滑的空白。"""
        cv = self.timeline
        content = getattr(self, "_timeline_content_h", 0) or 0
        try:
            width = float(str(cv.cget("scrollregion")).split()[2])
        except (ValueError, IndexError, tk.TclError):
            width = cv.winfo_width()
        visible = max(content, cv.winfo_height())
        cv.configure(scrollregion=(0, 0, width, visible))
        if content <= cv.winfo_height():
            cv.yview_moveto(0)

    def _timeline_wheel(self, e):
        cv = self.timeline
        try:
            region = [float(x) for x in str(cv.cget("scrollregion")).split()]
        except (ValueError, tk.TclError):
            region = []
        # 内容没占满可视高度：不允许滚（避免把空白的上面滑出来）
        if len(region) == 4 and region[3] <= cv.winfo_height() + 2:
            cv.yview_moveto(0)
            return "break"
        cv.yview_scroll(int(-e.delta / 120), "units")
        return "break"

    def refresh_timeline(self):
        cv = self.timeline
        self._anim_timeline.cancel()
        cv.delete("all")
        axis = self.current_axis()
        if not axis:
            cv.create_text(10, 20, anchor="nw", text="左侧新建一条技能轴",
                           fill=theme.TEXT_MUTED, font=theme.font(theme.F_SMALL))
            return

        color = theme.BURST if axis.role == ROLE_BURST else theme.CHARGE
        cv.create_rectangle(0, 0, 4000, 5, fill=color, outline="")

        expanded = self._expanded_option_rows(axis)
        base_h = NODE_H + 40

        x = 8
        y = 18
        nodes = axis.nodes
        last_is_branch = bool(nodes and
                              getattr(nodes[-1], "kind", "") == KIND_BRANCH)
        draw_nodes = nodes[:-1] if last_is_branch else nodes
        for node in draw_nodes:
            self._node_card(cv, node, x, y)
            x += NODE_W + NODE_GAP

        # 放置区（末尾是分支时，它就画在分支前面）
        slot_tag = "tl_slot"
        _before = set(cv.find_all())
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
        for _i in set(cv.find_all()) - _before:
            cv.addtag_withtag(slot_tag, _i)

        if last_is_branch:
            self._node_card(cv, nodes[-1], x + NODE_W + NODE_GAP, y)
            x += NODE_W + NODE_GAP

        height = base_h
        width = max(x + NODE_W + 24, cv.winfo_width())
        if expanded:
            # 分支展开：每条分支画成一行「和技能轴一样的卡片」
            branch_y = 18 + NODE_H + 18
            for oi, opt in expanded:
                row_w = self._branch_row(cv, oi, opt, branch_y,
                                        can_delete=len(expanded) > 1)
                width = max(width, row_w + 24)
                branch_y += NODE_H + 16
            if not expanded:
                cv.create_text(10, branch_y + 4, anchor="w",
                               text="还没有分支，点下面「＋ 加一条分支」",
                               fill=theme.TEXT_MUTED,
                               font=theme.font(theme.F_TINY))
            height = branch_y + 10
            tag = "bn_add"
            rounded_rect(cv, 10, branch_y - 2, 10 + 96, branch_y + 22, r=6,
                         fill=theme.PANEL_3, outline=theme.BORDER, tags=(tag,))
            cv.create_text(10 + 48, branch_y + 10, text="＋ 加一条分支",
                           fill=theme.CYAN, font=theme.font(theme.F_TINY, True),
                           tags=(tag,))
            cv.tag_bind(tag, "<Button-1>", lambda e: self._branch_add_option())
            cv.create_text(116, branch_y + 10, anchor="w",
                           text="点菱形收起分支 · 卡片可拖动排序，拖出删除",
                           fill=theme.TEXT_MUTED, font=theme.font(theme.F_TINY))
            height = branch_y + 34

        self._timeline_content_h = height
        visible_h = max(height, cv.winfo_height())
        cv.configure(height=height,
                     scrollregion=(0, 0, width, visible_h))
        # 内容没超过可视高度就强制回到顶部，不留可上滑的空白
        if height <= visible_h:
            cv.yview_moveto(0)
        elif expanded:
            cv.yview_moveto(0)      # 展开分支时保持主线在上
        self.tl_title.configure(text="技能轴 · %s" % axis.name, fg=color)
        self._sync_repeat_controls(axis)

    def _expanded_option_rows(self, axis):
        """当前展开的分支节点 -> [(选项序号, 选项)]，没展开返回空。"""
        if not self._expanded_branch:
            return []
        for node in axis.nodes:
            if getattr(node, "kind", "") == KIND_BRANCH and node.id == self._expanded_branch:
                return list(enumerate(node.options or []))
        self._expanded_branch = None
        return []

    def _branch_row(self, cv, oi, opt, y, can_delete=True):
        from .model import option_nodes, option_trigger

        tint = theme.CYAN if oi % 2 == 0 else theme.GREEN
        cv.create_rectangle(0, y - 6, 4000, y + NODE_H + 6, fill=theme.BG_2,
                            outline="")
        cv.create_rectangle(0, y - 6, 4, y + NODE_H + 6, fill=tint, outline="")

        trig = option_trigger(opt)
        trig_node = Node(operator=trig.get("operator") or "",
                         kind=trig.get("kind") or KIND_SKILL,
                         stage=trig.get("stage") or 1,
                         icon=self.icons.icon_for(trig.get("operator") or "",
                                                  trig.get("kind") or KIND_SKILL,
                                                  trig.get("stage") or 1) or "")
        self._branch_card(cv, trig_node, 10, y, oi, -1, tint=tint, trigger=True)

        x = 10 + NODE_W + NODE_GAP
        nodes = option_nodes(opt)
        for ni, node in enumerate(nodes):
            self._branch_card(cv, node, x, y, oi, ni, tint=tint)
            x += NODE_W + NODE_GAP

        # 末端放置区
        for sx0 in range(x, x + NODE_W, 12):
            cv.create_line(sx0, y, min(sx0 + 7, x + NODE_W), y, fill=theme.BORDER,
                           width=2)
            cv.create_line(sx0, y + NODE_H, min(sx0 + 7, x + NODE_W), y + NODE_H,
                           fill=theme.BORDER, width=2)
        for sy0 in range(y, y + NODE_H, 12):
            cv.create_line(x, sy0, x, min(sy0 + 7, y + NODE_H), fill=theme.BORDER,
                           width=2)
            cv.create_line(x + NODE_W, sy0, x + NODE_W,
                           min(sy0 + 7, y + NODE_H), fill=theme.BORDER, width=2)
        cv.create_text(x + NODE_W / 2, y + 40, text="＋", fill=theme.TEXT_DIM,
                       font=theme.font(14))
        cv.create_text(x + NODE_W / 2, y + 62, text="拖分支", fill=theme.TEXT_MUTED,
                       font=theme.font(theme.F_TINY))
        cv.create_text(x + NODE_W / 2, y + 74, text="技能到这里",
                       fill=theme.TEXT_MUTED, font=theme.font(theme.F_TINY))

        # 走完去向
        pill_x = x + NODE_W + 14
        next_id = str(opt.get("next") or "")
        target = self.store.axis_by_id(next_id) if next_id else None
        label = ("顺走 → 主线" if not next_id
                 else "跳到 → %s" % (target.name if target else "已删除的轴"))
        tag = "bn_next_%d" % oi
        w = theme.font(theme.F_TINY, True).measure(label) + 20
        rounded_rect(cv, pill_x, y + 30, pill_x + w, y + 54, r=6,
                     fill=theme.PANEL_3, outline=tint, tags=(tag,))
        cv.create_text(pill_x + w / 2, y + 42, text=label, fill=tint,
                       font=theme.font(theme.F_TINY, True), tags=(tag,))
        cv.tag_bind(tag, "<Button-1>", lambda e, i=oi: self._pick_branch_next(i))

        # 删除这条分支：只剩一条时置灰不可删
        dx = pill_x + w + 10
        del_tag = "bn_del_%d" % oi
        rounded_rect(cv, dx, y + 30, dx + 24, y + 54, r=6,
                     fill=theme.PANEL_3,
                     outline=theme.BAD if can_delete else theme.BORDER,
                     tags=(del_tag,))
        cv.create_text(dx + 12, y + 42, text="×",
                       fill=theme.BAD if can_delete else theme.TEXT_MUTED,
                       font=theme.font(theme.F_SMALL, True), tags=(del_tag,))
        if can_delete:
            cv.tag_bind(del_tag, "<Button-1>",
                        lambda e, i=oi: self._branch_remove_option(i))
        return dx + 24 + 40

    def _branch_card(self, cv, node, x, y, oi, ni, tint=theme.CYAN, trigger=False):
        tag = "br_%d_%d" % (oi, ni)
        outline = theme.ACCENT if trigger else theme.BORDER
        rounded_rect(cv, x, y, x + NODE_W, y + NODE_H, r=10,
                     fill=theme.PANEL_2, outline=outline, width=2 if trigger else 1,
                     tags=(tag,))
        photo = self.icons.render(node.icon, 52) if node.icon else None
        if photo is not None:
            cv.create_image(x + NODE_W / 2, y + 32, image=photo, tags=(tag,))
        cv.create_text(x + NODE_W / 2, y + 68, text=node.operator or "（未设）",
                       fill=theme.TEXT, font=theme.font(theme.F_SMALL, True),
                       tags=(tag,))
        cv.create_text(x + NODE_W / 2, y + 84,
                       text="%s · %s" % (self._node_label(node), self.key_hint(node)),
                       fill=theme.TEXT_MUTED,
                       font=theme.font(theme.F_TINY), tags=(tag,))
        if trigger:
            # 触发卡：不弹下拉，直接把技能栏的卡拖上来即可（也保留了拖动手感）
            pass
        else:
            cv.tag_bind(tag, "<Button-1>",
                        lambda e, i=oi, j=ni: self._branch_node_press(i, j))

    def _branch_node_press(self, oi, ni):
        self._begin_drag({"type": "branchmove", "opt": oi, "idx": ni}, "分支节点")

    def _pick_branch_trigger(self, oi):
        """兜底入口：也可以直接从技能栏把技能卡拖到触发卡上。"""
        node = self._branch_node_by_oi(oi)
        if node is None:
            return
        items = []
        for op in self.current_team().normalized():
            if not op:
                continue
            for kind in KINDS:
                items.append(("%s · %s" % (op, KIND_CN[kind]), (op, kind)))
        NiceMenu(self.root, items,
                 lambda pair, i=oi: self._set_trigger(i, pair[0], pair[1]))

    def _pick_branch_next(self, oi):
        node = self._branch_node_by_oi(oi)
        if node is None:
            return
        items = [("顺着走（回主线）", "")]
        for axis in self._order():
            items.append(("跳到 → %s" % axis.name, axis.id))
        NiceMenu(self.root, items,
                 lambda axis_id, i=oi: self._set_branch_next(i, axis_id))

    def _branch_node_by_oi(self, oi):
        axis = self.current_axis()
        if axis is None:
            return None
        for node in axis.nodes:
            if getattr(node, "kind", "") == KIND_BRANCH and node.id == self._expanded_branch:
                opts = node.options or []
                if 0 <= oi < len(opts):
                    return node
        return None

    def _branch_option(self, oi):
        node = self._branch_node_by_oi(oi)
        if node is None:
            return None
        opts = node.options or []
        return opts[oi] if 0 <= oi < len(opts) else None

    def _set_trigger(self, oi, operator, kind, stage=1):
        from .model import option_trigger
        opt = self._branch_option(oi)
        if opt is None:
            return
        trig = option_trigger(opt)
        trig.update({"operator": operator, "kind": kind,
                     "stage": max(1, int(stage or 1))})
        opt["trigger"] = trig
        self._after_branch_edit()

    def _set_branch_next(self, oi, axis_id):
        opt = self._branch_option(oi)
        if opt is None:
            return
        opt["next"] = axis_id
        self._after_branch_edit()

    def _after_branch_edit(self):
        self.store.save_axes()
        self.refresh_timeline()
        self.app.refresh_overlay()

    def _node_card(self, cv, node, x, y):
        tag = "nd_%s" % node.id
        if getattr(node, "kind", "") == KIND_BRANCH:
            # 分支点画成菱形，双击配置
            cx, cy = x + NODE_W / 2, y + NODE_H / 2
            r = min(NODE_W, NODE_H) / 2 - 4
            cv.create_polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r),
                               (cx - r, cy)], fill=theme.PANEL_3,
                              outline=theme.ACCENT, width=2, tags=(tag,))
            cv.create_text(cx, cy - 12, text="分支", fill=theme.ACCENT,
                           font=theme.font(theme.F_SMALL, True), tags=(tag,))
            cv.create_text(cx, cy + 6, text="%d 条" % len(node.options or []),
                           fill=theme.TEXT_MUTED,
                           font=theme.font(theme.F_TINY), tags=(tag,))
            cv.create_text(cx, cy + 22, text="点一下展开", fill=theme.TEXT_MUTED,
                           font=theme.font(theme.F_TINY), tags=(tag,))
            cv.tag_bind(tag, "<Button-1>", lambda e, n=node: self._node_press(n, e))
            return
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
                       text="%s · %s" % (self._node_label(node),
                                         self.key_hint(node)),
                       fill=theme.TEXT_MUTED, font=theme.font(theme.F_TINY), tags=(tag,))
        cv.tag_bind(tag, "<Button-1>", lambda e, n=node: self._node_press(n, e))

    def _node_press(self, node, e):
        self._begin_drag({"type": "move", "node": node}, node.operator or "节点")

    def _select_node(self, node_id):
        # 保留给旧调用；分支开合只由菱形切换
        pass

    def _node_label(self, node):
        """节点显示名：多形态用登记的名字（如「战技·意诀」），否则用种类名。"""
        if getattr(node, "kind", "") == KIND_BRANCH:
            return "分支"
        return self._form_label(node.operator, node.kind, getattr(node, "stage", 1))

    def _axis_ends_with_branch(self, axis):
        return bool(axis and axis.nodes and
                    getattr(axis.nodes[-1], "kind", "") == KIND_BRANCH)

    def add_node(self, operator, kind, index=None, stage=1):
        axis = self.current_axis()
        if not axis or not operator:
            return
        # 结尾是分支点时再加技能不会触发（顺走也走不到），直接拒绝
        if (index is None or index >= len(axis.nodes)) and \
                self._axis_ends_with_branch(axis):
            self.refresh_timeline()
            return
        file = self.icons.icon_for(operator, kind, stage) or ""
        node = Node(operator=operator, kind=kind, icon=file, stage=stage)
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

    def add_branch_node(self):
        """在主线末尾加一个分支点；结尾已经是分支就不再加。"""
        axis = self.current_axis()
        if not axis:
            return
        if self._axis_ends_with_branch(axis):
            return
        team = [m for m in self.current_team().normalized() if m]
        node = Node(kind=KIND_BRANCH, options=[{
            "trigger": {"operator": team[0] if team else "",
                        "kind": KIND_SKILL, "stage": 1},
            "nodes": [],
            "next": "",
        }])
        axis.nodes.append(node)
        self.store.save_axes()
        self.refresh_timeline()

    def edit_branch(self, node):
        """单击分支点：展开/收起分支行（再点一下收起）。"""
        if node is None or getattr(node, "kind", "") != KIND_BRANCH:
            return
        self._expanded_branch = None if self._expanded_branch == node.id else node.id
        self.refresh_timeline()

    def close_branch_panel(self):
        """兼容旧调用：收起展开的分支行。"""
        if self._expanded_branch:
            self._expanded_branch = None
            self.refresh_timeline()

    # ---------- 拖拽 ----------
    def _begin_drag(self, payload, label, image=None):
        """按下时先「上膛」，按住够久才真正开始拖（防误触）。"""
        self._end_drag()
        self._drag = dict(payload)
        self._drag.update({
            "moved": False,
            "armed": False,
            "aborted": False,
            "label": label,
            "image": image,
            "press": (self.root.winfo_pointerx(), self.root.winfo_pointery()),
            "arm_at": time.monotonic() + dragfx.HOLD_MS / 1000.0,
        })
        self._pending_drop = None
        self._arm_job = self.root.after(dragfx.HOLD_MS, self._arm_if_ready)
        self.root.bind_all("<B1-Motion>", self._drag_motion, add="+")
        self.root.bind_all("<ButtonRelease-1>", self._drag_release, add="+")

    def _arm_if_ready(self):
        """按住时间到了：不等鼠标动，先把幽灵亮出来（告诉用户「可以拖了」）。"""
        self._arm_job = None
        drag = self._drag
        if not drag or drag.get("aborted") or drag.get("armed"):
            return
        if time.monotonic() < drag.get("arm_at", 0.0):
            return
        self._arm_drag()

    def _arm_drag(self):
        """按住时间到了：造幽灵，进入真正的拖动状态。"""
        drag = self._drag
        if drag is None or drag.get("armed"):
            return
        drag["armed"] = True
        ghost, photo = dragfx.make_ghost(self.root, drag.get("label", ""),
                                         image=drag.get("image"))
        self._ghost = ghost
        self._ghost_photo = photo
        if ghost is not None:
            dragfx.set_ghost_alpha(ghost, 0.86)
        if drag.get("type") in ("move", "branchmove", "new"):
            self._capture_timeline_offsets()
        try:
            self.root.configure(cursor="fleur")
        except tk.TclError:
            pass

    def _drag_motion(self, e):
        drag = self._drag
        if not drag or drag.get("aborted"):
            return
        px, py = drag.get("press", (e.x_root, e.y_root))
        dist = abs(e.x_root - px) + abs(e.y_root - py)

        if not drag.get("armed"):
            if time.monotonic() < drag.get("arm_at", 0.0):
                # 还没按够时间：动得太早就是误触，直接放弃这次拖动
                if dist > dragfx.CANCEL_DIST:
                    drag["aborted"] = True
                return
            self._arm_drag()
            if not drag.get("armed"):
                return

        if not drag["moved"]:
            if dist < dragfx.DRAG_THRESHOLD:
                return
            drag["moved"] = True
        if not dragfx.move_ghost(self._ghost, e.x_root, e.y_root):
            self._ghost = None

        kind = self._drag.get("type")
        if kind == "team":
            gap = self._team_gap_at_global(e)
            self._pending_drop = gap
            members = self.current_team().normalized()
            self._preview_once("team", self.team_canvas,
                               "tm_%d" % self._drag["from"])
            self._preview_shift(self._anim_team, members, self._drag["from"],
                                gap, lambda i, _cn: "tm_%d" % i, 2,
                                TEAM_CARD_W + 10, fixed=4)
        elif kind == "reorder":
            idx = self._order_drop_index(e)
            order_ids = list(self.current_rotation().sequence()) \
                if self.current_rotation() else []
            if idx is not None:
                idx = min(idx, len(order_ids))
            self._pending_drop = idx
            self._preview_once("reorder", self.order_canvas,
                               "row_%s" % self._drag["axis"].id)
            axis_id = self._drag["axis"].id
            self._preview_shift(self._anim_order, order_ids,
                                order_ids.index(axis_id) if axis_id in order_ids else 0,
                                idx, lambda i, a_id: "row_%s" % a_id, 2,
                                AXIS_ROW_H, vertical=True, fixed=2)
        else:
            target = self._timeline_target(e)
            axis = self.current_axis()
            nodes = list(axis.nodes) if axis else []
            kind = self._drag.get("type")

            if kind == "branchmove":
                # 分支卡：可能移到同/别的分支行，也可能拖回主轴
                if target is not None and target[0] == "main":
                    target = ("main", target[1])
                self._pending_drop = target[1] if (target and target[0] == "main") \
                    else target
                if target is not None:
                    self._preview_cross(("branch", self._drag["opt"],
                                         self._drag["idx"]), target)
                return

            if kind == "new":
                self._pending_drop = target[1] if (target and target[0] == "main") \
                    else target
                self._preview_new_target(target)
                return
            if target is not None and target[0] == "trigger":
                self._pending_drop = target
                return
            if target is not None and target[0] == "branch":
                # 主轴卡拖到分支行：主轴那边收拢、分支那边让位
                self._pending_drop = target
                node = self._drag.get("node")
                from_idx = nodes.index(node) if node in nodes else 0
                self._preview_cross(("main", from_idx), target)
                return

            idx = target[1] if target is not None else None
            self._pending_drop = idx
            node = self._drag.get("node")
            from_idx = nodes.index(node) if node in nodes else 0
            self._preview_once("move", self.timeline,
                               "nd_%s" % getattr(node, "id", ""))
            self._preview_shift(self._anim_timeline, nodes, from_idx, idx,
                                lambda i, n: "nd_%s" % n.id, 8,
                                NODE_W + NODE_GAP, fixed=18)

    def _preview_once(self, key, cv, tag):
        """被拖的东西只藏一次，免得每帧都去改 canvas。"""
        if self._drag is None or self._drag.get("hidden_" + key):
            return
        self._drag["hidden_" + key] = self._hide_dragged(cv, tag)

    def _in_canvas(self, cv, e):
        try:
            rx, ry = cv.winfo_rootx(), cv.winfo_rooty()
            rw, rh = cv.winfo_width(), cv.winfo_height()
        except tk.TclError:
            return None
        x, y = e.x_root - rx, e.y_root - ry
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

    def _team_gap_at_global(self, e):
        pos = self._in_canvas(self.team_canvas, e)
        if pos is None:
            return None
        return self._team_gap_at(pos[0], pos[1])

    def _draw_team_indicator(self, gap):
        """已改成「让位预览」，不再画被幽灵挡住的竖线；保留空实现免得旧调用报错。"""
        return

    def _timeline_drop_index(self, e):
        pos = self._in_canvas(self.timeline, e)
        if pos is None:
            return None
        x, _y = pos
        axis = self.current_axis()
        total = len(axis.nodes) if axis else 0
        idx = int((x - 8 + (NODE_W + NODE_GAP) / 2) // (NODE_W + NODE_GAP))
        return max(0, min(idx, total))

    # ---------- 分支行：拖放目标 ----------
    def _branch_row_geometry(self):
        """展开中的分支行：{选项序号: (y, 节点数)}。"""
        axis = self.current_axis()
        rows = {}
        if axis is None or not self._expanded_branch:
            return rows
        y = 18 + NODE_H + 18
        for oi, opt in enumerate(self._branch_option_list()):
            rows[oi] = (y, len(opt.get("nodes") or []))
            y += NODE_H + 16
        return rows

    def _branch_option_list(self):
        axis = self.current_axis()
        if axis is None or not self._expanded_branch:
            return []
        for node in axis.nodes:
            if getattr(node, "kind", "") == KIND_BRANCH and node.id == self._expanded_branch:
                if node.options is None:
                    node.options = []
                return node.options        # 返回真实列表，删除/新增才改得到数据
        return []

    def _timeline_target(self, e):
        """返回 ("main", idx) 或 ("branch", oi, gap)；不在时间轴内返回 None。"""
        pos = self._in_canvas(self.timeline, e)
        if pos is None:
            return None
        x, y = pos
        for oi, (ry, count) in self._branch_row_geometry().items():
            if ry - 8 <= y <= ry + NODE_H + 8:
                # 第一格是触发卡：拖技能卡到这里 = 设为该分支的触发
                if x <= 10 + NODE_W:
                    return ("trigger", oi)
                start = 10 + NODE_W + NODE_GAP
                gap = int((x - start + (NODE_W + NODE_GAP) / 2) // (NODE_W + NODE_GAP))
                return ("branch", oi, max(0, min(gap, count)))
        axis = self.current_axis()
        total = len(axis.nodes) if axis else 0
        idx = int((x - 8 + (NODE_W + NODE_GAP) / 2) // (NODE_W + NODE_GAP))
        idx = max(0, min(idx, total))
        if axis and self._axis_ends_with_branch(axis) and idx >= total:
            idx = max(0, total - 1)      # 末尾分支：落到它前面
        return ("main", idx)

    def _capture_timeline_offsets(self):
        """记下主轴/分支卡片「bbox - 期望位置」的固有偏差（圆角平滑会多出约 2px）。"""
        drag = self._drag
        if drag is None:
            return
        cv = self.timeline
        offs = {}

        def measure(tag, where, idx):
            try:
                box = cv.bbox(tag)
            except tk.TclError:
                return
            if not box:
                return
            x, y = self._cell_pos(where, idx)
            offs[tag] = (box[0] - x, box[1] - y)

        axis = self.current_axis()
        for i, node in enumerate(axis.nodes if axis else []):
            measure("nd_%s" % node.id, ("main", None), i)
        for oi, opt in enumerate(self._branch_option_list()):
            for ni, node in enumerate(opt.get("nodes") or []):
                measure("br_%d_%d" % (oi, ni), ("branch", oi), ni)
        drag["offs"] = offs
        drag["offs_ready"] = True

    def _cell_pos(self, where, idx):
        """卡片在某区域的期望位置：where = ("main",None) 或 ("branch",oi)。"""
        step = NODE_W + NODE_GAP
        if where[0] == "main":
            return 8 + idx * step, 18
        oi = where[1]
        geom = self._branch_row_geometry()
        ry = geom.get(oi, (18 + NODE_H + 18, 0))[0]
        return 10 + NODE_W + NODE_GAP + idx * step, ry

    def _preview_cross(self, src, target):
        """跨区拖动时也让位：src=("main",idx)或("branch",oi,ni)，target=("main",idx)/(「branch」,oi,gap)。"""
        axis = self.current_axis()
        if axis is None:
            return
        cv = self.timeline
        step = NODE_W + NODE_GAP
        offs = self._drag.setdefault("offs", {})
        targets = []

        def add(tag, where, idx):
            x, y = self._cell_pos(where, idx)
            ox, oy = offs.get(tag, (0, 0))
            targets.append((tag, x + ox, y + oy))

        src_main = src[1] if src[0] == "main" else None
        src_branch = (src[1], src[2]) if src[0] == "branch" else None
        if src_main is not None:
            for i, node in enumerate(axis.nodes):
                tag = "nd_%s" % node.id
                if i == src_main:
                    self._preview_once("cross", cv, tag)
                    continue
                j = i - (1 if i > src_main else 0)
                if target[0] == "main" and src_branch and j >= target[1]:
                    j += 1
                add(tag, ("main", None), j)
        else:
            for i, node in enumerate(axis.nodes):
                j = i
                if target[0] == "main" and src_branch and j >= target[1]:
                    j += 1
                add("nd_%s" % node.id, ("main", None), j)

        opts = self._branch_option_list()
        for oi, opt in enumerate(opts):
            for ni, node in enumerate(opt.get("nodes") or []):
                tag = "br_%d_%d" % (oi, ni)
                if src_branch == (oi, ni):
                    self._preview_once("cross", cv, tag)
                    continue
                j = ni - (1 if src_branch and src_branch[0] == oi and ni > src_branch[1]
                          else 0)
                if target[0] == "branch" and target[1] == oi and j >= target[2]:
                    j += 1
                add(tag, ("branch", oi), j)

        last_branch = bool(axis.nodes and
                           getattr(axis.nodes[-1], "kind", "") == KIND_BRANCH)
        slot_x = 8 + (len(axis.nodes) - (1 if last_branch else 0)) * step
        slot_shift = 0
        if src_main is not None:
            slot_shift -= 1
        if target is not None and target[0] == "main":
            slot_shift += 1
        targets.append(("tl_slot", slot_x + slot_shift * step, 18))
        self._anim_timeline.move_to(targets)

    def _branch_insert(self, oi, gap, operator, kind, stage=1):
        if kind == KIND_BRANCH:
            return                       # 分支里不能插入分支
        opts = self._branch_option_list()
        if not (0 <= oi < len(opts)):
            return
        file = self.icons.icon_for(operator, kind, stage) or ""
        node = Node(operator=operator, kind=kind, icon=file, stage=stage)
        nodes = list(opts[oi].get("nodes") or [])
        gap = max(0, min(int(gap), len(nodes)))
        nodes.insert(gap, node)
        opts[oi]["nodes"] = nodes
        self._after_branch_edit()

    def _branch_take(self, oi, ni):
        """从分支里摘下一个节点（返回它，没找到返回 None）。"""
        opts = self._branch_option_list()
        if not (0 <= oi < len(opts)):
            return None
        nodes = list(opts[oi].get("nodes") or [])
        if not (0 <= ni < len(nodes)):
            return None
        node = nodes.pop(ni)
        opts[oi]["nodes"] = nodes
        return node

    def _main_take(self, node):
        """从主轴摘下节点。"""
        axis = self.current_axis()
        if axis is None or node not in axis.nodes:
            return False
        axis.nodes.remove(node)
        return True

    def _branch_move(self, oi, ni, target):
        opts = self._branch_option_list()
        if not (0 <= oi < len(opts)):
            return
        nodes = list(opts[oi].get("nodes") or [])
        if not (0 <= ni < len(nodes)):
            return
        node = nodes[ni]
        if target is None:
            nodes.pop(ni)                       # 拖到窗口外 = 删除
            opts[oi]["nodes"] = nodes
            self._after_branch_edit()
            return
        if isinstance(target, int):          # 分支 -> 主轴
            axis = self.current_axis()
            gap = max(0, min(target, len(axis.nodes)))
            if gap >= len(axis.nodes) and self._axis_ends_with_branch(axis):
                self._after_branch_edit()    # 不往分支结尾后面塞
                return
            if self._branch_take(oi, ni) is not None:
                axis.nodes.insert(gap, node)
                self.store.save_axes()
                self._after_branch_edit()
            return
        if isinstance(target, tuple) and len(target) == 2:
            if target[0] == "trigger":
                target = ("branch", target[1], 0)
            elif target[0] == "main":
                target = target[1]
        kind, toi, gap = target
        if kind != "branch":
            return
        if toi == oi:
            opts[oi]["nodes"] = move_item(nodes, ni, gap)
        else:
            nodes.pop(ni)
            opts[oi]["nodes"] = nodes
            dst = list(opts[toi].get("nodes") or [])
            dst.insert(max(0, min(gap, len(dst))), node)
            opts[toi]["nodes"] = dst
        self._after_branch_edit()

    def _branch_remove_option(self, oi):
        """删掉一条分支；只剩一条时不允许删。"""
        opts = self._branch_option_list()
        if len(opts) <= 1 or not (0 <= oi < len(opts)):
            return
        opts.pop(oi)
        self._after_branch_edit()

    def _branch_add_option(self):
        axis = self.current_axis()
        node = None
        for n in axis.nodes if axis else []:
            if getattr(n, "kind", "") == KIND_BRANCH and n.id == self._expanded_branch:
                node = n
                break
        if node is None:
            return
        if len(node.options or []) >= 12:
            return                       # 最多 12 条分支
        team = [m for m in self.current_team().normalized() if m]
        node.options = list(node.options or []) + [{
            "trigger": {"operator": team[0] if team else "",
                        "kind": KIND_SKILL, "stage": 1},
            "nodes": [],
            "next": "",
        }]
        self._after_branch_edit()

    # 旧的「插入线」指示已由 _preview_shift 的让位预览取代，这两个方法仅保留给外部调用
    def _draw_reorder_indicator(self, idx):
        return

    def _draw_drop_indicator(self, idx):
        return

    def _drag_release(self, e):
        drag = self._drag
        if not drag:
            return
        drop = self._pending_drop
        moved = drag.get("moved")
        armed = drag.get("armed")
        self._end_drag()

        kind = drag.get("type")

        if not armed:
            # 没按够时间（或过早移动）：当作单击，不改顺序
            if kind == "new":
                self.add_node(self.selected_member, drag["kind"], None,
                              drag.get("stage", 1))
            elif kind == "move":
                node = drag.get("node")
                if node is not None and getattr(node, "kind", "") == KIND_BRANCH:
                    self.edit_branch(node)      # 单击菱形：展开/收起分支行
            return

        if kind == "team":
            if not moved:
                return
            if not isinstance(drop, int):
                self.refresh_team()
                return
            members = self.current_team().normalized()
            self._team_drop(drag["from"], drop, members)
            return

        if kind == "reorder":
            if not moved or not isinstance(drop, int):
                self.refresh_order()
                return
            self._reorder_axis(drag["axis"], drop)
            return

        if kind == "branchmove":
            if not moved:
                return
            # drop 可能是分支里的 (branch, oi, gap)、主轴的 int，或 None(拖出)
            self._branch_move(drag["opt"], drag["idx"], drop)
            return

        if not moved:
            if kind == "new":
                self.add_node(self.selected_member, drag["kind"])
            elif kind == "move":
                node = drag.get("node")
                if node is not None and getattr(node, "kind", "") == KIND_BRANCH:
                    self.edit_branch(node)
                else:
                    self.close_branch_panel()
            return

        if kind == "new":
            if isinstance(drop, tuple) and drop[0] == "trigger":
                self._set_trigger(drop[1], self.selected_member, drag["kind"],
                                  drag.get("stage", 1))
                return
            if isinstance(drop, tuple) and drop[0] == "branch":
                self._branch_insert(drop[1], drop[2], self.selected_member,
                                    drag["kind"], drag.get("stage", 1))
            elif isinstance(drop, int):
                self.add_node(self.selected_member, drag["kind"], drop,
                              drag.get("stage", 1))
            else:
                self.refresh_timeline()
        elif kind == "move":
            node = drag.get("node")
            if isinstance(drop, tuple) and drop[0] == "branch":
                # 主轴 -> 分支行（分支点本身不能塞进分支）
                if getattr(node, "kind", "") == KIND_BRANCH:
                    self.refresh_timeline()
                    return
                if self._main_take(node):
                    self._branch_insert(drop[1], drop[2], node.operator,
                                        node.kind, getattr(node, "stage", 1))
            elif isinstance(drop, int):
                self._move_node(node, drop)
            else:
                self._remove_node(node)

    def _end_drag(self):
        self._drag = None
        self._pending_drop = None
        if self._arm_job is not None:
            try:
                self.root.after_cancel(self._arm_job)
            except (tk.TclError, ValueError):
                pass
            self._arm_job = None
        if self._ghost is not None:
            try:
                self._ghost.destroy()
            except tk.TclError:
                pass
            self._ghost = None
        self._ghost_photo = None
        try:
            self.root.unbind_all("<B1-Motion>")
            self.root.unbind_all("<ButtonRelease-1>")
        except tk.TclError:
            pass
        for cv in (self.timeline, self.order_canvas, self.team_canvas):
            try:
                cv.delete("drop_ind")
            except tk.TclError:
                pass
        try:
            self.team_canvas.configure(cursor="")
        except (tk.TclError, AttributeError):
            pass
        try:
            self.root.configure(cursor="")
        except tk.TclError:
            pass

    def _reorder_axis(self, axis, idx):
        rot = self.current_rotation()
        if not rot:
            return
        ids = rot.sequence()
        if axis.id not in ids:
            return
        old = ids.index(axis.id)
        new_ids = move_item(ids, old, idx)
        if new_ids != ids:
            self._set_order(new_ids)
        self.refresh_order()          # 不管顺序变没变都重画，清掉让位动画的中间态
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
        if idx >= len(axis.nodes) and self._axis_ends_with_branch(axis):
            self.refresh_timeline()      # 不往分支点后面塞
            return
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
    def _ask_export_scope(self):
        """弹个小菜单选导出范围。返回 "all" / "rotation" / None。"""
        menu = tk.Menu(self.root, tearoff=0, bg=theme.PANEL_2, fg=theme.TEXT,
                       activebackground=theme.ACCENT,
                       activeforeground="#221a06",
                       bd=0, font=theme.font(theme.F_SMALL))
        picked = {"v": None}
        menu.add_command(label="导出全部（所有编队 + 技能轴 + 设置）",
                         command=lambda: picked.update(v="all"))
        rot = self.current_rotation()
        menu.add_command(
            label="只导出当前编队%s（含它的技能轴与队伍）" % (
                "「%s」" % rot.name if rot else ""),
            command=lambda: picked.update(v="rotation"))
        try:
            x, y = self.root.winfo_pointerxy()
            menu.tk_popup(x, y)
        finally:
            try:
                menu.grab_release()
            except tk.TclError:
                pass
        return picked["v"]

    def do_export(self):
        scope = self._ask_export_scope()
        if not scope:
            return
        rot = self.current_rotation() if scope == "rotation" else None
        if scope == "rotation" and rot is None:
            messagebox.showinfo("没有编队", "当前还没有编队可以导出。",
                                parent=self.root)
            return
        stamp = time.strftime("%Y%m%d")
        initial = ("编队-%s-%s.json" % (rot.name, stamp)) if rot is not None \
            else ("终末地技能轴-%s.json" % stamp)
        path = filedialog.asksaveasfilename(
            parent=self.root, title="导出配置", defaultextension=".json",
            initialfile=initial,
            filetypes=[("JSON 文件", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        data = self.store.export_dict(rot)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            messagebox.showerror("导出失败", str(e), parent=self.root)
            return
        counts = data.get("counts", {})
        messagebox.showinfo(
            "导出成功",
            "已导出 %d 条技能轴、%d 个编队\n\n%s"
            % (counts.get("axes", 0), counts.get("rotations", 0), path),
            parent=self.root)

    def _ask_import_mode(self):
        """导入编队方式：覆盖全部 / 在现有基础上添加。"""
        win = tk.Toplevel(self.root)
        win.title("导入方式")
        win.configure(bg=theme.BG)
        win.transient(self.root)
        win.grab_set()
        result = {"mode": None}

        tk.Label(win, text="导入编队", bg=theme.BG, fg=theme.TEXT,
                 font=theme.font(theme.F_TITLE, True)).pack(anchor="w",
                                                            padx=20, pady=(16, 2))
        tk.Label(win, text="选择这两种之一：", bg=theme.BG, fg=theme.TEXT_MUTED,
                 font=theme.font(theme.F_SMALL)).pack(anchor="w", padx=20)

        def pick(mode):
            result["mode"] = mode
            win.destroy()

        for title, sub, mode in (
            ("覆盖当前所有编队", "轴、编队、队伍、设置都换成文件里的内容", "replace"),
            ("在现有基础上添加", "保留现有内容，导入的编队另起 id，重名自动区分", "append"),
        ):
            row = tk.Frame(win, bg=theme.PANEL, padx=12, pady=10)
            row.pack(fill="x", padx=20, pady=(8, 0))
            tk.Button(row, text=title, command=lambda m=mode: pick(m),
                      bg=theme.ACCENT, fg="#221a06", relief="flat", bd=0,
                      highlightthickness=0, cursor="hand2",
                      font=theme.font(theme.F_BODY, True), padx=12, pady=4,
                      anchor="w").pack(fill="x")
            tk.Label(row, text=sub, bg=theme.PANEL, fg=theme.TEXT_MUTED,
                     font=theme.font(theme.F_TINY), anchor="w").pack(fill="x")

        foot = tk.Frame(win, bg=theme.BG)
        foot.pack(fill="x", padx=20, pady=12)
        tk.Button(foot, text="取消", command=win.destroy, bg=theme.PANEL_3,
                  fg=theme.TEXT, relief="flat", bd=0, highlightthickness=0,
                  cursor="hand2", font=theme.font(theme.F_SMALL),
                  padx=14, pady=4).pack(side="right")
        win.bind("<Escape>", lambda e: win.destroy())
        center_window(win, self.root, 440, 300)
        self.root.wait_window(win)
        return result["mode"]

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
        mode = self._ask_import_mode()
        if mode is None:
            return
        ok, msg = self.store.import_dict(data, mode)
        if not ok:
            messagebox.showerror("导入失败", msg, parent=self.root)
            return
        self.current_axis_id = self.store.axes[0].id if self.store.axes else None
        self.refresh_all()
        self.app.rebuild_player()
        messagebox.showinfo("导入成功", msg, parent=self.root)
