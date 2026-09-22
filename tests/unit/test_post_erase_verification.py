from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.core.audit.ledger import AuditLedger
from app.core.devices.enumerator import disk_image_info, get_backend
from app.core.erasure.drive_eraser import DriveEraseResult
from app.core.erasure.post_erase_verification import VerifiedDriveEraseResult, run_verified_drive_erase
from tests.fixtures.fat_image import make_fat16_image_with_deleted_file


def test_post_erase_verification_simulation_mode(tmp_path: Path) -> None:
    ledger_db = tmp_path / "audit.sqlite3"
    ledger = AuditLedger(ledger_db, hmac_key=b"test-only-fixed-key")
    
    fake_img = tmp_path / "fake_image.img"
    fake_img.write_bytes(b"0" * 1024)
    info = disk_image_info(str(fake_img))
    backend = get_backend()
    
    with patch("app.core.erasure.post_erase_verification.run_drive_erase") as mock_erase:
        mock_erase.return_value = DriveEraseResult(
            ok=True,
            standard_id="single_pass_zero",
            simulation_mode=True,
            device_fingerprint="fake-fingerprint",
            pass_results=[],
            error=None,
            effective_target_path=str(fake_img)
        )
        with patch("app.core.erasure.post_erase_verification.run_recovery_scan") as mock_scan:
            result = run_verified_drive_erase(
                info=info,
                backend=backend,
                standard_id="single_pass_zero",
                ledger=ledger,
                simulation_mode=True,
                user_confirmed=True
            )
            
            # Should NOT call recovery scan if simulation_mode is True
            mock_scan.assert_not_called()
            assert result.recovery_check is None
            assert result.recovery_candidates_found == 0


def test_post_erase_verification_real_run(tmp_path: Path) -> None:
    # Build a real FAT image to test actual erase and recovery scan integration
    image_path = tmp_path / "real_test.img"
    make_fat16_image_with_deleted_file(str(image_path))
    
    ledger_db = tmp_path / "audit.sqlite3"
    ledger = AuditLedger(ledger_db, hmac_key=b"test-only-fixed-key")
    
    info = disk_image_info(str(image_path))
    backend = get_backend()
    
    # Run the verified erase end-to-end, simulation_mode=False
    # This will overwrite the file and then scan it.
    result = run_verified_drive_erase(
        info=info,
        backend=backend,
        standard_id="single_pass_zero",
        ledger=ledger,
        simulation_mode=False,
        user_confirmed=True
    )
    
    # Erase should succeed
    assert result.erase.ok is True
    
    # Recovery check should run and find 0 files since it's zero-filled
    assert result.recovery_check is not None
    assert result.recovery_candidates_found == 0
    assert len(result.recovery_check.candidates) == 0
    
    # Check ledger entries
    entries = ledger.get_entries()
    # Should have a drive_erase, a recovery_scan (logged by run_recovery_scan), and a post_erase_verification
    erase_entries = [e for e in entries if e.action == "drive_erase"]
    assert len(erase_entries) == 1
    erase_entry = erase_entries[0]
    
    pev_entries = [e for e in entries if e.action == "post_erase_verification"]
    assert len(pev_entries) == 1
    pev_entry = pev_entries[0]
    
    # The target strings must match
    assert pev_entry.target == erase_entry.target
    
    # The payload must link back to the erase entry
    assert pev_entry.payload["erase_entry_id"] == erase_entry.entry_id
    assert pev_entry.payload["candidates_found"] == 0
