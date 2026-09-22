# User Manual

## Introduction & Scope

This tool combines secure drive erasure, secure file/folder erasure, and
forensic file recovery in one desktop application. Every action is
recorded in a tamper-evident audit log and can be exported as a PDF/JSON
report.

It is a **hackathon prototype**, not a certified sanitization or forensic
product. Read [compliance_mapping.md](compliance_mapping.md) before
relying on it for anything beyond evaluation. In short:
- Erasure is software overwrite (NIST 800-88 Clear level at most). It does
  not guarantee physical destruction on SSDs, USB flash drives or memory
  cards.
- Recovery results and confidence scores are triage aids, not certified
  findings.
- Certificates follow the structure of a BSA Section 63 certificate but
  are not legally reviewed or digitally signed.

## Finding Your Way Around

The app has a menu on the left with six pages, grouped as **Erase**
(Drive Eraser, File & Folder Eraser), **Recover** (Recovery) and
**Evidence** (Audit Log, Reports), plus the **Dashboard** at the top.
Every page has a short description under its title, and each
long-running job shows a **Progress** card with a status badge (Idle,
Running, Done, Failed) and a log of what happened.

The **Dashboard** shows four summary tiles: the number of audit entries,
whether the audit chain verifies, how many PDF reports exist, and the
last logged action. Below them are shortcuts to the three modules and
the 15 most recent audit entries. All of this is read from the real
audit log and `reports/` folder; there is no sample data, so a fresh
install shows an empty dashboard.

**File pickers** are the app's own, not Finder/File Explorer/GTK, so they
look and behave the same on Windows, Linux and macOS. The left side lists
home folders and every mounted drive or volume; you can also type a full
path into **File name** and press Enter.

Colours are used consistently: blue buttons are normal main actions, red
buttons erase data, amber notes are warnings. Status is always also
written in text (for example `SAFE` / `BLOCKED`), not shown by colour
alone.

## Installation & System Requirements

- **Windows 10/11, Linux and macOS.** The automated test suite runs on all
  three in CI (GitHub Actions: Windows Server, Ubuntu, macOS). Day-to-day
  development and every manual walkthrough were done on macOS. Erasing a
  *physical* drive has not been tried on any platform — see
  `technical_documentation.md`, Platform Support Matrix.
- Python 3.10–3.13 (CI uses 3.12).
- **Windows:** `powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1`
  creates `.venv` and installs everything. PhotoRec is optional: download
  "TestDisk & PhotoRec" from cgsecurity.org and add the folder containing
  `photorec_win.exe` to PATH. Start the app from an **Administrator**
  terminal if you want to scan or erase a physical drive.
- **Linux / macOS:** `./scripts/setup_env.sh` installs `testdisk`
  (PhotoRec), `libmagic`, and on Linux the Qt runtime libraries; then
  `python3 -m venv .venv` and `.venv/bin/pip install -r requirements.txt`.
  Scanning or erasing a physical drive needs `sudo`.
- Optional components and what you lose without them:

| Component | If missing |
|---|---|
| `pytsk3` | No filesystem-aware recovery; only PhotoRec carving |
| `photorec` | No signature carving; only filesystem-aware recovery |
| `bulk_extractor` | The PII / Metadata Artifacts tab stays empty |
| `python-magic`, `magika` | Classification uses only the built-in signature table (python-magic is not installed on Windows) |
| `ppdeep` | Fuzzy hash column shows N/A |

The app keeps running when these are missing and lists unavailable
engines at the end of a scan.

## Safety Model — What This Tool Will and Won't Wipe

The Drive Eraser only allows two kinds of target:
1. A disk image file you select (e.g. `.img`, `.dd`).
2. A drive the operating system reports as external/removable.

Your internal system/boot drive is **never** a valid target. The device
table shows it as `BLOCKED`, and the same check runs in
`app/core/devices/safety.py` before any write, even if the GUI were
bypassed.

**Be careful:** any external drive the OS reports as removable *is*
allowed, including one holding data you care about. The type-to-confirm
dialog (its **Erase permanently** button stays disabled until you type the
exact text shown and tick the checkbox) is the only thing between you and a wipe. Double-check the device
name and size.

**Simulation mode** (on by default) makes a disk-image erase run on a
scratch copy, leaving your original file untouched. Simulation mode
cannot be used on a real device; turn it off explicitly for real hardware.

