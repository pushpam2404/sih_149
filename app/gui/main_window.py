"""Main window: sidebar navigation + stacked pages for the dashboard, the 3 modules, and audit/reports."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config.constants import APP_NAME, APP_VERSION
from app.config.settings import AUDIT_DB_PATH, SIMULATION_MODE_DEFAULT, ensure_data_dirs
from app.core.audit.ledger import AuditLedger
from app.gui.audit_log_view import AuditLogView
from app.gui.dashboard_view import DashboardView
from app.gui.drive_eraser_view import DriveEraserView
from app.gui.file_eraser_view import FileEraserView
from app.gui.recovery_view import RecoveryView
from app.gui.report_view import ReportView
from app.gui.theme import COLORS
from app.gui.widgets import icons
from app.gui.widgets.ui import Badge


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 820)
        # Small enough for a 1366×768 laptop at 125% scaling; pages scroll when content doesn't fit.
        self.setMinimumSize(960, 560)

        ensure_data_dirs()
        self._ledger = AuditLedger(AUDIT_DB_PATH)

        self._dashboard = DashboardView(self._ledger)
        self._drive_eraser = DriveEraserView(self._ledger)
        self._file_eraser = FileEraserView(self._ledger)
        self._recovery = RecoveryView(self._ledger)
        self._audit_log = AuditLogView(self._ledger)
        self._reports = ReportView()

        # (key, section, label, icon, page)
        pages = [
            ("dashboard", None, "Dashboard", "dashboard", self._dashboard),
            ("drive_eraser", "Erase", "Drive Eraser", "hard-drive", self._drive_eraser),
            ("file_eraser", None, "File && Folder Eraser", "file-x", self._file_eraser),
            ("recovery", "Recover", "Recovery", "recover", self._recovery),
            ("audit_log", "Evidence", "Audit Log", "audit", self._audit_log),
            ("reports", None, "Reports", "reports", self._reports),
        ]

        root = QWidget()
        root.setObjectName("AppRoot")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.setObjectName("Pages")
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._page_index: dict[str, int] = {}

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(248)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(14, 18, 14, 16)
        side.setSpacing(2)
        side.addLayout(self._brand())
        side.addSpacing(18)

        for index, (key, section, label, icon_name, page) in enumerate(pages):
            if section:
                side.addSpacing(14)
                section_label = QLabel(section)
                section_label.setObjectName("SidebarSection")
                side.addWidget(section_label)
                side.addSpacing(4)
            nav_btn = QPushButton(label)
            nav_btn.setProperty("nav", True)
            nav_btn.setCheckable(True)
            nav_btn.setCursor(Qt.PointingHandCursor)
            nav_btn.setIcon(icons.icon(icon_name, COLORS["text_subtle"], COLORS["text"]))
            nav_btn.setIconSize(QSize(18, 18))
            nav_btn.setToolTip(label.replace("&&", "&"))
            nav_btn.setFocusPolicy(Qt.TabFocus)
            self._nav_group.addButton(nav_btn, index)
            side.addWidget(nav_btn)
            self._stack.addWidget(page)
            self._page_index[key] = index

        side.addStretch()
        side.addWidget(self._sidebar_footer())

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self._stack, 1)
        self.setCentralWidget(root)

        self._nav_group.idClicked.connect(self._stack.setCurrentIndex)
        self._stack.currentChanged.connect(self._on_tab_changed)
        self._dashboard.navigate_requested.connect(self._navigate_to)
        self._nav_group.button(0).setChecked(True)
        # Start with focus on the page, not the first nav item, so no focus ring shows until the user tabs.
        self._stack.setFocusPolicy(Qt.StrongFocus)
        self._stack.setFocus()

    def _brand(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        row.setContentsMargins(6, 0, 0, 0)
        # The mark is a chain link written as a hash fragment: every action in
        # this app ends up as one link in the audit chain.
        logo = QLabel("#0")
        logo.setObjectName("BrandMark")
        logo.setFixedSize(32, 32)
        logo.setAlignment(Qt.AlignCenter)
        row.addWidget(logo)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        title = QLabel("Secure Erase & Recovery")
        title.setObjectName("BrandTitle")
        texts.addWidget(title)
        subtitle = QLabel("SIH 26149 · NTRO")
        subtitle.setObjectName("BrandSubtitle")
        texts.addWidget(subtitle)
        row.addLayout(texts, 1)
        return row

    def _sidebar_footer(self) -> QWidget:
        footer = QFrame()
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(6, 10, 6, 0)
        layout.setSpacing(8)
        if SIMULATION_MODE_DEFAULT:
            badge = Badge("Simulation mode on by default", "warning")
            badge.setToolTip("Drive erases start with Simulation mode checked. Real wipes need it turned off explicitly.")
            layout.addWidget(badge)
        version = QLabel(f"v{APP_VERSION}  ·  hackathon prototype")
        version.setObjectName("SidebarFooter")
        layout.addWidget(version)
        return footer

    def _navigate_to(self, key: str) -> None:
        index = self._page_index.get(key)
        if index is None:
            return
        self._nav_group.button(index).setChecked(True)
        self._stack.setCurrentIndex(index)

    def _on_tab_changed(self, index: int) -> None:
        widget = self._stack.widget(index)
        if widget is self._dashboard:
            self._dashboard.refresh()
        elif widget is self._audit_log:
            self._audit_log.refresh()
        elif widget is self._reports:
            self._reports.refresh()

    def closeEvent(self, event) -> None:
        self._ledger.close()
        super().closeEvent(event)
