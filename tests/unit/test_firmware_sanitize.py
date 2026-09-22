import platform
import shutil
import subprocess
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.audit.ledger import AuditLedger
from app.core.devices.backend_base import DeviceBackend, DeviceInfo
from app.core.erasure.firmware_sanitize import (
    FirmwareSanitizeResult,
    NonExternalTargetError,
    SecurityFreezeLockError,
    UnsupportedPlatformError,
    execute_ata_secure_erase,
    execute_nvme_sanitize,
)


@pytest.fixture
def ledger(tmp_path: Path) -> AuditLedger:
    return AuditLedger(tmp_path / "audit.sqlite3", hmac_key=b"test-only-fixed-key")


@pytest.fixture
def backend() -> DeviceBackend:
    # A dummy backend just to pass to execute_*, it doesn't need to do much
    backend_mock = MagicMock(spec=DeviceBackend)
    return backend_mock


@pytest.fixture
def ext_info() -> DeviceInfo:
    return DeviceInfo(
        path="/dev/sdX",
        display_name="External Test Drive",
        size_bytes=1000,
        is_removable=True,
        is_internal=False,
        is_system_container=False,
        is_disk_image=False,
        filesystem=None,
        model="Test Model",
        serial="TEST1234",
        topology_type="usb",
        has_hpa_dco=False,
        is_sed=False,
        ieee_2883_capabilities=[],
    )


def test_internal_drive_refusal(ledger, backend, ext_info):
    ext_info = replace(ext_info, is_removable=False, is_internal=True)
    with patch("app.core.erasure.firmware_sanitize.assert_safe"):
        with patch("app.core.erasure.firmware_sanitize.subprocess.run") as mock_run:
            with pytest.raises(NonExternalTargetError):
                execute_ata_secure_erase(info=ext_info, backend=backend, ledger=ledger, user_confirmed=True)
            mock_run.assert_not_called()


def test_non_linux_refusal(ledger, backend, ext_info):
    with patch("app.core.erasure.firmware_sanitize.assert_safe"):
        with patch("app.core.erasure.firmware_sanitize.platform.system", return_value="Darwin"):
            with patch("app.core.erasure.firmware_sanitize.subprocess.run") as mock_run:
                with pytest.raises(UnsupportedPlatformError):
                    execute_ata_secure_erase(info=ext_info, backend=backend, ledger=ledger, user_confirmed=True)
                mock_run.assert_not_called()


def test_missing_hdparm_refusal(ledger, backend, ext_info):
    with patch("app.core.erasure.firmware_sanitize.assert_safe"):
        with patch("app.core.erasure.firmware_sanitize.platform.system", return_value="Linux"):
            with patch("app.core.erasure.firmware_sanitize.shutil.which", return_value=None):
                with patch("app.core.erasure.firmware_sanitize.subprocess.run") as mock_run:
                    with pytest.raises(UnsupportedPlatformError):
                        execute_ata_secure_erase(info=ext_info, backend=backend, ledger=ledger, user_confirmed=True)
                    mock_run.assert_not_called()


def test_freeze_lock_refusal(ledger, backend, ext_info):
    with patch("app.core.erasure.firmware_sanitize.assert_safe"):
        with patch("app.core.erasure.firmware_sanitize.platform.system", return_value="Linux"):
            with patch("app.core.erasure.firmware_sanitize.shutil.which", return_value="/bin/hdparm"):
                with patch("app.core.erasure.firmware_sanitize.subprocess.run") as mock_run:
                    # Mock hdparm -I to return frozen
                    mock_proc = MagicMock()
                    mock_proc.stdout = "frozen"
                    mock_run.return_value = mock_proc
                    
                    with pytest.raises(SecurityFreezeLockError):
                        execute_ata_secure_erase(info=ext_info, backend=backend, ledger=ledger, user_confirmed=True)
                    
                    # Should have only called hdparm -I, not set-pass or erase
                    assert mock_run.call_count == 1


