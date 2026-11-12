"""Advanced File Carving and Recovery tab: pick a source, scan, review
classified/scored candidates, export selected files, generate a report."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import DATA_DIR, REPORTS_DIR
from app.core.audit.ledger import AuditLedger
from app.core.devices.enumerator import list_devices, raw_access_problem
from app.core.recovery.confidence import confidence_label
from app.core.recovery.engine_base import RecoveredFileCandidate
from app.core.recovery.scan_service import ScanSummary, run_recovery_scan
from app.core.reporting.json_report import save_json
from app.core.reporting.pdf_report import render_pdf
from app.core.reporting.report_builder import build_recovery_report
from app.gui.theme import COLORS, mono_font
from app.gui.widgets import file_dialogs
from app.gui.widgets.progress_panel import ProgressPanel
from app.gui.widgets.ui import Card, EmptyHint, Page, button, field_label, style_table
from app.gui.workers import Worker
from app.utils.logging_setup import get_logger

logger = get_logger(__name__)

_RESULT_COLUMNS = ["Name", "Engine", "File Type", "Size (bytes)", "Confidence", "Fragmented", "SHA-256", "Fuzzy Hash (ppdeep)"]
_ARTIFACT_COLUMNS = ["Artifact File", "Size (bytes)"]
_CONFIDENCE_COLORS = {"high": COLORS["success"], "medium": COLORS["accent"], "low": COLORS["text_muted"]}


class RecoveryView(QWidget):
    def __init__(self, ledger: AuditLedger, parent=None):
        super().__init__(parent)
        self._ledger = ledger
        self._worker: Worker | None = None
        self._last_summary: ScanSummary | None = None
        
        self._standard_candidates: list[RecoveredFileCandidate] = []
        self._artifact_candidates: list[RecoveredFileCandidate] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        page = Page(
            "Recovery",
            "Scan a disk image or attached drive for deleted files. Engines: pytsk3 (filesystem-aware), "
            "PhotoRec (signature carving) and bulk_extractor (PII / metadata), when installed.",
        )
        root.addWidget(page)

        top = QHBoxLayout()
        top.setSpacing(16)

        source_card = Card("Source", "Scanning only reads the source; recovered files are written elsewhere.", icon_name="search")
        source_card.body.addWidget(field_label("Source:"))
        source_row = QHBoxLayout()
        source_row.setSpacing(8)
        self._source_input = QLineEdit()
        self._source_input.setPlaceholderText("Path to a disk image file, or pick an attached device below")
        self._source_input.setFont(mono_font(12))
        source_row.addWidget(self._source_input, 1)

        browse_btn = button("Browse image…", icon_name="folder-open")
        browse_btn.clicked.connect(self._browse_image)
        source_row.addWidget(browse_btn)
        source_card.body.addLayout(source_row)

        source_card.body.addWidget(field_label("Or attached device:"))
        self._device_combo = QComboBox()
        self._device_combo.addItem("(none)", userData=None)
        for device in self._safe_list_devices():
            self._device_combo.addItem(f"{device.display_name} ({device.path})", userData=device.path)
        self._device_combo.currentIndexChanged.connect(self._on_device_selected)
        source_card.body.addWidget(self._device_combo)
        source_card.body.addStretch()

        scan_btn = button("Start recovery scan", variant="primary", icon_name="search", large=True)
        scan_btn.clicked.connect(self._start_scan)
        source_card.body.addWidget(scan_btn)
        top.addWidget(source_card, 3)

        progress_card = Card("Progress", icon_name="activity")
        self._progress = ProgressPanel(log_min_height=80)
        progress_card.body.addWidget(self._progress)
        top.addWidget(progress_card, 2)
        page.body.addLayout(top)

        results_card = Card("Results", "Select a recovered file to export it.", icon_name="recover")

        export_btn = button("Export selected file…", icon_name="download")
        export_btn.clicked.connect(self._export_selected)
        results_card.actions.addWidget(export_btn)

        report_btn = button("Generate forensic report", icon_name="file-output")
        report_btn.clicked.connect(self._generate_report)
        results_card.actions.addWidget(report_btn)

        self._results_tabs = QTabWidget()
        self._results_tabs.setDocumentMode(True)

        self._results_table = QTableWidget(0, len(_RESULT_COLUMNS))
        self._results_table.setHorizontalHeaderLabels(_RESULT_COLUMNS)
        self._results_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._results_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        style_table(self._results_table)
        header = self._results_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        for col, width in enumerate([190, 80, 80, 95, 100, 85, 140]):
            self._results_table.setColumnWidth(col, width)
        self._results_empty = EmptyHint(
            "No results yet.\nChoose a source and click Start recovery scan.", self._results_table.viewport()
        )
        self._results_tabs.addTab(self._results_table, "Recovered Files:")

        self._artifacts_table = QTableWidget(0, len(_ARTIFACT_COLUMNS))
        self._artifacts_table.setHorizontalHeaderLabels(_ARTIFACT_COLUMNS)
        self._artifacts_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._artifacts_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        style_table(self._artifacts_table)
        self._artifacts_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._artifacts_table.itemSelectionChanged.connect(self._show_artifact_contents)
        self._artifacts_empty = EmptyHint(
            "No PII / metadata artifacts.\nThis table is filled by bulk_extractor when it is installed.",
            self._artifacts_table.viewport(),
        )
        self._results_tabs.addTab(self._artifacts_table, "PII / Metadata Artifacts (Bulk Extractor):")
        self._update_result_tabs()

        results_card.body.addWidget(self._results_tabs, 1)
        page.body.addWidget(results_card, 1)

    def _update_result_tabs(self) -> None:
        results = self._results_table.rowCount()
        artifacts = self._artifacts_table.rowCount()
        self._results_tabs.setTabText(0, f"Recovered Files  ({results})")
        self._results_tabs.setTabText(1, f"PII / Metadata Artifacts — Bulk Extractor  ({artifacts})")
        self._results_empty.setVisible(results == 0)
        self._artifacts_empty.setVisible(artifacts == 0)

    def _safe_list_devices(self):
        try:
            return list_devices()
        except Exception as exc:
            logger.error("device enumeration failed: %s", exc)
            return []

    def _browse_image(self) -> None:
        path = file_dialogs.open_file(self, "Select disk image to scan", "Disk images (*.img *.dd *.dmg);;All files (*)")
        if path:
            self._source_input.setText(path)
            self._device_combo.setCurrentIndex(0)

    def _on_device_selected(self, index: int) -> None:
        path = self._device_combo.currentData()
        if path:
            self._source_input.setText(path)

    def _start_scan(self) -> None:
        source = self._source_input.text().strip()
        if not source:
            QMessageBox.warning(self, "No source", "Enter a disk image path or pick an attached device.")
            return
        problem = raw_access_problem(source)
        if problem:
            QMessageBox.warning(self, "Can't read this device", problem)
            return

        output_dir = str(DATA_DIR / "recovery_output" / f"scan_{int(time.time())}")
        self._progress.start(f"Scanning {source}...")
        self._results_table.setRowCount(0)
        self._update_result_tabs()

        self._worker = Worker(run_recovery_scan, source_path=source, output_dir=output_dir, ledger=self._ledger)
        self._worker.progress.connect(self._progress.log)
        self._worker.succeeded.connect(self._on_scan_success)
        self._worker.failed.connect(self._on_scan_failure)
        self._worker.start()

    def _on_scan_success(self, summary: ScanSummary) -> None:
        self._last_summary = summary
        unavailable_note = (
            f" (engines unavailable: {', '.join(summary.engines_unavailable)})"
            if summary.engines_unavailable
            else ""
        )
        self._progress.finish(f"Scan complete — {len(summary.candidates)} candidate(s) found{unavailable_note}")
        self._populate_results(summary.candidates)

    def _on_scan_failure(self, error: str) -> None:
        self._progress.finish(f"Error: {error}")
        QMessageBox.critical(self, "Scan failed", error)

    def _populate_results(self, candidates: list[RecoveredFileCandidate]) -> None:
        self._standard_candidates = [c for c in candidates if c.source_engine != "bulk_extractor"]
        self._artifact_candidates = [c for c in candidates if c.source_engine == "bulk_extractor"]
        
        self._results_table.setRowCount(len(self._standard_candidates))
        for row, candidate in enumerate(self._standard_candidates):
            score = candidate.confidence_score or 0
            values = [
                candidate.suggested_name,
                candidate.source_engine,
                candidate.file_type or "unknown",
                str(candidate.size_bytes),
                f"{score} ({confidence_label(score)})",
                "yes" if candidate.is_fragmented else "no",
                (candidate.sha256 or "")[:16] + "...",
                (candidate.fuzzy_hash or "")[:16] + "..." if candidate.fuzzy_hash else ("skipped (>4 MiB)" if candidate.size_bytes > 4 * 1024 * 1024 else "N/A"),
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setToolTip(value)
                elif col == 4:
                    item.setForeground(QColor(_CONFIDENCE_COLORS[confidence_label(score)]))
                elif col in (6, 7):
                    item.setFont(mono_font(12))
                    item.setForeground(QColor(COLORS["text_muted"]))
                    full = candidate.sha256 if col == 6 else candidate.fuzzy_hash
                    if full:
                        item.setToolTip(full)
                self._results_table.setItem(row, col, item)
                
        self._artifacts_table.setRowCount(len(self._artifact_candidates))
        for row, candidate in enumerate(self._artifact_candidates):
            values = [
                candidate.suggested_name,
                str(candidate.size_bytes)
            ]
            for col, value in enumerate(values):
                self._artifacts_table.setItem(row, col, QTableWidgetItem(value))
        self._update_result_tabs()

    def _show_artifact_contents(self) -> None:
        row = self._artifacts_table.currentRow()
        if row < 0 or row >= len(self._artifact_candidates):
            return
        candidate = self._artifact_candidates[row]
        try:
            with open(candidate.recovered_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(3000)
            if len(content) == 3000:
                content += "\n... [truncated]"
            QMessageBox.information(
                self, f"Artifact: {candidate.suggested_name}",
                content if content.strip() else "(Empty artifact file)"
            )
        except OSError as exc:
            QMessageBox.warning(self, "Error reading artifact", str(exc))

    def _export_selected(self) -> None:
        if not self._last_summary:
            return
        row = self._results_table.currentRow()
        if row < 0 or row >= len(self._standard_candidates):
            QMessageBox.warning(self, "No selection", "Select a recovered file from the results table first.")
            return
        candidate = self._standard_candidates[row]
        dest = file_dialogs.save_file(self, "Save recovered file as", candidate.suggested_name or "recovered_file")
        if dest:
            shutil.copyfile(candidate.recovered_path, dest)
            QMessageBox.information(self, "Exported", f"Saved to {dest}")

    def _generate_report(self) -> None:
        if not self._last_summary:
            QMessageBox.warning(self, "No scan yet", "Run a recovery scan first.")
            return
        report = build_recovery_report(self._last_summary)
        base = REPORTS_DIR / f"recovery_{report.report_id}"
        save_json(report, str(base.with_suffix(".json")))
        render_pdf(report, str(base.with_suffix(".pdf")))
        QMessageBox.information(self, "Report generated", f"Saved to {base}.pdf")
