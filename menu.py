"""环形菜单窗口（Qt 绘制的全屏透明浮层）。

交互：
- 出现在鼠标处（贴边时自动内收保证完整显示）
- 指针离开中心死区即高亮对应扇区，松手立刻执行
- 盘面会跟着指针小幅平移（appearance.follow），手感更「跟手」
- 单击模式（pinned）下左键点选，Esc / 点空白处关闭
"""
from __future__ import annotations

import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter
from PySide6.QtWidgets import QWidget

from icons import load_pixmap
from render import MAX_ITEMS, MenuStyle, draw_menu

__all__ = ["RadialMenu", "MAX_ITEMS"]


class RadialMenu(QWidget):
    picked = Signal(dict)
    dismissed = Signal()

    def __init__(self, items: list[dict], appearance: dict, anchor=None, pinned: bool = False):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.ArrowCursor)

        self.items = list(items)[:MAX_ITEMS]
        self.n = max(1, len(self.items))
        self.appearance = dict(appearance or {})
        self.style = MenuStyle(self.appearance)
        self.pinned = pinned
        self.hover = -1
        self._t = 0.0

        # 长按拖拽时跟随指针，单击模式下不跟随（否则光标会一直被「躲开」）
        self.follow = 0.0 if pinned else self.style.follow

        screen = QGuiApplication.screenAt(anchor or QCursor.pos()) or QGuiApplication.primaryScreen()
        self._screen_geo = screen.geometry()
        geo = self._screen_geo
        self.setGeometry(geo)

        margin = self.style.extent + 6
        cx = min(max((anchor or QCursor.pos()).x(), geo.left() + margin), geo.right() - margin)
        cy = min(max((anchor or QCursor.pos()).y(), geo.top() + margin), geo.bottom() - margin)
        # home = 逻辑锚点（选中判定基准），center = 实际绘制中心（home + 跟随偏移）
        self.home = QPointF(cx - geo.left(), cy - geo.top())
        self.center = QPointF(self.home)

        dpr = float(screen.devicePixelRatio() or 1.0)
        self._pixmaps = [load_pixmap(it, int(self.style.icon_size), dpr) for it in self.items]

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(110)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._anim.start()

        # 长按期间指针被其它窗口隐式抓取，收不到 MouseMove，用轮询光标位置兜住
        self._poll = QTimer(self)
        self._poll.setInterval(12)
        self._poll.timeout.connect(self._poll_cursor)
        self._poll.start()

    # ------------------------------------------------------------ 动画 / 轮询

    def _on_anim(self, value) -> None:
        self._t = float(value)
        try:
            self.setWindowOpacity(max(0.08, self._t))
        except Exception:
            pass
        self.update()

    def _poll_cursor(self) -> None:
        self.update_hover(QCursor.pos(), polled=True)

    # ------------------------------------------------------------ 跟随

    def _follow_to(self, local: QPointF) -> None:
        """盘面向指针方向平滑平移一小段，制造「跟手」的手感。

        注意：选中判定始终以 home 为原点，因此扇区角度和指针方向永远一致，
        不会出现「盘跟着走、光标却选不中」的情况。
        """
        if self.follow <= 0 or self.n <= 1:
            if self.center != self.home:
                self.center = QPointF(self.home)
                self.update()
            return

        dx = local.x() - self.home.x()
        dy = local.y() - self.home.y()
        limit = self.style.R * 0.90
        mag = math.hypot(dx, dy)
        if mag > limit > 0:
            dx, dy = dx / mag * limit, dy / mag * limit

        # 平滑跟随（0.5 系数 -> 约 60ms 追上），避免抖动
        nx = self.center.x() + (self.home.x() + dx * self.follow - self.center.x()) * 0.5
        ny = self.center.y() + (self.home.y() + dy * self.follow - self.center.y()) * 0.5

        margin = self.style.extent + 4
        g = self._screen_geo
        nx = min(max(nx, margin), g.width() - margin)
        ny = min(max(ny, margin), g.height() - margin)

        if abs(nx - self.center.x()) > 0.4 or abs(ny - self.center.y()) > 0.4:
            self.center = QPointF(nx, ny)
            self.update()

    # ------------------------------------------------------------ 绘制

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        draw_menu(p, self.items, self._pixmaps, self.style, self.center, self.hover,
                  self.n, t=self._t, grow=0.86 + 0.14 * self._t, dim=True,
                  rect=QRectF(self.rect()), pinned=self.pinned)
        p.end()

    # ------------------------------------------------------------ 事件

    def update_hover(self, global_pos, polled: bool = False) -> None:
        local = QPointF(self.mapFromGlobal(global_pos))
        self._follow_to(local)
        idx = self.style.sector_of(local, self.home, self.n)
        if idx != self.hover:
            self.hover = idx
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        local = QPointF(event.position())
        self._follow_to(local)
        idx = self.style.sector_of(local, self.home, self.n)
        if idx != self.hover:
            self.hover = idx
            self.update()

    def hovered_item(self) -> dict | None:
        if 0 <= self.hover < self.n:
            return self.items[self.hover]
        return None

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            local = QPointF(event.position())
            idx = self.style.sector_of(local, self.home, self.n)
            if idx >= 0:
                self.hover = idx
                self.picked.emit(self.items[idx])
            else:
                self.dismissed.emit()
        elif event.button() in (Qt.RightButton, Qt.MiddleButton):
            self.dismissed.emit()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key_Escape, Qt.Key_Space):
            self.dismissed.emit()
        elif Qt.Key_1 <= event.key() <= Qt.Key_9:
            idx = event.key() - Qt.Key_1
            if idx < self.n:
                self.picked.emit(self.items[idx])
        else:
            super().keyPressEvent(event)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self.setFocus(Qt.ActiveWindowFocusReason)
        self.update_hover(QCursor.pos())
