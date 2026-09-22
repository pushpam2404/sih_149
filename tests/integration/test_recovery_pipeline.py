"""End-to-end: build a real FAT disk image with a deleted file -> run the
recovery scan (pytsk3 + PhotoRec) -> confirm the deleted content comes back
with a sane classification/confidence score.

Uses hdiutil/diskutil (macOS), so this is skipped automatically if those
tools aren't available.
"""
import shutil

import pytest

from app.core.audit.ledger import AuditLedger
from app.core.recovery.scan_service import run_recovery_scan
from app.core.reporting.json_report import save_json
from app.core.reporting.pdf_report import render_pdf
from app.core.reporting.report_builder import build_recovery_report
from tests.fixtures.make_test_image import make_fat_image_with_deleted_file

pytestmark = pytest.mark.skipif(
    shutil.which("hdiutil") is None or shutil.which("diskutil") is None,
    reason="requires macOS hdiutil/diskutil to build the test fixture image",
)


def test_recovery_scan_finds_the_deleted_file(tmp_path):
    fixture = make_fat_image_with_deleted_file(str(tmp_path / "recovery_test.img"), size_mb=32)

    ledger = AuditLedger(tmp_path / "audit.sqlite3", hmac_key=b"test-only-fixed-key-not-for-production")
    summary = run_recovery_scan(
        source_path=fixture.image_path,
        output_dir=str(tmp_path / "recovered"),
        ledger=ledger,
    )

    assert summary.candidates, "expected at least one recovered candidate"

    matches = [
        c for c in summary.candidates
        if _read(c.recovered_path) == fixture.deleted_file_original_content
    ]
    assert matches, (
        f"deleted file content was not recovered by any engine; "
        f"got candidates: {[(c.source_engine, c.suggested_name, c.size_bytes) for c in summary.candidates]}"
    )

    for match in matches:
        assert match.sha256 is not None
        assert match.confidence_score is not None
        assert match.confidence_score >= 0

    entries = ledger.get_entries()
    assert len(entries) == 1
    assert entries[0].action == "recovery_scan"
    chain_check = ledger.verify_chain()
    assert chain_check.ok

    report = build_recovery_report(summary)
    json_path = save_json(report, str(tmp_path / "reports" / "recovery_report.json"))
    pdf_path = render_pdf(report, str(tmp_path / "reports" / "recovery_report.pdf"))
    assert json_path.exists()
    assert pdf_path.exists() and pdf_path.stat().st_size > 0

    ledger.close()


def _read(path: str) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return b""
