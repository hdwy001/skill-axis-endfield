# -*- coding: utf-8 -*-
"""软件名与图标资源路径（改名只改这里）。"""
import os

APP_TITLE = "大祥老师的终末地助手"
APP_SUB = "明日方舟：终末地 · 编队编排"
APP_VERSION = "2.0.0"
APP_VERSION_CN = "2.0"
# 界面上显示的软件名（带版本号）；exe/压缩包名仍用 APP_TITLE，避免更新和快捷方式失联
APP_TITLE_VERSIONED = "%s v%s" % (APP_TITLE, APP_VERSION)
APP_PUBLISHER = "Luyoo"


def resource(*parts):
    """assets/ 下的资源：开发时在项目根，打包后在 dist 根。"""
    from . import paths
    root = getattr(paths, "base_dir", None)
    if callable(root):
        root = root()
    if not root:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    primary = os.path.join(root, *parts)
    if os.path.exists(primary):
        return primary
    # 回退：项目源码根（沙箱/未打包 data 目录时也能找到 assets）
    fallback = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), *parts)
    return primary if os.path.exists(primary) else fallback


def icon_png():
    return resource("assets", "app_icon.png")


def icon_ico():
    return resource("assets", "app_icon.ico")
