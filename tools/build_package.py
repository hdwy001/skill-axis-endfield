# -*- coding: utf-8 -*-
"""打包成免安装 exe（onedir + 外置 data/），并产出可直接分发的版本化 ZIP。

用法：
    python tools/build_package.py            # 构建
    python tools/build_package.py --no-zip   # 只构建，不压缩

产出：
    dist/技能轴提示器/                                  —— 免安装目录
    dist/技能轴提示器-vX.Y.Z-win-x64.zip                —— 固定单一顶层目录
    dist/技能轴提示器-vX.Y.Z-win-x64.zip.sha256         —— 校验文件

发布包里的 data/*.json 来自「默认示例数据」，不会带开发者本机的
技能轴、窗口坐标、活动编队等私有状态；图标/立绘照常随包分发。
"""
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIBS = os.path.join(BASE, "_buildtmp", "libs")
# 允许临时换输出目录（旧 dist 里的 exe 被杀软/句柄占用时用它绕开）
DIST = os.environ.get("SKILL_AXIS_DIST") or os.path.join(BASE, "dist")
APP_NAME = "技能轴提示器"
OUT_DIR = os.path.join(DIST, APP_NAME)

sys.path.insert(0, BASE)
sys.path.insert(0, LIBS)

from app.model import Settings, make_demo_data  # noqa: E402
from app.version import VERSION  # noqa: E402

# 这些是本机运行状态，绝不进发布包
PRIVATE_JSON = ("axes.json", "rotations.json", "team.json", "settings.json")

BUILD_EXCLUDES = ("numpy", "pandas", "matplotlib", "scipy", "pytest",
                  "IPython", "setuptools", "pip")


def _write_defaults(data_dir):
    """用内置示例数据生成干净的默认配置。"""
    axes, rots, team = make_demo_data()
    settings = Settings()
    # 默认窗口位置，避免带着开发机的坐标
    settings.overlay_x = 120
    settings.overlay_y = 120
    settings.active_rotation = rots[0].id if rots else ""
    payloads = {
        "axes.json": [a.to_dict() for a in axes],
        "rotations.json": [r.to_dict() for r in rots],
        "team.json": team.to_dict(),
        "settings.json": settings.to_dict(),
    }
    for name, payload in payloads.items():
        _dump_json(os.path.join(data_dir, name), payload)


def _dump_json(path, payload):
    import json
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def _stage_data(out_dir):
    """拷贝素材，但把四个可变 JSON 换成默认示例。"""
    src = os.path.join(BASE, "data")
    dst = os.path.join(out_dir, "data")
    if not os.path.isdir(src):
        print("缺少 data/，跳过素材拷贝")
        return
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst,
                    ignore=shutil.ignore_patterns(
                        "_selftest_tmp*", "*.tmp", "__pycache__"))
    for name in PRIVATE_JSON:
        full = os.path.join(dst, name)
        if os.path.exists(full):
            os.remove(full)
    _write_defaults(dst)
    print("data/ 已重置为默认示例（不含个人编队与设置）")


def _copy_docs(out_dir):
    for name in ("使用说明.md", "启动说明.txt"):
        src = os.path.join(BASE, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(out_dir, name))
            print("拷贝", name)


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _make_zip(dist_dir, out_dir):
    """ZIP 内统一一个顶层目录，避免解压时把文件撒到当前目录。"""
    tag = "v%s" % VERSION
    zip_name = "%s-%s-win-x64.zip" % (APP_NAME, tag)
    zip_path = os.path.join(dist_dir, zip_name)
    if os.path.exists(zip_path):
        os.remove(zip_path)
    count = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for dirpath, dirnames, filenames in os.walk(out_dir):
            dirnames.sort()
            rel_dir = os.path.relpath(dirpath, out_dir)
            for filename in sorted(filenames):
                full = os.path.join(dirpath, filename)
                if rel_dir == ".":
                    arc = "%s/%s" % (APP_NAME, filename)
                else:
                    arc = "%s/%s/%s" % (APP_NAME,
                                        rel_dir.replace(os.sep, "/"), filename)
                zf.write(full, arc)
                count += 1
    digest = _sha256(zip_path)
    sha_path = zip_path + ".sha256"
    with open(sha_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("%s  %s\n" % (digest, zip_name))
    print("ZIP：%s（%d 个文件，%.1f MB）"
          % (zip_name, count, os.path.getsize(zip_path) / 1048576.0))
    print("SHA-256：%s" % digest)
    return zip_path


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    dist_dir = DIST
    if "--dist" in argv:
        idx = argv.index("--dist")
        if idx + 1 < len(argv):
            dist_dir = os.path.abspath(argv[idx + 1])
            argv = argv[:idx] + argv[idx + 2:]
    out_dir = os.path.join(dist_dir, APP_NAME)
    os.makedirs(dist_dir, exist_ok=True)
    if not os.path.isdir(LIBS):
        print("缺少 PyInstaller，请先运行 tools/_fetch_pyinstaller.py")
        return 1

    env = dict(os.environ)
    # buildshim 里的 sitecustomize.py 会让父进程和 PyInstaller 隔离子进程
    # 都跳过会卡死的 platform/WMIC 探测（见该文件说明）
    shim = os.path.join(BASE, "tools", "buildshim")
    env["PYTHONPATH"] = os.pathsep.join(
        [shim, LIBS] + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    # 用专用启动器跑 PyInstaller：本机 platform.win32_ver() 会卡死，
    # 而 PyInstaller.compat 在 import 阶段就会调它（详见 tools/_run_pyinstaller.py）
    cmd = [
        sys.executable, "-B", os.path.join(BASE, "tools", "_run_pyinstaller.py"),
        "--noconfirm", "--clean",
        "--windowed",
        "--name", APP_NAME,
        "--distpath", dist_dir,
        "--workpath", os.path.join(BASE, "_buildtmp", "work"),
        "--specpath", os.path.join(BASE, "_buildtmp"),
        "--hidden-import", "PIL._tkinter_finder",
    ]
    for mod in BUILD_EXCLUDES:
        cmd += ["--exclude-module", mod]
    cmd.append(os.path.join(BASE, "main.py"))

    print("版本：%s" % VERSION)
    print("执行:", " ".join(cmd))
    rc = subprocess.call(cmd, env=env, cwd=BASE)
    if rc != 0:
        print("打包失败，返回码", rc)
        return rc

    exe = os.path.join(out_dir, APP_NAME + ".exe")
    if not os.path.exists(exe):
        alt = os.path.join(out_dir, "main.exe")
        if os.path.exists(alt):
            exe = alt
    if not os.path.exists(exe):
        print("没有找到生成的 exe")
        return 1
    print("exe:", exe)

    _stage_data(out_dir)
    _copy_docs(out_dir)

    if "--no-zip" not in argv:
        _make_zip(dist_dir, out_dir)

    print("\n完成：", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
