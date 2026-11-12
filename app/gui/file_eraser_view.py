"""Secure File & Folder Eraser tab: pick files/folders, confirm, erase, report."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import REPORTS_DIR
from app.core.audit.ledger import AuditLedger
from app.core.erasure.file_eraser import BatchEraseResult, erase_batch, erase_folder
from app.core.reporting.json_report import save_json
from app.core.reporting.pdf_report import render_pdf
from app.core.reporting.report_builder import build_file_erase_report
from app.gui.widgets import file_dialogs
from app.gui.widgets.confirm_dialog import ConfirmDestructiveDialog
from app.gui.theme import mono_font
from app.gui.widgets.progress_panel import ProgressPanel
from app.gui.widgets.ui import Badge, Callout, Card, EmptyHint, Page, button
from app.gui.workers import Worker


class FileEraserView(QWidget):
    def __init__(self, ledger: AuditLedger, parent=None):
        super().__init__(parent)
        self._ledger = ledger
        self._worker: Worker | None = None
        self._queued_folder: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        page = Page(
            "File & Folder Eraser",
            "Overwrite files with random data, strip metadata, rename, then delete — so the contents "
            "can't be recovered by normal undelete tools.",
        )
        root.addWidget(page)

        queue_card = Card("Erase queue", "Files or one folder to securely erase.", icon_name="file-x")
        self._count_badge = Badge("0 items", "neutral")
        queue_card.actions.addWidget(self._count_badge)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        add_files_btn = button("Add files…", icon_name="file-plus")
        add_files_btn.clicked.connect(self._add_files)
        button_row.addWidget(add_files_btn)

        add_folder_btn = button("Add folder…", icon_name="folder-plus")
        add_folder_btn.clicked.connect(self._add_folder)
        button_row.addWidget(add_folder_btn)

        clear_btn = button("Clear queue", variant="ghost", icon_name="x")
        clear_btn.clicked.connect(self._clear_queue)
        button_row.addWidget(clear_btn)
        button_row.addStretch()
        queue_card.body.addLayout(button_row)

        self._queue_list = QListWidget()
        self._queue_list.setMinimumHeight(160)
        self._queue_list.setFont(mono_font(12))
        self._empty_hint = EmptyHint(
            "Nothing queued yet.\nUse Add Files... or Add Folder... to choose what to erase.",
            self._queue_list.viewport(),
        )
        model = self._queue_list.model()
        model.rowsInserted.connect(self._update_queue_state)
        model.rowsRemoved.connect(self._update_queue_state)
        model.modelReset.connect(self._update_queue_state)
        queue_card.body.addWidget(self._queue_list, 1)

        queue_card.body.addWidget(
            Callout(
                "On SSDs and copy-on-write filesystems (e.g. APFS) old copies of the data may survive "
                "elsewhere on the disk. The app lists these caveats after each erase.",
                tone="warning",
            )
        )

        erase_row = QHBoxLayout()
        erase_row.addStretch()
        erase_btn = button("Securely erase queue", variant="danger", icon_name="trash", large=True)
        erase_btn.clicked.connect(self._start_erase)
        erase_row.addWidget(erase_btn)
        queue_card.body.addLayout(erase_row)
        page.body.addWidget(queue_card, 3)

        progress_card = Card("Progress", icon_name="activity")
        self._progress = ProgressPanel(log_min_height=90)
        progress_card.body.addWidget(self._progress)
        page.body.addWidget(progress_card, 2)

        self._update_queue_state()

    def _update_queue_state(self, *_args) -> None:
        count = self._queue_list.count()
        self._empty_hint.setVisible(count == 0)
        if self._queued_folder:
            self._count_badge.set("1 folder", "warning")
        else:
            self._count_badge.set(f"{count} file{'s' if count != 1 else ''}", "warning" if count else "neutral")

    def _add_files(self) -> None:
        paths = file_dialogs.open_files(self, "Select files to securely erase")
        for path in paths:
            self._queue_list.addItem(path)

    def _add_folder(self) -> None:
        path = file_dialogs.existing_directory(self, "Select folder to securely erase (entire folder)")
        if path:
            self._queued_folder = path
            self._queue_list.clear()
            self._queue_list.addItem(f"[FOLDER — all contents] {path}")

    def _clear_queue(self) -> None:
        self._queue_list.clear()
        self._queued_folder = None
        self._update_queue_state()

    def _start_erase(self) -> None:
        if self._queue_list.count() == 0:
            QMessageBox.warning(self, "Nothing queued", "Add files or a folder to erase first.")
            return

        if self._queued_folder:
            warning = f"You are about to irreversibly erase the ENTIRE FOLDER:\n\n{self._queued_folder}"
            confirm_token = "ERASE FOLDER"
        else:
            count = self._queue_list.count()
            warning = f"You are about to irreversibly erase {count} file(s)."
            confirm_token = "ERASE FILES"

        if not ConfirmDestructiveDialog.confirm(self, warning, confirm_token):
            return

        self._progress.start("Erasing queued items...")

        if self._queued_folder:
            self._worker = Worker(erase_folder, folder_path=self._queued_folder, ledger=self._ledger)
        else:
            paths = [self._queue_list.item(i).text() for i in range(self._queue_list.count())]
            self._worker = Worker(erase_batch, paths=paths, ledger=self._ledger)

        self._worker.progress.connect(self._progress.log)
        self._worker.succeeded.connect(self._on_success)
        self._worker.failed.connect(self._on_failure)
        self._worker.start()

    def _on_success(self, batch: BatchEraseResult) -> None:
        status = "PASS" if batch.ok else f"{len(batch.failed)} of {len(batch.results)} failed"
        self._progress.finish(f"Erase complete — {status}")
        self._queue_list.clear()
        self._queued_folder = None
        self._update_queue_state()
        
        all_warnings = set()
        for res in batch.results:
            if hasattr(res, "warnings"):
                for w in res.warnings:
                    all_warnings.add(w)

        report = build_file_erase_report(batch)
        base = REPORTS_DIR / f"file_erase_{report.report_id}"
        save_json(report, str(base.with_suffix(".json")))
        render_pdf(report, str(base.with_suffix(".pdf")))

        if batch.ok:
            if all_warnings:
                warn_text = "\n".join(f"- {w}" for w in all_warnings)
                QMessageBox.warning(self, "Erase complete, with filesystem warnings", 
                    f"All items were overwritten and unlinked, but the underlying filesystem presents some caveats:\n\n{warn_text}\n\nReport saved to {base}.pdf")
            else:
                QMessageBox.information(self, "Erase complete", f"All items erased.\nReport saved to {base}.pdf")
        else:
            QMessageBox.warning(self, "Erase completed with failures", f"{status}\nReport saved to {base}.pdf")

    def _on_failure(self, error: str) -> None:
        self._progress.finish(f"Error: {error}")
        QMessageBox.critical(self, "Erase failed", error)
