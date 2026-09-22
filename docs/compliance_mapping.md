# Compliance Mapping & Claims Register

This document states plainly what this tool does and does not claim. It
exists so the gap between "a standard's procedure is implemented" and
"certified compliant" is never ambiguous to a user, judge, or auditor.

**Ground rules we hold ourselves to:**
- We say "implements the procedure of X", never "certified/compliant with X",
  unless an accredited body has certified it. None has.
- Every limitation below is also stated in the reports and certificates the
  tool generates, not only in this document.
- If a feature is simulated, unwired, or untested, we say so.

## Claims Register

| We claim | We do NOT claim |
|---|---|
| Overwrite procedures of NIST SP 800-88 Rev.1 **Clear** and DoD 5220.22-M (3-pass) are implemented and verified by sampled read-back | NIST 800-88 **Purge** or **Destroy**; IEEE 2883 sanitization; any certification |
| Overwrites every *logical* sector of the target | Physical destruction of data on SSDs, flash, or copy-on-write filesystems |
| File eraser overwrites content, renames to a random name, clears extended attributes, then unlinks | Removal of every trace: journal entries, snapshots, filesystem free-space remnants, backups, cloud copies |
| The audit log is hash-chained; `verify_chain()` detects modified, deleted, or reordered entries | That tampering is *impossible* — someone who can rewrite the whole database and knows the MAC key can rebuild a valid chain |
| Recovered files are SHA-256 hashed at recovery time | Formal forensic certification (ISO/IEC 27037, NIST CFTT), write-blocker enforcement |
| Certificates are *structured after* the BSA 2023 Section 63 certificate | Legal admissibility, legal review, or a digital signature |
| Confidence score ranks candidates within one scan | That the score is a calibrated probability |

## NIST SP 800-88 Rev.1

| Level | Status | Notes |
|---|---|---|
| **Clear** | Procedure implemented | `app/core/erasure/standards/nist_800_88.py` — one overwrite pass, verified by random sampled read-back (`app/core/erasure/verifier.py`). Verification samples 1% of blocks (min 16, max 512), **not** every block. |
| **Purge** | Implemented on Linux for external/removable drives, gated behind explicit double-confirmation; ATA path via `hdparm` two-step Security Erase, NVMe path via `nvme sanitize` + Sanitize Log polling; **not validated against physical hardware as of 2026-09-22**; not available on macOS/Windows (no safe firmware-execution path exists there). | Needs drive-native commands (ATA Secure Erase/Sanitize, NVMe Format/Sanitize). |
| **Destroy** | Not implemented | Physical destruction is outside any software tool's scope. |

## DoD 5220.22-M

Implemented as the classic 3-pass overwrite (0x00, 0xFF, random) in
`app/core/erasure/standards/dod_522022m.py`, with verification after each
pass. DoD 5220.22-M predates flash storage, and the DoD itself no longer
references it as a sanitization method; we include it because many
procurement checklists still ask for it. It is a Clear-equivalent
software overwrite with the same SSD caveat below.

## The SSD / Wear-Leveling Caveat (applies to every overwrite standard)

On an SSD, the flash translation layer (FTL) remaps logical sectors to
physical NAND cells. An OS-level overwrite may land on a *different*
physical cell than the one holding the original data, leaving the original
physically intact and potentially recoverable via chip-off or direct NAND
access. Over-provisioned and retired blocks are never reachable by an
OS-level write at all. This is a property of all overwrite-based wiping on
flash, not a bug specific to this tool.

**This tool does not claim physical-media-level destruction on SSDs,
USB flash drives, or memory cards.** Reports should be read as "logical
erasure with verified overwrite."

TRIM: after a file erase the tool attempts a best-effort `fstrim` on
Linux (needs root). On macOS it does nothing (no safe per-volume TRIM
trigger is available from user space), and on Windows it is not attempted
(NTFS sends TRIM for freed clusters on its own schedule).

## Secure File & Folder Eraser

The SSD caveat applies, and more strongly: copy-on-write filesystems
(APFS, Btrfs, ZFS) write an "overwrite" to new blocks by design, and APFS
local snapshots or Time Machine may retain earlier versions. The tool
detects the filesystem and shows specific warnings (APFS copy-on-write,
NTFS small files resident in the MFT, ext3/ext4 journaling) in the GUI and
the audit entry. Windows adds NTFS Volume Shadow Copy / alternate data
stream warnings, ReFS is treated as copy-on-write, and FAT/exFAT volumes
get a warning that most of the original file name stays recoverable from
the deleted directory entry (seen in our own recovery tests). It **warns only** — it never deletes snapshots or edits
the MFT/journal. Every file-erasure report states that the overwrite is
**best-effort logical erasure**.

