# Technical Documentation

Status labels used throughout: **Verified** (exercised by automated tests
or manual runs on real hardware), **Implemented, untested** (code exists
but has not been run on the target platform/tool), **Not wired** (code
exists but nothing in the app calls it), **Not implemented**.

## Architecture Overview

```
app/gui/     PySide6 views — no business logic; long jobs run on a QThread
             (app/gui/workers.py) so the UI thread never blocks on I/O.
  theme.py   Colour tokens, bundled fonts, the Qt stylesheet (see GUI & Theme).
  widgets/   Shared UI pieces: ui.py (page/card/badge/stat tile helpers),
             icons.py (inline SVG icons), device table, progress panel,
             type-to-confirm dialog.
  assets/    Bundled fonts (Fira Sans, Fira Code) and a checkbox icon.
app/core/    Pure Python, no Qt imports — independently testable.
  devices/   Cross-platform device enumeration + safe-target enforcement.
  erasure/   Wipe standards, chunked overwrite I/O, verification,
             filesystem-aware warnings, firmware command reference strings.
  recovery/  pytsk3, PhotoRec and bulk_extractor engines, classification
             (signatures + libmagic + Magika), confidence scoring, hashing.
  audit/     Hash-chained audit ledger (SQLite), HMAC tags, certificates.
  reporting/ Generic Report object -> PDF (reportlab) and JSON.
app/config/  Constants and runtime settings (paths, simulation-mode default).
app/utils/   Logging, entropy math, subprocess helpers.
scripts/     setup_env.sh (Linux/macOS deps), setup_env.ps1 (Windows setup),
             benchmark.py (performance numbers), check_platform.py (real-machine
             device/safety self-check), make_practice_image.py (demo FAT image).
.github/     CI workflow: tests + check_platform on Windows, Ubuntu, macOS.
```

Every destructive action and every recovery scan calls
`AuditLedger.append_entry()`. This is enforced by code structure (the
orchestrators `drive_eraser.py`, `file_eraser.py` and `scan_service.py`
each log directly), not by any mechanism that makes bypassing it
impossible.

## Device Safety & System-Drive Detection — Verified on Windows, Linux and macOS (system/internal disks); USB detection unit-tested only

`app/core/devices/backend_base.py` defines one normalized `DeviceInfo`
dataclass that every platform backend returns, so `safety.py` never has
to special-case platforms.

`safety.classify_target()` is **deny-list-first**. A target is allowed
only if it is:
1. a disk image file (`is_disk_image=True`), or
2. a device the backend positively identifies as removable/external AND
   not internal AND not the system container.

Anything else, including anything the backend can't classify, is denied.
Every backend's `is_system_drive()` also returns True for any internal
disk, as a second layer.

How each backend finds the system disk and decides "removable":

| | System disk | Removable | If enumeration fails |
|---|---|---|---|
| **macOS** (`backend_macos.py`) | whole disk equal to `ParentWholeDisk` of `diskutil info -plist /` | `RemovableMedia` or `Ejectable` | treated as system disk |
| **Windows** (`backend_windows.py`) | `Get-Disk` `IsSystem` **or** `IsBoot` **or** the disk holding `%SystemDrive%`'s partition | bus type USB, SD or MMC only | no devices listed |
| **Linux** (`backend_linux.py`) | any descendant in `lsblk`'s tree (partition, LVM, LUKS) mounted at `/`, `/boot`, `/boot/efi`, `/efi`, `/usr`, `/var`, `/home` or used as swap | `RM` flag, or transport `usb`/`mmc` (`HOTPLUG` ignored — hot-swap internal bays set it) | exception, shown as an empty list |

Windows notes: the enumeration script casts every field inside PowerShell
so the JSON is the same on Windows PowerShell 5.1 (which serializes the
BusType enum as a number) and PowerShell 7 (a string); the parser accepts
both. Raw writes need Administrator; `open_raw()` takes the disk offline
with `Set-Disk` for the write (Windows refuses writes to sectors of mounted
volumes) and restores its online/read-only state afterwards, also when
the write fails.

