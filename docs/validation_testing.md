# Validation & Testing

## Test Strategy Overview

Three layers, plus a platform self-check:
- **Unit tests** (`tests/unit/`) — synthetic data and recorded tool output
  (PowerShell `Get-Disk` JSON, `lsblk -J`), no external tools.
- **Integration tests** (`tests/integration/`) — real disk images and the
  real `pytsk3`/PhotoRec engines. One recovery test builds its image with
  macOS `hdiutil`/`diskutil` (skipped elsewhere); the other builds a FAT16
  image in pure Python and runs on every OS.
- **GUI tests** (`tests/gui/`) — pytest-qt with Qt's `offscreen` platform,
  so they need no display.
- **`scripts/check_platform.py`** — run on a real machine: lists the actual
  disks, checks the system disk is blocked and nothing internal is allowed,
  detects the filesystem, and builds the main window headless. Writes to
  nothing.

```bash
.venv/bin/python -m pytest                 # Windows: .venv\Scripts\python.exe -m pytest
.venv/bin/python -m scripts.check_platform --gui
```

## Continuous Integration

`.github/workflows/tests.yml` runs on every push to `main`, on GitHub-hosted
runners with Python 3.12: **windows-latest**, **ubuntu-latest** and
**macos-latest**. Each job installs dependencies (Windows through
`scripts/setup_env.ps1`, the same script users run), runs the whole test
suite, then runs `scripts/check_platform.py --gui` on the runner itself.
Results are published as annotations on the run page.

## Latest Recorded Runs

**CI, 2026-09-17, commit `baff29f` (83 tests at the time):**

| Runner | Tests | Platform self-check on the runner |
|---|---|---|
| Windows Server 2025 | 82 passed, 1 skipped (macOS-only fixture), 11.3 s | 2 disks. `PhysicalDrive0` (system) → BLOCKED; `PhysicalDrive1` (internal data disk) → BLOCKED. Filesystem: NTFS. GUI built. |
| Ubuntu (Azure kernel 6.17) | 82 passed, 1 skipped (macOS-only fixture), 7.9 s | 1 disk. `/dev/sda` (system) → BLOCKED. Filesystem: ext4. GUI built. |
| macOS (Darwin 25.6) | 83 passed, 21.2 s | 7 disks. System APFS container → BLOCKED; internal disks → BLOCKED; 4 attached disk images → SAFE. Filesystem: APFS. GUI built. |

