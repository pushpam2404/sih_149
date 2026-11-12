"""Overview tab: recent audit activity and chain-integrity status at a glance."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.constants import APP_NAME, APP_VERSION
from app.config.settings import REPORTS_DIR
from app.core.audit.ledger import AuditLedger
from app.gui.theme import COLORS, mono_font
from app.gui.widgets import icons
from app.gui.widgets.ui import Card, EmptyHint, Page, StatTile, button, style_table

_RECENT_LIMIT = 15
_COLUMNS = ["Timestamp (UTC)", "Action", "Target", "Chain link"]

_MODULES = [
    ("drive_eraser", "hard-drive", "Drive Eraser", "Wipe a whole removable drive or disk image, with verification."),
    ("file_eraser", "file-x", "File & Folder Eraser", "Overwrite and delete individual files or a folder."),
    ("recovery", "recover", "Recovery", "Scan an image or drive for deleted files."),
]


class _ModuleCard(QFrame):
    def __init__(self, icon_name: str, title: str, text: str, on_open, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, 18, COLORS["text_subtle"]))
        head.addWidget(ic)
        t = QLabel(title)
        t.setObjectName("CardTitle")
        head.addWidget(t, 1)
        layout.addLayout(head)
        body = QLabel(text)
        body.setObjectName("CardSubtitle")
        body.setWordWrap(True)
        layout.addWidget(body, 1)
        open_btn = button("Open", variant="ghost")
        open_btn.clicked.connect(on_open)
        layout.addWidget(open_btn, 0, Qt.AlignLeft)


class DashboardView(QWidget):
    # Emitted with a page key ("drive_eraser", "file_eraser", "recovery") when a module card is opened.
    navigate_requested = Signal(str)

    def __init__(self, ledger: AuditLedger, parent=None):
        super().__init__(parent)
        self._ledger = ledger

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        page = Page(
            "Overview",
            f"{APP_NAME}  ·  v{APP_VERSION}  ·  every erase and scan is recorded in a hash-chained audit log.",
        )
        root.addWidget(page)

        refresh_btn = button("Refresh", icon_name="refresh")
        refresh_btn.clicked.connect(self.refresh)
        page.header_actions.addWidget(refresh_btn)

        stats = QHBoxLayout()
        stats.setSpacing(16)
        self._entries_tile = StatTile("Audit entries", "activity")
        self._chain_tile = StatTile("Chain integrity", "audit")
        self._reports_tile = StatTile("PDF reports", "reports")
        self._last_tile = StatTile("Last activity", "recover")
        # The chain tile is the one figure that matters most, so it gets the most room.
        for tile, stretch in ((self._chain_tile, 2), (self._entries_tile, 1), (self._reports_tile, 1), (self._last_tile, 1)):
            stats.addWidget(tile, stretch)
        page.body.addLayout(stats)

        modules = QHBoxLayout()
        modules.setSpacing(16)
        for key, icon_name, title, text in _MODULES:
            modules.addWidget(_ModuleCard(icon_name, title, text, lambda _=False, k=key: self.navigate_requested.emit(k)))
        page.body.addLayout(modules)

        activity = Card("Recent activity", "Latest audit log entries, newest first. Each one carries the start of its own hash, the link the next entry chains to.", icon_name="activity")
        self._status_label = QLabel()
        self._status_label.setObjectName("Hint")
        activity.actions.addWidget(self._status_label)
        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        style_table(self._table)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self._empty = EmptyHint("No activity yet. Erase or scan something to see it here.", self._table.viewport())
        activity.body.addWidget(self._table)
        page.body.addWidget(activity, 1)

        self.refresh()

    def refresh(self) -> None:
        entries = self._ledger.get_entries()
        chain = self._ledger.verify_chain()
        chain_status = "intact" if chain.ok else f"broken at entry {chain.broken_at_entry_id}"
        self._status_label.setText(
            f"Audit entries: {len(entries)}  ·  Chain integrity: {chain_status}"
        )

        self._entries_tile.set_value(str(len(entries)), "logged actions in the ledger")
        if chain.ok:
            self._chain_tile.set_value("Intact", f"{len(entries)} links verified just now, SHA-256", tone="success")
        else:
            self._chain_tile.set_value("Broken", f"first bad entry: {chain.broken_at_entry_id}", tone="danger")
        report_count = len(list(REPORTS_DIR.glob("*.pdf"))) if REPORTS_DIR.exists() else 0
        self._reports_tile.set_value(str(report_count), "in the reports folder")
        if entries:
            last = entries[-1]
            self._last_tile.set_value(last.action.replace("_", " ").capitalize(), last.timestamp[:19].replace("T", "  "))
        else:
            self._last_tile.set_value("None", "nothing logged yet", tone="neutral")

        recent = entries[-_RECENT_LIMIT:][::-1]
        self._table.setRowCount(len(recent))
        for row, entry in enumerate(recent):
            values = [entry.timestamp, entry.action, entry.target, (entry.entry_hash or "")[:10]]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 3:
                    item.setFont(mono_font(12))
                    item.setForeground(QColor(COLORS["seal"]))
                    item.setToolTip(entry.entry_hash)
                if col == 0:
                    item.setFont(mono_font(12))
                    item.setForeground(QColor(COLORS["text_muted"]))
                self._table.setItem(row, col, item)
        self._empty.setVisible(not recent)
