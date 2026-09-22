"""Builds structured Report objects from job results.

Report is deliberately generic (title + summary + sections of rows) so
pdf_report.py and json_report.py only need to know how to render this one
shape, regardless of which module produced it.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.core.devices.backend_base import DeviceInfo
from app.core.erasure.drive_eraser import DriveEraseResult
from app.core.erasure.file_eraser import BatchEraseResult
from app.core.recovery.confidence import confidence_label
from app.core.recovery.scan_service import ScanSummary


@dataclass
class ReportSection:
    title: str
    rows: list[dict]


@dataclass
class Report:
    report_id: str
    title: str
    generated_at: str
    report_type: str
    summary: dict
    sections: list[ReportSection] = field(default_factory=list)
    notice: str | None = None


def _new_report_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_drive_erase_report(result: DriveEraseResult, info: DeviceInfo, recovery_check: ScanSummary | None = None) -> Report:
    passes_rows = [
        {
            "fill_mode": r.fill_mode,
            "result": "PASS" if r.ok else "FAIL",
            "samples_checked": r.samples_checked,
            "sample_failures": len(r.failures),
        }
        for r in result.pass_results
    ]
    summary_dict = {
        "target": info.display_name,
        "target_fingerprint": result.device_fingerprint,
        "size_bytes": info.size_bytes,
        "standard": result.standard_id,
        "simulation_mode": result.simulation_mode,
        "result": "PASS" if result.ok else "FAIL",
        "error": result.error,
    }
    if recovery_check is not None:
        summary_dict["post_erase_verification"] = {
            "engines_used": recovery_check.engines_used,
            "engines_unavailable": recovery_check.engines_unavailable,
            "candidates_found": len(recovery_check.candidates),
            "candidate_names": [c.suggested_name for c in recovery_check.candidates[:10]],
        }

    return Report(
        report_id=_new_report_id(),
        title=f"Secure Drive Erasure Certificate — {info.display_name}",
        generated_at=_now(),
        report_type="drive_erasure_certificate",
        summary=summary_dict,
        sections=[ReportSection(title="Overwrite Passes", rows=passes_rows)],
        notice=(
            "SIMULATION MODE — this run wiped a scratch copy of the selected disk "
            "image; the original source was not modified." if result.simulation_mode else None
        ),
    )


def build_file_erase_report(batch: BatchEraseResult) -> Report:
    rows = [
        {
            "path": r.path,
            "result": "PASS" if r.ok else "FAIL",
            "bytes_overwritten": r.bytes_overwritten,
            "metadata_cleared": r.metadata_cleared,
            "error": r.error,
        }
        for r in batch.results
    ]
    return Report(
        report_id=_new_report_id(),
        title="Secure File & Folder Erasure Report",
        generated_at=_now(),
        report_type="file_erasure_report",
        summary={
            "files_processed": len(batch.results),
            "files_succeeded": len(batch.results) - len(batch.failed),
            "files_failed": len(batch.failed),
            "result": "PASS" if batch.ok else "FAIL",
        },
        sections=[ReportSection(title="Files", rows=rows)],
        notice=(
            "In-place overwrite is best-effort logical erasure. On SSDs and "
            "copy-on-write filesystems (e.g. APFS), wear-leveling/CoW may mean the "
            "original physical blocks were not overwritten — see compliance_mapping.md."
        ),
    )


def build_recovery_report(scan: ScanSummary) -> Report:
    rows = [
        {
            "suggested_name": c.suggested_name,
            "source_engine": c.source_engine,
            "file_type": c.file_type,
            "size_bytes": c.size_bytes,
            "sha256": c.sha256,
            "confidence_score": c.confidence_score,
            "confidence_label": confidence_label(c.confidence_score or 0),
            "fragmented": c.is_fragmented,
        }
        for c in scan.candidates
    ]
    return Report(
        report_id=_new_report_id(),
        title=f"Forensic Recovery Report — {scan.source_path}",
        generated_at=_now(),
        report_type="recovery_forensic_report",
        summary={
            "source": scan.source_path,
            "engines_used": scan.engines_used,
            "engines_unavailable": scan.engines_unavailable,
            "candidates_found": len(scan.candidates),
        },
        sections=[ReportSection(title="Recovered File Candidates", rows=rows)],
        notice=(
            "This report may reference evidentiary data. Recovered files and this "
            "report should not be modified once generated; confidence scores are a "
            "heuristic triage aid, not a certified probability."
        ),
    )
