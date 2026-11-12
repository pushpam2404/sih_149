"""Lists generated reports (from the reports/ directory) and opens them."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QSize, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import REPORTS_DIR
from app.gui.theme import COLORS
from app.gui.widgets import icons
from app.gui.widgets.ui import Badge, Card, EmptyHint, Page, button, hint

_KIND_LABELS = {
    "drive_erase": "Drive erase",
    "file_erase": "File erase",
    "recovery": "Recovery scan",
}


class ReportView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        page = Page("Reports", "PDF reports generated after each erase or recovery scan (a JSON copy is saved alongside).")
        root.addWidget(page)

        refresh_btn = button("Refresh", icon_name="refresh")
        refresh_btn.clicked.connect(self.refresh)
        page.header_actions.addWidget(refresh_btn)

        open_btn = button("Open PDF", variant="primary", icon_name="file-output")
        open_btn.clicked.connect(self._open_selected)
        page.header_actions.addWidget(open_btn)

        card = Card("Generated reports", icon_name="reports")
        self._count_badge = Badge("0 reports", "neutral")
        card.actions.addWidget(self._count_badge)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SingleSelection)
        self._list.setIconSize(QSize(18, 18))
        self._list.setSpacing(2)
        self._list.itemDoubleClicked.connect(lambda _item: self._open_selected())
        self._empty = EmptyHint("No reports yet. They appear here after an erase or a recovery scan.", self._list.viewport())
        card.body.addWidget(self._list, 1)
        card.body.addWidget(hint(f"Folder: {REPORTS_DIR}  ·  Double-click a report to open it."))
        page.body.addWidget(card, 1)

        self.refresh()

    def refresh(self) -> None:
        self._list.clear()
        pdfs = sorted(REPORTS_DIR.glob("*.pdf"), reverse=True) if REPORTS_DIR.exists() else []
        for pdf_path in pdfs:
            item = QListWidgetItem(icons.icon("reports", COLORS["text_muted"]), pdf_path.name)
            kind = next((label for prefix, label in _KIND_LABELS.items() if pdf_path.name.startswith(prefix)), "Report")
            modified = datetime.fromtimestamp(pdf_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            item.setToolTip(f"{kind} · saved {modified}")
            self._list.addItem(item)
        self._count_badge.set(f"{len(pdfs)} report{'s' if len(pdfs) != 1 else ''}", "primary" if pdfs else "neutral")
        self._empty.setVisible(not pdfs)

    def _open_selected(self) -> None:
        item = self._list.currentItem()
        if item is None:
            QMessageBox.warning(self, "No selection", "Select a report from the list first.")
            return
        path = REPORTS_DIR / item.text()
        if not path.exists():
            QMessageBox.critical(self, "Not found", f"{path} no longer exists.")
            self.refresh()
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