def test_ata_success_path(ledger, backend, ext_info):
    with patch("app.core.erasure.firmware_sanitize.assert_safe"):
        with patch("app.core.erasure.firmware_sanitize.platform.system", return_value="Linux"):
            with patch("app.core.erasure.firmware_sanitize.shutil.which", return_value="/bin/hdparm"):
                with patch("app.core.erasure.firmware_sanitize.subprocess.run") as mock_run:
                    # Mock three calls: hdparm -I, hdparm --security-set-pass, hdparm --security-erase
                    def side_effect(*args, **kwargs):
                        mock_proc = MagicMock()
                        mock_proc.returncode = 0
                        if "-I" in args[0]:
                            mock_proc.stdout = "not frozen"
                        else:
                            mock_proc.stdout = ""
                        return mock_proc
                    
                    mock_run.side_effect = side_effect
                    
                    result = execute_ata_secure_erase(info=ext_info, backend=backend, ledger=ledger, user_confirmed=True)
                    
                    assert result.ok is True
                    assert result.method == "ata_secure_erase"
                    
                    entries = ledger.get_entries()
                    assert len(entries) == 1
                    assert entries[0].action == "firmware_sanitize"
                    assert entries[0].payload["result"] == "PASS"


def test_ata_failure_path(ledger, backend, ext_info):
    with patch("app.core.erasure.firmware_sanitize.assert_safe"):
        with patch("app.core.erasure.firmware_sanitize.platform.system", return_value="Linux"):
            with patch("app.core.erasure.firmware_sanitize.shutil.which", return_value="/bin/hdparm"):
                with patch("app.core.erasure.firmware_sanitize.subprocess.run") as mock_run:
                    def side_effect(*args, **kwargs):
                        mock_proc = MagicMock()
                        if "-I" in args[0]:
                            mock_proc.stdout = "not frozen"
                            mock_proc.returncode = 0
                        elif "--security-set-pass" in args[0]:
                            mock_proc.returncode = 0
                        else:
                            # Erase fails
                            mock_proc.returncode = 1
                            mock_proc.stderr = "Drive rejected command"
                        return mock_proc
                    
                    mock_run.side_effect = side_effect
                    
                    result = execute_ata_secure_erase(info=ext_info, backend=backend, ledger=ledger, user_confirmed=True)
                    
                    assert result.ok is False
                    assert "Drive rejected command" in result.error
                    
                    entries = ledger.get_entries()
                    assert len(entries) == 1
                    assert entries[0].payload["result"] == "FAIL"


def test_nvme_success_path(ledger, backend, ext_info):
    ext_info = replace(ext_info, topology_type="nvme", path="/dev/nvme0n1")
    
    with patch("app.core.erasure.firmware_sanitize.assert_safe"):
        with patch("app.core.erasure.firmware_sanitize.shutil.which", return_value="/bin/nvme"):
            with patch("app.core.erasure.firmware_sanitize.subprocess.run") as mock_run:
                with patch("app.core.erasure.firmware_sanitize.time.sleep") as mock_sleep:
                    def side_effect(*args, **kwargs):
                        mock_proc = MagicMock()
                        mock_proc.returncode = 0
                        if "sanitize-log" in args[0]:
                            mock_proc.stdout = "Sanitize Completed Successfully"
                        else:
                            mock_proc.stdout = ""
                        return mock_proc
                    
                    mock_run.side_effect = side_effect
                    
                    result = execute_nvme_sanitize(info=ext_info, backend=backend, ledger=ledger, user_confirmed=True)
                    
                    assert result.ok is True
                    assert result.method == "nvme_sanitize"
                    mock_sleep.assert_called_once()
                    
                    entries = ledger.get_entries()
                    assert len(entries) == 1
                    assert entries[0].payload["result"] == "PASS"


def test_nvme_timeout_path(ledger, backend, ext_info):
    ext_info = replace(ext_info, topology_type="nvme", path="/dev/nvme0n1")
    
    with patch("app.core.erasure.firmware_sanitize.assert_safe"):
        with patch("app.core.erasure.firmware_sanitize.shutil.which", return_value="/bin/nvme"):
            with patch("app.core.erasure.firmware_sanitize.subprocess.run") as mock_run:
                with patch("app.core.erasure.firmware_sanitize.time.sleep") as mock_sleep:
                    def side_effect(*args, **kwargs):
                        mock_proc = MagicMock()
                        mock_proc.returncode = 0
                        if "sanitize-log" in args[0]:
                            mock_proc.stdout = "Sanitize in progress"
                        else:
                            mock_proc.stdout = ""
                        return mock_proc
                    
                    mock_run.side_effect = side_effect
                    
                    result = execute_nvme_sanitize(info=ext_info, backend=backend, ledger=ledger, user_confirmed=True, max_polls=2)
                    
                    assert result.ok is False
                    assert "Timed out" in result.error
                    assert mock_sleep.call_count == 2
                    
                    entries = ledger.get_entries()
                    assert len(entries) == 1
                    assert entries[0].payload["result"] == "FAIL"
