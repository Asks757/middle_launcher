"""配置读取 / 校验 / 默认值。

配置文件是同目录下的 config.json，用户可以直接编辑（重启或托盘菜单「重新加载」生效）。
设计原则：任何字段缺失或写错都不能让程序起不来，一律回落到默认值。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("MIDDLE_LAUNCHER_CONFIG") or (APP_DIR / "config.json"))
LOG_PATH = APP_DIR / "launcher.log"
ASSETS_DIR = APP_DIR / "assets"

IS_WIN = os.name == "nt"

# ---------------------------------------------------------------- 默认外观

DEFAULT_APPEARANCE = {
    "radius": 132,          # 图标环半径（逻辑像素）
    "icon_size": 40,        # 单个图标尺寸
    "font_size": 9.5,         # 标签字号
    "dim": 0.22,            # 背景压暗强度 0~1
    "accent": "#4C8DFF",    # 悬停高亮色
    "bg": "#1B1D23",        # 环体颜色
    "bg_alpha": 236,        # 环体不透明度 0~255
    "text": "#EDEFF5",
    "follow": 0.0,          # 盘面跟随指针的比例 0=固定，越大越跟手
    "dead_zone": 0.34,      # 中心死区（相对半径），越小越灵敏
}

DEFAULT_TRIGGER = {
    "mode": "hold",         # hold=长按中键；click=单击中键立即弹出
    "hold_ms": 260,         # 长按判定阈值
    "button": "middle",     # middle / left / right / x1 / x2
    "hotkey": "ctrl+alt+space",
    "suppress": False,      # 仅 Windows 生效：吞掉中键事件，避免被其它程序响应
    "drag_guard": 26,       # 长按期间指针移动超过该像素数则视为拖拽，不弹菜单
}


# ---------------------------------------------------------------- 默认项目

def _first_command(*names: str) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def _xdg_dir(key: str, *fallbacks: str) -> str | None:
    """优先用 xdg-user-dir 拿到本地化目录（中文系统是 ~/下载），不存在则返回 None。"""
    try:
        out = subprocess.run(["xdg-user-dir", key], capture_output=True,
                             text=True, timeout=2).stdout.strip()
        if out and Path(out).is_dir():
            return out
    except Exception:
        pass
    for name in fallbacks:
        q = Path.home() / name
        if q.is_dir():
            return str(q)
    return None


def default_items() -> list[dict]:
    """按当前系统生成一组开箱即用的启动项。"""
    items: list[dict] = []
    if IS_WIN:
        profile = Path(os.environ.get("USERPROFILE", str(Path.home())))
        items = [
            {"label": "浏览器", "type": "url", "target": "https://www.bing.com", "color": "#4C8DFF"},
            {"label": "资源管理", "type": "command", "target": "explorer.exe", "color": "#F0B429"},
        ]
        for label, sub, color in (("下载", "Downloads", "#38B284"), ("桌面", "Desktop", "#8B7CF6")):
            p = profile / sub
            if p.is_dir():
                items.append({"label": label, "type": "folder", "target": str(p), "color": color})
        items += [
            {"label": "记事本", "type": "command", "target": "notepad.exe", "color": "#5AA9E6"},
            {"label": "终端", "type": "command", "target": "powershell.exe", "color": "#F06A6A"},
            {"label": "设置", "type": "config", "color": "#9AA3B2"},
        ]
    else:
        items = [
            {"label": "浏览器", "type": "url", "target": "https://www.bing.com", "color": "#4C8DFF"},
            {"label": "文件", "type": "folder", "target": str(Path.home()), "color": "#F0B429"},
        ]
        dl = _xdg_dir("DOWNLOAD", "Downloads", "下载")
        if dl:
            items.append({"label": "下载", "type": "folder", "target": dl, "color": "#38B284"})
        desk = _xdg_dir("DESKTOP", "Desktop", "桌面")
        if desk:
            items.append({"label": "桌面", "type": "folder", "target": desk, "color": "#8B7CF6"})
        term = _first_command("deepin-terminal", "gnome-terminal", "konsole",
                              "xfce4-terminal", "x-terminal-emulator", "xterm")
        if term:
            items.append({"label": "终端", "type": "command", "target": term, "color": "#F06A6A"})
        editor = _first_command("deepin-editor", "gedit", "kate", "xed", "mousepad", "pluma")
        if editor:
            items.append({"label": "编辑器", "type": "command", "target": editor, "color": "#5AA9E6"})
        shot = _first_command("deepin-screenshot", "gnome-screenshot", "spectacle", "flameshot")
        if shot:
            items.append({"label": "截图", "type": "command", "target": shot, "color": "#22B8CF"})
        items.append({"label": "设置", "type": "config", "color": "#9AA3B2"})
    return items


def default_config() -> dict:
    return {
        "version": 1,
        "appearance": dict(DEFAULT_APPEARANCE),
        "trigger": dict(DEFAULT_TRIGGER),
        "items": default_items(),
    }


# ---------------------------------------------------------------- 读 / 写

def _merge(base: dict, patch: dict) -> dict:
    out = dict(base)
    for k, v in (patch or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load(create_if_missing: bool = True) -> dict:
    if not CONFIG_PATH.exists():
        cfg = default_config()
        if create_if_missing:
            save(cfg)
        return cfg
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("配置文件根节点必须是对象")
    except Exception:
        # 坏文件备份一份，避免用户的手工修改被直接覆盖丢失
        try:
            shutil.copy2(CONFIG_PATH, CONFIG_PATH.with_suffix(".json.bad"))
        except Exception:
            pass
        cfg = default_config()
        save(cfg)
        return cfg

    cfg = _merge(default_config(), raw)
    items = cfg.get("items")
    if not isinstance(items, list) or not items:
        cfg["items"] = default_items()
    else:
        cfg["items"] = [i for i in items if isinstance(i, dict) and i.get("label")][:16]
        if not cfg["items"]:
            cfg["items"] = default_items()
    return cfg


def save(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def log(msg: str) -> None:
    """极简日志：追加写，超过 256KB 自动截断。"""
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 256 * 1024:
            LOG_PATH.write_text("", encoding="utf-8")
        import datetime
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:
        pass
