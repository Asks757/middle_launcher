"""与界面无关的系统能力：启动程序 / 打开文件 / 开机自启。

Windows 与 Linux（X11、Wayland 均可）用同一套代码，差异只在这里收敛。
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

from config import APP_DIR, CONFIG_PATH, IS_WIN, log


class LaunchError(Exception):
    pass


# ---------------------------------------------------------------- 基础工具

def expand(value: str) -> str:
    """展开 ~、$HOME、%USERPROFILE% 等。"""
    if not value:
        return ""
    try:
        return os.path.expandvars(os.path.expanduser(str(value)))
    except Exception:
        return str(value)


def spawn(argv: list[str], cwd: str | None = None) -> None:
    """脱离父进程启动，避免本程序退出时把子进程一起带走。"""
    if not argv:
        raise LaunchError("命令为空")
    kwargs: dict = {}
    if IS_WIN:
        kwargs["creationflags"] = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
        kwargs["close_fds"] = True
    else:
        kwargs["start_new_session"] = True
        kwargs["stdin"] = subprocess.DEVNULL
        kwargs["stdout"] = subprocess.DEVNULL
        kwargs["stderr"] = subprocess.DEVNULL
    try:
        subprocess.Popen(argv, cwd=cwd, **kwargs)
    except FileNotFoundError as e:
        raise LaunchError(f"找不到可执行文件：{argv[0]}") from e
    except OSError as e:
        raise LaunchError(f"启动失败：{e}") from e


def open_url(url: str) -> None:
    if IS_WIN:
        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return
        except OSError as e:
            raise LaunchError(f"无法打开链接：{e}") from e
    spawn(["xdg-open", url])


def run_shell_script(path: Path, args: list[str] | None = None) -> None:
    spawn(["/bin/bash", str(path)] + list(args or []), cwd=str(path.parent))


def open_path(path: str) -> None:
    p = Path(expand(path))
    if not p.exists():
        raise LaunchError(f"路径不存在：{p}")
    if p.suffix.lower() == ".desktop":
        launch_desktop_file(p)
        return
    if p.suffix.lower() == ".sh" and not IS_WIN:
        run_shell_script(p)
        return
    if IS_WIN:
        try:
            os.startfile(str(p))  # type: ignore[attr-defined]
            return
        except OSError as e:
            raise LaunchError(f"无法打开：{e}") from e
    spawn(["xdg-open", str(p)])


def _split_command(target: str) -> list[str]:
    t = target.strip()
    if Path(t).exists():          # 整串就是一个可执行文件路径（含空格也安全）
        return [t]
    if IS_WIN:
        parts = shlex.split(t, posix=False)
        return [p.strip('"') for p in parts]
    return shlex.split(t)


def launch_desktop_file(path: Path) -> None:
    """解析 .desktop 的 Exec 行并直接启动，避免 xdg-open 把它当文本打开。"""
    exec_line, terminal, workdir = None, False, None
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("Exec="):
            exec_line = line[5:].strip()
        elif line.startswith("Terminal=") and "true" in line.lower():
            terminal = True
        elif line.startswith("Path="):
            workdir = line[5:].strip()
    if not exec_line:
        raise LaunchError(".desktop 中没有 Exec 字段")
    argv = [a for a in shlex.split(exec_line) if not (len(a) == 2 and a.startswith("%"))]
    if terminal:
        argv = _wrap_terminal(argv)
    spawn(argv, cwd=workdir if workdir and Path(workdir).is_dir() else None)


def _wrap_terminal(argv: list[str]) -> list[str]:
    for term, flag in (("deepin-terminal", "-e"), ("gnome-terminal", "--"),
                       ("konsole", "-e"), ("xfce4-terminal", "-e"),
                       ("x-terminal-emulator", "-e"), ("xterm", "-e")):
        if _which(term):
            return [term, flag] + argv
    return argv


def _which(name: str) -> str | None:
    from shutil import which
    return which(name)


def open_in_editor(path: Path) -> None:
    """用系统默认程序打开配置文件，方便手工编辑。"""
    p = Path(path)
    if not p.exists():
        raise LaunchError(f"文件不存在：{p}")
    if IS_WIN:
        try:
            os.startfile(str(p))  # type: ignore[attr-defined]
            return
        except OSError:
            pass
        spawn(["notepad.exe", str(p)])
        return
    for ed in ("deepin-editor", "gedit", "kate", "xed", "mousepad", "pluma"):
        if _which(ed):
            spawn([ed, str(p)])
            return
    spawn(["xdg-open", str(p)])


# ---------------------------------------------------------------- 启动一项

def launch(item: dict) -> None:
    kind = str(item.get("type") or "auto").lower()
    target = expand(str(item.get("target") or ""))
    args = [str(a) for a in (item.get("args") or [])]

    if kind == "config":
        open_in_editor(CONFIG_PATH)
        return
    if not target:
        raise LaunchError("该项目没有填写 target")

    if kind == "auto":
        if target.startswith(("http://", "https://")):
            kind = "url"
        elif Path(target).exists():
            kind = "file"
        else:
            kind = "command"

    if kind == "url":
        open_url(target)
    elif kind in ("file", "folder", "dir"):
        open_path(target)
    elif kind in ("command", "app", "run"):
        argv = _split_command(target)
        script = Path(argv[0])
        if script.suffix.lower() == ".sh" and script.is_file() and not IS_WIN:
            run_shell_script(script, args)
        else:
            spawn(argv + args, cwd=str(script.parent) if script.is_file() else None)
    else:
        raise LaunchError(f"未知类型：{kind}")


# ---------------------------------------------------------------- 开机自启

_AUTOSTART_LINUX = Path.home() / ".config" / "autostart" / "middle_launcher.desktop"
_AUTOSTART_WIN = (Path(os.environ.get("APPDATA", str(Path.home())))
                  / "Microsoft/Windows/Start Menu/Programs/Startup/middle_launcher.vbs")


def _pythonw() -> str:
    exe = Path(sys.executable)
    if IS_WIN:
        cand = exe.with_name("pythonw.exe")
        if cand.exists():
            return str(cand)
    return str(exe)


def autostart_path() -> Path:
    return _AUTOSTART_WIN if IS_WIN else _AUTOSTART_LINUX


def is_autostart() -> bool:
    return autostart_path().exists()


def set_autostart(enabled: bool) -> None:
    target = autostart_path()
    if not enabled:
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    app_py = APP_DIR / "app.py"
    if IS_WIN:
        content = (
            'Set sh = CreateObject("WScript.Shell")\r\n'
            f'sh.Run """{_pythonw()}"" ""{app_py}""", 0, False\r\n'
        )
    else:
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=中键启动器\n"
            "Comment=鼠标中键环形启动菜单\n"
            f'Exec="{_pythonw()}" "{app_py}"\n'
            f"Icon={APP_DIR / 'assets' / 'icon.png'}\n"
            "Terminal=false\n"
            "X-GNOME-Autostart-enabled=true\n"
        )
    target.write_text(content, encoding="utf-8")
    log(f"开机自启已{'启用' if enabled else '停用'}：{target}")