## Module 1: Drive Eraser

1. Open **Drive Eraser** from the left menu. Click **Refresh Devices** to list
   attached drives, or **Select Disk Image File...** to pick an image.
2. In the **Targets** card, select a row. Only rows marked `SAFE` (green)
   can be erased; `BLOCKED` rows (red) show the reason, and hovering shows
   the full text.
3. In the **Wipe options** card, choose a wipe standard (single pass
   zero/random, NIST 800-88 Clear, or DoD 5220.22-M) and check the
   Simulation Mode box is set as you intend. The note under the checkbox
   is amber while simulation is on and turns red when it is off.
4. Click the red **Erase Selected Target** button, type the confirmation
   code, tick the acknowledgment box, and click **Erase permanently**.
5. Progress and per-pass verification results appear in the **Progress**
   card.
   A PDF and JSON report are written to `reports/`.

After a real (non-simulation) erase, the tool automatically attempts to recover files from the target and reports what it found; 0 found is stronger evidence than the per-pass sampled check alone, but is still this tool checking itself.

What "PASS" means: every pass completed and a random sample of blocks read
back with the expected pattern. It does **not** mean every block was
checked (see the coverage table in `technical_documentation.md`), and on
SSDs it does not mean the physical flash cells were erased.

Real drives are erased at the drive's own write speed. A 64 GB USB stick
at a typical 20–30 MB/s takes roughly 35–55 minutes per pass, so
DoD 5220.22-M takes about three times that.

## Module 2: File & Folder Eraser

1. Open **File & Folder Eraser** from the left menu.
2. **Add Files...** for individual files, or **Add Folder...** to queue an
   entire folder (its contents are erased and the folder removed). The
   badge on the **Erase queue** card shows how many files (or "1 folder")
   are queued.
3. Click the red **Securely Erase Queue** button, type `ERASE FILES` (or
   `ERASE FOLDER`), tick the box, click **Erase permanently**, and watch
   the **Progress** card. Expect
   roughly a quarter of a second per file even for tiny files (filesystem
   checks run for each one).
4. If the filesystem can keep old copies of data, a **"Erase Complete with
   Filesystem Warnings"** dialog lists why (for example, APFS copy-on-write
   or local snapshots). These warnings are also stored in the audit log.
5. A report lists per-file PASS/FAIL, bytes overwritten, and whether
   extended attributes were cleared.

What this does **not** remove: APFS snapshots and Time Machine backups,
filesystem journal records, Spotlight/QuickLook caches, cloud-synced
copies, or copies elsewhere on disk. On macOS (APFS) the overwrite most
likely lands on new blocks, so treat file erasure there as "deleted and
renamed with metadata stripped", not "physically overwritten".

## Module 3: Recovery

1. Open **Recovery** from the left menu. In the **Source** card, browse to
   a disk image, or pick an attached device from the dropdown.
2. Click **Start Recovery Scan**. Installed engines run in turn: pytsk3
   (filesystem-aware), PhotoRec (signature carving), bulk_extractor
   (PII/metadata artifacts).
3. **Recovered Files** tab (in the **Results** card; the tab title shows
   the number of results): name, engine, file type, size, confidence
   score (0–100 with high/medium/low), fragmentation flag, SHA-256, and
   fuzzy hash ("skipped (>4 MiB)" for large files, to keep scans fast).
   Confidence is coloured green (high), amber (medium) or grey (low).
   Hashes are shortened in the table; hover over one to see it in full.
4. **PII / Metadata Artifacts — Bulk Extractor** tab (bulk_extractor only): click a row to
   preview the extracted feature file (for example, email addresses).
5. Select a recovered file and click **Export Selected File...**, or click
   **Generate Forensic Report** for a PDF/JSON report.

How to read the results:
- **Confidence** ranks candidates *within this scan*. A score of 80 is not
  "80% likely genuine", and scores from different scans are not comparable.
- **Fragmented = yes** means PhotoRec found the file in several pieces and
  the tool rebuilt it from PhotoRec's map. Fragmented files are more
  likely to be partly corrupt; open them before relying on them.
- PhotoRec carves by file signature. Files without one (plain text, many
  logs and configs) are only found by pytsk3, which needs the filesystem
  structure to still exist.
