"""可视化设置窗口。

把所有配置项做成正常界面：拖入文件、从应用列表挑程序、改外观时右侧实时预览，
保存后主程序立即热重载，不用再手写 JSON。
"""
from __future__ import annotations

import copy
import shlex
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QColorDialog, QComboBox,
                               QDialog, QFileDialog, QFormLayout,
                               QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPushButton, QRadioButton, QSlider,
                               QTabWidget, QToolButton, QVBoxLayout, QWidget)

import config as cfgmod
from apps import scan_apps
from icons import PALETTE, item_color, load_pixmap
from render import MAX_ITEMS, MenuStyle, draw_menu

TYPE_CHOICES = [
    ("文件夹", "folder"),
    ("文件", "file"),
    ("网址", "url"),
    ("程序", "command"),
    ("自动识别", "auto"),
    ("打开设置面板", "config"),
]
TYPE_LABEL = {v: k for k, v in TYPE_CHOICES}

APP_STYLE = """
QDialog { background: #F5F6F8; }
QLabel { color: #23262B; }
QLabel#h1 { font-size: 17px; font-weight: 600; }
QLabel#sub { color: #6B7280; font-size: 12px; }
QLabel#sect { font-weight: 600; color: #374151; }
QLabel#hint { color: #8A9099; font-size: 11px; }
QLabel#val { color: #4C8DFF; font-weight: 600; }
QGroupBox { background: #FFFFFF; border: 1px solid #E3E6EB; border-radius: 8px;
            margin-top: 14px; padding: 10px 12px 12px 12px; font-weight: 600; color: #374151; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }
QLineEdit, QComboBox { background: #FFFFFF; border: 1px solid #D7DBE2; border-radius: 6px;
                       padding: 5px 8px; color: #1F2328; min-height: 18px; }
QLineEdit:focus, QComboBox:focus { border-color: #4C8DFF; }
QListWidget { background: #FFFFFF; border: 1px solid #D7DBE2; border-radius: 8px; }
QListWidget::item { padding: 5px 4px; border-radius: 6px; }
QListWidget::item:selected { background: #E8F0FF; color: #1F2328; }
QPushButton { background: #FFFFFF; border: 1px solid #D7DBE2; border-radius: 6px;
              padding: 6px 14px; color: #23262B; }
QPushButton:hover { border-color: #A9B6CC; }
QPushButton#primary { background: #4C8DFF; border: 1px solid #4C8DFF; color: #FFFFFF;
                      font-weight: 600; }
QPushButton#primary:hover { background: #3C7DEB; }
QToolButton { background: #FFFFFF; border: 1px solid #D7DBE2; border-radius: 6px; padding: 4px 8px; }
QToolButton:hover { border-color: #A9B6CC; }
QTabWidget::pane { border: none; background: transparent; }
QTabBar::tab { background: transparent; padding: 7px 16px; color: #6B7280; border: none;
               border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #4C8DFF; border-bottom: 2px solid #4C8DFF; font-weight: 600; }
QSlider::groove:horizontal { height: 4px; background: #DDE1E8; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
                             background: #4C8DFF; }
QCheckBox, QRadioButton { color: #23262B; }
"""


# ---------------------------------------------------------------- 小工具

def _hint(text: str) -> QLabel:
    lb = QLabel(text)
    lb.setObjectName("hint")
    lb.setWordWrap(True)
    lb.setMaximumWidth(560)
    return lb


