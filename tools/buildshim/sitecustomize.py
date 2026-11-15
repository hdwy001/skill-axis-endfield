# -*- coding: utf-8 -*-
"""让每个新建的 python 进程都跳过会卡死的 platform 探测。

为什么需要它：PyInstaller 在分析阶段会 fork 出隔离子进程来跑 hook，
这些子进程是全新的解释器，拿不到主进程里打的补丁，于是又在
platform.uname() -> _wmi_query()（WMIC）上卡死。

放在 PYTHONPATH 上的 sitecustomize.py 会被每个解释器启动时自动导入，
所以补丁对父进程和所有子进程同时生效。只影响构建环境。
"""
import os
import sys

if sys.platform.startswith("win"):


    def _install():
        import platform

        if getattr(platform, "_skillaxis_probe_patched", False):
            return

        # 1) WMIC 查询按字段数返回空串元组，调用方解包成「未知」
        platform._wmi_query = lambda category, *fields: tuple("" for _ in fields)

        # 2) win32_ver 用 sys.getwindowsversion()
        original_win32_ver = platform.win32_ver

        def fast_win32_ver(*args, **kwargs):
            try:
                info = sys.getwindowsversion()
                major, minor, build = info[0], info[1], info[2]
            except Exception:                       # noqa: BLE001
                return original_win32_ver(*args, **kwargs)
            release = "11" if (major == 10 and build >= 22000) else str(major)
            return (release, "%d.%d.%d" % (major, minor, build), "", "Workstation")

        platform.win32_ver = fast_win32_ver

        # 3) uname 不碰任何外部命令（必须返回命名元组）
        def fast_uname():
            info = sys.getwindowsversion()
            machine = (os.environ.get("PROCESSOR_ARCHITEW6432")
                       or os.environ.get("PROCESSOR_ARCHITECTURE")
                       or "AMD64")
            host = os.environ.get("COMPUTERNAME") or "localhost"
            return platform.uname_result(
                "Windows", host,
                "%d.%d.%d" % (info[0], info[1], info[2]),
                "10" if info[0] == 10 else str(info[0]),
                machine.lower())

        platform.uname = fast_uname
        platform._skillaxis_probe_patched = True

    try:
        _install()
    except Exception:                               # noqa: BLE001
        pass
