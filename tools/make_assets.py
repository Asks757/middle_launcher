"""生成应用图标（assets/icon.png 与 assets/icon.ico）。"""
from __future__ import annotations

import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QBuffer, QByteArray  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from icons import app_icon_pixmap  # noqa: E402

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def png_bytes(size: int) -> bytes:
    pm = app_icon_pixmap(size)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    pm.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def main() -> None:
    app = QApplication([])  # noqa: F841  (QPixmap 需要 QGuiApplication)
    os.makedirs(ASSETS, exist_ok=True)

    with open(os.path.join(ASSETS, "icon.png"), "wb") as f:
        f.write(png_bytes(256))

    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [(s, png_bytes(s)) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, data in images:
        entries += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    with open(os.path.join(ASSETS, "icon.ico"), "wb") as f:
        f.write(header + entries + blobs)

    print("assets written:", os.listdir(ASSETS))


if __name__ == "__main__":
    main()
