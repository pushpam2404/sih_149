"""Reproducible benchmarks for docs/performance_evaluation.md.

Usage: .venv/bin/python -m scripts.benchmark
All work happens in a temporary directory; nothing outside it is touched.
"""
from __future__ import annotations

import os
import platform
import shutil
import statistics
import tempfile
import time
from pathlib import Path

from app.config.constants import (
    STANDARD_DOD_5220_22_M,
    STANDARD_NIST_800_88_CLEAR,
    STANDARD_SINGLE_PASS_RANDOM,
    STANDARD_SINGLE_PASS_ZERO,
)
from app.core.audit.ledger import AuditLedger
from app.core.devices.enumerator import disk_image_info, get_backend
from app.core.erasure.drive_eraser import run_drive_erase
from app.core.erasure.file_eraser import erase_batch
from app.core.recovery.photorec_engine import PhotoRecEngine
from app.core.recovery.scan_service import run_recovery_scan
from app.core.recovery.tsk_engine import TskEngine
from tests.fixtures.fat_image import make_fat16_image_with_deleted_file
from tests.fixtures.make_test_image import make_fat_image_with_deleted_file

RUNS = 3
ERASE_SIZES_MB = [64, 512]
STANDARDS = [
    STANDARD_SINGLE_PASS_ZERO,
    STANDARD_SINGLE_PASS_RANDOM,
    STANDARD_NIST_800_88_CLEAR,
    STANDARD_DOD_5220_22_M,
]
RECOVERY_SIZES_MB = [32, 128]


def _timed(fn):
    start = time.perf_counter()
    result = fn()
    return time.perf_counter() - start, result


def bench_drive_erase(work: Path) -> None:
    print("\n## Drive erase (simulation mode, disk image on internal SSD)")
    print(f"median of {RUNS} runs; includes scratch-copy creation + passes + sampled verification\n")
    print("| Standard | Size | Median time | Min–max | Median throughput | Verified |")
    print("|---|---|---|---|---|---|")
    backend = get_backend()  # unused for disk images, but required by the signature
    for size_mb in ERASE_SIZES_MB:
        src = work / f"src_{size_mb}.img"
        with open(src, "wb") as f:
            f.truncate(size_mb * 1024 * 1024)
        info = disk_image_info(str(src))
        for std in STANDARDS:
            times, oks = [], []
            for i in range(RUNS):
                ledger = AuditLedger(work / f"audit_{std}_{size_mb}_{i}.sqlite3", hmac_key=b"benchmark-only-fixed-key")
                scratch = work / f"scratch_{std}_{size_mb}_{i}"
                elapsed, result = _timed(lambda: run_drive_erase(
                    info, backend, standard_id=std, ledger=ledger,
                    simulation_mode=True, user_confirmed=True,
                    simulation_scratch_dir=scratch,
                ))
                ledger.close()
                times.append(elapsed)
                oks.append(result.ok)
                if result.effective_target_path:
                    Path(result.effective_target_path).unlink(missing_ok=True)
            med = statistics.median(times)
            print(f"| {std} | {size_mb} MB | {med:.2f}s | {min(times):.2f}–{max(times):.2f}s "
                  f"| {size_mb / med:.0f} MB/s | {sum(oks)}/{RUNS} PASS |")
        src.unlink()


def bench_file_erase(work: Path) -> None:
    print("\n## File eraser (batch, 1 overwrite pass)\n")
    print("| Scenario | Median time | Min–max | All PASS |")
    print("|---|---|---|---|")
    for count, size_kb in [(100, 64), (10, 10 * 1024)]:
        times, oks = [], []
        for i in range(RUNS):
            folder = work / f"files_{count}_{size_kb}_{i}"
            folder.mkdir()
            paths = []
            for n in range(count):
                p = folder / f"f{n}.bin"
                p.write_bytes(os.urandom(size_kb * 1024))
                paths.append(str(p))
            ledger = AuditLedger(work / f"audit_files_{count}_{i}.sqlite3", hmac_key=b"benchmark-only-fixed-key")
            elapsed, batch = _timed(lambda: erase_batch(paths, ledger))
            ledger.close()
            times.append(elapsed)
            oks.append(batch.ok)
        med = statistics.median(times)
        label = f"{count} files × {size_kb // 1024} MB" if size_kb >= 1024 else f"{count} files × {size_kb} KB"
        print(f"| {label} | {med:.2f}s | {min(times):.2f}–{max(times):.2f}s | {all(oks)} |")


def bench_recovery(work: Path) -> None:
    # macOS: images formatted by the real FAT driver (hdiutil/diskutil), as in the
    # published numbers. Elsewhere: the pure-Python 16 MiB FAT16 fixture.
    native = shutil.which("hdiutil") is not None and shutil.which("diskutil") is not None
    fixture_kind = "hdiutil/diskutil FAT" if native else "pure-Python FAT16"
    print(f"\n## Recovery ({fixture_kind} image with one deleted text file)\n")
    print("| Image | Engine | Median time | Min–max | Candidates | Deleted file recovered byte-exact |")
    print("|---|---|---|---|---|---|")
    for size_mb in (RECOVERY_SIZES_MB if native else [16]):
        image_path = str(work / f"rec_{size_mb}.img")
        if native:
            fixture = make_fat_image_with_deleted_file(image_path, size_mb=size_mb)
        else:
            fixture = make_fat16_image_with_deleted_file(image_path)
        for engine_cls in (TskEngine, PhotoRecEngine):
            engine = engine_cls()
            if not engine.is_available():
                print(f"| {size_mb} MB | {engine.name} | unavailable | | | |")
                continue
            times, counts, hits = [], [], []
            for i in range(RUNS):
                ledger = AuditLedger(work / f"audit_rec_{engine.name}_{size_mb}_{i}.sqlite3", hmac_key=b"benchmark-only-fixed-key")
                out = work / f"out_{engine.name}_{size_mb}_{i}"
                elapsed, summary = _timed(lambda: run_recovery_scan(
                    fixture.image_path, str(out), ledger, engines=[engine]))
                ledger.close()
                times.append(elapsed)
                counts.append(len(summary.candidates))
                hits.append(any(
                    Path(c.recovered_path).is_file()
                    and Path(c.recovered_path).read_bytes() == fixture.deleted_file_original_content
                    for c in summary.candidates
                ))
            med = statistics.median(times)
            print(f"| {size_mb} MB | {engine.name} | {med:.2f}s | {min(times):.2f}–{max(times):.2f}s "
                  f"| {statistics.median(counts):.0f} | {sum(hits)}/{RUNS} |")


def main() -> None:
    print(f"Machine: {platform.machine()} {platform.platform()} / Python {platform.python_version()}")
    with tempfile.TemporaryDirectory(prefix="sih149_bench_") as tmp:
        work = Path(tmp)
        bench_drive_erase(work)
        bench_file_erase(work)
        bench_recovery(work)


if __name__ == "__main__":
    main()
