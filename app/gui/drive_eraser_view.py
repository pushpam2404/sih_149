"""Secure Drive Eraser tab: pick a safe target, pick a standard, confirm, erase, verify, report."""
from __future__ import annotations

from pathlib import Path
import shutil

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from app.config.settings import REPORTS_DIR
from app.core.audit.ledger import AuditLedger
from app.core.devices.enumerator import disk_image_info, get_backend, list_devices, raw_access_problem
from app.core.devices.fingerprint import fingerprint
from app.core.devices.safety import classify_target
from app.core.erasure.drive_eraser import DriveEraseResult, run_drive_erase
from app.core.erasure.firmware_sanitize import (
    FirmwareSanitizeResult,
    execute_ata_secure_erase,
    execute_nvme_sanitize,
)
from app.core.erasure.post_erase_verification import VerifiedDriveEraseResult, run_verified_drive_erase
from app.core.erasure.standards import list_standards
from app.core.reporting.json_report import save_json
from app.core.reporting.pdf_report import render_pdf
from app.core.reporting.report_builder import build_drive_erase_report
from app.gui.widgets import file_dialogs
from app.gui.widgets.confirm_dialog import ConfirmDestructiveDialog
from app.gui.widgets.device_table import DeviceTable
from app.gui.widgets.progress_panel import ProgressPanel
from app.gui.widgets.ui import Callout, Card, Page, button, field_label
from app.gui.workers import Worker
from app.utils.logging_setup import get_logger

logger = get_logger(__name__)


