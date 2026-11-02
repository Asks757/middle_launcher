# 中键启动器 (Middle Launcher)

按住鼠标中键 0.3 秒，屏幕上的光标处会展开一个环形菜单，朝想要的方向松开，就打开对应的程序、文件、文件夹或网址。全程手不离鼠标。

Windows 10/11 与 Linux（X11 / Wayland）通用，同一套代码、同一份配置。

```
        浏览器
    终端   ○   文件
      设置   下载
        桌面
```

## 特性

- **图形化设置**：启动项、外观、触发方式都能点点鼠标改，右侧实时预览
- **跟随指针**：盘面会朝鼠标方向轻微平移，拖动时更贴手（可调，也可关掉）
- **长按触发**，单击中键仍然保留系统原生行为（浏览器新标签、X11 中键粘贴等）
- 扇形按主色区分，悬停高亮，中心实时显示目标路径
- 自动取用系统真实图标（文件夹、文档、程序），取不到时用文字色块兜底
- 全屏轻微压暗，聚焦菜单，Esc / 点空白处取消
- 贴边自动内收，多屏时出现在光标所在屏幕
- 托盘菜单：打开菜单、编辑配置、重新加载、开机自启、日志、退出
- 单实例：文件锁 + 本地套接字双保险，重复启动只会唤出已有实例，不会叠出两个转盘
- 快捷键 `Ctrl+Alt+Space` 兜底，适合没有中键的鼠标 / Wayland 环境

## 安装位置

源码、配置、图标都在 `middle_launcher` 目录中。Linux 下可用安装脚本创建运行环境；Windows 下运行 `install_windows.bat` 建环境。

## 安装

### Linux

```bash
bash install.sh
```

脚本会：创建 `.venv` 并装依赖 → 生成图标 → 自检 → 在桌面和应用菜单创建「中键启动器」图标 → 加入开机自启 → 启动程序。

依赖：Python ≥ 3.9（需带 venv）。Debian/UOS/Ubuntu 若缺：`sudo apt install python3 python3-venv`。

### Windows

1. 安装 Python 3.9+（安装时勾选 **Add python.exe to PATH**）
2. 双击 `install_windows.bat`

脚本会创建 `.venv`、装依赖、在桌面生成 `Middle Launcher` 快捷方式并启动。之后双击该快捷方式即可。

## 图形化设置

托盘菜单 → **设置…**，或桌面上的「中键启动器 设置」图标，或命令行 `python app.py --settings`。

| 页签 | 能改什么 |
| --- | --- |
| **启动项** | 添加程序（从系统应用列表里搜）、文件、文件夹、网址；拖动排序；改名称/类型/目标/参数/主色/图标；直接把文件从文件管理器拖进列表即可添加 |
| **外观** | 转盘半径、图标与文字大小、中心死区、跟随指针强度、三处配色、盘面透明度、背景压暗 |
| **触发与行为** | 长按或单击、长按阈值、拖拽判定、备用快捷键、开机自启、Windows 中键拦截 |

右侧的预览和真实菜单用的是**同一套绘制代码**，鼠标移到预览的扇区上也会高亮，改完参数立刻能看到效果。点「保存并应用」写入 `config.json` 并热重载，不用重启程序。

## 用法

| 操作 | 效果 |
| --- | --- |
| **按住中键 ≥0.3 秒** | 菜单弹出，移动高亮，**松开即打开** |
| 快捷键 `Ctrl+Alt+Space` | 菜单弹出并保持，**左键点选** |
| 松开时停在中心 | 取消 |
| 按住中键朝某方向移动 | 转盘位置保持固定，对应扇区高亮 |
| Esc / 右键 / 点空白处 | 取消 |
| 数字键 1–9 | 直接打开第 N 项 |
| 托盘图标左键 | 打开菜单 |

**为什么是"长按"？** 单击中键在浏览器里是"新标签打开链接"、在 Linux 终端里是"粘贴"，全局抢走会很难用。长按 0.3 秒既能区分意图，也不影响原有习惯。嫌慢可以把 `hold_ms` 调小；想改成"按下即弹出"就把 `mode` 改成 `click`。

## 配置文件

位置：`config.json`（与 `app.py` 同目录）。改完在托盘菜单点「重新加载配置」，或命令行 `python app.py --reload`。

### 启动项

```json
{
  "items": [
    {"label": "浏览器", "type": "url",    "target": "https://www.bing.com", "color": "#4C8DFF"},
    {"label": "项目",   "type": "folder", "target": "~/work/demo"},
    {"label": "文档",   "type": "file",   "target": "~/Desktop/周报.docx"},
    {"label": "终端",   "type": "command","target": "deepin-terminal", "args": ["-w", "new"]},
    {"label": "设置",   "type": "config"}
  ]
}
```