Not cleared: filesystem journal entries, directory-entry slack, the
original file name in journal records, macOS Spotlight/QuickLook caches,
backups, and copies in other locations.

## Tamper-Evident Audit Ledger

| Mechanism | What it actually provides | Limitation |
|---|---|---|
| SHA-256 hash chain (`prev_hash` → `entry_hash`) | Detects edited, deleted, or reordered entries | An attacker who rewrites *every* entry from the tampered point onward can produce a self-consistent chain |
| Forward-secure HMAC tag per entry (key ratchets after each entry) | Makes the full-rewrite attack above require the key | The key now comes from the OS keystore (macOS Keychain / Windows Credential Manager / Linux Secret Service) via `keystore.py`, generated on first use and never present in source. If no keystore backend is available (e.g. headless Linux with no Secret Service session) it falls back to a private, mode-0600 file under the app's data directory instead — still per-machine generated, but not OS-keystore-protected in that case. Either way, whoever can read that key (from the keystore or the fallback file) can still forge a self-consistent chain — this raises the bar from "anyone with the source code" to "someone with access to this machine's keystore or its data directory," not to zero-trust. |
| SQLite triggers blocking `UPDATE`/`DELETE` | Stops accidental edits and edits made through ordinary SQL | Anyone with file access can drop the triggers or edit the file directly. The chain check is the real defense, and it only *detects* tampering after the fact. |
| Trusted timestamping (`timestamping.py`) | **Not active.** Code exists to request an RFC 3161 token from a public TSA, but nothing in the app calls it | Timestamps in the log come from the local system clock and can be wrong or altered |

"Blockchain & Cybersecurity" theme: this is a single-machine hash chain,
the core data structure a blockchain uses. There is no distributed
ledger, consensus, or external anchoring.

### Independent Post-Erase Verification

Automatic on real erases, this mechanism logs an `ACTION_POST_ERASE_VERIFICATION` entry linked to the erase entry via `erase_entry_id`, surfaced in the certificate's `audit_trail`. This raises confidence the wipe worked, but it does not make the claim independently verified by a third party.

## Certificates (BSA 2023 Section 63-style)

The Audit Log page generates a JSON certificate for a chosen target. It
contains operator/organization details, the target's audit entries with
their hashes, whether the audit chain verified at issue time, and an
embedded `limitations` list.

- It is **structured after** the Section 63 certificate. It has not been
  reviewed by a lawyer, and generating it does not make evidence admissible.
- The operator types the wipe status. The tool does not derive it
  automatically, but the underlying audit entries (with PASS/FAIL and the
  standard used) are included so a reviewer can check it.
- `integrity_digest` (a SHA-384 digest of the certificate) is now signed
  with **Ed25519** (`signature_ed25519`, `public_key_ed25519` — see
  `signing.py`). The private key lives in the OS keystore (same mechanism
  as the ledger's HMAC key above) and never leaves this machine; the
  public key travels inside the certificate, so a reviewer can verify the
  certificate was not altered after signing with no access to this app,
  this machine, or any shared secret. This is **not PKI**: there is no
  certificate authority binding that public key to an operator's or
  organization's identity — it proves integrity since signing, not who
  signed it. If the `cryptography` package is unavailable at generation
  time, the certificate falls back to the old unsigned SHA-384 digest and
  says so explicitly in its own `limitations` list and `signature_algorithm`
  field.

## Advanced File Carving and Recovery — Evidentiary Integrity

- Recovery engines only **read** the source. They do not enforce read-only
  access at the OS level, though — use a hardware write-blocker or a
  read-only image for real evidence.
- Every candidate is SHA-256 hashed when recovered, and reports carry a
  "do not modify" notice.
- The tool has **not** been validated against ISO/IEC 27037 or NIST CFTT.
  Those require process controls (write-blockers, custody procedures,
  examiner qualification) beyond a software tool.

## Summary Against the Problem Statement

| Requirement | Status |
|---|---|
| Compliance with data destruction standards | **Partial** — Clear-level overwrite procedures implemented; Purge implemented for external drives on Linux; nothing certified |
| Tamper-resistant reporting | **Implemented as tamper-evident** (detects, does not prevent); HMAC key and certificate signing key now come from the OS keystore, not a hardcoded literal — see the ledger table above for what that does and doesn't change |
| Preserving evidential integrity | **Partial** — hashing and read-only access by convention; no enforced write-blocking, not certified |
| Compliance with forensic standards | **Not claimed** |
| Cross-platform (Windows, Linux, macOS) | **Partial** — the test suite and a real-machine self-check pass on all three in CI; physical-drive erase and USB detection on real hardware have not been tested on any of them |