class DriveEraserView(QWidget):
    def __init__(self, ledger: AuditLedger, parent=None):
        super().__init__(parent)
        self._ledger = ledger
        self._backend = get_backend()
        self._worker: Worker | None = None
        self._selected_image_path: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        page = Page(
            "Drive Eraser",
            "Overwrite an entire removable drive or disk image, verify the result, and generate a report. "
            "The system/boot drive is always blocked.",
        )
        root.addWidget(page)

        refresh_btn = button("Refresh Devices", icon_name="refresh")
        refresh_btn.clicked.connect(self._refresh_devices)
        page.header_actions.addWidget(refresh_btn)

        pick_image_btn = button("Select Disk Image File...", icon_name="disc")
        pick_image_btn.clicked.connect(self._pick_disk_image)
        page.header_actions.addWidget(pick_image_btn)

        targets = Card(
            "Targets",
            "Select one row marked SAFE. Rows marked BLOCKED can never be erased.",
            icon_name="hard-drive",
        )
        self._table = DeviceTable()
        self._table.setMinimumHeight(170)
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)
        targets.body.addWidget(self._table)
        page.body.addWidget(targets, 3)

        lower = QHBoxLayout()
        lower.setSpacing(16)

        options = Card("Wipe options", icon_name="layers")
        options.body.addWidget(field_label("Wipe standard"))
        self._standard_combo = QComboBox()
        for standard in list_standards():
            self._standard_combo.addItem(standard.display_name, userData=standard.id)
        options.body.addWidget(self._standard_combo)

        self._simulation_checkbox = QCheckBox("Simulation mode (wipe a scratch copy, not the original)")
        self._simulation_checkbox.setChecked(True)
        options.body.addWidget(self._simulation_checkbox)

        self._simulation_on_note = Callout(
            "Simulation is <b>ON</b>: a scratch copy of a disk image is wiped, the original stays untouched.",
            tone="warning",
            icon_name="flask",
        )
        self._simulation_off_note = Callout(
            "Simulation is <b>OFF</b>: the selected target will be <b>really</b> overwritten.",
            tone="danger",
        )
        options.body.addWidget(self._simulation_on_note)
        options.body.addWidget(self._simulation_off_note)
        self._simulation_checkbox.toggled.connect(self._update_simulation_note)
        self._update_simulation_note(self._simulation_checkbox.isChecked())
        options.body.addStretch()

        erase_btn = button("Erase Selected Target", variant="danger", icon_name="trash", large=True)
        erase_btn.clicked.connect(self._start_erase)
        options.body.addWidget(erase_btn)
        
        advanced = Card("Advanced", icon_name="shield-alert")
        self._firmware_btn = button("Firmware Sanitize (Purge)...", variant="danger", icon_name="trash")
        self._firmware_btn.clicked.connect(self._start_firmware_sanitize)
        self._firmware_btn.setEnabled(False)
        advanced.body.addWidget(self._firmware_btn)
        
        options_layout = QVBoxLayout()
        options_layout.addWidget(options)
        options_layout.addWidget(advanced)
        options_layout.addStretch()
        
        lower.addLayout(options_layout, 2)

        progress_card = Card("Progress", icon_name="activity")
        self._progress = ProgressPanel()
        progress_card.body.addWidget(self._progress)
        lower.addWidget(progress_card, 3)

        page.body.addLayout(lower, 2)

        self._refresh_devices()

    def _update_simulation_note(self, simulation_on: bool) -> None:
        self._simulation_on_note.setVisible(simulation_on)
        self._simulation_off_note.setVisible(not simulation_on)

    def _refresh_devices(self) -> None:
        try:
            devices = list_devices()
        except Exception as exc:
            logger.error("device enumeration failed: %s", exc)
            devices = []
        if self._selected_image_path:
            devices = [disk_image_info(self._selected_image_path)] + devices
        self._table.set_devices(devices, self._backend)

    def _pick_disk_image(self) -> None:
        path = file_dialogs.open_file(self, "Select disk image file", "Disk images (*.img *.dd *.dmg);;All files (*)")
        if path:
            self._selected_image_path = path
            self._refresh_devices()

    def _start_erase(self) -> None:
        info = self._table.selected_device()
        if info is None:
            QMessageBox.warning(self, "No target selected", "Select a device or disk image from the table first.")
            return

        verdict = classify_target(info, self._backend)
        if not verdict.allowed:
            QMessageBox.critical(self, "Target refused", f"This target cannot be erased: {verdict.reason}")
            return

        if not info.is_disk_image:
            if self._simulation_checkbox.isChecked():
                QMessageBox.information(
                    self, "Simulation mode is on",
                    "Simulation mode only works with disk image files. To erase a real drive, "
                    "turn Simulation mode off explicitly — or select a disk image instead.",
                )
                return
            problem = raw_access_problem(info.path, write=True)
            if problem:
                QMessageBox.warning(self, "Not enough permissions", problem)
                return

        confirm_token = fingerprint(info)[:8]
        warning = (
            f"You are about to irreversibly erase:\n\n{info.display_name} ({info.path})\n\n"
            f"Standard: {self._standard_combo.currentText()}\n"
            f"Simulation mode: {'ON — a scratch copy will be wiped, original untouched' if self._simulation_checkbox.isChecked() else 'OFF — this is a REAL wipe'}"
        )
        if not ConfirmDestructiveDialog.confirm(self, warning, confirm_token):
            return

        standard_id = self._standard_combo.currentData()
        simulation_mode = self._simulation_checkbox.isChecked()

        self._progress.start(f"Erasing {info.display_name}...")
        self._worker = Worker(
            run_verified_drive_erase,
            info=info,
            backend=self._backend,
            standard_id=standard_id,
            ledger=self._ledger,
            simulation_mode=simulation_mode,
            user_confirmed=True,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(lambda result: self._on_success(result, info))
        self._worker.failed.connect(self._on_failure)
        self._worker.start()

    def _on_progress(self, message: str) -> None:
        self._progress.log(message)

    def _on_success(self, result: VerifiedDriveEraseResult, info) -> None:
        status = "PASS" if result.erase.ok else f"FAIL: {result.erase.error}"
        self._progress.finish(f"Erase complete — {status}")

        report = build_drive_erase_report(result.erase, info, result.recovery_check)
        base = REPORTS_DIR / f"drive_erase_{report.report_id}"
        save_json(report, str(base.with_suffix(".json")))
        render_pdf(report, str(base.with_suffix(".pdf")))

        msg_text = f"Verification PASSED.\nReport saved to {base}.pdf"
        if result.erase.ok and result.recovery_check is not None and result.recovery_candidates_found == 0:
            msg_text += "\n\nIndependent recovery check: 0 files recoverable."

        if result.erase.ok:
            QMessageBox.information(self, "Erase complete", msg_text)
        else:
            QMessageBox.critical(self, "Erase failed", f"{result.erase.error}\nReport saved to {base}.pdf")

        if result.recovery_check is not None and result.recovery_candidates_found > 0:
            QMessageBox.warning(self, "Recovery Check Warning", f"⚠ Independent recovery check found {result.recovery_candidates_found} recoverable file(s) after the wipe. See the report for details.")

    def _on_failure(self, error: str) -> None:
        self._progress.finish(f"Error: {error}")
        QMessageBox.critical(self, "Erase failed", error)

    def _on_table_selection_changed(self) -> None:
        info = self._table.selected_device()
        if not info:
            self._firmware_btn.setEnabled(False)
            self._firmware_btn.setToolTip("Select a target first.")
            return

        verdict = classify_target(info, self._backend)
        if not verdict.allowed:
            self._firmware_btn.setEnabled(False)
            self._firmware_btn.setToolTip(f"Not allowed: {verdict.reason}")
            return

        if not (info.is_removable and not info.is_internal):
            self._firmware_btn.setEnabled(False)
            self._firmware_btn.setToolTip("Only available for external/removable drives.")
            return

        if shutil.which("hdparm") is None and shutil.which("nvme") is None:
            self._firmware_btn.setEnabled(False)
            self._firmware_btn.setToolTip("Not available on this OS (missing hdparm/nvme-cli).")
            return

        self._firmware_btn.setEnabled(True)
        self._firmware_btn.setToolTip("Issues real firmware commands (ATA Secure Erase / NVMe Sanitize).")

    def _start_firmware_sanitize(self) -> None:
        info = self._table.selected_device()
        if not info:
            return

        method = "NVMe Sanitize" if getattr(info, "topology_type", "") == "nvme" else "ATA Secure Erase"
        confirm_token = fingerprint(info)[:8] + "-FIRMWARE"
        warning = (
            f"This issues real firmware commands directly to {info.display_name}'s controller ({method}). "
            f"An interruption, power loss, or unsupported drive can permanently destroy this device. "
            f"This is different from, and riskier than, the standard erase above. It cannot be undone or simulated."
        )
        if not ConfirmDestructiveDialog.confirm(self, warning, confirm_token):
            return

        self._progress.start(f"Running {method} on {info.display_name}...")
        
        target_func = execute_nvme_sanitize if method == "NVMe Sanitize" else execute_ata_secure_erase
        self._worker = Worker(
            target_func,
            info=info,
            backend=self._backend,
            ledger=self._ledger,
            user_confirmed=True,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.succeeded.connect(self._on_firmware_success)
        self._worker.failed.connect(self._on_failure)
        self._worker.start()

    def _on_firmware_success(self, result: FirmwareSanitizeResult) -> None:
        status = "PASS" if result.ok else "FAIL"
        self._progress.finish(f"Firmware Sanitize complete — {status}")
        
        if result.ok:
            QMessageBox.information(self, "Firmware Sanitize complete", "PASS: Firmware command completed successfully.")
        else:
            QMessageBox.critical(self, "Firmware Sanitize failed", f"FAIL: {result.error}")

