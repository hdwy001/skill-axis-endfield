# -*- coding: utf-8 -*-
"""版本号：界面显示 + 更新检查都读这里。

发版流程：
    1. 改这里的 VERSION
    2. python tools/make_manifest.py     （生成 update/manifest.json）
    3. git add -A && git commit && git push
程序「检查更新」会对比 github 上 manifest 里的 version 和本地这个值。
"""

VERSION = "1.3.0"
APP_NAME = "技能轴提示器"
APP_TITLE = "技能轴提示器 · 明日方舟：终末地"
