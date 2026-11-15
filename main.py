# -*- coding: utf-8 -*-
"""大祥老师的终末地助手 入口。

用法：
    python main.py              正常启动
    python main.py --selftest   只跑逻辑自测，不开窗口
    python main.py --smoke      构建界面后自动关闭，用于快速验证
"""
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

if getattr(sys, "frozen", False):
    # 打包后：把 exe 所在目录也加进来，方便读取外置 data/
    _exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    if _exe_dir not in sys.path:
        sys.path.insert(0, _exe_dir)


def _prefer_external_code():
    """打包后允许用 exe 旁边的 .py 覆盖内置模块（增量更新用）。

    更新器只会把改过的文件写到 exe 所在目录，这里让 import 优先读磁盘上的
    那一份：`app/model.py` 存在时就用它，不存在时回落到 PyInstaller 内置副本。
    开发态不生效，避免干扰正常的源码导入。
    """
    if not getattr(sys, "frozen", False):
        return
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    if not exe_dir or not os.path.isdir(exe_dir):
        return

    import importlib.util

    class _ExternalFinder:
        """只接管 exe 目录里真实存在的 .py / 包。"""

        @staticmethod
        def _locate(fullname):
            rel = fullname.replace(".", os.sep)
            for path in (os.path.join(exe_dir, rel + ".py"),
                         os.path.join(exe_dir, rel, "__init__.py")):
                if os.path.isfile(path):
                    return path
            return None

        def find_spec(self, fullname, path=None, target=None):
            if fullname != "app" and not fullname.startswith("app."):
                return None
            origin = self._locate(fullname)
            if origin is None:
                return None
            is_pkg = origin.endswith("__init__.py")
            return importlib.util.spec_from_file_location(
                fullname, origin,
                submodule_search_locations=[os.path.dirname(origin)] if is_pkg else None)

    sys.meta_path.insert(0, _ExternalFinder())


_prefer_external_code()


def _maybe_elevate():
    """打包运行时，如果不是管理员就尝试提权重启。

    游戏通常以管理员运行，而 Windows 的 UIPI 会挡住低权限进程的键盘钩子，
    表现就是「桌面上能按键，切到游戏就完全没反应」。
    """
    if not getattr(sys, "frozen", False):
        return False
    if "--no-elevate" in sys.argv:
        return False
    try:
        from app import paths
        from app.elevation import is_admin, relaunch_as_admin
        from app.model import Store
        store = Store(paths.base_dir())
        if not getattr(store.settings, "auto_elevate", True):
            return False
        if is_admin():
            return False
        return relaunch_as_admin()
    except Exception:
        return False


def main():
    if "--selftest" in sys.argv:
        from app.selftest import main as selftest_main
        raise SystemExit(selftest_main())

    if "--smoke" in sys.argv:
        from app.application import Application
        app = Application()
        app.root.after(900, app.on_close)
        app.root.mainloop()
        print("SMOKE_OK")
        return

    if _maybe_elevate():
        return          # 已发起提权，当前进程退出

    from app.application import run
    run()


if __name__ == "__main__":
    main()
