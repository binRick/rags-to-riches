import sys
import threading
import webbrowser
from datetime import datetime

from PyQt6.QtCore import Qt, QSortFilterProxyModel, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStatusBar,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from . import cache, github, search as search_mod

# ── Catppuccin Mocha palette ──────────────────────────────────────────────────
BG       = "#1e1e2e"
SURFACE  = "#181825"
OVERLAY  = "#313244"
TEXT     = "#cdd6f4"
SUBTEXT  = "#6c7086"
ACCENT   = "#89b4fa"
GREEN    = "#a6e3a1"
YELLOW   = "#f9e2af"

STYLE = f"""
QMainWindow, QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}}
QLineEdit, QComboBox {{
    background: {OVERLAY};
    color: {TEXT};
    border: none;
    border-radius: 6px;
    padding: 5px 10px;
    font-size: 13px;
}}
QComboBox QAbstractItemView {{
    background: {OVERLAY};
    color: {TEXT};
    selection-background-color: {ACCENT};
    selection-color: {BG};
    border: none;
}}
QPushButton {{
    background: {OVERLAY};
    color: {ACCENT};
    border: none;
    border-radius: 6px;
    padding: 5px 14px;
    font-size: 13px;
}}
QPushButton:hover  {{ background: {ACCENT}; color: {BG}; }}
QPushButton:disabled {{ color: {SUBTEXT}; }}
QTableView {{
    background: {SURFACE};
    color: {TEXT};
    gridline-color: {OVERLAY};
    border: none;
    font-size: 13px;
    selection-background-color: {OVERLAY};
    selection-color: {TEXT};
}}
QHeaderView::section {{
    background: {OVERLAY};
    color: {ACCENT};
    border: none;
    padding: 6px 8px;
    font-weight: bold;
}}
QScrollBar:vertical {{
    background: {BG};
    width: 8px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {OVERLAY};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QStatusBar {{
    background: #11111b;
    color: {SUBTEXT};
    font-size: 11px;
}}
QLabel#toolbar-label {{
    color: {ACCENT};
    font-weight: bold;
}}
"""


# ── Background fetch worker ───────────────────────────────────────────────────

