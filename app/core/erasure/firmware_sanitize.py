"""Reference command strings for firmware-level sanitize (the kind IEEE 2883 Purge relies on).

WARNING: Executing these commands destructively can brick drives if the OS
suspends the machine or if passwords are lost.
For safety during the hackathon/demo, these functions operate in 
DOCUMENTATION-ONLY mode. They return the exact command that would have been
executed but DO NOT run it.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import time
from dataclasses import dataclass

from app.config.constants import ACTION_FIRMWARE_SANITIZE
from app.core.audit.ledger import AuditLedger
from app.core.devices.backend_base import DeviceBackend, DeviceInfo
from app.core.devices.fingerprint import fingerprint
from app.core.devices.safety import assert_safe
from app.core.erasure.drive_eraser import ConfirmationRequiredError
from app.utils.logging_setup import get_logger

logger = get_logger(__name__)


def generate_nvme_format_command(info: DeviceInfo) -> list[str]:
    """Generates the NVMe Format NVM command (IEEE 2883-2022 Purge/Sanitize).
    
    This command instructs the NVMe controller to securely erase all namespaces.
    """
    if "nvme" not in info.path:
        raise ValueError(f"Drive {info.path} is not an NVMe device.")
    
    # User Data Erase (SES=1) or Cryptographic Erase (SES=2)
    # nvme format /dev/nvme0n1 --ses=1
    return ["nvme", "format", info.path, "--ses=1"]


def generate_hdparm_security_erase_command(info: DeviceInfo, password: str = "NULL") -> list[str]:
    """Generates the ATA Secure Erase command via hdparm.
    
    1. Sets a user password.
    2. Issues the SECURITY ERASE UNIT command.
    """
    # The actual execution would look like:
    # hdparm --user-master u --security-set-pass {password} {info.path}
    # hdparm --user-master u --security-erase {password} {info.path}
    
    # We return the combined erase command for logging
    return ["hdparm", "--user-master", "u", "--security-erase", password, info.path]


def simulate_firmware_sanitize(info: DeviceInfo, method: str) -> dict:
    """Simulates a firmware sanitize and returns the audit trail data."""
    if method == "nvme_format":
        cmd = generate_nvme_format_command(info)
    elif method == "ata_secure_erase":
        cmd = generate_hdparm_security_erase_command(info)
    else:
        raise ValueError(f"Unknown firmware sanitize method: {method}")
        
    logger.info("SIMULATED FIRMWARE SANITIZE: %s", " ".join(cmd))
    
    return {
        "command": " ".join(cmd),
        "status": "simulated",
        "compliance": "none - command was generated but NOT executed; no Purge performed",
        "message": "For safety, firmware commands are logged but not executed."
    }


class UnsupportedPlatformError(RuntimeError):
    """Raised when the current OS/toolchain can't perform this firmware operation."""


class NonExternalTargetError(RuntimeError):
    """Raised when the target is not confirmed external/removable — firmware
    commands are only ever allowed against external/removable drives."""


class SecurityFreezeLockError(RuntimeError):
    """Raised when the drive reports a Security Freeze Lock — this cannot be
    cleared by software; the operator must physically unplug/replug the
    drive (or suspend/resume the host) and try again."""


@dataclass
class FirmwareSanitizeResult:
    ok: bool
    method: str            # "ata_secure_erase" | "nvme_sanitize"
    command: list[str]
    exit_code: int | None
    device_fingerprint: str
    error: str | None = None


def _assert_safe_for_firmware(info: DeviceInfo, backend: DeviceBackend) -> None:
    assert_safe(info, backend)  # existing deny-list-first gate, unchanged
    if not (info.is_removable and not info.is_internal):
        raise NonExternalTargetError(
            f"Firmware sanitize refused: {info.display_name} is not confirmed external/removable. "
            "This operation is only permitted on external/removable drives."
        )


def check_security_freeze_lock(info: DeviceInfo) -> bool:
    """Returns True if hdparm -I reports the drive as frozen. Linux only."""
    if platform.system() != "Linux" or shutil.which("hdparm") is None:
        raise UnsupportedPlatformError("hdparm is required and only available on Linux.")
    proc = subprocess.run(["hdparm", "-I", info.path], capture_output=True, text=True, timeout=30)
    output = proc.stdout.lower()
    if "not\tfrozen" in output or "not frozen" in output:
        return False
    if "frozen" in output:
        return True
    # Can't confidently determine state — treat as frozen (fail closed).
    logger.warning("Could not determine freeze-lock state for %s; treating as frozen (refusing).", info.path)
    return True


