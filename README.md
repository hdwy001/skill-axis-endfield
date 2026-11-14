# 技能轴提示器 · 明日方舟：终末地

一个**只读**的悬浮提示工具：事先把技能释放顺序排好，游戏里按对应按键，悬浮窗自动跳到下一个技能。

不注入游戏、不改内存、不模拟按键，只被动监听键盘/手柄。

---

## 特性

- **编队制**：一个编队 = N 条充能轴 + 1 条爆发轴，无限循环；每个编队有独立的 4 人队伍
- **长条悬浮窗**：一条横向流水线，从左到右即释放顺序；当前用琥珀描边框标出，按过的变暗
- **宽度自适应**：技能少就短，多就长；可拖边框**等比缩放**
- **透明度可调**：只影响底色，文字始终清晰（逐像素 alpha，非抠图）
- **按键规则照游戏**：
  - 键盘：技能=短按 `1~4`（按队伍位）、连携=`E`、终结=长按同数字
  - 手柄：连携=`RB`、战技=`LB` + `X/Y/A/B`
  - 手柄终结技**两种方式随便选**（照游戏内「终结技施放动作 2」开关）：长按战技键，或先按住终结键（默认 `RB`）+ 字母键
- **错按有反馈 + 容错**：按错会红圈闪一下并提示「现在应放什么」；
  点错到后面的技能会自动跳过去；技能键手抖按住超时也算（都可关）
- **重置**：`F8`、悬浮窗右上角「重」、编辑器「重置进度」三处入口，重置后保持原来的运行/暂停状态
- **编队拖动排序**：左栏编队标签块，单击切换、拖动换顺序、双击改名
- **队伍拖动换位**：队伍卡片可直接拖动，位置即按键 1~4（拖动会改按键映射）
- **高 DPI 清晰**：声明 DPI 感知 + 全布局按物理像素绘制，150% 缩放下不再被 Windows 拉伸糊化
- **自动保存**：改动 0.8 秒后落盘，切换编队/退出时立即保存
- **自动提权**：游戏常以管理员运行，程序会请求管理员权限（否则钩子收不到按键）

---

## 运行

需要 Python 3.10+ 和 Pillow。

```bash
pip install -r requirements.txt
python main.py
```

首次运行会自动下载技能图标与干员立绘：

```bash
python tools/fetch_icons.py
python tools/fetch_portraits.py
```

## 自测

```bash
python main.py --selftest     # 72 项逻辑自测
python main.py --smoke        # 构界面后自动关闭
```

## 打包成 exe

需要 PyInstaller（`pip install pyinstaller`）：

```bash
python tools/build_package.py
```

产物在 `dist/技能轴提示器/`，与 `data/` 同级即可免安装运行。

---

## 目录结构

```
main.py                 入口（--selftest / --smoke）
app/
  application.py        装配层：监听、手柄、播放器、编辑器、自动保存、提权
  overlay.py            悬浮窗（长条流水线，Pillow 合成 + 逐像素贴图）
  layeredwin.py         UpdateLayeredWindow 封装
  editor.py             编辑器：播放顺序 / 队伍 / 技能 / 技能轴
  model.py              数据模型与存储（Axis / Rotation / Team / Settings）
  player.py             播放状态机
  iconart.py            图标合成（技能 / 连携 / 终结三种样式）
  icons.py              图标库与立绘加载
  fonts.py              MiSans + 文字测宽 + Pillow 字体
  dpi.py                DPI 感知与逻辑/物理像素换算
  scaledcanvas.py       按 DPI 自动缩放的 Canvas（布局仍写逻辑像素）
  gamepad.py            XInput 手柄轮询
  padrouter.py          手柄按键 -> 动作判定（两种终结技方式）
  listener.py           键盘/鼠标钩子 + 轮询兜底
  elevation.py          管理员权限检测与提权
  settingsdialog.py     设置弹窗
  textdialog.py         命名弹窗
  selftest.py           自测
tools/                  抓素材 / 打包 / 设计稿渲染
```

---

## 使用提示

- 游戏必须**窗口化**或**无边框窗口**，独占全屏会盖住悬浮窗
- 请**以管理员身份运行**，否则游戏窗口获得焦点时收不到按键
- 快捷键：`F7` 开始/暂停　`F8` 重置　`F9` 显示/隐藏　`F10` 点击穿透

---

## 免责声明

本项目为个人辅助工具，与鹰角网络无关。

游戏图标、立绘等素材版权归**鹰角网络**所有，仓库中**不包含**这些素材，
由 `tools/fetch_icons.py` 在本地从 wiki 拉取，仅供个人搭配工具使用，请勿二次分发。

使用本工具产生的任何后果由使用者自行承担。
