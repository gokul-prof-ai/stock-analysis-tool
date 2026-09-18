from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class StatTile(QWidget):
    """Small KPI tile: label above value."""

    def __init__(self, label: str, value: str, positive: bool | None = None, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        top = QLabel(label)
        top.setObjectName("StatLabel")
        layout.addWidget(top)

        bottom = QLabel(value)
        if positive is True:
            bottom.setObjectName("PosValue")
        elif positive is False:
            bottom.setObjectName("NegValue")
        else:
            bottom.setObjectName("StatValue")
        layout.addWidget(bottom)


class GaugeWidget(QWidget):
    """TradingView-style semicircular decision gauge (0-100)."""

    def __init__(self, score: Optional[float], parent=None) -> None:
        super().__init__(parent)
        self._score = score
        self.setFixedHeight(150)
        self.setMinimumWidth(260)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        width = self.width()
        height = self.height()
        side = min(width, (height - 24) * 2)
        rect = QRectF((width - side) / 2, height - 24 - side / 2, side, side)

        pen = QPen()
        pen.setWidthF(12)
        pen.setCapStyle(Qt.RoundCap)

        zones = [(0, 40, "#f23645"), (40, 60, "#ff9800"), (60, 100, "#089981")]

        for low, high, color in zones:
            pen.setColor(QColor(color))
            painter.setPen(pen)
            start = 180 - low * 1.8
            span = -(high - low) * 1.8
            painter.drawArc(rect, int(start * 16), int(span * 16))

        if self._score is not None:
            clamped = max(0.0, min(100.0, self._score))
            angle = 180 - clamped * 1.8
            center_x = rect.center().x()
            center_y = rect.center().y()
            radius = side / 2 - 12
            tip_x = center_x + radius * math.cos(math.radians(angle))
            tip_y = center_y - radius * math.sin(math.radians(angle))

            painter.setPen(QPen(QColor("#d1d4dc"), 3))
            painter.drawLine(QPointF(center_x, center_y), QPointF(tip_x, tip_y))

            painter.setPen(QPen(QColor("#d1d4dc")))
            painter.drawText(QRectF(0, height - 22, width, 20), Qt.AlignCenter, f"{clamped:.0f} / 100")

        painter.end()
