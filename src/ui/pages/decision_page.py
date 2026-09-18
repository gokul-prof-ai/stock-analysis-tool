from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.ui.widgets import GaugeWidget


class DecisionPage(QWidget):
    """Investment Decision section with gauge, breakdown and risk flags."""

    def __init__(self) -> None:
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(12)

        placeholder = QLabel("No decision available. Load a company first.")
        placeholder.setObjectName("SubtitleLabel")
        self._layout.addWidget(placeholder)
        self._layout.addStretch(1)

    def set_bundle(self, bundle) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        decision = bundle.decision

        title = QLabel("Investment Decision")
        title.setObjectName("TitleLabel")
        self._layout.addWidget(title)

        if decision is None:
            message = QLabel("Decision engine unavailable for this dataset.")
            message.setObjectName("SubtitleLabel")
            self._layout.addWidget(message)
            self._layout.addStretch(1)
            return

        header = QHBoxLayout()
        gauge = GaugeWidget(decision.score)
        header.addWidget(gauge)

        rec_layout = QVBoxLayout()
        rec_label = QLabel(decision.recommendation.upper())
        rec_label.setObjectName(
            "PosValue" if decision.recommendation in {"buy"} else
            ("NegValue" if decision.recommendation in {"avoid"} else "StatValue")
        )
        rec_label.setStyleSheet("font-size: 30px;")
        rec_layout.addWidget(rec_label)

        score_label = QLabel(f"Composite score: {decision.score if decision.score is not None else 'N/A'} / 100")
        score_label.setObjectName("SubtitleLabel")
        rec_layout.addWidget(score_label)
        rec_layout.addStretch(1)

        header.addLayout(rec_layout)
        header.addStretch(1)
        self._layout.addLayout(header)

        breakdown = decision.inputs.get("component_breakdown", [])

        if breakdown:
            label = QLabel("Signal Breakdown")
            label.setObjectName("SectionLabel")
            self._layout.addWidget(label)

            table = QTableWidget()
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels(["Component", "Reading", "Points"])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setRowCount(len(breakdown))
            table.setAlternatingRowColors(True)

            for row, item in enumerate(breakdown):
                table.setItem(row, 0, QTableWidgetItem(str(item.get("component", ""))))
                table.setItem(row, 1, QTableWidgetItem(str(item.get("reading", ""))))
                points = item.get("points", 0)
                table.setItem(row, 2, QTableWidgetItem(f"{points:+.0f}"))

            self._layout.addWidget(table)

        if decision.rationale:
            label = QLabel("Rationale")
            label.setObjectName("SectionLabel")
            self._layout.addWidget(label)

            for reason in decision.rationale:
                bullet = QLabel(f"• {reason}")
                bullet.setObjectName("BulletLabel")
                bullet.setWordWrap(True)
                self._layout.addWidget(bullet)

        if bundle.forensic is not None and bundle.forensic.red_flags:
            label = QLabel("Risk Flags")
            label.setObjectName("SectionLabel")
            self._layout.addWidget(label)

            for flag in bundle.forensic.red_flags:
                bullet = QLabel(f"• [{flag.severity.upper()}] {flag.code}: {flag.message}")
                bullet.setObjectName("BulletLabel")
                bullet.setWordWrap(True)
                self._layout.addWidget(bullet)

        disclaimer = QLabel(
            "Educational analysis only. Not investment advice. Verify with primary sources before acting."
        )
        disclaimer.setObjectName("SubtitleLabel")
        disclaimer.setWordWrap(True)
        self._layout.addWidget(disclaimer)

        self._layout.addStretch(1)