class Slider(QWidget):
    """一行：标题 + 滑杆 + 数值。"""

    changed = Signal()

    def __init__(self, title: str, lo: int, hi: int, val: int, suffix: str = "",
                 fmt=None, tip: str = "", parent=None):
        super().__init__(parent)
        if tip:
            self.setToolTip(tip)
        self.suffix = suffix
        self.fmt = fmt or (lambda v: str(v))
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lb = QLabel(title)
        lb.setMinimumWidth(78)
        if tip:
            lb.setToolTip(tip)
        lay.addWidget(lb)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setValue(int(val))
        self.slider.setPageStep(max(1, (hi - lo) // 10))
        lay.addWidget(self.slider, 1)
        self.value = QLabel()
        self.value.setObjectName("val")
        self.value.setMinimumWidth(52)
        self.value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.value)
        self.slider.valueChanged.connect(self._on_change)
        self._on_change(self.slider.value())

    def _on_change(self, v: int) -> None:
        self.value.setText(self.fmt(v) + self.suffix)
        self.changed.emit()

    def get(self) -> float:
        return self.slider.value()

    def set(self, v: float) -> None:
        self.slider.setValue(int(round(float(v))))


class ColorField(QWidget):
    """当前颜色块 + 8 个预设色 + 自定义。"""

    changed = Signal()

    def __init__(self, value: str = "#4C8DFF", parent=None):
        super().__init__(parent)
        self._color = QColor(value)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.swatch_btns: list[QToolButton] = []
        for c in PALETTE:
            b = QToolButton()
            b.setFixedSize(22, 22)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolTip(c)
            b.setStyleSheet(f"QToolButton{{background:{c};border-radius:5px;border:1px solid #00000018;}}")
            b.clicked.connect(lambda _=False, col=c: self.set_color(col, emit=True))
            lay.addWidget(b)
            self.swatch_btns.append(b)
        self.custom = QToolButton()
        self.custom.setText("自定义…")
        self.custom.clicked.connect(self._pick)
        lay.addWidget(self.custom)
        lay.addStretch(1)
        self._refresh()

    def _pick(self) -> None:
        c = QColorDialog.getColor(self._color, self, "选择颜色")
        if c.isValid():
            self.set_color(c.name(), emit=True)

    def set_color(self, value: str, emit: bool = False) -> None:
        c = QColor(str(value))
        if not c.isValid():
            return
        self._color = c
        self._refresh()
        if emit:
            self.changed.emit()

    def _refresh(self) -> None:
        self.custom.setStyleSheet(
            f"QToolButton{{background:{self._color.name()};border-radius:6px;"
            f"border:1px solid #00000022;padding:2px 10px;color:"
            f"{'#111' if self._color.lightness() > 140 else '#fff'};}}")
        self.custom.setText(self._color.name().upper())

    def get(self) -> str:
        return self._color.name()


# ---------------------------------------------------------------- 实时预览

class PreviewWidget(QWidget):
    """和真实转盘同一套绘制代码的小号预览，鼠标移上去就能试手感。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 320)
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.items: list[dict] = []
        self.appearance: dict = {}
        self.style = MenuStyle({})
        self.hover = -1
        self._pix: list[QPixmap] = []

    def set_data(self, items: list[dict], appearance: dict) -> None:
        self.items = list(items)[:MAX_ITEMS]
        self.appearance = dict(appearance)
        self.style = MenuStyle(self.appearance)
        dpr = float(self.devicePixelRatioF() or 1.0)
        size = max(8, int(self.style.icon_size))
        self._pix = [load_pixmap(it, size, dpr) for it in self.items]
        self.hover = -1
        self.update()

    # --- 坐标换算：把控件坐标映射回「菜单单位」
    def _k(self) -> float:
        return max(0.05, min(self.width(), self.height()) / (2 * self.style.extent * 1.04))

    def _to_menu(self, pos) -> QPointF:
        k = self._k()
        return QPointF((pos.x() - self.width() / 2) / k, (pos.y() - self.height() / 2) / k)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        idx = self.style.sector_of(self._to_menu(event.position()), QPointF(0, 0),
                                   max(1, len(self.items)))
        if idx != self.hover:
            self.hover = idx
            self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self.hover != -1:
            self.hover = -1
            self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = QRectF(self.rect())
        grad = QLinearGradient(0, 0, rect.width(), rect.height())
        grad.setColorAt(0.0, QColor("#2C3040"))
        grad.setColorAt(1.0, QColor("#191B22"))
        p.fillRect(rect, grad)

        if not self.items:
            p.setPen(QColor(255, 255, 255, 90))
            p.setFont(QFont("", 10))
            p.drawText(rect, Qt.AlignCenter, "还没有启动项")
            p.end()
            return

        k = self._k()
        p.translate(self.width() / 2, self.height() / 2)
        p.scale(k, k)
        draw_menu(p, self.items, self._pix, self.style, QPointF(0, 0), self.hover,
                  max(1, len(self.items)), t=1.0, grow=1.0, dim=False,
                  text_px_floor=8.0)
        p.end()


# ---------------------------------------------------------------- 列表（支持拖入文件）

class ItemList(QListWidget):
    filesDropped = Signal(list)
    reordered = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIconSize(QSize(26, 26))
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setAlternatingRowColors(False)
        self.setUniformItemSizes(True)

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
            if paths:
                self.filesDropped.emit(paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)
        self.reordered.emit()


# ---------------------------------------------------------------- 单项编辑表单

class ItemForm(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.item: dict | None = None
        self._loading = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        self.empty = QLabel("← 先在左侧添加或选择一个启动项")
        self.empty.setObjectName("sub")
        lay.addWidget(self.empty)

        self.body = QWidget()
        form = QFormLayout(self.body)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(9)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.ed_label = QLineEdit()
        self.ed_label.setPlaceholderText("显示在转盘上的名字")
        self.ed_label.textEdited.connect(self._push)
        form.addRow("名称", self.ed_label)

        self.cb_type = QComboBox()
        for label, value in TYPE_CHOICES:
            self.cb_type.addItem(label, value)
        self.cb_type.currentIndexChanged.connect(self._on_type)
        form.addRow("类型", self.cb_type)

        target_row = QWidget()
        tl = QHBoxLayout(target_row)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(6)
        self.ed_target = QLineEdit()
        self.btn_browse = QToolButton()
        self.btn_browse.setText("浏览…")
        self.btn_browse.clicked.connect(self._browse)
        tl.addWidget(self.ed_target, 1)
        tl.addWidget(self.btn_browse)
        self.ed_target.textEdited.connect(self._push)
        form.addRow("目标", target_row)

        self.ed_args = QLineEdit()
        self.ed_args.setPlaceholderText("可选，空格分隔，例如 --new-window")
        self.ed_args.textEdited.connect(self._push)
        form.addRow("启动参数", self.ed_args)

        self.color = ColorField("#4C8DFF")
        self.color.changed.connect(self._push)
        form.addRow("主色", self.color)

        icon_row = QWidget()
        il = QHBoxLayout(icon_row)
        il.setContentsMargins(0, 0, 0, 0)
        il.setSpacing(6)
        self.preview_icon = QLabel()
        self.preview_icon.setFixedSize(30, 30)
        self.preview_icon.setScaledContents(True)
        il.addWidget(self.preview_icon)
        self.ed_icon = QLineEdit()
        self.ed_icon.setPlaceholderText("留空=自动识别；也可填图标名或图片路径")
        self.ed_icon.textEdited.connect(self._push)
        self.btn_icon = QToolButton()
        self.btn_icon.setText("图片…")
        self.btn_icon.clicked.connect(self._browse_icon)
        il.addWidget(self.ed_icon, 1)
        il.addWidget(self.btn_icon)
        form.addRow("图标", icon_row)

        self.tip = _hint("")
        form.addRow("", self.tip)

        lay.addWidget(self.body)
        lay.addStretch(1)
        self.body.setVisible(False)

    # --- 数据进出
    def set_item(self, item: dict | None) -> None:
        self.item = item
        self._loading = True
        try:
            self.body.setVisible(item is not None)
            self.empty.setVisible(item is None)
            if item is None:
                return
            self.ed_label.setText(str(item.get("label") or ""))
            kind = str(item.get("type") or "auto").lower()
            idx = self.cb_type.findData(kind)
            if idx < 0:
                idx = self.cb_type.findData("auto")
            self.cb_type.setCurrentIndex(idx)
            self.ed_target.setText(str(item.get("target") or ""))
            args = item.get("args") or []
            self.ed_args.setText(" ".join(str(a) for a in args) if isinstance(args, list) else str(args))
            self.color.set_color(item_color(item).name())
            self.ed_icon.setText(str(item.get("icon") or ""))
            self._update_enabled()
            self._refresh_icon()
        finally:
            self._loading = False

    def _on_type(self) -> None:
        if self._loading or self.item is None:
            return
        self.item["type"] = self.cb_type.currentData()
        self._update_enabled()
        self._push()

    def _update_enabled(self) -> None:
        if self.item is None:
            return
        kind = str(self.item.get("type") or "auto")
        is_cfg = kind == "config"
        self.ed_target.setEnabled(not is_cfg)
        self.btn_browse.setEnabled(not is_cfg)
        self.ed_args.setEnabled(kind == "command")
        if is_cfg:
            self.ed_target.setText("")
            self.tip.setText("这一项会打开本设置窗口，方便你随时调整。")
        elif kind == "url":
            self.tip.setText("填完整地址，例如 https://www.bing.com")
        elif kind == "command":
            self.tip.setText("程序路径或命令名（如 firefox、code），参数填在下一行。")
        elif kind in ("file", "folder"):
            self.tip.setText("选择具体路径；相对路径可用 ~ 开头。")
        else:
            self.tip.setText("自动判断：网址→浏览器，存在的路径→打开，其它当命令执行。")

    def _push(self) -> None:
        if self._loading or self.item is None:
            return
        self.item["label"] = self.ed_label.text().strip()
        kind = self.cb_type.currentData()
        self.item["type"] = kind
        target = self.ed_target.text().strip()
        if target:
            self.item["target"] = target
        else:
            self.item.pop("target", None)

        raw_args = self.ed_args.text().strip()
        if raw_args and kind == "command":
            try:
                parts = shlex.split(raw_args, posix=not cfgmod.IS_WIN)
            except ValueError:
                parts = raw_args.split()
            self.item["args"] = parts
        else:
            self.item.pop("args", None)

        self.item["color"] = self.color.get()
        icon = self.ed_icon.text().strip()
        if icon:
            self.item["icon"] = icon
        else:
            self.item.pop("icon", None)

        self._refresh_icon()
        self.changed.emit()

    def _refresh_icon(self) -> None:
        if self.item is None:
            return
        dpr = float(self.devicePixelRatioF() or 1.0)
        pm = load_pixmap(self.item, 32, dpr)
        self.preview_icon.setPixmap(pm)

    def _browse(self) -> None:
        if self.item is None:
            return
        kind = self.cb_type.currentData()
        start = str(Path(str(self.item.get("target") or "~")).expanduser())
        if not Path(start).exists():
            start = str(Path.home())
        if kind == "folder":
            path = QFileDialog.getExistingDirectory(self, "选择文件夹", start)
        elif kind == "command":
            path, _ = QFileDialog.getOpenFileName(self, "选择程序", "/usr/bin" if
                                                  not cfgmod.IS_WIN else start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "选择文件", start)
        if path:
            self.ed_target.setText(path)
            self._push()

    def _browse_icon(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图标图片", str(Path.home()),
            "图片 (*.png *.svg *.ico *.jpg *.jpeg *.xpm);;所有文件 (*)")
        if path:
            self.ed_icon.setText(path)
            self._push()


# ---------------------------------------------------------------- 程序选择器

class AppPicker(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("添加程序")
        self.setStyleSheet(APP_STYLE)
        self.resize(520, 560)
        self.setWindowModality(Qt.WindowModal)
        self.apps = scan_apps()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索程序名…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)

        self.list = QListWidget()
        self.list.setIconSize(QSize(28, 28))
        dpr = float(self.devicePixelRatioF() or 1.0)
        for app in self.apps:
            it = QListWidgetItem(load_pixmap(app, 28, dpr), app["label"])
            it.setData(Qt.UserRole, app)
            self.list.addItem(it)
        self.list.itemDoubleClicked.connect(lambda _i: self.accept())
        lay.addWidget(self.list, 1)

        row = QHBoxLayout()
        self.count = _hint(f"共 {len(self.apps)} 个程序，双击直接添加")
        row.addWidget(self.count)
        row.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("添加所选")
        btn_ok.setObjectName("primary")
        btn_ok.clicked.connect(self.accept)
        row.addWidget(btn_cancel)
        row.addWidget(btn_ok)
        lay.addLayout(row)

    def _filter(self, text: str) -> None:
        key = text.strip().lower()
        shown = 0
        for i in range(self.list.count()):
            it = self.list.item(i)
            hit = key in it.text().lower()
            it.setHidden(bool(key) and not hit)
            shown += 1 if hit or not key else 0
        self.count.setText(f"{shown} / {len(self.apps)} 个程序")

    def chosen(self) -> list[dict]:
        out = []
        for it in self.list.selectedItems():
            app = dict(it.data(Qt.UserRole))
            app.pop("_name_raw", None)
            app.setdefault("color", item_color(app).name())
            out.append(app)
        return out


# ---------------------------------------------------------------- 主窗口

class SettingsDialog(QDialog):
    applied = Signal(dict)

    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("中键启动器 · 设置")
        self.setStyleSheet(APP_STYLE)
        self.resize(940, 640)
        self.setMinimumSize(820, 560)
        self.cfg = copy.deepcopy(cfg or {})
        self.items: list[dict] = [dict(i) for i in (self.cfg.get("items") or [])]
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        head = QVBoxLayout()
        head.setSpacing(1)
        h1 = QLabel("中键启动器")
        h1.setObjectName("h1")
        sub = QLabel("按住鼠标中键 0.3 秒唤出转盘 · 松手即打开 · 改动保存后立即生效")
        sub.setObjectName("sub")
        head.addWidget(h1)
        head.addWidget(sub)
        root.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(14)
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_items_tab(), "启动项")
        self.tabs.addTab(self._build_look_tab(), "外观")
        self.tabs.addTab(self._build_trigger_tab(), "触发与行为")
        body.addWidget(self.tabs, 1)

        side = QFrame()
        side.setFixedWidth(344)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(6)
        cap = QLabel("实时预览")
        cap.setObjectName("sect")
        sl.addWidget(cap)
        self.preview = PreviewWidget()
        sl.addWidget(self.preview, 1)
        tip = _hint("预览可交互：鼠标移到扇区上即高亮。")
        sl.addWidget(tip)
        body.addWidget(side)
        root.addLayout(body, 1)

        foot = QHBoxLayout()
        self.status = _hint("")
        foot.addWidget(self.status, 1)
        btn_reset = QPushButton("恢复默认")
        btn_reset.clicked.connect(self._reset)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("保存并应用")
        btn_save.setObjectName("primary")
        btn_save.setDefault(True)
        btn_save.clicked.connect(self._save)
        foot.addWidget(btn_reset)
        foot.addWidget(btn_cancel)
        foot.addWidget(btn_save)
        root.addLayout(foot)

        self._load_from_cfg()
        self._refresh_list(select=0)

    # ------------------------------------------------------------ 启动项页

    def _build_items_tab(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        for text, slot, tip in (
            ("＋ 程序", self._add_app, "从系统应用列表里挑选"),
            ("＋ 文件夹", lambda: self._add_path("folder"), "选一个文件夹"),
            ("＋ 文件", lambda: self._add_path("file"), "选一个文件"),
            ("＋ 网址", self._add_url, "手工填一个网址"),
        ):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            bar.addWidget(b)
        bar.addStretch(1)
        for text, slot, tip in (("↑", lambda: self._move(-1), "上移（转盘按此顺序排列）"),
                                ("↓", lambda: self._move(1), "下移"),
                                ("删除", self._remove, "删除选中项")):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            bar.addWidget(b)
        lay.addLayout(bar)

        split = QHBoxLayout()
        split.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(6)
        self.list = ItemList()
        self.list.currentRowChanged.connect(self._on_select)
        self.list.filesDropped.connect(self._add_files)
        self.list.reordered.connect(self._after_reorder)
        left.addWidget(self.list, 1)
        left.addWidget(_hint("顺序 = 顺时针排列；支持从文件管理器拖入。"))
        split.addLayout(left, 2)

        right = QVBoxLayout()
        right.setSpacing(6)
        box = QGroupBox("选中项")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(4, 6, 4, 4)
        self.form = ItemForm()
        self.form.changed.connect(self._on_item_changed)
        bl.addWidget(self.form)
        right.addWidget(box)
        right.addStretch(1)
        split.addLayout(right, 3)
        lay.addLayout(split, 1)

        self.count_hint = _hint("")
        lay.addWidget(self.count_hint)
        return page

    def _refresh_list(self, select: int | None = None) -> None:
        current = select if select is not None else max(0, self.list.currentRow())
        self._loading = True
        try:
            self.list.clear()
            dpr = float(self.devicePixelRatioF() or 1.0)
            for it in self.items:
                kind = TYPE_LABEL.get(str(it.get("type") or "auto"), "自动")
                text = f"{it.get('label') or '(未命名)'}"
                row = QListWidgetItem(load_pixmap(it, 26, dpr), text)
                row.setToolTip(f"{kind} · {it.get('target') or ''}")
                row.setData(Qt.UserRole, id(it))
                self.list.addItem(row)
            n = len(self.items)
            self.count_hint.setText(
                f"共 {n} 项" + ("（已满，最多 12 项）" if n >= MAX_ITEMS else f"，还能再加 {MAX_ITEMS - n} 项"))
            if self.items:
                self.list.setCurrentRow(min(max(0, current), n - 1))
        finally:
            self._loading = False
        self._on_select(max(0, self.list.currentRow()))

    def _current(self) -> dict | None:
        row = self.list.currentRow()
        if 0 <= row < len(self.items):
            return self.items[row]
        return None

    def _on_select(self, row: int) -> None:
        if self._loading:
            return
        self.form.set_item(self.items[row] if 0 <= row < len(self.items) else None)

    def _after_reorder(self) -> None:
        """拖拽排序后，把 self.items 按列表里的新顺序重排。"""
        ids = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        by_id = {id(it): it for it in self.items}
        new_order = [by_id[i] for i in ids if i in by_id]
        if len(new_order) == len(self.items):
            self.items = new_order
        self._refresh_list(select=self.list.currentRow())
        self._sync_preview()

    def _on_item_changed(self) -> None:
        row = self.list.currentRow()
        item = self._current()
        if item is None or not (0 <= row < self.list.count()):
            return
        rowitem = self.list.item(row)
        rowitem.setText(item.get("label") or "(未命名)")
        dpr = float(self.devicePixelRatioF() or 1.0)
        rowitem.setIcon(load_pixmap(item, 26, dpr))
        kind = TYPE_LABEL.get(str(item.get("type") or "auto"), "自动")
        rowitem.setToolTip(f"{kind} · {item.get('target') or ''}")
        self._sync_preview()

    # --- 增删改
    def _add_item(self, item: dict) -> None:
        if len(self.items) >= MAX_ITEMS:
            QMessageBox.information(self, "已满", f"最多 {MAX_ITEMS} 项，先删掉一些再加。")
            return
        self.items.append(item)
        self._refresh_list(select=len(self.items) - 1)
        self._sync_preview()

    def _add_app(self) -> None:
        dlg = AppPicker(self)
        if dlg.exec() == QDialog.Accepted:
            for app in dlg.chosen():
                self._add_item(app)

    def _add_path(self, kind: str) -> None:
        start = str(Path.home())
        if kind == "folder":
            path = QFileDialog.getExistingDirectory(self, "选择文件夹", start)
        else:
            path, _ = QFileDialog.getOpenFileName(self, "选择文件", start)
        if path:
            self._add_item({"label": Path(path).stem if kind == "file" else Path(path).name,
                            "type": kind, "target": path})

    def _add_files(self, paths: list[str]) -> None:
        for p in paths:
            q = Path(p)
            self._add_item({"label": q.stem if q.is_file() else q.name,
                            "type": "file" if q.is_file() else "folder",
                            "target": str(q)})

    def _add_url(self) -> None:
        self._add_item({"label": "新网址", "type": "url", "target": "https://"})

    def _remove(self) -> None:
        row = self.list.currentRow()
        if not (0 <= row < len(self.items)):
            return
        item = self.items[row]
        if item.get("type") == "config":
            self.status.setText("「打开设置面板」这一项建议保留，方便随时进来改。" )
        del self.items[row]
        self._refresh_list(select=min(row, len(self.items) - 1))
        self._sync_preview()

    def _move(self, delta: int) -> None:
        row = self.list.currentRow()
        new = row + delta
        if not (0 <= row < len(self.items)) or not (0 <= new < len(self.items)):
            return
        self.items[row], self.items[new] = self.items[new], self.items[row]
        self._refresh_list(select=new)
        self._sync_preview()

    # ------------------------------------------------------------ 外观页

    def _build_look_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 10, 0, 0)
        outer.setSpacing(10)

        box = QGroupBox("尺寸与间距")
        bl = QVBoxLayout(box)
        bl.setSpacing(8)
        self.s_radius = Slider("转盘半径", 80, 220, 132, " px", tip="转盘的外圈大小")
        self.s_icon = Slider("图标大小", 24, 64, 40, " px", tip="每个扇区图标的大小")
        self.s_font = Slider("文字大小", 7, 18, 10, " px", tip="扇区标签与中心文字的字号")
        self.s_dead = Slider("中心死区", 15, 70, 34, " %",
                             tip="指针离中心多近时不选中任何扇区；越小越灵敏")
        self.s_follow = Slider("跟随指针", 0, 80, 42, " %",
                               tip="盘面朝鼠标方向平移的比例；0 = 完全固定")
        for s in (self.s_radius, self.s_icon, self.s_font, self.s_dead, self.s_follow):
            s.changed.connect(self._sync_preview)
            bl.addWidget(s)
        bl.addWidget(_hint("跟随指针越大越贴手（0 = 固定）；中心死区越小越灵敏。"))
        outer.addWidget(box)

        box2 = QGroupBox("配色")
        g = QGridLayout(box2)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(8)
        g.addWidget(QLabel("盘面底色"), 0, 0)
        self.c_bg = ColorField("#1B1D23")
        self.c_bg.changed.connect(self._sync_preview)
        g.addWidget(self.c_bg, 0, 1, 1, 3)
        g.addWidget(QLabel("文字颜色"), 1, 0)
        self.c_text = ColorField("#EDEFF5")
        self.c_text.changed.connect(self._sync_preview)
        g.addWidget(self.c_text, 1, 1, 1, 3)
        g.addWidget(QLabel("高亮描边"), 2, 0)
        self.c_accent = ColorField("#4C8DFF")
        self.c_accent.changed.connect(self._sync_preview)
        g.addWidget(self.c_accent, 2, 1, 1, 3)
        outer.addWidget(box2)

        box3 = QGroupBox("背景与透明度")
        bl3 = QVBoxLayout(box3)
        self.s_alpha = Slider("盘面不透明", 120, 255, 236, "",
                             tip="盘面底色的不透明度")
        self.s_dim = Slider("背景压暗", 0, 90, 22, " %",
                            tip="弹出菜单时把整屏调暗，突出转盘")
        for s in (self.s_alpha, self.s_dim):
            s.changed.connect(self._sync_preview)
            bl3.addWidget(s)
        bl3.addWidget(_hint("背景压暗把整屏调暗以突出转盘；0 = 不压暗。"))
        outer.addWidget(box3)
        outer.addStretch(1)
        return page

    # ------------------------------------------------------------ 触发页

    def _build_trigger_tab(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 10, 0, 0)
        outer.setSpacing(10)

        box = QGroupBox("怎么唤出")
        bl = QVBoxLayout(box)
        bl.setSpacing(8)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(16)
        self.rb_hold = QRadioButton("按住中键 0.3 秒（推荐）")
        self.rb_click = QRadioButton("按下中键立即弹出")
        self.rb_hold.setToolTip("不影响浏览器「中键新标签」、终端「中键粘贴」")
        mode_row.addWidget(self.rb_hold)
        mode_row.addWidget(self.rb_click)
        mode_row.addStretch(1)
        bl.addLayout(mode_row)
        self.rb_hold.toggled.connect(self._sync_trigger)
        self.rb_click.toggled.connect(self._sync_trigger)

        self.s_hold = Slider("长按阈值", 120, 800, 260, " ms")
        self.s_drag = Slider("拖拽判定", 0, 80, 26, " px")
        self.s_hold.changed.connect(self._sync_trigger)
        self.s_drag.changed.connect(self._sync_trigger)
        bl.addWidget(self.s_hold)
        bl.addWidget(self.s_drag)
        bl.addWidget(_hint("长按期间指针移动超过该距离，就当作拖拽，不弹菜单。"))

        out_row = QHBoxLayout()
        out_row.addWidget(QLabel("备用快捷键"))
        self.ed_hotkey = QLineEdit()
        self.ed_hotkey.setPlaceholderText("例如 ctrl+alt+space")
        out_row.addWidget(self.ed_hotkey, 1)
        bl.addLayout(out_row)
        bl.addWidget(_hint("中键被占用时用它唤出；菜单保持打开，用左键点选。"))
        outer.addWidget(box)

        box2 = QGroupBox("运行")
        bl2 = QVBoxLayout(box2)
        self.cb_autostart = QCheckBox("开机自动启动")
        bl2.addWidget(self.cb_autostart)
        self.cb_suppress = QCheckBox("拦截中键事件（仅 Windows，避免被其他程序同时响应）")
        bl2.addWidget(self.cb_suppress)
        if not cfgmod.IS_WIN:
            self.cb_suppress.setEnabled(False)
            self.cb_suppress.setToolTip("Linux 下由系统层处理，此项无效")

        btns = QHBoxLayout()
        b_json = QPushButton("打开 config.json")
        b_json.clicked.connect(lambda: self._open_path(cfgmod.CONFIG_PATH))
        b_log = QPushButton("打开日志")
        b_log.clicked.connect(lambda: self._open_path(cfgmod.LOG_PATH))
        btns.addWidget(b_json)
        btns.addWidget(b_log)
        btns.addStretch(1)
        bl2.addLayout(btns)
        outer.addWidget(box2)
        outer.addStretch(1)
        return page

    def _open_path(self, path: Path) -> None:
        from core import open_in_editor
        try:
            open_in_editor(path)
        except Exception as e:
            QMessageBox.warning(self, "打开失败", str(e))

    # ------------------------------------------------------------ 数据流

    def _load_from_cfg(self) -> None:
        self._loading = True
        try:
            ap = self.cfg.get("appearance") or {}
            defaults = cfgmod.DEFAULT_APPEARANCE
            self.s_radius.set(ap.get("radius", defaults["radius"]))
            self.s_icon.set(ap.get("icon_size", defaults["icon_size"]))
            self.s_font.set(round(float(ap.get("font_size", defaults["font_size"])) * 1.0))
            self.s_dead.set(float(ap.get("dead_zone", defaults["dead_zone"])) * 100)
            self.s_follow.set(float(ap.get("follow", defaults["follow"])) * 100)
            self.s_alpha.set(ap.get("bg_alpha", defaults["bg_alpha"]))
            self.s_dim.set(float(ap.get("dim", defaults["dim"])) * 100)
            self.c_bg.set_color(str(ap.get("bg", defaults["bg"])))
            self.c_text.set_color(str(ap.get("text", defaults["text"])))
            self.c_accent.set_color(str(ap.get("accent", defaults["accent"])))

            tr = self.cfg.get("trigger") or {}
            tdef = cfgmod.DEFAULT_TRIGGER
            mode = str(tr.get("mode", tdef["mode"]))
            self.rb_click.setChecked(mode == "click")
            self.rb_hold.setChecked(mode != "click")
            self.s_hold.set(tr.get("hold_ms", tdef["hold_ms"]))
            self.s_drag.set(tr.get("drag_guard", tdef["drag_guard"]))
            self.ed_hotkey.setText(str(tr.get("hotkey", tdef["hotkey"])))
            self.cb_suppress.setChecked(bool(tr.get("suppress", False)))

            from core import is_autostart
            try:
                self.cb_autostart.setChecked(is_autostart())
            except Exception:
                self.cb_autostart.setChecked(False)
        finally:
            self._loading = False
        self._sync_trigger()
        self._sync_preview()

    def _appearance(self) -> dict:
        return {
            "radius": int(self.s_radius.get()),
            "icon_size": int(self.s_icon.get()),
            "font_size": round(float(self.s_font.get()), 1),
            "dead_zone": round(self.s_dead.get() / 100.0, 3),
            "follow": round(self.s_follow.get() / 100.0, 3),
            "bg_alpha": int(self.s_alpha.get()),
            "dim": round(self.s_dim.get() / 100.0, 3),
            "bg": self.c_bg.get(),
            "text": self.c_text.get(),
            "accent": self.c_accent.get(),
        }

    def _trigger(self) -> dict:
        tr = dict(self.cfg.get("trigger") or {})
        tr["mode"] = "click" if self.rb_click.isChecked() else "hold"
        tr["hold_ms"] = int(self.s_hold.get())
        tr["drag_guard"] = int(self.s_drag.get())
        tr["hotkey"] = self.ed_hotkey.text().strip()
        tr["suppress"] = bool(self.cb_suppress.isChecked())
        tr.setdefault("button", "middle")
        return tr

    def _sync_preview(self) -> None:
        if self._loading:
            return
        self.preview.set_data(self.items, self._appearance())

    def _sync_trigger(self) -> None:
        if self._loading:
            return
        self.s_hold.setEnabled(self.rb_hold.isChecked())

    # ------------------------------------------------------------ 保存

    def _validate(self) -> list[str]:
        errs = []
        for i, it in enumerate(self.items, 1):
            label = str(it.get("label") or "").strip()
            kind = str(it.get("type") or "auto")
            if not label:
                errs.append(f"第 {i} 项没有名称")
            if kind != "config" and not str(it.get("target") or "").strip():
                errs.append(f"「{label or i}」没有填写目标")
            if kind == "url":
                t = str(it.get("target") or "").strip()
                if t and not t.startswith(("http://", "https://", "file://")):
                    errs.append(f"「{label}」的网址要以 http:// 或 https:// 开头")
        return errs

    def _save(self) -> None:
        errs = self._validate()
        if errs:
            QMessageBox.warning(self, "还有问题", "\n".join(errs))
            return
        if not self.items:
            QMessageBox.warning(self, "没有启动项", "至少保留一个启动项。")
            return

        cfg = copy.deepcopy(self.cfg)
        cfg["appearance"] = self._appearance()
        cfg["trigger"] = self._trigger()
        cfg["items"] = [self._clean(dict(i)) for i in self.items]

        try:
            cfgmod.save(cfg)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return

        try:
            from core import set_autostart
            set_autostart(bool(self.cb_autostart.isChecked()))
        except Exception as e:
            QMessageBox.warning(self, "开机自启设置失败", str(e))

        self.cfg = cfg
        self.applied.emit(cfg)
        self.accept()

    @staticmethod
    def _clean(item: dict) -> dict:
        out = {}
        for k in ("label", "type", "target", "args", "icon", "color"):
            v = item.get(k)
            if v in (None, "", []):
                continue
            out[k] = v
        if str(out.get("type")) == "config":
            out.pop("target", None)
        out.setdefault("type", "auto")
        return out

    def _reset(self) -> None:
        if QMessageBox.question(self, "恢复默认",
                                "把所有启动项和外观恢复成默认设置？") != QMessageBox.Yes:
            return
        self.cfg = cfgmod.default_config()
        self.items = [dict(i) for i in self.cfg["items"]]
        self._load_from_cfg()
        self._refresh_list(select=0)
        self.status.setText("已填入默认值，点「保存并应用」才生效。")
