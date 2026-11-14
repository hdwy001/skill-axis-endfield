# -*- coding: utf-8 -*-
"""技能图标加载与缓存。

图标文件放在 data/icons/ 目录，节点里存文件名（或绝对路径）。
优先用 Pillow 做高质量缩放；没有 Pillow 时退回 Tk 原生加载。
"""
import json
import os
import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageTk
    _HAS_PIL = True
except Exception:  # pragma: no cover
    _HAS_PIL = False

from .iconart import compose, compose_combo, compose_portrait, element_rgb
from . import dpi

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")

# 已执行过的图标压暗到这个亮度倍数
DIMMED = 0.45


def _dim(im, factor):
    """等比压暗一张 RGBA 图。"""
    r, g, b, a = im.split()
    r = r.point(lambda v: int(v * factor))
    g = g.point(lambda v: int(v * factor))
    b = b.point(lambda v: int(v * factor))
    return Image.merge("RGBA", (r, g, b, a))


def _circle_mask(im):
    """把方形图裁成圆形，边缘用超采样做抗锯齿。"""
    w, h = im.size
    d = min(w, h)
    im = im.crop(((w - d) // 2, (h - d) // 2, (w - d) // 2 + d, (h - d) // 2 + d))
    ss = 4
    mask = Image.new("L", (d * ss, d * ss), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d * ss - 1, d * ss - 1), fill=255)
    mask = mask.resize((d, d), Image.LANCZOS)
    out = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    out.paste(im, (0, 0), mask)
    return out


class IconStore:
    def __init__(self, base_dir):
        self.dir = os.path.join(base_dir, "data", "icons")
        self.portrait_dir = os.path.join(base_dir, "data", "portraits")
        for d in (self.dir, self.portrait_dir):
            try:
                os.makedirs(d, exist_ok=True)
            except OSError:
                pass
        self._cache = {}
        self._meta = None

    # ---------- 路径 ----------
    def resolve(self, value):
        if not value:
            return None
        path = value if os.path.isabs(value) else os.path.join(self.dir, value)
        return path if os.path.isfile(path) else None

    def store_name(self, path):
        """若文件在 icons 目录内，只存文件名，方便整个项目拷走。"""
        try:
            rel = os.path.relpath(path, self.dir)
            if not rel.startswith(".."):
                return rel.replace("\\", "/")
        except ValueError:
            pass
        return path

    def list_files(self):
        try:
            return sorted(f for f in os.listdir(self.dir)
                          if f.lower().endswith(IMAGE_EXTS))
        except OSError:
            return []

    def manifest(self):
        """读取图标库清单；没有清单时把目录里所有图片当作自定义图标。"""
        path = os.path.join(self.dir, "index.json")
        data = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or []
        except (OSError, ValueError):
            data = []
        known = {d.get("file") for d in data}
        for name in self.list_files():
            if name in known:
                continue
            data.append({
                "file": name,
                "cn": os.path.splitext(name)[0],
                "en": "",
                "kind": "custom",
                "kind_cn": "自定义",
                "skill": "",
            })
        return data

    def meta(self, value):
        """返回某张图标的元数据（稀有度/职业/属性等）。"""
        if not value:
            return {}
        if self._meta is None:
            self._meta = {}
            for entry in self.manifest():
                key = entry.get("file")
                if key:
                    self._meta[key] = entry
        return self._meta.get(value, {})

    def refresh_meta(self):
        self._meta = None

    # ---------- 干员维度查询 ----------
    def skills_of(self, cn):
        """返回 {skill/combo/ult: 文件名}。"""
        out = {}
        if not cn:
            return out
        for entry in self.manifest():
            if entry.get("cn") == cn:
                out[entry.get("kind", "custom")] = entry.get("file", "")
        return out

    def icon_for(self, cn, kind):
        return self.skills_of(cn).get(kind, "")

    def element_of(self, cn):
        for entry in self.manifest():
            if entry.get("cn") == cn:
                return entry.get("element", "")
        return ""

    def accent_for(self, element="", cn=""):
        """干员/元素对应的强调色。"""
        if not element and cn:
            element = self.element_of(cn)
        r, g, b = element_rgb(element)
        return "#%02x%02x%02x" % (r, g, b)

    # ---------- 立绘 ----------
    def portrait_path(self, value):
        """找该图标所属干员的立绘。"""
        meta = self.meta(value)
        cn = meta.get("cn") or os.path.splitext(os.path.basename(value or ""))[0]
        if not cn:
            return None
        path = os.path.join(self.portrait_dir, cn + ".png")
        if os.path.isfile(path):
            return path
        # 立绘文件名可能是中文，也可能是英文
        en = meta.get("en")
        if en:
            alt = os.path.join(self.portrait_dir, en + ".png")
            if os.path.isfile(alt):
                return alt
        return None

    # ---------- 合成最终图标 ----------
    def _px(self, size):
        """逻辑尺寸 -> 物理像素（高 DPI 下图标才不发虚）。"""
        return max(10, int(round(float(size) * dpi.factor())))

    def render_portrait(self, cn, size, dim=False):
        """只要干员头像，不带右下角技能图标。队伍栏用。"""
        path = self.portrait_path_cn(cn)
        if not path:
            return None
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            return None
        size = self._px(size)
        element = self.element_of(cn)
        key = ("portrait", path, size, element, bool(dim), stamp)
        if key in self._cache:
            return self._cache[key]
        try:
            im = compose_portrait(path, size, element)
            if dim:
                im = _dim(im, DIMMED)
            photo = ImageTk.PhotoImage(im)
        except Exception:
            photo = None
        self._cache[key] = photo
        return photo

    def portrait_path_cn(self, cn):
        """按中文名找立绘。"""
        if not cn:
            return None
        path = os.path.join(self.portrait_dir, cn + ".png")
        return path if os.path.isfile(path) else None

    def render_pil(self, value, size, dim=False):
        """返回 PIL RGBA 图（给逐像素透明绘制用）。"""
        path = self.resolve(value)
        if not path:
            return None
        meta = self.meta(value)
        kind = meta.get("kind", "custom")
        element = meta.get("element", "")
        size = max(8, int(size))
        key = ("pil", path, size, kind, element, bool(dim))
        if key in self._cache:
            return self._cache[key]
        try:
            if kind == "combo":
                portrait = self.portrait_path(os.path.basename(path)) or ""
                im = compose_combo(portrait, path, size, element)
            elif kind == "ult":
                im = compose(path, size, element, "ult")
            else:
                im = compose(path, size, element, "skill")
            if dim:
                im = _dim(im, DIMMED)
        except Exception:
            im = None
        self._cache[key] = im
        return im

    def portrait_pil(self, cn, size, dim=False):
        path = self.portrait_path_cn(cn)
        if not path:
            return None
        size = max(8, int(size))
        element = self.element_of(cn)
        key = ("pilportrait", path, size, element, bool(dim))
        if key in self._cache:
            return self._cache[key]
        try:
            im = compose_portrait(path, size, element)
            if dim:
                im = _dim(im, DIMMED)
        except Exception:
            im = None
        self._cache[key] = im
        return im

    def render(self, value, size, dim=False):
        """按图标类型合成游戏样式，返回可直接画的 PhotoImage。

        技能 / 自定义 -> 暗底 + 底部扇形
        连携          -> 立绘圆盘 + 右下角小图标
        终结技        -> 整个圆填元素色
        """
        path = self.resolve(value)
        if not path:
            return None
        meta = self.meta(value)
        kind = meta.get("kind", "custom")
        element = meta.get("element", "")
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            return None

        size = self._px(size)
        key = (path, size, kind, element, bool(dim), stamp)
        if key in self._cache:
            return self._cache[key]

        image = self._compose(path, size, kind, element, dim)
        self._cache[key] = image
        return image

    def _compose(self, path, size, kind, element, dim):
        if not _HAS_PIL:
            return self.get(os.path.basename(path), size)
        try:
            if kind == "combo":
                portrait = self.portrait_path(os.path.basename(path)) or ""
                im = compose_combo(portrait, path, size, element)
            elif kind == "ult":
                im = compose(path, size, element, "ult")
            else:
                im = compose(path, size, element, "skill")
            if dim:
                im = _dim(im, DIMMED)
            return ImageTk.PhotoImage(im)
        except Exception:
            return None

    # ---------- 加载 ----------
    def get(self, value, size, circle=False):
        path = self.resolve(value)
        if not path:
            return None
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            return None
        key = (path, int(size), stamp, bool(circle))
        if key in self._cache:
            return self._cache[key]
        image = self._load(path, size, circle)
        # 缓存住引用，避免 Tk 图片被回收后显示空白
        self._cache[key] = image
        return image

    def _load(self, path, size, circle=False):
        size = max(8, int(size))
        if _HAS_PIL:
            try:
                im = Image.open(path).convert("RGBA")
                im.thumbnail((size, size), Image.LANCZOS)
                if circle:
                    im = _circle_mask(im)
                return ImageTk.PhotoImage(im)
            except Exception:
                return None
        try:
            photo = tk.PhotoImage(file=path)
        except Exception:
            return None
        factor = max(1, int(max(photo.width(), photo.height()) / size))
        if factor > 1:
            photo = photo.subsample(factor, factor)
        return photo
