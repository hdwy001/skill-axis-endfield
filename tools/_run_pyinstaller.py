# -*- coding: utf-8 -*-
"""PyInstaller 启动器：先绕过本机 platform 探测卡死的问题，再跑构建。

背景（实测调用栈）：
    PyInstaller.compat 在 import 阶段调用 platform.uname()
    -> platform.system() -> platform._get_machine_win32() -> platform._wmi_query()
    这台机器上 WMIC 查询不返回，于是构建永远停在 `import PyInstaller`。

做法：在导入 PyInstaller 之前，把 platform 里会走 WMIC / 慢系统调用的几处
换成基于 sys.getwindowsversion() 与环境变量的快速实现。只影响本进程。

用法（由 tools/build_package.py 调用）：
    python tools/_run_pyinstaller.py <常规 PyInstaller 参数...>
"""
import os
import platform
import sys


def patch_platform_probes():
    """让 platform 的 Windows 探测不再依赖 WMIC。"""
    if getattr(platform, "_skillaxis_patched", False):
        return

    # 1) WMIC 查询直接短路：按请求的字段数返回空字符串元组，
    #    调用方（platform.get_win32 等）会解包成「未知」，不会卡住也不会抛错
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

    # 3) uname 全部走环境变量 + getwindowsversion，不碰任何外部命令
    def fast_uname():
        info = sys.getwindowsversion()
        machine = (os.environ.get("PROCESSOR_ARCHITEW6432")
                   or os.environ.get("PROCESSOR_ARCHITECTURE")
                   or "AMD64")
        # 注意：不能调用 platform.node()，它内部又会调 uname() 造成自递归
        host = os.environ.get("COMPUTERNAME") or "localhost"
        # 必须返回命名元组，否则 platform.system() 取 .system 会失败
        return platform.uname_result(
            "Windows", host,
            "%d.%d.%d" % (info[0], info[1], info[2]),
            "10" if info[0] == 10 else str(info[0]),
            machine.lower())

    platform.uname = fast_uname
    platform._skillaxis_patched = True


def main():
    patch_platform_probes()
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    libs = os.path.join(base, "_buildtmp", "libs")
    if libs not in sys.path:
        sys.path.insert(0, libs)
    import PyInstaller.__main__
    sys.argv = ["pyinstaller"] + sys.argv[1:]
    return PyInstaller.__main__.run()


if __name__ == "__main__":
    raise SystemExit(main())
