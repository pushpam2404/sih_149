"""Audit ledger viewer: lists every logged action and can verify the hash chain."""
from __future__ import annotations

import json

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

from app.core.audit.ledger import AuditLedger
from app.core.audit.certificate import CertificateGenerator
from app.gui.theme import COLORS, mono_font
from app.gui.widgets import file_dialogs
from app.gui.widgets.ui import Badge, Card, EmptyHint, Page, button, hint, style_table

_COLUMNS = ["ID", "Timestamp (UTC)", "Actor", "Action", "Target", "Entry Hash"]


class AuditLogView(QWidget):
    def __init__(self, ledger: AuditLedger, parent=None):
        super().__init__(parent)
        self._ledger = ledger

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        page = Page(
            "Audit Log",
            "Hash-chained record of every erase and scan. Click a row to see its full details.",
        )
        root.addWidget(page)

        refresh_btn = button("Refresh", icon_name="refresh")
        refresh_btn.clicked.connect(self.refresh)
        page.header_actions.addWidget(refresh_btn)

        verify_btn = button("Verify chain integrity", variant="primary", icon_name="audit")
        verify_btn.clicked.connect(self._verify_chain)
        page.header_actions.addWidget(verify_btn)

        cert_btn = button("Generate certificate (Sec. 63-style)", icon_name="certificate")
        cert_btn.clicked.connect(self._generate_certificate)
        page.header_actions.addWidget(cert_btn)

        card = Card("Ledger entries", icon_name="activity")
        self._count_badge = Badge("0 entries", "neutral")
        card.actions.addWidget(self._count_badge)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        style_table(self._table)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        self._table.itemSelectionChanged.connect(self._show_selected_payload)
        self._empty = EmptyHint("The audit log is empty.", self._table.viewport())
        card.body.addWidget(self._table)
        page.body.addWidget(card, 1)

        card.body.addWidget(
            hint(
                "Each entry is chained to the previous one with SHA-256 and a ratcheting HMAC tag. "
                "Timestamps come from this computer's clock. Verification detects changes after the fact; "
                "it cannot stop someone with file access from editing the database."
            )
        )

        self.refresh()

    def refresh(self) -> None:
        entries = self._ledger.get_entries()
        self._entries = entries
        self._table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            values = [
                str(entry.entry_id),
                entry.timestamp,
                entry.actor,
                entry.action,
                entry.target,
                entry.entry_hash[:16] + "...",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col in (0, 1, 5):
                    item.setFont(mono_font(12))
                    item.setForeground(QColor(COLORS["text_muted"]))
                if col == 5:
                    item.setToolTip(entry.entry_hash)
                self._table.setItem(row, col, item)
        self._count_badge.set(f"{len(entries)} entries", "primary" if entries else "neutral")
        self._empty.setVisible(not entries)

    def _verify_chain(self) -> None:
        result = self._ledger.verify_chain()
        if result.ok:
            QMessageBox.information(
                self, "Chain verified",
                f"Audit chain is intact — {result.entries_checked} entries verified, no tampering detected.",
            )
        else:
            QMessageBox.critical(
                self, "Chain verification FAILED",
                f"Tampering detected at entry {result.broken_at_entry_id}:\n{result.reason}",
            )

    def _show_selected_payload(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(getattr(self, "_entries", [])):
            return
        entry = self._entries[row]
        QMessageBox.information(
            self, f"Entry {entry.entry_id} details",
            json.dumps(entry.payload, indent=2)[:3000],
        )

    def _generate_certificate(self) -> None:
        entries = self._ledger.get_entries()
        if not entries:
            QMessageBox.warning(self, "No entries", "The audit log is empty.")
            return
            
        targets = sorted(list(set(e.target for e in entries)))
        if not targets:
            QMessageBox.warning(self, "No targets", "No targets found in the audit log.")
            return

        target, ok = QInputDialog.getItem(
            self, "Select Target", "Select device/target for the certificate:", targets, 0, False
        )
        if not ok or not target:
            return

        operator_name, ok = QInputDialog.getText(self, "Operator Name", "Enter the operator's name:")
        if not ok or not operator_name:
            return

        org_name, ok = QInputDialog.getText(self, "Organization Name", "Enter the organization's name:")
        if not ok or not org_name:
            return
            
        wipe_status, ok = QInputDialog.getText(self, "Wipe Status", "Enter wipe status as you verified it (e.g. 'Clear - overwrite verified'):", text="Clear - overwrite verified")
        if not ok or not wipe_status:
            return

        out_path = file_dialogs.save_file(
            self, "Save Certificate", f"certificate_{operator_name.replace(' ', '_')}.json", "JSON Files (*.json)"
        )
        if not out_path:
            return

        try:
            generator = CertificateGenerator(self._ledger, operator_name, org_name)
            generator.generate_json_certificate(target, wipe_status, out_path)
            QMessageBox.information(self, "Success", f"Certificate generated and saved to:\n{out_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to generate certificate:\n{exc}")
