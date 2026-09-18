from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget


class ChartGalleryWidget(QWidget):
    """PySide6 widget for displaying exported technical chart PNGs."""

    def __init__(self, image_paths: list[Path], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Technical Charts")

        layout = QVBoxLayout(self)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)

        content = QWidget()
        content_layout = QVBoxLayout(content)

        for image_path in image_paths:
            label = QLabel(image_path.name)
            pixmap = QPixmap(str(image_path))

            if not pixmap.isNull():
                label.setPixmap(pixmap.scaledToWidth(1100, Qt.SmoothTransformation))

            content_layout.addWidget(label)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        layout.addWidget(scroll)
