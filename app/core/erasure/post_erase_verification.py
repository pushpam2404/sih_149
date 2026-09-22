"""Runs a drive erase, then — for real (non-simulation) erases — an
independent recovery scan against the same target, so the erase's own
"wiped clean" claim is checked by a different code path (a different
engine actually attempting to recover files) rather than only by the
erase's own sampled read-back verification.

This does not make the check a third party: it is still this machine,
this process, checking its own work. It is nonetheless meaningfully
stronger evidence than sampled entropy verification alone, because
PhotoRec/pytsk3 are independent implementations attempting actual file
recovery, not just reading back bytes the eraser itself wrote.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config.constants import ACTION_POST_ERASE_VERIFICATION
from app.config.settings import DATA_DIR
from app.core.audit.ledger import AuditLedger
from app.core.devices.backend_base import DeviceBackend
from app.core.devices.backend_base import DeviceInfo
from app.core.devices.fingerprint import fingerprint
from app.core.erasure.drive_eraser import DriveEraseResult, ProgressCallback, run_drive_erase
from app.core.recovery.scan_service import ScanSummary, run_recovery_scan
from app.utils.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass
class VerifiedDriveEraseResult:
    erase: DriveEraseResult
    recovery_check: ScanSummary | None
    recovery_candidates_found: int


def run_verified_drive_erase(
    info: DeviceInfo,
    backend: DeviceBackend,
    standard_id: str,
    ledger: AuditLedger,
    *,
    simulation_mode: bool = True,
    user_confirmed: bool = False,
    simulation_scratch_dir: Path | None = None,
    progress_cb: ProgressCallback | None = None,
) -> VerifiedDriveEraseResult:
    erase_result = run_drive_erase(
        info,
        backend,
        standard_id,
        ledger,
        simulation_mode=simulation_mode,
        user_confirmed=user_confirmed,
        simulation_scratch_dir=simulation_scratch_dir,
        progress_cb=progress_cb,
    )

    if simulation_mode:
        # Simulation wipes a scratch copy, not the thing the user cares
        # about proving is wiped — skip the recovery check to keep
        # simulation runs fast, as documented in Part 1 of the plan.
        return VerifiedDriveEraseResult(erase=erase_result, recovery_check=None, recovery_candidates_found=0)

    if progress_cb:
        progress_cb("Running independent recovery verification...")

    dev_fingerprint = fingerprint(info)
    target_label = f"{info.display_name} ({dev_fingerprint})"  # must match drive_eraser.py's target string exactly

    # Find the erase entry we just wrote, to link the two entries by id.
    # append_entry() returns the AuditEntry it wrote; run_drive_erase()
    # doesn't currently return that entry, only DriveEraseResult, so we
    # look it up as the most recent entry for this target instead.
    entries = ledger.get_entries()
    erase_entry_id = next(
        (e.entry_id for e in reversed(entries) if e.target == target_label and e.action == "drive_erase"),
        None,
    )

    output_dir = DATA_DIR / "post_erase_verification" / f"{dev_fingerprint}"
    output_dir.mkdir(parents=True, exist_ok=True)

    scan_summary = run_recovery_scan(
        source_path=erase_result.effective_target_path,
        output_dir=str(output_dir),
        ledger=ledger,
        target_label=target_label,
        progress_cb=progress_cb,
    )

    # run_recovery_scan already logged its own ACTION_RECOVERY_SCAN entry.
    # Log a second, distinctly-actioned entry that explicitly carries the
    # link and is what the certificate/report code should look for.
    ledger.append_entry(
        action=ACTION_POST_ERASE_VERIFICATION,
        target=target_label,
        payload={
            "erase_entry_id": erase_entry_id,
            "candidates_found": len(scan_summary.candidates),
            "engines_used": scan_summary.engines_used,
            "engines_unavailable": scan_summary.engines_unavailable,
        },
    )

    return VerifiedDriveEraseResult(
        erase=erase_result,
        recovery_check=scan_summary,
        recovery_candidates_found=len(scan_summary.candidates),
    )
