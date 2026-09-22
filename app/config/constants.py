"""Shared constants used across erasure, recovery, and audit modules."""

APP_NAME = "Integrated Secure Erasure & Recovery Tool"
APP_VERSION = "0.1.0-mvp"

# I/O chunk size for erasure writers and verification readers.
CHUNK_SIZE = 4 * 1024 * 1024  # 4 MiB

# Fraction (and cap) of a target's blocks sampled during post-wipe verification.
VERIFY_SAMPLE_FRACTION = 0.01
VERIFY_SAMPLE_MIN_BLOCKS = 16
VERIFY_SAMPLE_MAX_BLOCKS = 512

# Wipe standard identifiers (see app/core/erasure/standards/).
STANDARD_SINGLE_PASS_ZERO = "single_pass_zero"
STANDARD_SINGLE_PASS_RANDOM = "single_pass_random"
STANDARD_NIST_800_88_CLEAR = "nist_800_88_clear"
STANDARD_DOD_5220_22_M = "dod_5220_22_m"

ALL_STANDARDS = (
    STANDARD_SINGLE_PASS_ZERO,
    STANDARD_SINGLE_PASS_RANDOM,
    STANDARD_NIST_800_88_CLEAR,
    STANDARD_DOD_5220_22_M,
)

# Audit action names — kept as constants so ledger entries stay consistent.
ACTION_DRIVE_ERASE = "drive_erase"
ACTION_FILE_ERASE = "file_erase"
ACTION_RECOVERY_SCAN = "recovery_scan"
ACTION_POST_ERASE_VERIFICATION = "post_erase_verification"
ACTION_FIRMWARE_SANITIZE = "firmware_sanitize"
ACTION_REPORT_EXPORT = "report_export"

# Recovery candidate confidence bands (0-100 score -> label), used by GUI + reports.
CONFIDENCE_HIGH = 75
CONFIDENCE_MEDIUM = 40
