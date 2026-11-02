"""全局触发：鼠标按键 / 快捷键。

- 长按模式（默认）：按住中键超过 hold_ms 才弹出菜单，松手时执行指针所在项。
  这样单击中键仍然交给系统（浏览器新标签、X11 中键粘贴等）不受影响。
- 单击模式：按下即弹出，点选后执行，适合不想按住的人。
- 快捷键：始终注册，作为中键不可用时的兜底（Wayland 下尤其有用）。
"""
from __future__ import annotations

import os
from PySide6.QtCore import QObject, QTimer, Signal

from config import IS_WIN, log

_MODS = {
    "ctrl": "<ctrl>", "control": "<ctrl>",
    "alt": "<alt>", "option": "<alt>",
    "shift": "<shift>",
    "win": "<cmd>", "super": "<cmd>", "meta": "<cmd>", "cmd": "<cmd>",
}


def parse_hotkey(text: str) -> str | None:
    """"ctrl+alt+space" -> "<ctrl>+<alt>+space"，可直接交给 pynput。"""
    if not text:
        return None
    parts = [p.strip().lower() for p in str(text).replace(" ", "").split("+") if p.strip()]
    if not parts:
        return None
    key = parts[-1]
    mods = [_MODS[m] for m in parts[:-1] if m in _MODS]
    if len(key) == 1:
        key_part = key
    elif key.startswith("f") and key[1:].isdigit():
        key_part = f"<{key}>"
    elif key in ("space", "enter", "tab", "esc", "escape", "insert", "delete", "home", "end",
                 "page_up", "page_down", "up", "down", "left", "right"):
        key_part = "<" + ("esc" if key == "escape" else key) + ">"
    else:
        return None
    return "+".join(mods + [key_part])


class Trigger(QObject):
    activated = Signal(str)      # "hold" / "click" / "hotkey"
    released = Signal()          # 中键松开（仅长按模式需要）

    _raw_press = Signal()
    _raw_release = Signal()
    _raw_hotkey = Signal()

    def __init__(self, cfg: dict | None = None, parent: QObject | None = None):
        super().__init__(parent)
        cfg = cfg or {}
        self.mode = str(cfg.get("mode", "hold")).lower()
        self.hold_ms = max(80, int(cfg.get("hold_ms", 260) or 260))
        self.button = str(cfg.get("button", "middle")).lower()
        self.hotkey_text = str(cfg.get("hotkey", "") or "")
        self.suppress = bool(cfg.get("suppress", False)) and IS_WIN
        self.drag_guard = int(cfg.get("drag_guard", 26) or 0)

        self._mouse_listener = None
        self._hotkey_listener = None
        self._down = False
        self._press_pos = (0, 0)
        self.error = ""

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.hold_ms)
        self._timer.timeout.connect(self._on_hold)

        self._raw_press.connect(self._on_press)
        self._raw_release.connect(self._on_release)
        self._raw_hotkey.connect(lambda: self.activated.emit("hotkey"))

    # ------------------------------------------------------------ 生命周期

    def start(self) -> bool:
        if not self._start_mouse():
            return False
        self._start_hotkey()
        return True

    def stop(self) -> None:
        for attr in ("_mouse_listener", "_hotkey_listener"):
            listener = getattr(self, attr)
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
                setattr(self, attr, None)

    # ------------------------------------------------------------ 鼠标

    def _start_mouse(self) -> bool:
        try:
            from pynput import mouse
        except Exception as e:                       # 没有 X11 / 缺少 python-xlib
            self.error = f"无法监听鼠标：{e}"
            log(self.error)
            return False
        try:
            btn = getattr(mouse.Button, self.button, mouse.Button.middle)
            self._listener_button = btn
            self._mouse_listener = mouse.Listener(on_click=self._on_click)
            self._mouse_listener.daemon = True
            self._mouse_listener.start()
            log(f"鼠标监听已启动：button={self.button} mode={self.mode} suppress={self.suppress}")
            return True
        except Exception as e:
            self.error = f"鼠标监听启动失败：{e}"
            log(self.error)
            return False

    def _on_click(self, x, y, button, pressed):
        try:
            if button != getattr(self, "_listener_button", None):
                return True
            if pressed:
                self._press_pos = (x, y)
                self._raw_press.emit()
            else:
                self._raw_release.emit()
        except Exception as e:
            log(f"鼠标回调异常：{e}")
            return True
        # 仅 Windows 下 pynput 支持吞掉事件
        return not self.suppress

    def _on_hold(self) -> None:
        """长按达到阈值：若期间指针大幅移动（多半是拖拽），就不弹菜单。"""
        if self.drag_guard > 0:
            try:
                from PySide6.QtGui import QCursor, QGuiApplication
                dpr = float(QGuiApplication.primaryScreen().devicePixelRatio() or 1.0)
                px, py = self._press_pos[0] / dpr, self._press_pos[1] / dpr
                pos = QCursor.pos()
                if abs(pos.x() - px) + abs(pos.y() - py) > self.drag_guard:
                    log("长按期间指针移动较大，判定为拖拽，忽略")
                    return
            except Exception:
                pass
        self.activated.emit("hold")

    def _on_press(self) -> None:
        if self._down:
            return
        self._down = True
        if self.mode == "click":
            self.activated.emit("click")
        else:
            self._timer.start()

    def _on_release(self) -> None:
        self._down = False
        if self._timer.isActive():
            self._timer.stop()          # 快速点击：不弹菜单，保持系统原生行为
            return
        self.released.emit()

    # ------------------------------------------------------------ 快捷键

    def _start_hotkey(self) -> None:
        combo = parse_hotkey(self.hotkey_text)
        if not combo:
            return
        try:
            from pynput import keyboard
            self._hotkey_listener = keyboard.GlobalHotKeys(
                {combo: lambda: self._raw_hotkey.emit()}
            )
            self._hotkey_listener.daemon = True
            self._hotkey_listener.start()
            log(f"快捷键已注册：{combo}")
        except Exception as e:
            log(f"快捷键注册失败（{combo}）：{e}")
            self._hotkey_listener = None