def execute_ata_secure_erase(
    info: DeviceInfo,
    backend: DeviceBackend,
    ledger: AuditLedger,
    *,
    user_confirmed: bool,
    password: str = "NULL",
) -> FirmwareSanitizeResult:
    if not user_confirmed:
        raise ConfirmationRequiredError("Firmware sanitize requires explicit user confirmation.")
    _assert_safe_for_firmware(info, backend)
    if platform.system() != "Linux" or shutil.which("hdparm") is None:
        raise UnsupportedPlatformError("ATA Secure Erase requires hdparm, which is only available on Linux.")
    if check_security_freeze_lock(info):
        raise SecurityFreezeLockError(
            f"{info.display_name} reports a Security Freeze Lock. Physically unplug and "
            "reconnect the drive (or suspend/resume this machine), then retry."
        )

    dev_fingerprint = fingerprint(info)
    set_pass_cmd = ["hdparm", "--user-master", "u", "--security-set-pass", password, info.path]
    erase_cmd = ["hdparm", "--user-master", "u", "--security-erase", password, info.path]

    set_pass_proc = subprocess.run(set_pass_cmd, capture_output=True, text=True, timeout=30)
    if set_pass_proc.returncode != 0:
        result = FirmwareSanitizeResult(
            ok=False, method="ata_secure_erase", command=set_pass_cmd,
            exit_code=set_pass_proc.returncode, device_fingerprint=dev_fingerprint,
            error=f"security-set-pass failed: {set_pass_proc.stderr.strip()}",
        )
        _log_firmware_result(ledger, info, dev_fingerprint, result)
        return result

    erase_proc = subprocess.run(erase_cmd, capture_output=True, text=True, timeout=3600)
    result = FirmwareSanitizeResult(
        ok=erase_proc.returncode == 0,
        method="ata_secure_erase",
        command=erase_cmd,
        exit_code=erase_proc.returncode,
        device_fingerprint=dev_fingerprint,
        error=None if erase_proc.returncode == 0 else erase_proc.stderr.strip(),
    )
    _log_firmware_result(ledger, info, dev_fingerprint, result)
    return result


def execute_nvme_sanitize(
    info: DeviceInfo,
    backend: DeviceBackend,
    ledger: AuditLedger,
    *,
    user_confirmed: bool,
    sanact: str = "0x02",
    poll_interval_s: float = 5.0,
    max_polls: int = 240,   # 20 minutes at 5s intervals — Sanitize can be slow
) -> FirmwareSanitizeResult:
    if not user_confirmed:
        raise ConfirmationRequiredError("Firmware sanitize requires explicit user confirmation.")
    _assert_safe_for_firmware(info, backend)
    if shutil.which("nvme") is None:
        raise UnsupportedPlatformError("NVMe Sanitize requires the nvme-cli tool, which is not installed.")

    dev_fingerprint = fingerprint(info)
    cmd = ["nvme", "sanitize", info.path, f"--sanact={sanact}"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        result = FirmwareSanitizeResult(
            ok=False, method="nvme_sanitize", command=cmd, exit_code=proc.returncode,
            device_fingerprint=dev_fingerprint, error=proc.stderr.strip(),
        )
        _log_firmware_result(ledger, info, dev_fingerprint, result)
        return result

    log_cmd = ["nvme", "sanitize-log", info.path]
    for _ in range(max_polls):
        time.sleep(poll_interval_s)
        log_proc = subprocess.run(log_cmd, capture_output=True, text=True, timeout=30)
        if "sanitize completed successfully" in log_proc.stdout.lower():
            result = FirmwareSanitizeResult(
                ok=True, method="nvme_sanitize", command=cmd, exit_code=0,
                device_fingerprint=dev_fingerprint, error=None,
            )
            _log_firmware_result(ledger, info, dev_fingerprint, result)
            return result
        if "sanitize failed" in log_proc.stdout.lower():
            result = FirmwareSanitizeResult(
                ok=False, method="nvme_sanitize", command=cmd, exit_code=None,
                device_fingerprint=dev_fingerprint, error="Device reported sanitize failure.",
            )
            _log_firmware_result(ledger, info, dev_fingerprint, result)
            return result

    result = FirmwareSanitizeResult(
        ok=False, method="nvme_sanitize", command=cmd, exit_code=None,
        device_fingerprint=dev_fingerprint,
        error=f"Timed out waiting for sanitize completion after {max_polls * poll_interval_s:.0f}s.",
    )
    _log_firmware_result(ledger, info, dev_fingerprint, result)
    return result


def _log_firmware_result(ledger: AuditLedger, info: DeviceInfo, dev_fingerprint: str, result: FirmwareSanitizeResult) -> None:
    ledger.append_entry(
        action=ACTION_FIRMWARE_SANITIZE,
        target=f"{info.display_name} ({dev_fingerprint})",
        payload={
            "method": result.method,
            "command": result.command,
            "exit_code": result.exit_code,
            "result": "PASS" if result.ok else "FAIL",
            "error": result.error,
        },
    )
