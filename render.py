"""环形菜单的几何计算与绘制。

菜单窗口（menu.py）和设置窗口里的实时预览（settings.py）共用这套代码，
保证「预览里看到的」和「按中键弹出的」是同一个东西。
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen,
                           QPixmap)

from icons import item_color

MAX_ITEMS = 12


def _num(src: dict, key: str, default: float) -> float:
    v = src.get(key, default)
    if v is None or v == "":
        return float(default)
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _color(src: dict, key: str, default: str) -> QColor:
    c = QColor(str(src.get(key) or default))
    return c if c.isValid() else QColor(default)


class MenuStyle:
    """由 appearance 配置派生出的字号/半径/配色。"""

    def __init__(self, appearance: dict | None = None):
        a = dict(appearance or {})
        self.R = max(60.0, _num(a, "radius", 132))
        self.icon_size = max(16.0, _num(a, "icon_size", 40))
        self.font_size = max(6.0, _num(a, "font_size", 9.5))
        self.accent = _color(a, "accent", "#4C8DFF")
        self.bg = _color(a, "bg", "#1B1D23")
        self.bg_alpha = int(max(0, min(255, _num(a, "bg_alpha", 236))))
        self.text_color = _color(a, "text", "#EDEFF5")
        self.dim = max(0.0, min(0.95, _num(a, "dim", 0.22)))
        self.dead_ratio = max(0.15, min(0.7, _num(a, "dead_zone", 0.34)))
        self.follow = max(0.0, min(0.9, _num(a, "follow", 0.0)))

        self.r_in = self.R * 0.55
        self.r_out = self.R * 1.22
        self.dead = self.R * self.dead_ratio

    # -------------------------------------------------- 几何

    @property
    def icon_radius(self) -> float:
        return self.r_in + 5 + self.icon_size / 2

    @property
    def label_radius(self) -> float:
        return self.icon_radius + self.icon_size / 2 + 12

    @property
    def extent(self) -> float:
        """包含外发光在内需要占用的半径。"""
        return self.r_out + 22

    def sector_path(self, index: int, n: int, r_in: float, r_out: float,
                    center: QPointF) -> QPainterPath:
        step = 360.0 / max(1, n)
        start = 90.0 - index * step - step / 2.0
        outer = QRectF(center.x() - r_out, center.y() - r_out, r_out * 2, r_out * 2)
        inner = QRectF(center.x() - r_in, center.y() - r_in, r_in * 2, r_in * 2)
        path = QPainterPath()
        path.arcMoveTo(outer, start)
        path.arcTo(outer, start, step)
        path.arcTo(inner, start + step, -step)
        path.closeSubpath()
        return path

    def point_at(self, degrees: float, radius: float, center: QPointF) -> QPointF:
        rad = math.radians(degrees)
        return QPointF(center.x() + radius * math.cos(rad),
                       center.y() - radius * math.sin(rad))

    def sector_of(self, pos: QPointF, home: QPointF, n: int,
                  slack: float = 2.2) -> int:
        """pos / home 用同一坐标系；判定以 home（菜单的固定锚点）为准。"""
        dx = pos.x() - home.x()
        dy = home.y() - pos.y()                     # Qt 角度以 y 向上为正
        dist = math.hypot(dx, dy)
        if dist < self.dead or dist > self.r_out * slack:
            return -1
        angle = math.degrees(math.atan2(dy, dx)) % 360.0
        rel = (90.0 - angle) % 360.0                # 0 = 正上方，顺时针递增
        step = 360.0 / max(1, n)
        return int(((rel + step / 2.0) % 360.0) // step) % n


# ---------------------------------------------------------------- 绘制

def draw_menu(p: QPainter, items: list[dict], pixmaps: list[QPixmap], style: MenuStyle,
              center: QPointF, hover: int = -1, n: int | None = None,
              t: float = 1.0, grow: float | None = None, dim: bool = True,
              rect: QRectF | None = None, pinned: bool = False,
              text_px_floor: float = 0.0) -> None:
    """把整只转盘画到 p 上。center 用 p 当前坐标系的坐标。

    text_px_floor：文字在屏幕上的最小像素高度（预览缩小显示时防止字糊成一片）。
    """
    n = n or max(1, len(items))
    t = max(0.0, min(1.0, t))
    grow = (0.86 + 0.14 * t) if grow is None else grow
    c = center
    r_in = style.r_in * grow
    r_out = style.r_out * grow

    scale = max(0.02, p.transform().m11() or 1.0)

    def font_px(units: float, floor: float = 0.0) -> int:
        px = units
        if text_px_floor > 0:
            px = max(px, max(floor, text_px_floor) / scale)
        return max(8, int(round(px)))

    p.save()
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)

    if dim and style.dim > 0 and rect is not None:
        p.fillRect(rect, QColor(0, 0, 0, int(255 * style.dim * t)))

    # 外发光
    for i, alpha in enumerate((10, 20, 34)):
        pen = QPen(QColor(0, 0, 0, int(alpha * t)))
        pen.setWidthF(2.0 + i * 3)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(c, r_out + 5 + i * 4, r_out + 5 + i * 4)

    # 底盘（整圆，避免环内外出现透明缝隙）
    bg = QColor(style.bg)
    bg.setAlpha(int(style.bg_alpha * t))
    p.setPen(Qt.NoPen)
    p.setBrush(bg)
    p.drawEllipse(c, r_out, r_out)

    # 每个扇区一层很淡的主色，便于用颜色辨认
    for i in range(n):
        tint = item_color(items[i])
        tint.setAlpha(int(30 * t))
        p.setBrush(tint)
        p.setPen(Qt.NoPen)
        p.drawPath(style.sector_path(i, n, r_in, r_out, c))

    # 悬停扇区
    if 0 <= hover < n:
        hi = item_color(items[hover])
        hi.setAlpha(int(78 * t))
        p.setBrush(hi)
        p.setPen(Qt.NoPen)
        p.drawPath(style.sector_path(hover, n, r_in, r_out, c))

        glow = item_color(items[hover])
        glow.setAlpha(int(210 * t))
        pen = QPen(glow)
        pen.setWidthF(1.8)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(style.sector_path(hover, n, r_in + 1.2, r_out - 1.2, c))

    # 扇区分隔线
    if n > 1:
        sep = QColor(255, 255, 255, 20)
        sep.setAlpha(int(20 * t))
        pen = QPen(sep)
        pen.setWidthF(1.0)
        p.setPen(pen)
        step = 360.0 / n
        for i in range(n):
            ang = 90.0 - i * step - step / 2.0
            p.drawLine(style.point_at(ang, r_in + 3, c),
                       style.point_at(ang, r_out - 3, c))

    # 外描边
    edge = QColor(style.accent)
    edge.setAlpha(int(70 * t))
    pen = QPen(edge)
    pen.setWidthF(1.2)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(c, r_out, r_out)

    # 图标与标签
    show_label = n <= 8
    step = 360.0 / n
    for i in range(n):
        ang = 90.0 - i * step
        ipos = style.point_at(ang, style.icon_radius * grow, c)
        pm = pixmaps[i] if i < len(pixmaps) else None
        scale = 1.10 if i == hover else 1.0
        side = style.icon_size * scale * grow
        if pm is not None and not pm.isNull():
            p.drawPixmap(QRectF(ipos.x() - side / 2, ipos.y() - side / 2, side, side),
                         pm, QRectF(pm.rect()))

        if show_label:
            f = QFont()
            f.setPixelSize(font_px(style.font_size * grow * 1.18, 8))
            f.setWeight(QFont.Medium if i == hover else QFont.Normal)
            p.setFont(f)
            col = QColor(style.text_color)
            col.setAlpha(int((255 if i == hover else 200) * t))
            p.setPen(col)
            lpos = style.point_at(ang, style.label_radius * grow, c)
            maxw = max(48.0, 2 * math.pi * style.label_radius * (step / 360.0) * 0.95)
            fm = QFontMetricsF(f)
            text = fm.elidedText(str(items[i].get("label", "")), Qt.ElideRight, maxw)
            rect_txt = QRectF(lpos.x() - maxw / 2, lpos.y() - fm.height() / 2,
                              maxw, fm.height())
            p.drawText(rect_txt, Qt.AlignHCenter | Qt.AlignVCenter, text)

    _draw_hub(p, style, c, r_in, hover, items, n, t, pinned, font_px)
    p.restore()


def _draw_hub(p: QPainter, style: MenuStyle, c: QPointF, r_in: float, hover: int,
              items: list[dict], n: int, t: float, pinned: bool, font_px) -> None:
    hub_r = r_in * 0.995
    hub = QColor(style.bg).lighter(112)
    hub.setAlpha(int(min(255, style.bg_alpha)) * int(t * 255) // 255)
    p.setPen(Qt.NoPen)
    p.setBrush(hub)
    p.drawEllipse(c, hub_r, hub_r)

    pen = QPen(QColor(255, 255, 255, int(20 * t)))
    pen.setWidthF(1.0)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(c, hub_r, hub_r)

    maxw = hub_r * 1.62
    if 0 <= hover < n:
        item = items[hover]
        f = QFont()
        f.setPixelSize(font_px(14 * t, 9))
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetricsF(f)
        col = QColor(style.text_color)
        col.setAlpha(int(255 * t))
        p.setPen(col)
        label = fm.elidedText(str(item.get("label", "")), Qt.ElideRight, maxw)
        p.drawText(QRectF(c.x() - maxw / 2, c.y() - 22, maxw, 18),
                   Qt.AlignHCenter | Qt.AlignVCenter, label)

        sub = str(item.get("target") or item.get("type") or "")
        if item.get("type") == "config":
            sub = "打开设置面板"
        f2 = QFont()
        f2.setPixelSize(font_px(9.5 * t, 7))
        p.setFont(f2)
        fm2 = QFontMetricsF(f2)
        col2 = QColor(style.text_color)
        col2.setAlpha(int(130 * t))
        p.setPen(col2)
        sub = fm2.elidedText(sub, Qt.ElideMiddle, maxw)
        p.drawText(QRectF(c.x() - maxw / 2, c.y() + 1, maxw, 14),
                   Qt.AlignHCenter | Qt.AlignVCenter, sub)
    else:
        f = QFont()
        f.setPixelSize(font_px(11 * t, 8))
        p.setFont(f)
        col = QColor(style.text_color)
        col.setAlpha(int(120 * t))
        p.setPen(col)
        hint = "点击选择" if pinned else "松开选择"
        p.drawText(QRectF(c.x() - maxw / 2, c.y() - 16, maxw, 16),
                   Qt.AlignHCenter | Qt.AlignVCenter, hint)
        f2 = QFont()
        f2.setPixelSize(font_px(9 * t, 7))
        p.setFont(f2)
        col2 = QColor(style.text_color)
        col2.setAlpha(int(70 * t))
        p.setPen(col2)
        p.drawText(QRectF(c.x() - maxw / 2, c.y() + 2, maxw, 14),
                   Qt.AlignHCenter | Qt.AlignVCenter, "Esc 取消")
