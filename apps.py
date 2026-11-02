"""从系统里收集可用程序，供设置界面的「添加程序」选择器使用。

Linux：解析 .desktop（目标直接存 .desktop 路径，交给 core.launch_desktop_file 启动）
Windows：扫描开始菜单里的 .lnk 快捷方式
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from config import IS_WIN

_cache: list[dict] | None = None

_EXEC_FIELD = re.compile(r"%[fFuUdDnNickvm]")


def _desktop_dirs() -> list[Path]:
    home = Path.home()
    return [p for p in (
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        Path("/var/lib/flatpak/exports/share/applications"),
        Path("/var/lib/snapd/desktop/applications"),
        home / ".local/share/applications",
        home / ".local/share/flatpak/exports/share/applications",
    ) if p.is_dir()]


def _parse_desktop(path: Path) -> dict | None:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None

    name = name_loc = icon = exec_line = None
    nodisplay = hidden = False
    typ = "Application"
    in_entry = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            in_entry = line == "[Desktop Entry]"
            continue
        if not in_entry or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if key == "Type":
            typ = val
        elif key == "Name":
            name = val
        elif key.startswith("Name[zh_CN]"):
            name_loc = val
        elif key == "Icon":
            icon = val
        elif key == "Exec":
            exec_line = val
        elif key == "NoDisplay":
            nodisplay = val.lower() == "true"
        elif key == "Hidden":
            hidden = val.lower() == "true"

    if typ != "Application" or nodisplay or hidden:
        return None
    label = (name_loc or name or "").strip()
    if not label or not exec_line:
        return None
    return {
        "label": label,
        "type": "file",          # .desktop 会被 core.open_path 识别并解析 Exec
        "target": str(path),
        "icon": (icon or "").strip(),
        "_name_raw": (name or "").strip(),
    }


def _scan_linux() -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for d in _desktop_dirs():
        for f in sorted(d.glob("*.desktop")):
            item = _parse_desktop(f)
            if not item:
                continue
            key = item["label"].lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(item)
    return out


def _scan_windows() -> list[dict]:
    roots: list[Path] = []
    for env in ("PROGRAMDATA", "APPDATA"):
        base = os.environ.get(env)
        if base:
            roots.append(Path(base) / "Microsoft/Windows/Start Menu/Programs")
    out: list[dict] = []
    seen: set[str] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for f in root.rglob("*.lnk"):
            label = f.stem
            if label.lower().startswith(("uninstall", "卸载")):
                continue
            if label.lower() in seen:
                continue
            seen.add(label.lower())
            out.append({"label": label, "type": "file", "target": str(f), "icon": str(f)})
    return out


def scan_apps(refresh: bool = False) -> list[dict]:
    global _cache
    if _cache is not None and not refresh:
        return _cache
    try:
        apps = _scan_windows() if IS_WIN else _scan_linux()
    except Exception:
        apps = []
    apps.sort(key=lambda a: a["label"].lower())
    _cache = apps
    return apps
