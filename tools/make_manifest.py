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
INCLUDE_DIRS = ("app",)
INCLUDE_FILES = ("main.py", "使用说明.md", "启动说明.txt")
SKIP_DIRS = ("__pycache__",)


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def collect():
    """返回 {相对路径: 绝对路径}。"""
    found = {}
    for name in INCLUDE_FILES:
        full = os.path.join(BASE, name)
        if os.path.isfile(full):
            found[name] = full
    for folder in INCLUDE_DIRS:
        root = os.path.join(BASE, folder)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for filename in filenames:
                if not filename.endswith((".py", ".json", ".md")):
                    continue
                full = os.path.join(dirpath, filename)
                rel = os.path.relpath(full, BASE).replace(os.sep, "/")
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
            "size": os.path.getsize(full),
        }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    total = sum(item["size"] for item in payload["files"].values())
    print("版本 %s：%d 个文件，共 %.1f KB" % (APP_VERSION, len(files), total / 1024.0))
    print("已写入", OUT_FILE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