The runners are virtual machines. Their disks are virtual (e.g. "Msft
Virtual Disk"), so the self-check proves the system-disk and internal-disk
paths on real Windows/Linux, but **not** USB detection — that is only
covered by unit tests with recorded `Get-Disk`/`lsblk` output.

**Local, 2026-09-17, macOS (Apple M4), Python 3.11.16:** 84 passed, 0 skipped,
about 6 s. The Magika deprecation warnings from earlier runs are gone (the
classifier now uses the current Magika API).

## Unit Tests

| File | Tests | What it verifies |
|---|---|---|
| `test_audit_ledger.py` | 4 | Empty chain is valid; appended entries link by `prev_hash`; a payload edited via raw SQL (with the append-only trigger dropped, as an attacker with file access could) is detected at the right entry; a ledger database created before HMAC tags existed still opens and verifies. |
| `test_erasure_writer_verifier.py` | 4 | Zero/ones/random passes write the expected data; `verify_pass()` flags data that was never wiped. |
| `test_file_eraser.py` | 4 | A file is overwritten, renamed and unlinked, and logged; a missing file fails cleanly; batch and folder erasure process every item. |
| `test_safety.py` | 7 | Disk images allowed; system container denied; internal non-removable denied with its own reason; external/removable allowed; ambiguous devices denied. Uses constructed `DeviceInfo` objects, not real hardware. |
| `test_backend_windows.py` | 14 | PowerShell JSON parsing (list, single object, garbage); BusType as name *and* as PowerShell 5.1 integer; system NVMe disk and internal SATA disk blocked; USB stick allowed; `IsSystem`, `IsBoot` or hosting `%SystemDrive%` each block even a USB disk; unknown bus fails closed; `\\.\PhysicalDriveN` parsing; no devices if PowerShell fails; raw write refused without Administrator; raw write takes the disk offline, clears and restores read-only, and brings it back online — also when opening the device fails. |
| `test_backend_linux.py` | 6 | `"0"`/`"1"` string flags vs booleans (`bool("0")` was the old bug); system disk found through LVM and LUKS children; USB stick allowed; internal data disk blocked; a live USB running the OS is blocked although removable; loop devices skipped. |
| `test_platform_helpers.py` | 20 | Subprocess wrapper: missing binary → failed result, non-UTF-8 output doesn't crash; Windows executable names for PhotoRec/bulk_extractor; filesystem warning wording for APFS, ReFS, Btrfs, NTFS (small/large), ext4, FAT, exFAT, unknown; filesystem actually detected on the running OS; recovered file names valid on Windows; Magika old/new API parsing; writer finishes when a raw handle accepts partial writes. |
| `test_recovery_classification.py` | 7 | JPEG header/footer detection; truncated file flagged as footer-missing; score ordering complete > truncated, contiguous > fragmented, cross-engine > single engine. |

## Integration Tests

| File | Tests | Scenario |
|---|---|---|
| `test_drive_erase_simulation.py` | 4 | 2 MB image erased in simulation mode: original bytes unchanged, scratch copy all zeros and verified, PDF/JSON reports created. Erase refused without `user_confirmed=True`. Default scratch copy goes to the data folder, not the current working directory. Simulation mode refused for a real device before anything is opened or logged. |
| `test_recovery_pipeline.py` | 1 | macOS only: 32 MB FAT image built with `hdiutil`/`diskutil`, a known text file written then deleted, full `run_recovery_scan()` run. Asserts the **exact original bytes** are recovered by at least one engine, the file is hashed and scored, the audit chain verifies, and reports are generated. |
| `test_recovery_pipeline_portable.py` | 2 | All OSes: pure-Python FAT16 image with a deleted file. pytsk3 recovers it byte-exact under its FAT-deleted name and doesn't report the kept file; the full scan pipeline hashes, scores, logs one verified audit entry and writes reports. |
| `test_practice_image_script.py` | 2 | `scripts/make_practice_image.py` produces an image whose deleted photo pytsk3 returns byte-exact; a missing input file exits with an error. |

## GUI Tests

| File | Tests | What it verifies |
|---|---|---|
| `tests/gui/test_gui_smoke.py` | 9 | All six pages exist in sidebar order; sidebar and dashboard-card navigation; empty states on a fresh install; dashboard lists a real ledger entry after refresh; Simulation mode starts checked; the simulation note switches when toggled; the confirm dialog's button enables only for the exact token plus the checkbox; the file-queue badge and Clear; result-tab counts. Device enumeration is stubbed so results don't depend on the machine. |

Note on the recovery tests: they pass because **pytsk3** recovers the file
from the surviving FAT directory entry. PhotoRec runs in the full-pipeline
tests but does not recover the plain-text file (see
`performance_evaluation.md`). Signature carving without filesystem
metadata is not verified by any test.

## What the Tests Do NOT Cover

Be aware of these before trusting a component:

| Component | Coverage |
|---|---|
| GUI | Smoke tests only (see above). Not covered: file dialogs, the certificate dialogs, running a real erase or scan from the GUI, visual layout (checked by eye on macOS; not checked on Windows or Linux). |
| Certificate generation (`certificate.py`) | None automated. Checked by hand once. |
| HMAC tag verification failures (wrong key, missing tag) | Not tested; only the success path runs. |
| Filesystem warnings (`fs_aware.py`) | Wording is asserted per filesystem, and detection runs on the real OS in CI (NTFS on Windows, ext4 on Linux, APFS on macOS). Not tested: ReFS/Btrfs/FAT *detection* on a real volume, the APFS snapshot count. |
| bulk_extractor engine | Not tested; binary not installed on the dev machine. |
| Magika / python-magic classification | Runs during recovery tests; results not asserted. |
| Fragment reassembly (`reassembly.py`) | Not tested; the fixture file is not fragmented. |
| Real physical drives | No automated test; see manual checklist. |
| Linux and Windows backends | Enumeration and system-disk blocking run on CI virtual machines; parsing/safety tested with recorded output. **Never run:** USB detection on real hardware, and any raw read or write of a physical drive (including the Windows offline/online sequence against a real disk). |
| Large targets (> 1 GB), damaged media, non-FAT filesystems (NTFS, ext4, exFAT, APFS) | Not tested. Recovery is only validated on small FAT images. |
| Recovery of formatted media | Not tested. The fixture deletes a file; it does not reformat the volume. |
| Signature carving (PhotoRec) recovering a known file | Not tested; PhotoRec returns 0 matching files on the current fixture. |

## Recovery Validation — Honest Scope

The only recovery ground truth we have is: **one deleted 55-byte text file
on a small FAT image, recovered byte-for-byte**. We have **not** measured
recovery rates on a benchmark corpus (e.g. the DFRWS carving challenges or
NIST CFReDS images), on fragmented files, or on overwritten or damaged
media. Any recovery-rate claim beyond "works on the FAT fixture" would be
unsupported.

## Manual Test Checklist (real hardware)

Not yet recorded as completed. Fill in date and result when run.

Run it on each OS you intend to demo on (Windows needs an Administrator
terminal, Linux/macOS need `sudo` for the physical-drive steps).

- [ ] Plug in a spare USB drive with no data you need.
- [ ] Drive Eraser: the USB drive shows `SAFE`, internal disks show `BLOCKED`.
- [ ] Real (non-simulation) single-pass erase on the USB drive; verification passes.
- [ ] Recovery on the wiped drive returns 0 or near-0 candidates without crashing.
- [ ] Reformat the drive, add and delete a known file, scan, confirm it comes back.
- [ ] Audit Log: all actions listed; **Verify chain integrity** reports intact.
- [ ] Generate a certificate for the USB drive and read it end to end.
- [ ] Open every generated PDF and check for formatting problems.

## Safety Guard-Rail Checks

- Erasing the system drive is blocked in `safety.py`
  (`tests/unit/test_safety.py`), independent of the GUI.
- `run_drive_erase()` raises `ConfirmationRequiredError` unless
  `user_confirmed=True` (tested).
- Simulation mode against a real device raises
  `SimulationModeMismatchError` before the device is opened (tested).
- Windows raw writes are refused without Administrator rights (tested with a
  stubbed privilege check).

## Known Issues

- **Fixed 2026-09-17:** the app crashed on startup with an audit database
  created before the `mac_tag` column was added (`no such column: mac_tag`).
  Tests missed it because they always create a fresh database. The store
  now adds the column when missing, and a regression test covers it.

- **Fixed 2026-09-17:** the classifier used Magika's removed
  `output.score` field, so Magika failed silently for every file (logged as
  an error, classification fell back to signatures only). It now reads
  `result.score` and supports the old API too.
- **Fixed 2026-09-17:** Linux `lsblk` flags given as `"0"` were parsed as
  True, which could mark internal disks removable.
- Until 2026-09-17 the suite took about 3 minutes because pure-Python
  fuzzy hashing (`ppdeep`) stalled on a large carved blob. Fuzzy hashing
  is now skipped for files over 4 MiB; the suite takes about 6 seconds.
- An interrupted test run can leave an orphaned `photorec` process
  running; check with `ps aux | grep photorec`.