- The same file often appears twice (once per engine). Identical SHA-256
  values across engines raise the confidence score.
- Scans take time: PhotoRec reads the whole image, and a multi-gigabyte
  device can take many minutes. See `performance_evaluation.md`.

**Evidence handling:** the tool only reads the source, but it does not
enforce read-only access. For real evidence, scan a forensic image or use
a hardware write-blocker.

## Audit Log, Certificates & Reports

- The **Audit Log** page lists every logged action with its hash (hover
  over a hash to see it in full). Click a row to see the entry's details.
- **Verify Chain Integrity** recomputes every entry's hash, chain link and
  MAC tag, and names the first entry that fails. It *detects* tampering
  after the fact; it cannot prevent someone with file access from
  changing the database.
- **Generate Certificate (Sec. 63-style)** asks for a target, operator
  name, organization, and the wipe status, then saves a JSON certificate
  with that target's audit entries and an embedded list of limitations.
  Enter a wipe status you have actually verified; the tool does not check
  what you type against the audit result.
- The **Reports** page lists generated PDFs; select one and click
  **Open PDF**, or double-click it.

Timestamps come from this computer's clock. No trusted timestamping
authority is used.

## Simulation Mode Guide

Simulation mode lets you demo the Drive Eraser repeatedly without a fresh
USB stick. Pick or create a disk image (e.g. with `dd` or Disk Utility),
leave Simulation Mode checked, and each run wipes a fresh scratch copy
while the source image stays intact. Simulation runs are labelled
"SIMULATION MODE" in their reports.

## Troubleshooting

- **"unknown wipe standard"** — the standard ID isn't registered in
  `app/core/erasure/standards/__init__.py`. Shouldn't happen through the GUI.
- **Recovery finds 0 candidates** — check the scan result message or the
  audit entry for `engines_unavailable`. If both `pytsk3` and `photorec`
  are listed, no engine ran; re-run `setup_env.sh`. A genuinely wiped or
  empty image also returns 0.
- **PII / Metadata Artifacts tab is empty** — `bulk_extractor` is not installed, or the
  image contained no emails/URLs/other features.
- **Device table is empty** — device enumeration failed (see terminal
  output). macOS: `diskutil` isn't on PATH. Windows: PowerShell couldn't run
  `Get-Disk` (it needs the Storage module, present on Windows 8+ and
  Server 2012+). Linux: `lsblk` is missing.
- **"Can't read this device" / "Not enough permissions"** — reading or
  erasing a physical drive needs Administrator (Windows) or root (Linux,
  macOS). Disk image files don't.
- **Real device erase fails with a permission error** — raw device writes
  need elevated permissions.

## FAQ

**Q: Can this permanently sanitize an SSD?**
A: Yes, but with strict conditions. Standard wipe passes leave data in remapped or over-provisioned flash cells. The "Advanced" Firmware Sanitize (Purge) feature solves this by issuing real firmware commands (ATA Secure Erase / NVMe Sanitize) to the drive controller. However, this feature is:
1. Gated strictly to external/removable drives (never internal/system drives).
2. Available only on Linux (requires `hdparm` or `nvme-cli`; macOS/Windows cannot safely issue these commands).
3. Subject to Security Freeze Locks (you may need to physically unplug/replug the drive if the OS freezes it).
4. **Not yet validated against physical hardware** — it is new and should be treated as unproven until tested by a human on a spare drive.

**Q: Is the certificate legally valid?**
A: Not on its own. It follows the structure of a BSA 2023 Section 63
certificate, but it has not been legally reviewed and is not digitally
signed.

**Q: Can the audit log be faked?**
A: Edits are detected by Verify Chain Integrity. The MAC key now loads from
the OS keystore (Keychain / Credential Manager / Secret Service) instead of
a fixed value in source, and exported certificates are additionally signed
with an Ed25519 key from the same keystore, verifiable with the embedded
public key and no access to this machine. Neither is a certificate
authority: someone with access to this machine's keystore (or, on a system
with no keystore backend, its private key-fallback file) and the database
file could still rebuild a consistent fake log.

**Q: Does recovery modify the source device/image?**
A: The engines only read from the source and write recovered files to a
separate output directory. Read-only access is not enforced by the OS, so
use a write-blocker or a read-only image for real evidence.