Linux note: older util-linux prints lsblk flags as the strings `"0"`/`"1"`.
The previous parser used `bool(...)`, and `bool("0")` is `True`, so internal
disks could be reported as removable. Fixed and covered by tests with both
output formats.

**Limitation:** "removable/external" comes from what the OS reports. An
external drive that happens to hold important data is still an allowed
target; the only protection there is the type-to-confirm dialog.

**A real bug caught during development:** `diskutil info -plist <id>`
requires `-plist` directly after `info`. The original code appended it
last, which silently broke `get_device_info()` for every real device.
Mocked unit tests did not catch it; running against real hardware did.

## Wipe Standards — Verified on disk images

`app/core/erasure/standards/`: single-pass zero, single-pass random,
NIST 800-88 Clear (one overwrite), DoD 5220.22-M (0x00, 0xFF, random).
See `compliance_mapping.md` for what these do and don't guarantee.

Verification (`app/core/erasure/verifier.py`) runs after **every** pass
and reads back a **random sample** of 4 MiB blocks — 1% of blocks, minimum
16, maximum 512 — checking for the expected constant fill (zero/ones
passes) or Shannon-entropy randomness (random passes). A failure is
reported and logged as FAIL.

**Limitation — sampling coverage:**

| Target size | 4 MiB blocks | Blocks read back | Coverage |
|---|---|---|---|
| 64 MiB | 16 | 16 | 100% |
| 256 MiB | 64 | 16 | 25% |
| 1 GiB | 256 | 16 | 6.25% |
| 64 GiB | 16,384 | 163 | 1% |
| 1 TiB | 262,144 | 512 (cap) | 0.2% |

A small region that was never written can go undetected on large
targets, and the random-fill check tests for high entropy, so a region
that still holds encrypted or compressed original data would also pass.
Full read-back verification is not implemented.

Real (non-image) device erasure goes through the same code path via the
backend's `open_raw()`, which needs elevated permissions (Administrator on
Windows, root on Linux/macOS). The GUI checks this before starting and
explains what's missing. No run against a physical drive is recorded in
`validation_testing.md` on any platform; all automated tests use disk
images or recorded enumeration output.

### Independent Post-Erase Verification

`app/core/erasure/post_erase_verification.py` orchestrates `run_verified_drive_erase()`, which wraps `run_drive_erase()`. On real erases (non-simulation), it automatically runs a recovery scan (`run_recovery_scan`) against the target immediately after wiping it to verify no files can be recovered by an independent engine, providing stronger evidence than the per-pass sampled check alone.

## Filesystem-Aware File Erasure — Warning text unit-tested; detection checked per OS

`app/core/erasure/fs_aware.py` detects the filesystem of a file before
erasing it and returns warnings shown in the GUI and stored in the audit
entry:
- APFS, ReFS, Btrfs, ZFS: copy-on-write warning (APFS also counts local
  Time Machine snapshots).
- NTFS: files under ~1 KB may live inside their MFT record; Volume Shadow
  Copies may keep earlier versions; alternate data streams aren't overwritten.
- ext2/3/4, XFS: journaling may keep fragments.
- FAT/exFAT: contents are overwritten but the deleted directory entry keeps
  most of the original file name (observed in our own recovery tests).

Detection: macOS `statfs(2)` via ctypes, Windows `GetVolumeInformationW`
via ctypes, Linux `df -T`. The result is cached per device, so a folder of
many files costs one detection, not one per file (the old code spawned
`df`/`stat`/`diskutil`/`tmutil` for every file, ~0.2 s each).

It only warns. It never deletes snapshots or edits filesystem metadata.
`invoke_trim()` runs `fstrim` on Linux (needs root; at most once a minute
per volume), and does nothing on macOS and Windows.

## Firmware Sanitize — Not wired (on purpose)