| 字段 | 说明 |
| --- | --- |
| `label` | 菜单里显示的名字（≤6 字最佳） |
| `type` | `url` / `file` / `folder` / `command` / `config` / `auto`（按 target 猜） |
| `target` | 网址、路径或命令；支持 `~`、`$HOME`、`%USERPROFILE%` |
| `args` | 仅 `command` 用，参数数组 |
| `color` | 扇形颜色，如 `#4C8DFF`，省略则按名字自动分配 |
| `icon` | 可选，图标文件路径或系统主题图标名 |

最多 12 项；超过 8 项时自动隐藏扇形标签，改在中心显示。Linux 下将 `.sh` 添加为 `file` 或 `command` 都会通过 Bash 运行，脚本无需额外添加执行权限。

### 触发方式

```json
"trigger": {
  "mode": "hold",        // hold=长按 / click=单击立即弹出
  "hold_ms": 260,        // 长按判定阈值（毫秒）
  "button": "middle",    // middle / left / right / x1 / x2
  "hotkey": "ctrl+alt+space",
  "suppress": false,     // 仅 Windows：吞掉中键事件（默认关，避免影响其它软件）
  "drag_guard": 26       // 长按期间指针位移超过该像素数则判定为拖拽，不弹菜单
}
```

### 外观

```json
"appearance": {
  "radius": 132,       // 图标环半径
  "icon_size": 40,
  "font_size": 9.5,
  "dim": 0.22,         // 背景压暗 0~1
  "bg": "#1B1D23",     // 圆盘底色
  "bg_alpha": 236,     // 0~255
  "accent": "#4C8DFF",
  "text": "#EDEFF5",
  "follow": 0,         // 盘面跟随指针的比例，0=固定（默认），越大越贴手
  "dead_zone": 0.34    // 中心死区（相对半径），越小越灵敏
}
```

## 命令行

```bash
python app.py              # 启动（已在运行时只唤出菜单）
python app.py --show       # 立即弹出菜单
python app.py --settings   # 打开可视化设置（--edit 同义）
python app.py --json       # 用外部编辑器打开 config.json
python app.py --reload     # 重新加载配置
python app.py --quit       # 退出
python app.py --autostart-on / --autostart-off   # 开机自启开关
```

## 常见问题

**按中键没反应？**
① 确认托盘里有图标（程序在运行）；② 是否是"按住"而不是"点一下"；③ 鼠标驱动（罗技 G HUB 等）可能占用了中键，把中键释放出来；④ 长按时如果手在移动，会被判定为拖拽（`drag_guard`），把数值调大或设为 0 可关闭该保护。

**Wayland 下能监听鼠标吗？**
合成器通常不允许全局抓取鼠标。此时用快捷键 `Ctrl+Alt+Space`，或把系统快捷键（如 `Super+Space`）绑到 `python app.py --show`。托盘与菜单本身在 Wayland 下正常。

**提示 `libxcb-util.so.1` 缺失？**
`sudo apt install libxcb-util1`。本目录 `libs/` 已内置该库，启动时会自动加载。

**想让转盘跟随鼠标？**
① 默认固定转盘位置；在「设置 → 外观 → 跟随指针」中调大数值可开启跟随；
② 「中心死区」调小，指针稍动就能选中扇区；
③ 如果屏幕上同时出现两个转盘——多半是有旧版本残留进程在跑，执行 `python app.py --quit` 后重新启动。新版本用文件锁保证同机只有一个实例。

**菜单卡顿 / 变形？**
`appearance.radius` 过大时可能超出小屏，程序会自动内收，但建议 `radius` 不超过屏高的 1/6。

**出问题看日志**：`launcher.log`（托盘菜单「打开日志」）。

## 目录结构

```
middle_launcher/
├── app.py            # 入口：托盘、单实例锁、菜单调度
├── settings.py       # 图形化设置窗口（含实时预览、程序选择器）
├── render.py         # 环形菜单的几何与绘制（菜单与预览共用）
├── menu.py           # 菜单窗口：跟手、悬停、点选
├── apps.py           # 扫描系统应用列表（.desktop / .lnk）
├── trigger.py        # 全局中键 / 快捷键监听
├── icons.py          # 图标解析与兜底
├── core.py           # 启动程序、开机自启
├── config.py         # 配置读写与默认值
├── config.json       # 你的配置
├── assets/           # 图标
├── libs/             # 精简系统缺失的 xcb 库（Linux）
├── tools/            # 图标生成、Windows 快捷方式
├── install.sh        # Linux 安装
├── install_windows.bat
└── launcher.log
```

## 卸载

```bash
# Linux：先退出程序，再删快捷方式，最后整个程序目录一起删掉
cd /path/to/middle_launcher && python app.py --quit
rm -f ~/.config/autostart/middle_launcher.desktop \
      ~/Desktop/中键启动器.desktop ~/Desktop/中键启动器-设置.desktop \
      ~/.local/share/applications/middle_launcher.desktop \
      ~/.local/share/applications/middle_launcher-settings.desktop
rm -rf /path/to/middle_launcher      # 程序本体 + .venv + 配置
```

Windows：托盘菜单退出，删除整个程序文件夹、桌面快捷方式，以及
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\middle_launcher.vbs`。
