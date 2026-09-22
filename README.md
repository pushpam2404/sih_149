# Integrated Secure Data Erasure & Advanced File Recovery Tool

[![tests](https://github.com/pushpam2404/SIH_149/actions/workflows/tests.yml/badge.svg)](https://github.com/pushpam2404/SIH_149/actions/workflows/tests.yml)

SIH Problem Statement 26149 (NTRO) — one desktop app that combines secure
drive/file erasure with forensic file carving and recovery. Every action is
recorded in a tamper-evident, hash-chained audit log and exported as PDF/JSON
reports. Runs on **Windows, Linux and macOS**.

**This is a hackathon prototype, not a certified product.** We've tried to
state exactly what works, what doesn't, and what we haven't tested. See
[What we claim and don't](#what-we-claim-and-dont) and
[docs/compliance_mapping.md](docs/compliance_mapping.md).

## Why this matters

Investigators currently use one tool to destroy data and a different one to
recover it, with no shared, verifiable record connecting the two. This tool
puts both workflows behind one hash-chained audit log, so every erase and
every recovery scan can be checked afterwards. It can also produce a
certificate structured after India's BSA 2023 Section 63 electronic-evidence
certificate.

## Modules

1. **Secure Drive Eraser** — wipes disk images and external/removable drives
   (the system drive is always blocked) using single-pass, NIST 800-88 Clear,
   or DoD 5220.22-M overwrite, with sampled read-back verification after each
   pass. Simulation mode is on by default.
2. **Secure File & Folder Eraser** — overwrite, rename to a random name, clear
   extended attributes, unlink; batch and folder support; filesystem-specific
   warnings (APFS/ReFS/Btrfs copy-on-write, NTFS MFT and shadow copies, ext4
   journal, FAT file names).
3. **File Carving & Recovery** — pytsk3 (filesystem-aware), PhotoRec
   (signature carving) and bulk_extractor (PII/metadata artifacts), with file
   type classification (signature table, libmagic, Magika), a 0–100
   confidence score, SHA-256 and fuzzy hashes, and cross-engine agreement.
4. **Audit & Reporting** — SHA-256 hash chain with per-entry HMAC tags and
   append-only database triggers, a chain verification button, PDF/JSON
   reports, and JSON certificates.

## Platform support

Runs on **Windows 10/11, Linux and macOS**, with the same look on all three:
the app draws its own theme, fonts, icons and file picker, so only the
window's title bar differs.

| | Windows | Linux | macOS |
|---|---|---|---|
| Erase disk images, recover deleted files | ✅ | ✅ | ✅ |
| System disk always blocked | ✅ | ✅ | ✅ |
| Erase or scan a **physical** drive | ⚠️ untested | ⚠️ untested | ⚠️ untested |
| Rights needed for a physical drive | Administrator | root (`sudo`) | root (`sudo`) |

## What we claim and don't

| ✅ Works (tested) | ⚠️ Works with caveats | ❌ Not done |
|---|---|---|
| Simulation-mode erase of disk images, verified — on Windows, Linux and macOS | Erase verification reads a **sample** of blocks (100% at 64 MB, 6% at 1 GB, 0.2% at 1 TB) | |
| | NIST 800-88 Purge (ATA Secure Erase / NVMe Sanitize) is implemented and executable, gated to external/removable drives and double-confirmed — but Linux-only (hdparm/nvme-cli), not available on macOS/Windows, and not yet tested against physical hardware | |
| System drive blocked from erasure (checked on real Windows, Linux and macOS machines) | Overwrite does **not** guarantee physical erasure on SSDs, flash, APFS or other copy-on-write filesystems | A recorded erase test on a physical drive, on any OS |
| File overwrite + rename + xattr clear + unlink | Audit HMAC key and certificate signing key load from the OS keystore (fallback: a private file) — not a PKI, and whoever can read that key can still forge a chain | Partition-table recovery (TestDisk not wired) |
| Deleted-file recovery, byte-exact, on FAT images (via pytsk3) | Tamper-*evident*, not tamper-*proof*: detects edits, can't prevent them | Trusted (RFC 3161) timestamping in the app flow |
| Hash-chain tamper detection | Certificate is Ed25519-signed but **not legally reviewed**; no CA binds the key to an identity | Recovery-rate measurement on a real forensic corpus |
| Automated tests pass on Windows, Linux and macOS | Confidence scores are uncalibrated heuristics | |
| | Independent post-erase recovery check runs automatically on real erases (PhotoRec/pytsk3 attempt recovery against the just-wiped target) — still same-machine software checking itself, a different code path/engine but not a third party | |
| | Bifragment gap carving exists (`reassembly.py`) but is called with `attempt_gap_carving=False` — built, not enabled | |
| | bulk_extractor untested (not installed on our dev machine or CI) | A test showing a deleted file carved *without* filesystem metadata |
| | Fuzzy hashes skipped for files > 4 MiB (pure-Python hashing is too slow) | Windows code signing / installer |

## Benchmarks (Apple M4, disk images on internal SSD)

Median of 3 runs, measured 2026-09-17 (macOS only):

| Operation | Result |
|---|---|
| NIST 800-88 Clear, 512 MB image (incl. verification) | 1.2 s (first run: 2.2 s — see docs) |
| DoD 5220.22-M, 512 MB image | 6.1 s (first run: 11.4 s) |
| File eraser, 100 × 64 KB files | 0.05 s (was 23.4 s before per-volume caching) |
| Recovery scan, 128 MB FAT image — pytsk3 | 0.02 s, deleted file recovered 3/3 |
| Recovery scan, 128 MB FAT image — PhotoRec | 0.28 s, deleted text file recovered **0/3** (no signature to carve) |

These measure software overhead on a fast internal SSD. A physical USB
drive will be limited by its own write speed. Full tables, methodology and
caveats: [docs/performance_evaluation.md](docs/performance_evaluation.md).

## Setup

You need Python 3.10–3.13 (3.12 recommended) and git.

### Windows

```powershell
git clone https://github.com/pushpam2404/SIH_149.git
cd SIH_149
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
```

The script creates `.venv` and installs the Python packages (pytsk3 comes
as a prebuilt package, no Sleuth Kit install needed). **Optional:** for
PhotoRec signature carving, download *TestDisk & PhotoRec* for Windows from
[cgsecurity.org](https://www.cgsecurity.org/wiki/TestDisk_Download), unzip
it, and add the folder containing `photorec_win.exe` to your PATH.

### Linux

```bash
git clone https://github.com/pushpam2404/SIH_149.git
cd SIH_149
./scripts/setup_env.sh            # testdisk (PhotoRec), libmagic, Qt runtime libs (apt or dnf)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### macOS

```bash
git clone https://github.com/pushpam2404/SIH_149.git
cd SIH_149
./scripts/setup_env.sh            # testdisk (PhotoRec), libmagic, sleuthkit via Homebrew
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run

| | Command |
|---|---|
| Windows | `.venv\Scripts\python.exe -m app.main` |
| Linux / macOS | `.venv/bin/python -m app.main` |

The audit log and reports are stored in `data/` and `reports/` inside the
project folder (a packaged build stores them in the user's app-data folder
instead). To scan or erase a **physical** drive, start the app from an
Administrator terminal (Windows) or with `sudo` (Linux/macOS); disk image
files need no special rights.

## See it working

Follow **[docs/walkthrough.md](docs/walkthrough.md)** — a step-by-step,
plain-English walkthrough of the whole app. You'll start it, tour every
page, then do the core demo yourself: securely erase one photo, delete
another the normal way, scan the disk, and see which one comes back.

- **macOS:** the full erase-vs-recover exercise on a throwaway disk image.
- **Windows / Linux:** a recovery demo with a practice image built from
  your own photo (no admin rights needed), and the full exercise on a spare
  USB stick.

Developers: how the code is tested, and what isn't, is in
[docs/validation_testing.md](docs/validation_testing.md).

## Safety notes

- Drive erasure defaults to **simulation mode**, which wipes a scratch copy of
  a disk image. Simulation mode cannot target a real device.
- Only disk images and drives the OS reports as external/removable can be
  selected. The system drive never can. **Any external drive can be**, so
  check the name and size before confirming.
- On Windows, erasing a physical drive takes that disk **offline** for the
  duration of the erase (Windows blocks raw writes to mounted volumes) and
  brings it back online afterwards.
- Firmware-level (NVMe/ATA) sanitize commands are generated as reference
  strings only and never executed.

## Documentation

- [Walkthrough](docs/walkthrough.md) — start here: run the app and see erase vs. recover in action
- [User manual](docs/user_manual.md)
- [Technical documentation](docs/technical_documentation.md) — architecture, per-component status, platform matrix
- [Validation & testing](docs/validation_testing.md) — what is and isn't tested
- [Performance evaluation](docs/performance_evaluation.md) — measured benchmarks
- [Compliance mapping](docs/compliance_mapping.md) — claims register

Bundled third-party assets: Fira Sans / Fira Code fonts (SIL Open Font
License, `app/gui/assets/fonts/OFL.txt`) and Lucide icons (ISC License,
`app/gui/assets/icons/LUCIDE_LICENSE.txt`).