`app/core/erasure/firmware_sanitize.py` builds NVMe Format and ATA
Secure Erase command strings for reference. It never executes them,
nothing in the app calls it, and its result is labelled "no Purge
performed".

## Hash-Chained Audit Ledger — Verified

Each `AuditEntry` (`app/core/audit/models.py`) stores `prev_hash` and
`entry_hash = SHA256(canonical_json({timestamp, actor, action, target,
payload, prev_hash}))`. `verify_chain()` checks, for every entry in order:
1. `prev_hash` equals the previous entry's `entry_hash` (catches deletion
   and reordering);
2. recomputing the hash matches the stored hash (catches edits);
3. the HMAC tag matches, using a key that is ratcheted forward (one-way
   hashed) after every entry.

`app/core/audit/store.py` adds SQLite triggers that reject `UPDATE` and
`DELETE` on the table.

Limitations:
- **The HMAC starting key loads from the OS keystore** (macOS Keychain /
  Windows Credential Manager / Linux Secret Service, via
  `app/core/audit/keystore.py`), generated on first use — see
  `AuditLedger.__init__`. It is no longer a value present in source. If no
  keystore backend is available, it falls back to a private, mode-0600
  file under the app's data directory instead of failing — still
  per-machine generated, just not OS-keystore-protected in that case.
  Either way, whoever can read that key can still recompute valid tags and
  rebuild a self-consistent chain; this is a real barrier against "anyone
  with the source code," not a barrier against "anyone with access to this
  machine."
- Triggers only stop ordinary SQL. Anyone with file access can drop them.
  The chain check *detects* tampering; nothing *prevents* it.
- Entries with no MAC tag (older databases) are skipped by the MAC check
  instead of being flagged.
- Timestamps come from the local clock. `timestamping.py` contains an
  RFC 3161 client (via `openssl ts` to freetsa.org, falling back to a
  local placeholder) but it is **not wired** — nothing calls
  `AuditLedger.timestamp_entry()`.
- This is a single-machine hash chain, not a distributed blockchain.

## Certificates — Verified (generation), not legally reviewed

`app/core/audit/certificate.py`, triggered from the Audit Log page,
writes a JSON certificate *structured after* the BSA 2023 Section 63
certificate: operator, organization, target, the target's audit entries
(hash, result, standard), whether the chain verified at issue, and an
embedded `limitations` list. The wipe status is typed by the operator.
The `integrity_digest` is unkeyed SHA-384 — not a digital signature.
No automated test covers certificate generation yet.

## Recovery Engine Design

| Engine | Status | What it does |
|---|---|---|
| `TskEngine` (pytsk3 / Sleuth Kit) | Verified on FAT images | Walks filesystem metadata, finds unallocated (deleted) entries, reads them through the filesystem's own block map. Needs intact filesystem structures. |
| `PhotoRecEngine` | Runs on FAT images; **did not recover the deleted plain-text test file** (no signature), so carving is unverified | Signature carving with no filesystem needed. Driven through PhotoRec's **undocumented** `/cmd <image> search` mode (found by inspecting the binary), with `stdin=DEVNULL` so it can't block on a keypress. Parses the DFXML `report.xml`. Other `/cmd` argument combinations tried (partition selection, file-type filters) either errored or stalled, so only whole-image search is used. |
| `BulkExtractorEngine` | Implemented, **untested on the dev machine** (`bulk_extractor` is not installed there) | Runs `bulk_extractor` and lists each non-empty feature file (emails, URLs, etc.) as an artifact, shown in a separate GUI table. If the binary is missing the engine is skipped and the table stays empty. |
| `TestDiskEngine` | **Not wired** | `analyze_partitions()` exists but nothing calls it. There is no partition-table recovery in the app. |

**Fragmented files:** when PhotoRec's report lists more than one byte run
for a file, `reassembly.reassemble()` re-extracts it by concatenating
those runs in order. This relies entirely on PhotoRec's own fragment
detection. The bifragment gap-carving code in `reassembly.py` is disabled
(`attempt_gap_carving=False`) and untested. pytsk3 handles fragmentation
through the filesystem's block map.

