"""图标加载：真实文件图标 → 主题图标 → 文字色块（兜底）。"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileInfo, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QFileIconProvider

PALETTE = ["#4C8DFF", "#F0B429", "#38B284", "#8B7CF6",
           "#F06A6A", "#22B8CF", "#E86AA6", "#7BD389"]

_THEME_FALLBACK = {
    "config": ["preferences-system", "settings"],
    "url": ["applications-internet", "web-browser", "applications-other"],
    "folder": ["folder", "inode-directory"],
    "file": ["text-x-generic", "application-x-generic"],
}

_provider: QFileIconProvider | None = None
_cache: dict[tuple, QPixmap] = {}


def item_color(item: dict) -> QColor:
    raw = item.get("color")
    if raw:
        c = QColor(str(raw))
        if c.isValid():
            return c
    seed = sum(ord(ch) for ch in str(item.get("label", "")))
    return QColor(PALETTE[seed % len(PALETTE)])


def _theme_icon(names: list[str]) -> QIcon | None:
    for n in names:
        if QIcon.hasThemeIcon(n):
            ic = QIcon.fromTheme(n)
            if not ic.isNull():
                return ic
    return None


def _letter_pixmap(label: str, color: QColor, size: int, dpr: float) -> QPixmap:
    px = int(size * dpr)
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)

    grad = QLinearGradient(0, 0, px, px)
    grad.setColorAt(0.0, color.lighter(118))
    grad.setColorAt(1.0, color.darker(112))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawRoundedRect(QRectF(0, 0, px, px), px * 0.30, px * 0.30)

    text = (label or "?").strip()[:1]
    f = QFont()
    f.setPixelSize(int(px * 0.52))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 235))
    p.drawText(QRectF(0, 0, px, px), Qt.AlignCenter, text)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def load_pixmap(item: dict, size: int, dpr: float = 1.0) -> QPixmap:
    """返回 size×size（逻辑像素）的图标。"""
    key = (str(item.get("icon") or ""), str(item.get("type") or ""),
           str(item.get("target") or ""), str(item.get("label") or ""), size, round(dpr, 2))
    if key in _cache:
        return _cache[key]

    global _provider
    icon: QIcon | None = None
    explicit = str(item.get("icon") or "").strip()
    kind = str(item.get("type") or "auto").lower()
    target = str(item.get("target") or "")

    if explicit:
        p = Path(explicit)
        if p.exists():
            icon = QIcon(str(p))
        elif QIcon.hasThemeIcon(explicit):
            icon = QIcon.fromTheme(explicit)

    if icon is None and kind in ("file", "folder", "dir", "auto") and target:
        p = Path(target).expanduser()
        if p.exists():
            try:
                if _provider is None:
                    _provider = QFileIconProvider()
                icon = _provider.icon(QFileInfo(str(p)))
            except Exception:
                icon = None

    if icon is None:
        icon = _theme_icon(_THEME_FALLBACK.get(kind, []))

    color = item_color(item)
    if icon is not None and not icon.isNull():
        pm = icon.pixmap(int(size * dpr), int(size * dpr))
        if not pm.isNull():
            pm.setDevicePixelRatio(dpr)
            _cache[key] = pm
            return pm

    pm = _letter_pixmap(str(item.get("label", "")), color, size, dpr)
    _cache[key] = pm
    return pm


def app_icon_pixmap(px: int = 256) -> QPixmap:
    """程序自己的标志：一个环形菜单的抽象图形。"""
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    c = px / 2.0
    r_out = px * 0.46
    r_in = px * 0.24
    cf = QPointF(c, c)

    grad = QLinearGradient(0, 0, px, px)
    grad.setColorAt(0.0, QColor("#5B9BFF"))
    grad.setColorAt(1.0, QColor("#7A6BFF"))
    p.setPen(Qt.NoPen)
    p.setBrush(grad)
    p.drawEllipse(cf, r_out, r_out)

    # 挖空中间，形成圆环
    p.setCompositionMode(QPainter.CompositionMode_Clear)
    p.drawEllipse(cf, r_in, r_in)
    p.setCompositionMode(QPainter.CompositionMode_SourceOver)

    # 环上的三个点，暗示「多选项的转盘」
    import math
    p.setBrush(QColor(255, 255, 255, 235))
    for deg in (90, 210, 330):
        rad = math.radians(deg)
        dot_r = px * 0.052
        p.drawEllipse(QPointF(c + 0.35 * px * math.cos(rad), c - 0.35 * px * math.sin(rad)),
                      dot_r, dot_r)
    p.end()
    return pm
