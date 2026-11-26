# -*- coding: utf-8 -*-
"""生成增量更新清单 update/manifest.json。

用法：
    python tools/make_manifest.py

清单结构：
    {"version": "1.1.0",
     "files": {"main.py": {"sha256": "...", "size": 1234}, ...}}

客户端只下载「本地缺失 / sha256 不一致」的文件，所以改几个文件就只拉几个。
只收录代码与说明文档，不收 data/ 下的图标立绘（体积大、且属游戏素材）。
"""
import hashlib
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

from app.brand import APP_VERSION, APP_TITLE  # noqa: E402

OUT_DIR = os.path.join(BASE, "update")
OUT_FILE = os.path.join(OUT_DIR, "manifest.json")
REPO = "hdwy001/skill-axis-endfield"

# 参与增量更新的文件（相对项目根，统一用 / 分隔）
#   2026-11-27：把 data/ 下的素材也纳入，这样「新增干员」只要改图标/立绘/清单
#   就能通过应用内「检查更新」拉到，不用重下整个安装包。
#   注意：运行期私有数据（axes/rotations/team/settings.json）绝不能进清单，
#   所以这里只列明确的两个素材目录，不做整棵 data/ 的遍历。
INCLUDE_DIRS = (
    ("app", (".py", ".json", ".md")),
    ("data/icons", (".png", ".json")),
    ("data/portraits", (".png", ".json")),
)
INCLUDE_FILES = ("main.py", "使用说明.md", "启动说明.txt", "data/forms.json")
SKIP_DIRS = ("__pycache__",)
# 这些是每台机器各自的运行状态，绝不进清单
PRIVATE_FILES = ("data/axes.json", "data/rotations.json",
                 "data/team.json", "data/settings.json")

# 只有文本文件才需要把工作区的 CRLF 折成 LF；图片等二进制必须原字节上传/比对
TEXT_EXTS = (".py", ".md", ".json", ".txt", ".bat", ".cfg", ".toml",
             ".yml", ".yaml", ".spec")


def published_bytes(path):
    """GitHub 上实际会下发的字节。

    文本文件：仓库里存的是 LF，git 的 autocrlf 只在工作区把它转成 CRLF，
    所以清单必须按「去掉 CR」后的内容算 —— 否则 Windows 上生成的清单
    和客户端真正下载到的文件永远对不上，增量更新会每次都全量重下。

    二进制文件（png/ico）：**绝不能做换行替换**，PNG 字节里出现 0d 0a 是常态，
    替换会直接毁掉图片哈希（客户端每次都以为文件变了）。
    """
    with open(path, "rb") as f:
        data = f.read()
    if path.lower().endswith(TEXT_EXTS) and b"\r\n" in data:
        data = data.replace(b"\r\n", b"\n")
    return data


def sha256_of(path):
    return hashlib.sha256(published_bytes(path)).hexdigest()


def collect():
    """返回 {相对路径: 绝对路径}。"""
    found = {}
    for name in INCLUDE_FILES:
        full = os.path.join(BASE, name)
        if os.path.isfile(full):
            found[name] = full
    for folder, exts in INCLUDE_DIRS:
        root = os.path.join(BASE, folder)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for filename in filenames:
                if not filename.lower().endswith(exts):
                    continue
                full = os.path.join(dirpath, filename)
                rel = os.path.relpath(full, BASE).replace(os.sep, "/")
                if rel in PRIVATE_FILES:
                    continue
                found[rel] = full
    return found


def main():
    files = collect()
    if not files:
        print("没有找到可发布的文件")
        return 1
    payload = {
        "version": APP_VERSION,
        "app": APP_TITLE,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "repo": REPO,
        "files": {},
    }
    for rel in sorted(files):
        full = files[rel]
        payload["files"][rel] = {
            "sha256": sha256_of(full),
            "size": len(published_bytes(full)),
        }
    # 安全检查：私有运行数据绝不能进清单（否则更新会覆盖别人的编队/设置）
    leaked = sorted(rel for rel in payload["files"] if rel in PRIVATE_FILES)
    if leaked:
        print("拒绝生成：清单里混进了私有数据 %s" % leaked)
        return 2
    icons = sum(1 for rel in payload["files"]
                if rel.startswith("data/icons/") and rel.endswith(".png"))
    portraits = sum(1 for rel in payload["files"]
                    if rel.startswith("data/portraits/") and rel.endswith(".png"))

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    total = sum(item["size"] for item in payload["files"].values())
    print("版本 %s：%d 个文件，共 %.1f KB" % (APP_VERSION, len(files), total / 1024.0))
    print("  其中图标 %d 张、立绘 %d 张（新增干员走增量更新只需拉这几张）"
          % (icons, portraits))
    print("已写入", OUT_FILE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
