# -*- coding: utf-8 -*-
"""从 GitHub 拉增量更新。

仓库里放一份 update/manifest.json，长这样：

    {"version": "1.3.1",
     "files": {"main.py": {"sha256": "...", "size": 1234},
               "app/model.py": {"sha256": "...", "size": 5678}, ...}}

检查时只比 sha256：本地没有、或者哈希不一样的才下载，
所以「改了几个文件就只拉几个文件」——这就是增量更新。

打包成 exe 后也能用：更新的 .py 会写到 exe 旁边，
main.py 里装了 finder 让 exe 优先加载这些外部文件（见 _prefer_external_code）。
"""

import hashlib
import json
import os
import urllib.request

from .brand import APP_VERSION as VERSION

REPO = "hdwy001/skill-axis-endfield"
BRANCH = "main"
RAW_BASE = "https://raw.githubusercontent.com/%s/%s/" % (REPO, BRANCH)
MANIFEST_URL = RAW_BASE + "update/manifest.json"
USER_AGENT = "skill-axis-endfield-updater/1.0"

BACKUP_DIRNAME = "update_backup"


class UpdateError(Exception):
    """更新过程里的可读错误。"""


def http_get(url, timeout=15):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def fetch_manifest(timeout=12):
    try:
        raw = http_get(MANIFEST_URL, timeout=timeout)
    except Exception as exc:                     # 网络/404/证书都落到这里
        raise UpdateError("连不上 GitHub：%s" % exc)
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise UpdateError("manifest.json 不是合法 JSON")
    if not isinstance(data.get("files"), dict) or not data["files"]:
        raise UpdateError("manifest.json 里没有 files")
    return data


def parse_version(text):
    parts = []
    for chunk in str(text or "").replace("-", ".").split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def local_version():
    return VERSION


def is_newer(remote, local=None):
    return parse_version(remote) > parse_version(local or VERSION)


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_relpath(rel):
    """挡掉 ../ 和绝对路径。"""
    rel = str(rel).replace("\\", "/").strip()
    if not rel or rel.startswith("/") or ":" in rel:
        return None
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts or ".." in parts:
        return None
    return "/".join(parts)


def plan(manifest, base_dir):
    """算出需要下载的文件：[(相对路径, manifest 项)]。"""
    todo = []
    for rel, info in sorted(manifest.get("files", {}).items()):
        rel = safe_relpath(rel)
        if rel is None:
            continue
        want = str((info or {}).get("sha256", "")).lower()
        full = os.path.join(base_dir, *rel.split("/"))
        if not os.path.isfile(full):
            todo.append((rel, info))
            continue
        if not want:
            continue
        try:
            if file_hash(full) != want:
                todo.append((rel, info))
        except OSError:
            todo.append((rel, info))
    return todo


def download(rel, timeout=20):
    url = RAW_BASE + rel
    try:
        return http_get(url, timeout=timeout)
    except Exception as exc:
        raise UpdateError("下载 %s 失败：%s" % (rel, exc))


def apply(items, base_dir, on_progress=None, on_file=None):
    """下载并写入。返回 (写入文件数, 备份目录)。

    先全部下载到内存，全部成功才动磁盘，避免下到一半留下半套代码。
    """
    blobs = []
    total = len(items)
    for i, (rel, _info) in enumerate(items):
        if on_progress is not None:
            on_progress(i, total, rel)
        blobs.append((rel, download(rel)))
    if on_progress is not None:
        on_progress(total, total, "")

    stamp = _timestamp()
    backup_root = os.path.join(base_dir, BACKUP_DIRNAME, stamp)
    written = 0
    for rel, data in blobs:
        full = os.path.join(base_dir, *rel.split("/"))
        os.makedirs(os.path.dirname(full) or base_dir, exist_ok=True)
        if os.path.isfile(full):
            bak = os.path.join(backup_root, *rel.split("/"))
            os.makedirs(os.path.dirname(bak) or backup_root, exist_ok=True)
            try:
                with open(full, "rb") as src, open(bak, "wb") as dst:
                    dst.write(src.read())
            except OSError:
                pass
        tmp = full + ".new"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, full)
        written += 1
        if on_file is not None:
            on_file(rel, written, total)
    return written, backup_root


def _timestamp():
    import time
    return time.strftime("%Y%m%d-%H%M%S")
