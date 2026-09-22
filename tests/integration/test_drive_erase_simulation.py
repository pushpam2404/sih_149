"""End-to-end: create a disk image -> erase it in simulation mode -> verify.

Uses a plain disk-image DeviceInfo (is_disk_image=True), which never
touches the real device backend, so this test runs anywhere without
needing hdiutil/diskutil device attachment.
"""
from pathlib import Path

from app.core.audit.ledger import AuditLedger
from app.core.devices.enumerator import disk_image_info
from app.core.devices.backend_macos import MacOSDeviceBackend
from app.core.erasure.drive_eraser import run_drive_erase
from app.core.reporting.json_report import save_json
from app.core.reporting.pdf_report import render_pdf
from app.core.reporting.report_builder import build_drive_erase_report


def test_simulation_mode_wipes_a_copy_and_leaves_original_untouched(tmp_path):
    original = tmp_path / "source.img"
    original.write_bytes(b"\xAA" * (2 * 1024 * 1024))
    original_bytes_before = original.read_bytes()

    ledger = AuditLedger(tmp_path / "audit.sqlite3", hmac_key=b"test-only-fixed-key-not-for-production")
    info = disk_image_info(str(original))
    backend = MacOSDeviceBackend()  # unused for image targets, but required by the signature

    result = run_drive_erase(
        info,
        backend,
        standard_id="single_pass_zero",
        ledger=ledger,
        simulation_mode=True,
        user_confirmed=True,
        simulation_scratch_dir=tmp_path / "scratch",
    )

    assert result.ok
    assert result.effective_target_path != str(original)
    assert original.read_bytes() == original_bytes_before, "original image must be untouched in simulation mode"

    scratch_bytes = open(result.effective_target_path, "rb").read()
    assert scratch_bytes == b"\x00" * len(scratch_bytes)

    entries = ledger.get_entries()
    assert len(entries) == 1
    assert entries[0].payload["result"] == "PASS"

    report = build_drive_erase_report(result, info)
    assert "SIMULATION MODE" in (report.notice or "")

    json_path = save_json(report, str(tmp_path / "reports" / "drive_report.json"))
    pdf_path = render_pdf(report, str(tmp_path / "reports" / "drive_report.pdf"))
    assert json_path.exists()
    assert pdf_path.exists()
    assert pdf_path.stat().st_size > 0

    ledger.close()


def test_drive_erase_refuses_without_confirmation(tmp_path):
    original = tmp_path / "source.img"
    original.write_bytes(b"\xAA" * 1024)
    ledger = AuditLedger(tmp_path / "audit.sqlite3", hmac_key=b"test-only-fixed-key-not-for-production")
    info = disk_image_info(str(original))
    backend = MacOSDeviceBackend()

    import pytest
    from app.core.erasure.drive_eraser import ConfirmationRequiredError

    with pytest.raises(ConfirmationRequiredError):
        run_drive_erase(
            info, backend, standard_id="single_pass_zero", ledger=ledger,
            simulation_mode=True, user_confirmed=False,
        )
    ledger.close()


def test_default_scratch_copy_goes_to_data_dir_not_working_directory(tmp_path, monkeypatch):
    from app.core.erasure import drive_eraser

    original = tmp_path / "source.img"
    original.write_bytes(b"\xAA" * (1024 * 1024))
    data_dir = tmp_path / "appdata"
    elsewhere = tmp_path / "some_other_cwd"
    elsewhere.mkdir()
    monkeypatch.setattr(drive_eraser, "DATA_DIR", data_dir)
    monkeypatch.chdir(elsewhere)

    ledger = AuditLedger(tmp_path / "audit.sqlite3", hmac_key=b"test-only-fixed-key-not-for-production")
    try:
        result = run_drive_erase(
            disk_image_info(str(original)), MacOSDeviceBackend(), standard_id="single_pass_zero",
            ledger=ledger, simulation_mode=True, user_confirmed=True,
        )
    finally:
        ledger.close()

    assert result.ok
    assert Path(result.effective_target_path).parent == data_dir / "simulation"
    assert not (elsewhere / "data").exists()


def test_simulation_mode_is_refused_for_a_real_device(tmp_path):
    import pytest
    from app.core.devices.backend_base import DeviceInfo
    from app.core.erasure.drive_eraser import SimulationModeMismatchError

    usb = DeviceInfo(
        path="/dev/fake-usb", display_name="USB", size_bytes=1024, is_disk_image=False,
        is_removable=True, is_internal=False, is_system_container=False,
    )

    class _AllowingBackend(MacOSDeviceBackend):
        def is_system_drive(self, info):
            return False

        def open_raw(self, info, mode):
            raise AssertionError("simulation mode must refuse before any device is opened")

    ledger = AuditLedger(tmp_path / "audit.sqlite3", hmac_key=b"test-only-fixed-key-not-for-production")
    try:
        with pytest.raises(SimulationModeMismatchError):
            run_drive_erase(usb, _AllowingBackend(), standard_id="single_pass_zero", ledger=ledger,
                            simulation_mode=True, user_confirmed=True)
        assert ledger.get_entries() == []
    finally:
        ledger.close()