**Classification** (`classifier.py`):
1. Our own magic-byte signature table (`signatures.py`) — primary, checks
   header and footer.
2. `python-magic` / libmagic cross-check — optional.
3. Magika (Google's ML file-type model) — optional. It is used **only when
   the signature table returns "unknown" and Magika's score is above 0.8**.
   Otherwise its label is recorded in the reasons but does not change the
   type.

**Confidence score** (`confidence.py`), 0–100: +40 header match, +25
footer match (−10 if expected but missing), +10 non-zero size, +10
contiguous (−15 fragmented), +15 cross-engine agreement (pytsk3 and
PhotoRec produced byte-identical files, compared by SHA-256). The weights
are hand-chosen to give a sensible ordering, **not calibrated** on a
labelled dataset.

**Hashing:** SHA-256 for integrity and `ppdeep` fuzzy hashes (CTPH) for
similarity. Fuzzy hashes are only computed for files up to 4 MiB, because
`ppdeep` is pure Python and took 10+ minutes on a 32 MB carved file.
Fuzzy hashes are displayed and stored, but the app has no "compare against
a known file" feature.

## GUI & Theme — Manually checked, no automated GUI tests

- **Layout:** `main_window.py` uses a left sidebar (`QButtonGroup` of
  checkable buttons) and a `QStackedWidget` instead of a tab bar. Switching
  to the Dashboard, Audit Log or Reports refreshes that page, as before.
  Dashboard module cards emit `navigate_requested(key)`.
- **Styling:** `theme.apply_theme()` sets the Fusion style, a dark
  `QPalette`, and one application stylesheet built from the `COLORS`
  tokens. Views set only object names / dynamic properties (for example
  `variant="danger"`), not colours. Fusion is used so the stylesheet
  renders the same on every platform instead of mixing with native macOS
  controls. Native file pickers still follow the OS appearance.
- **Contrast:** colour pairs were checked with the WCAG relative-luminance
  formula: white on the blue (#2563EB) and red (#DC2626) buttons is 5.2:1
  and 4.8:1; body text on cards is 14.6:1; muted and subtle text is at
  least 5:1. Status is always written as text as well as shown by colour.
- **Fonts:** Fira Sans (UI) and Fira Code (paths, hashes, logs) are loaded
  from `app/gui/assets/fonts/` (SIL Open Font License, `OFL.txt`). If they
  are missing the app falls back to system fonts. `sih149.spec` already
  bundles `app/gui/assets`.
- **Icons:** Lucide icons (ISC licence, `app/gui/assets/icons/LUCIDE_LICENSE.txt`)
  embedded as SVG path data and rendered with `QtSvg`, so they can take any
  theme colour. No emoji are used as icons.
- **What was checked (2026-09-17):** every page rendered to images
  offscreen and on macOS and inspected by eye. `tests/gui/test_gui_smoke.py`
  (pytest-qt, offscreen) checks the confirm dialog only enables its button
  for the exact token plus checkbox, queue badge and empty states,
  simulation mode starting checked, and sidebar/dashboard navigation — on
  Windows, Linux and macOS in CI. Nobody has *looked* at the GUI on a
  Windows or Linux desktop; fonts are bundled, so text should match, but
  native file dialogs will look like each OS's own.
- **Same UI on every OS:** the only platform-drawn parts left are the window
  title bar and font rasterisation. Everything inside the window, including
  dialogs, is Qt-drawn with one stylesheet: `theme.apply_theme()` sets
  `AA_DontUseNativeDialogs`, and `widgets/file_dialogs.py` wraps QFileDialog
  with the non-native dialog, a `ThemedIconProvider` (Lucide folder/file/
  drive icons instead of the OS icon theme) and a sidebar of home folders
  plus mounted volumes (`QDir.drives()` on Windows, `/Volumes/*` on macOS,
  `/media/$USER`, `/run/media/$USER`, `/mnt` on Linux). Trade-off: no
  Finder/Explorer favourites, tags or search. `scripts/render_screenshots.py`
  renders every page and dialog; CI runs it with each OS's real display
  system and publishes the PNGs to `ci-screenshots-<os>` branches.
- **Small screens:** every page is a scroll area (`widgets/ui.py::Page`). CI
  screenshots on a 1024×768 Windows runner showed cards drawn on top of each
  other when the window was shorter than the content; pages now scroll
  instead. The window's minimum size is 960×560, which fits a 1366×768 laptop
  at 125% display scaling.
- **Windows specifics:** the process sets its own AppUserModelID so the
  taskbar shows the app rather than python.exe; subprocesses (PowerShell,
  PhotoRec) start with `CREATE_NO_WINDOW` so no console windows flash.

## Report Generation Pipeline

`report_builder.py` turns a `DriveEraseResult`, `BatchEraseResult`, or
`ScanSummary` into a generic `Report`. `json_report.py` and
`pdf_report.py` render it. PDF tables are capped at the first 200 rows per
section; the JSON export contains everything. Each report type carries a
notice (simulation mode, best-effort erasure, or evidentiary data).

## Platform Support Matrix

Evidence levels: **CI** = GitHub-hosted runner (virtual machine, virtual
disks), see `validation_testing.md`; **dev Mac** = run by hand on the
Apple M4 development machine; **unit** = tested with recorded tool output
only.

| Capability | Windows | Linux | macOS |
|---|---|---|---|
| Install via setup script | Verified (CI runs `setup_env.ps1`) | apt path used in CI (`setup_env.sh` itself not run in CI); dnf path untested | Homebrew packages installed in CI (the script itself isn't run there); dev Mac |
| Device enumeration | Verified (CI, PowerShell `Get-Disk` JSON) | Verified (CI, `lsblk -J`) | Verified (CI + dev Mac, `diskutil -plist`) |
| System disk blocked | Verified (CI) | Verified (CI) | Verified (CI + dev Mac) |
| USB/removable drive recognised as SAFE | Unit only | Unit only | Disk images: CI; USB stick: not recorded |
| Raw device read (recovery scan of a drive) | Implemented, untested (needs Administrator) | Implemented, untested (needs root) | One scan of `/dev/disk4` (an attached disk image) is in the dev Mac's audit log; its result wasn't recorded |
| Raw device erase | Implemented, untested (Administrator; disk taken offline via `Set-Disk`) | Implemented, untested (root) | Implemented, untested (root) |
| Disk image erase (simulation) | Verified (CI tests) | Verified (CI tests) | Verified (CI tests + dev Mac) |
| Test fixture image builder | Pure-Python FAT16: verified (CI) | Pure-Python FAT16: verified (CI) | `hdiutil` and pure-Python: verified |
| pytsk3 recovery | Verified (CI) | Verified (CI) | Verified (CI + dev Mac) |
| PhotoRec | Not installed in CI; binary name `photorec_win` recognised (unit) | Installed in CI (apt `testdisk`) and run by the pipeline tests; its output isn't asserted | Verified (CI + dev Mac) |
| bulk_extractor | Untested | Untested | Untested |
| Filesystem detection | Verified NTFS (CI) | Verified ext4 (CI) | Verified APFS (CI + dev Mac) |
| GUI | Builds headless (CI); never viewed on a real Windows desktop | Builds headless (CI); never viewed on a Linux desktop | Builds headless (CI); used on the dev Mac |
| Packaged build (`sih149.spec`) | Not built | Not built | Not built |

## Known Gaps (not implemented)

- NIST 800-88 Purge (firmware sanitize execution) — deliberately excluded.
- Full read-back verification (only sampling).
- Partition-table recovery (TestDisk not wired).
- Gap carving for fragments PhotoRec can't map.
- Secure key storage for the audit HMAC key.
- Trusted timestamping in the app flow.
- Exporting the full audit ledger as a PDF/JSON document.
- Automated GUI tests.
