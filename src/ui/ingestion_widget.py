from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .workers import IngestionWorker, SearchWorker

ROLE_SLUG = Qt.UserRole
ROLE_NAME = Qt.UserRole + 1


class IngestionWidget(QWidget):
    """Landing page: Mode A online fetch with live suggestions, Mode B file upload."""

    analysis_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("LandingPanel")
        self.worker: IngestionWorker | None = None
        self._search_worker: SearchWorker | None = None
        self._selected_slug: str | None = None
        self._selected_name: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 50, 60, 40)
        layout.setSpacing(20)

        title = QLabel("Stock Analysis Tool v2.0")
        title.setObjectName("TitleLabel")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        subtitle = QLabel("Search a company or upload a local report to begin")
        subtitle.setObjectName("SubtitleLabel")
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)

        search_card = QWidget()
        search_card.setObjectName("SearchCard")
        search_layout = QVBoxLayout(search_card)
        search_layout.setContentsMargins(14, 14, 14, 14)
        search_layout.setSpacing(10)

        self.search_label = QLabel("Company search")
        self.search_label.setObjectName("SectionLabel")
        self.search_label.setAlignment(Qt.AlignLeft)
        search_layout.addWidget(self.search_label)

        row = QHBoxLayout()
        row.setSpacing(10)
        self.ticker_input = QLineEdit()
        self.ticker_input.setObjectName("MainInput")
        self.ticker_input.setPlaceholderText("Search company or ticker (e.g., Axis Bank, RELIANCE)...")
        self.ticker_input.setMinimumHeight(44)
        self.ticker_input.setClearButtonEnabled(True)
        self.ticker_input.setToolTip("Search by company name or ticker")
        self.ticker_input.setAccessibleName("Company search")
        self.ticker_input.setFocusPolicy(Qt.StrongFocus)
        self.search_label.setBuddy(self.ticker_input)
        self.ticker_input.returnPressed.connect(self._fetch_online)

        self.fetch_btn = QPushButton("Fetch Online Data")
        self.fetch_btn.setObjectName("FetchButton")
        self.fetch_btn.setMinimumHeight(44)
        self.fetch_btn.setMinimumWidth(170)
        self.fetch_btn.setToolTip("Load company data from the online source")
        self.fetch_btn.clicked.connect(self._fetch_online)

        row.addWidget(self.ticker_input, stretch=1)
        row.addWidget(self.fetch_btn)
        search_layout.addLayout(row)
        layout.addWidget(search_card)

        self.suggestion_list = QListWidget()
        self.suggestion_list.setMaximumHeight(230)
        self.suggestion_list.setVisible(False)
        self.suggestion_list.setAlternatingRowColors(True)
        self.suggestion_list.setSelectionMode(QListWidget.SingleSelection)
        self.suggestion_list.setFocusPolicy(Qt.StrongFocus)
        self.suggestion_list.itemClicked.connect(self._apply_suggestion)
        self.suggestion_list.itemActivated.connect(self._apply_suggestion)
        layout.addWidget(self.suggestion_list)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(350)
        self._debounce.timeout.connect(self._start_search)
        self.ticker_input.textChanged.connect(self._on_ticker_changed)

        self.upload_btn = QPushButton("Upload Local Report  (PDF / XLSX / XLS / CSV / JSON)")
        self.upload_btn.setObjectName("SecondaryButton")
        self.upload_btn.setMinimumHeight(56)
        self.upload_btn.setToolTip("Upload a financial report file from your machine")
        self.upload_btn.clicked.connect(self._upload_file)
        layout.addWidget(self.upload_btn)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0)
        layout.addWidget(self.progress)

        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusLabel")
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addStretch(1)

    def _on_ticker_changed(self, text: str) -> None:
        self._selected_slug = None
        self._selected_name = None

        if len(text.strip()) >= 2:
            self._debounce.start()
        else:
            self.suggestion_list.setVisible(False)

    def _start_search(self) -> None:
        query = self.ticker_input.text().strip()

        if len(query) < 2:
            return

        self._search_worker = SearchWorker(query)
        self._search_worker.results_ready.connect(self._show_suggestions)
        self._search_worker.search_failed.connect(self._hide_suggestions)
        self._search_worker.start()

    def _hide_suggestions(self, _message: str = "") -> None:
        self.suggestion_list.setVisible(False)

    def _show_suggestions(self, results: list) -> None:
        self.suggestion_list.clear()

        if not results:
            self.suggestion_list.setVisible(False)
            return

        for result in results:
            item = QListWidgetItem(f"{result['name']}   ({result['slug']})")
            item.setData(ROLE_SLUG, result["slug"])
            item.setData(ROLE_NAME, result["name"])
            self.suggestion_list.addItem(item)

        self.suggestion_list.setVisible(True)

    def _apply_suggestion(self, item: QListWidgetItem) -> None:
        self._selected_slug = item.data(ROLE_SLUG)
        self._selected_name = item.data(ROLE_NAME)

        self.ticker_input.blockSignals(True)
        self.ticker_input.setText(self._selected_name or "")
        self.ticker_input.blockSignals(False)

        self.suggestion_list.setVisible(False)

    def _fetch_online(self) -> None:
        text = self.ticker_input.text().strip()

        if not text:
            QMessageBox.warning(self, "Input Required", "Please enter a company name or ticker.")
            return

        target = self._selected_slug if (self._selected_slug and text == self._selected_name) else text
        self.suggestion_list.setVisible(False)
        self._start_worker(ticker=target, file_path=None)

    def _upload_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Financial Report",
            "",
            "Supported Files (*.pdf *.xlsx *.xls *.csv *.json)",
        )
        if path:
            self._start_worker(ticker=None, file_path=path)

    def _start_worker(self, ticker: str | None, file_path: str | None) -> None:
        self._set_ui_loading(True)
        self.status_label.setText("Processing data... Please wait.")

        self.worker = IngestionWorker(ticker, file_path)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_finished(self, ticker: str) -> None:
        self._set_ui_loading(False)
        self.status_label.setText(f"Loaded {ticker}. Opening workspace...")
        self.analysis_requested.emit(ticker)

    def _on_error(self, error_msg: str) -> None:
        self._set_ui_loading(False)
        self.status_label.setText(f"Error: {error_msg}")
        error_text = "Failed to process data:\n\n" + error_msg
        QMessageBox.critical(self, "Ingestion Error", error_text)

    def _set_ui_loading(self, loading: bool) -> None:
        self.progress.setVisible(loading)
        self.fetch_btn.setEnabled(not loading)
        self.upload_btn.setEnabled(not loading)
        self.ticker_input.setEnabled(not loading)
