#!/usr/bin/env python3
"""中键启动器 —— 按鼠标中键唤出环形启动菜单。

支持的平台：Windows 10/11、Linux（X11 / Wayland）
依赖：PySide6-Essentials、pynput
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))


def _bootstrap_libs() -> None:
    """部分精简发行版缺少 Qt6 需要的 libxcb-util.so.1，用自带的库兜底。"""
    if os.name == "nt" or os.environ.get("MIDDLE_LAUNCHER_BOOTSTRAPPED") == "1":
        return
    libs = os.path.join(_HERE, "libs")
    if not os.path.exists(os.path.join(libs, "libxcb-util.so.1")):
        return
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = ":".join([libs] + [p for p in env.get("LD_LIBRARY_PATH", "").split(":") if p])
    env["MIDDLE_LAUNCHER_BOOTSTRAPPED"] = "1"
    try:
        os.execve(sys.executable, [sys.executable, os.path.abspath(__file__)] + sys.argv[1:], env)
    except Exception:
        pass


_bootstrap_libs()

import argparse  # noqa: E402

from PySide6.QtCore import QCoreApplication, QObject, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QAction, QCursor, QIcon  # noqa: E402
from PySide6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon  # noqa: E402

import config as cfgmod  # noqa: E402
from core import (LaunchError, is_autostart, launch, open_in_editor,  # noqa: E402
                  set_autostart)
from icons import app_icon_pixmap  # noqa: E402
from menu import RadialMenu  # noqa: E402
from settings import SettingsDialog  # noqa: E402
from trigger import Trigger  # noqa: E402

SERVER_NAME = "middle_launcher-single-instance"
# Linux 下用固定路径的本地套接字（/tmp 在部分环境下不可靠），Windows 用命名管道
SOCKET = SERVER_NAME if cfgmod.IS_WIN else str(cfgmod.APP_DIR / ".launcher.sock")
LOCK_PATH = cfgmod.APP_DIR / ".instance.lock"


class InstanceLock:
    """跨平台互斥锁：保证同时只有一个实例在跑。

    只靠本地套接字不够 —— 套接字文件被删掉/残留时两个实例会同时存活，
    于是每次按中键都会叠着弹出两个转盘。这里用文件锁兜底。
    """

    def __init__(self, path):
        self.path = path
        self.handle = None

    def acquire(self) -> bool:
        try:
            fh = open(self.path, "a+")
        except OSError:
            return False
        try:
            fh.seek(0, os.SEEK_END)
            if fh.tell() == 0:
                fh.write("\0")
                fh.flush()
            fh.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            try:
                fh.close()
            except Exception:
                pass
            return False
        try:
            fh.seek(0)
            fh.truncate()
            fh.write(f"{os.getpid()}\n")
            fh.flush()
        except Exception:
            pass
        self.handle = fh          # 持有到进程结束，锁才有效
        return True


class Launcher(QObject):
    def __init__(self, app: QApplication, show_on_start: bool = False):
        super().__init__()
        self.app = app
        self.cfg = cfgmod.load()
        self.menu: RadialMenu | None = None
        self.pinned = False
        self._quitting = False
        self.settings_dlg: SettingsDialog | None = None

        self.icon = QIcon(app_icon_pixmap(256))
        app.setWindowIcon(self.icon)

        self._build_tray()
        self._start_trigger()
        self._start_server()

        if show_on_start:
            QTimer.singleShot(250, lambda: self.show_menu(pinned=True))
        cfgmod.log("中键启动器已启动")

    # ------------------------------------------------------------ 托盘

    def _build_tray(self) -> None:
        self.tray: QSystemTrayIcon | None = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            cfgmod.log("系统托盘不可用，仅保留中键触发")
            return
        self.tray = QSystemTrayIcon(self.icon, self.app)
        self.tray.setToolTip("中键启动器 · 按下鼠标中键唤出菜单")

        m = QMenu()
        act_show = QAction("打开菜单", m)
        act_show.triggered.connect(lambda: self.show_menu(pinned=True))
        m.addAction(act_show)

        act_settings = QAction("设置…", m)
        act_settings.triggered.connect(self.open_settings)
        m.addAction(act_settings)

        m.addSeparator()
        self.act_auto = QAction("开机自动启动", m)
        self.act_auto.setCheckable(True)
        self.act_auto.setChecked(is_autostart())
        self.act_auto.toggled.connect(self._toggle_autostart)
        m.addAction(self.act_auto)

        act_reload = QAction("重新加载配置", m)
        act_reload.triggered.connect(self.reload)
        m.addAction(act_reload)

        act_edit = QAction("编辑 config.json", m)
        act_edit.triggered.connect(lambda: self._safe(open_in_editor, cfgmod.CONFIG_PATH))
        m.addAction(act_edit)

        act_log = QAction("打开日志", m)
        act_log.triggered.connect(lambda: self._safe(open_in_editor, cfgmod.LOG_PATH))
        m.addAction(act_log)

        m.addSeparator()
        act_quit = QAction("退出", m)
        act_quit.triggered.connect(self.quit)
        m.addAction(act_quit)

        self.tray.setContextMenu(m)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_menu(pinned=True)

    def _toggle_autostart(self, enabled: bool) -> None:
        try:
            set_autostart(enabled)
        except Exception as e:
            self._notify(f"设置开机自启失败：{e}")

    # ------------------------------------------------------------ 触发

    def _start_trigger(self) -> None:
        self.trigger = Trigger(self.cfg.get("trigger") or {})
        self.trigger.activated.connect(self._on_activated)
        self.trigger.released.connect(self._on_released)
        if not self.trigger.start():
            self._notify("鼠标监听启动失败，可用托盘菜单或快捷键唤出：" + (self.trigger.error or ""))
        elif self.trigger.error:
            self._notify(self.trigger.error)

    def _on_activated(self, reason: str) -> None:
        if self.menu is not None:
            return
        self.show_menu(pinned=reason != "hold")

    def _on_released(self) -> None:
        if self.menu is None or self.pinned:
            return
        self.menu.update_hover(QCursor.pos())
        item = self.menu.hovered_item()
        if item is None:
            self.close_menu()
            return
        self.close_menu()
        self.do_launch(item)

    # ------------------------------------------------------------ 菜单

    def show_menu(self, pinned: bool = False) -> None:
        if self.menu is not None:
            return
        items = self.cfg.get("items") or []
        if not items:
            self._notify("配置里没有任何启动项")
            return
        self.pinned = pinned
        menu = RadialMenu(items, self.cfg.get("appearance") or {}, QCursor.pos(), pinned)
        menu.picked.connect(self._on_picked)
        menu.dismissed.connect(self.close_menu)
        self.menu = menu
        menu.show()
        cfgmod.log(f"弹出菜单 pinned={pinned} 项目数={len(items)} 锚点={QCursor.pos().x()},{QCursor.pos().y()}")

    def _on_picked(self, item: dict) -> None:
        self.close_menu()
        self.do_launch(item)

    def close_menu(self) -> None:
        if self.menu is None:
            return
        menu, self.menu = self.menu, None
        QTimer.singleShot(0, menu.close)

    def do_launch(self, item: dict) -> None:
        if str(item.get("type") or "").lower() == "config":
            self.open_settings()
            return
        try:
            launch(item)
            cfgmod.log(f"打开：{item.get('label')} → {item.get('target')}")
        except LaunchError as e:
            cfgmod.log(f"打开失败：{item.get('label')} {e}")
            self._notify(str(e))
        except Exception as e:  # 兜底，绝不让异常炸掉主循环
            cfgmod.log(f"未预期错误：{e}")
            self._notify(f"打开失败：{e}")

    # ------------------------------------------------------------ 设置

    def open_settings(self) -> None:
        """打开可视化设置窗口（已打开则前置）。"""
        self.close_menu()
        if self.settings_dlg is not None:
            self.settings_dlg.showNormal()
            self.settings_dlg.raise_()
            self.settings_dlg.activateWindow()
            return
        dlg = SettingsDialog(self.cfg)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.applied.connect(self._on_settings_applied)
        dlg.destroyed.connect(self._on_settings_closed)
        self.settings_dlg = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        cfgmod.log("打开设置窗口")

    def _on_settings_closed(self, *_args) -> None:
        self.settings_dlg = None

    def _on_settings_applied(self, cfg: dict) -> None:
        self.cfg = cfg
        self.reload(silent=True)
        if self.tray is not None:
            self.act_auto.blockSignals(True)
            self.act_auto.setChecked(is_autostart())
            self.act_auto.blockSignals(False)
        self._notify("设置已保存并生效")

    # ------------------------------------------------------------ 配置

    def reload(self, silent: bool = False) -> None:
        self.cfg = cfgmod.load()
        try:
            self.trigger.stop()
        except Exception:
            pass
        self._start_trigger()
        if not silent:
            self._notify("配置已重新加载")

    # ------------------------------------------------------------ 单实例 / 退出

    def _start_server(self) -> None:
        QLocalServer.removeServer(SOCKET)
        self.server = QLocalServer(self)
        if not self.server.listen(SOCKET):
            cfgmod.log(f"单实例服务启动失败：{self.server.errorString()}")
            return
        self.server.newConnection.connect(self._on_connection)

    def _on_connection(self) -> None:
        sock = self.server.nextPendingConnection()
        if sock is None:
            return
        sock.readyRead.connect(lambda: self._handle_request(sock))
        sock.disconnected.connect(sock.deleteLater)

    def _handle_request(self, sock: QLocalSocket) -> None:
        cmd = bytes(sock.readAll()).decode("utf-8", "ignore").strip()
        if cmd in ("edit", "settings"):
            self.open_settings()
        elif cmd == "json":
            self._safe(open_in_editor, cfgmod.CONFIG_PATH)
        elif cmd == "reload":
            self.reload()
        elif cmd == "quit":
            self.quit()
        else:
            self.show_menu(pinned=True)
        sock.disconnectFromServer()

    def _notify(self, text: str) -> None:
        cfgmod.log(text)
        if self.tray is not None:
            try:
                self.tray.showMessage("中键启动器", text, QSystemTrayIcon.Information, 3000)
            except Exception:
                pass

    def _safe(self, fn, *args) -> None:
        try:
            fn(*args)
        except Exception as e:
            self._notify(str(e))

    def quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        cfgmod.log("退出")
        try:
            self.trigger.stop()
        except Exception:
            pass
        try:
            self.server.close()
        except Exception:
            pass
        if self.tray is not None:
            self.tray.hide()
        self.app.quit()


# ---------------------------------------------------------------- 简易客户端

def send_command(cmd: str) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SOCKET)
    if not sock.waitForConnected(300):
        return False
    sock.write(cmd.encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(300)
    sock.disconnectFromServer()
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="中键启动器")
    parser.add_argument("--show", action="store_true", help="立即弹出菜单（已在运行时唤醒）")
    parser.add_argument("--settings", "--edit", dest="settings", action="store_true",
                        help="打开可视化设置窗口")
    parser.add_argument("--json", action="store_true", help="用外部编辑器打开 config.json")
    parser.add_argument("--reload", action="store_true", help="重新加载配置")
    parser.add_argument("--quit", action="store_true", help="退出正在运行的实例")
    parser.add_argument("--no-tray", action="store_true", help="不显示托盘图标")
    parser.add_argument("--autostart-on", action="store_true", help="开启开机自启后退出")
    parser.add_argument("--autostart-off", action="store_true", help="关闭开机自启后退出")
    args, _ = parser.parse_known_args()

    if args.autostart_on or args.autostart_off:
        enabled = bool(args.autostart_on)
        try:
            set_autostart(enabled)
            print(("已开启" if enabled else "已关闭") + "开机自启")
            return 0
        except Exception as e:
            print(f"设置失败：{e}")
            return 1

    QCoreApplication.addLibraryPath(str(cfgmod.APP_DIR / "libs" / "qt6" / "plugins"))
    app = QApplication(sys.argv[:1])
    app.setApplicationName("中键启动器")
    app.setApplicationDisplayName("中键启动器")
    app.setQuitOnLastWindowClosed(False)

    # 单实例：先抢锁；抢不到说明已有实例在跑，只把指令转交给它
    lock = InstanceLock(LOCK_PATH)
    if not lock.acquire():
        cmd = "settings" if args.settings else "json" if args.json else \
              "reload" if args.reload else "quit" if args.quit else "show"
        if not send_command(cmd):
            cfgmod.log("已有实例在运行，但指令没能送过去；为避免出现两个转盘，本次启动放弃")
        return 0

    if args.quit:
        # 顺便清理可能残留的旧实例（旧版本不认锁文件）
        send_command("quit")
        print("已通知正在运行的实例退出")
        return 0
    if args.json:
        try:
            open_in_editor(cfgmod.CONFIG_PATH)
            return 0
        except Exception as e:
            print(f"打开失败：{e}")
            return 1

    launcher = Launcher(app, show_on_start=args.show)
    launcher.lock = lock
    if args.settings:
        launcher.open_settings()
    if args.no_tray and launcher.tray is not None:
        launcher.tray.hide()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
