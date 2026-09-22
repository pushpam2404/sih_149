"""End-to-end recovery on every OS: build a FAT16 image with a deleted file in
pure Python -> run the full recovery scan -> the deleted bytes come back.

Unlike test_recovery_pipeline.py (macOS hdiutil/diskutil fixture), this
needs no OS tools, so it runs on Windows and Linux too. PhotoRec is not
required: plain text has no file signature to carve, so pytsk3 is the
engine expected to find it.
"""
import pytest

from app.core.audit.ledger import AuditLedger
from app.core.recovery.scan_service import run_recovery_scan
from app.core.recovery.tsk_engine import TskEngine
from app.core.reporting.json_report import save_json
from app.core.reporting.pdf_report import render_pdf
from app.core.reporting.report_builder import build_recovery_report
from tests.fixtures.fat_image import make_fat16_image_with_deleted_file

pytestmark = pytest.mark.skipif(not TskEngine().is_available(), reason="pytsk3 is not installed")


def test_pytsk3_recovers_deleted_file_from_pure_python_fat_image(tmp_path):
    fixture = make_fat16_image_with_deleted_file(str(tmp_path / "portable.img"))

    candidates = TskEngine().scan(fixture.image_path, str(tmp_path / "tsk_out"))

    matches = [c for c in candidates if _read(c.recovered_path) == fixture.deleted_file_original_content]
    assert len(matches) == 1
    match = matches[0]
    assert match.is_deleted_entry
    # FAT replaces the first character of a deleted name; the rest survives.
    assert match.suggested_name.endswith(fixture.deleted_file_name[1:])
    # The kept (not deleted) file must not be reported as recovered.
    assert all(not c.suggested_name.endswith(fixture.kept_file_name) for c in candidates)


def test_full_scan_pipeline_logs_hashes_and_reports(tmp_path):
    fixture = make_fat16_image_with_deleted_file(str(tmp_path / "portable.img"))
    ledger = AuditLedger(tmp_path / "audit.sqlite3", hmac_key=b"test-only-fixed-key-not-for-production")
    try:
        summary = run_recovery_scan(
            source_path=fixture.image_path,
            output_dir=str(tmp_path / "recovered"),
            ledger=ledger,
        )

        assert "pytsk3" in summary.engines_used
        matches = [c for c in summary.candidates if _read(c.recovered_path) == fixture.deleted_file_original_content]
        assert matches, [(c.source_engine, c.suggested_name) for c in summary.candidates]
        for match in matches:
            assert match.sha256 and len(match.sha256) == 64
            assert match.confidence_score is not None

        entries = ledger.get_entries()
        assert [e.action for e in entries] == ["recovery_scan"]
        assert entries[0].payload["candidates_found"] == len(summary.candidates)
        assert ledger.verify_chain().ok

        report = build_recovery_report(summary)
        assert save_json(report, str(tmp_path / "reports" / "r.json")).exists()
        pdf = render_pdf(report, str(tmp_path / "reports" / "r.pdf"))
        assert pdf.exists() and pdf.stat().st_size > 0
    finally:
        ledger.close()


def _read(path: str) -> bytes:
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return b""