class FetchWorker(QThread):
    page_fetched = pyqtSignal(int, int)   # page, total
    finished     = pyqtSignal(list)       # repos
    error        = pyqtSignal(str)

    def run(self) -> None:
        try:
            token = github.get_token()
            if not token:
                self.error.emit("No GitHub token found. Set GITHUB_TOKEN env var.")
                return

            def on_page(page: int, total: int) -> None:
                self.page_fetched.emit(page, total)

            repos = github.fetch_starred(token, on_page=on_page)
            cache.save(repos)
            self.finished.emit(repos)
        except Exception as exc:
            self.error.emit(str(exc))


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    COLS = ["Repository", "Description", "Language", "Stars", "URL"]
    COL_WIDTHS = [220, 380, 110, 70, 260]

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Rags to Riches — GitHub Stars")
        self.resize(1150, 700)

        self._all_repos: list[dict] = []
        self._worker: FetchWorker | None = None

        self._build_ui()
        self._load_cache_or_fetch()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(12, 10, 12, 4)
        layout.setSpacing(8)

        # toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        toolbar.addWidget(self._label("Search:"))
        self._search = QLineEdit()
        self._search.setPlaceholderText("name, description, topic, language…")
        self._search.setMinimumWidth(260)
        self._search.textChanged.connect(self._apply_filters)
        toolbar.addWidget(self._search)

        toolbar.addWidget(self._label("Language:"))
        self._lang_combo = QComboBox()
        self._lang_combo.setMinimumWidth(130)
        self._lang_combo.currentTextChanged.connect(self._apply_filters)
        toolbar.addWidget(self._lang_combo)

        toolbar.addWidget(self._label("Sort:"))
        self._sort_combo = QComboBox()
        self._sort_combo.addItems(["Stars", "Name", "Updated"])
        self._sort_combo.setMinimumWidth(100)
        self._sort_combo.currentTextChanged.connect(self._apply_filters)
        toolbar.addWidget(self._sort_combo)

        toolbar.addStretch()

        self._refresh_btn = QPushButton("⟳  Refresh")
        self._refresh_btn.clicked.connect(self._fetch)
        toolbar.addWidget(self._refresh_btn)

        layout.addLayout(toolbar)

        # table
        self._model = QStandardItemModel(0, len(self.COLS))
        self._model.setHorizontalHeaderLabels(self.COLS)

        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setShowGrid(False)
        self._table.verticalHeader().setDefaultSectionSize(28)

        self._table.setStyleSheet(f"QTableView {{ alternate-background-color: {BG}; }}")

        for i, w in enumerate(self.COL_WIDTHS):
            self._table.setColumnWidth(i, w)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        self._table.doubleClicked.connect(self._open_selected)

        layout.addWidget(self._table)

        # status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Loading…")

    def _label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("toolbar-label")
        return lbl

    # ── Data loading ──────────────────────────────────────────────────────────

    def _load_cache_or_fetch(self) -> None:
        repos, timestamp = cache.load()
        if repos:
            age = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
            self._set_repos(repos)
            self._status.showMessage(f"Loaded {len(repos)} repos from cache (fetched at {age})")
        else:
            self._fetch()

    def _fetch(self) -> None:
        if self._worker and self._worker.isRunning():
            return
        self._refresh_btn.setEnabled(False)
        self._status.showMessage("Fetching starred repos from GitHub…")
        self._worker = FetchWorker()
        self._worker.page_fetched.connect(self._on_page)
        self._worker.finished.connect(self._on_fetch_done)
        self._worker.error.connect(self._on_fetch_error)
        self._worker.start()

    def _on_page(self, page: int, total: int) -> None:
        self._status.showMessage(f"Fetching… {total} repos so far (page {page})")

    def _on_fetch_done(self, repos: list) -> None:
        self._set_repos(repos)
        self._status.showMessage(f"Fetched {len(repos)} starred repos from GitHub")
        self._refresh_btn.setEnabled(True)

    def _on_fetch_error(self, msg: str) -> None:
        self._status.showMessage(f"Error: {msg}")
        self._refresh_btn.setEnabled(True)

    def _set_repos(self, repos: list[dict]) -> None:
        self._all_repos = repos
        langs = sorted({r.get("language") or "" for r in repos if r.get("language")})
        current_lang = self._lang_combo.currentText()
        self._lang_combo.blockSignals(True)
        self._lang_combo.clear()
        self._lang_combo.addItems(["All"] + langs)
        idx = self._lang_combo.findText(current_lang)
        self._lang_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self._lang_combo.blockSignals(False)
        self._apply_filters()

    # ── Filtering & display ───────────────────────────────────────────────────

    def _apply_filters(self) -> None:
        query = self._search.text().strip()
        lang  = self._lang_combo.currentText()
        sort  = self._sort_combo.currentText()

        repos = self._all_repos

        if query:
            repos = search_mod.search(repos, query)

        if lang and lang != "All":
            repos = [r for r in repos if (r.get("language") or "") == lang]

        if sort == "Stars":
            repos = sorted(repos, key=lambda r: r.get("stargazers_count", 0), reverse=True)
        elif sort == "Name":
            repos = sorted(repos, key=lambda r: r["full_name"].lower())
        elif sort == "Updated":
            repos = sorted(repos, key=lambda r: r.get("updated_at", ""), reverse=True)

        self._populate(repos)

    def _populate(self, repos: list[dict]) -> None:
        self._model.removeRows(0, self._model.rowCount())

        for repo in repos:
            stars_item = QStandardItem()
            stars_item.setData(repo.get("stargazers_count", 0), Qt.ItemDataRole.DisplayRole)
            stars_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            row = [
                QStandardItem(repo["full_name"]),
                QStandardItem((repo.get("description") or "")[:100]),
                QStandardItem(repo.get("language") or ""),
                stars_item,
                QStandardItem(repo["html_url"]),
            ]
            self._model.appendRow(row)

        total = len(self._all_repos)
        shown = len(repos)
        suffix = f"  ·  showing {shown} of {total}" if shown != total else f"  ·  {total} repos"
        current = self._status.currentMessage().split("  ·")[0]
        self._status.showMessage(current + suffix)

    # ── Events ────────────────────────────────────────────────────────────────

    def _open_selected(self) -> None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return
        row = indexes[0].row()
        url = self._model.item(row, 4).text()
        webbrowser.open(url)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._open_selected()
        else:
            super().keyPressEvent(event)


# ── Entry point ───────────────────────────────────────────────────────────────

def run() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
