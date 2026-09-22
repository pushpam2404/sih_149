"""Recovery orchestration: run engines -> hash + classify + score each
candidate -> cross-engine agreement -> audit log.

Cross-engine agreement is detected by comparing SHA-256 hashes of
recovered bytes across engines — if pytsk3 and PhotoRec each
independently recovered the same content, that's a strong signal the
recovery is genuine, regardless of what each engine named the file.
"""
from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

try:
    import ppdeep
    _PPDEEP_AVAILABLE = True
except ImportError:
    _PPDEEP_AVAILABLE = False

from app.config.constants import ACTION_RECOVERY_SCAN
from app.core.audit.ledger import AuditLedger
from app.core.recovery.classifier import classify
from app.core.recovery.confidence import score_candidate
from app.core.recovery.engine_base import RecoveredFileCandidate, RecoveryEngine
from app.core.recovery.photorec_engine import PhotoRecEngine
from app.core.recovery.tsk_engine import TskEngine
from app.core.recovery.bulk_extractor_engine import BulkExtractorEngine
from app.utils.logging_setup import get_logger

logger = get_logger(__name__)

ProgressCallback = Callable[[str], None]  # (status message)

_FUZZY_HASH_MAX_BYTES = 4 * 1024 * 1024


@dataclass
class ScanSummary:
    source_path: str
    candidates: list[RecoveredFileCandidate]
    engines_used: list[str]
    engines_unavailable: list[str]


def _default_engines() -> list[RecoveryEngine]:
    return [TskEngine(), PhotoRecEngine(), BulkExtractorEngine()]


def _hash_file(path: str) -> tuple[str | None, str | None]:
    """Returns (sha256, fuzzy_hash)."""
    sha256_hash = None
    fuzzy_hash = None
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        sha256_hash = h.hexdigest()
    except OSError:
        pass
        
    # ppdeep is pure Python (~minutes per 30 MB); larger files would stall the scan.
    if _PPDEEP_AVAILABLE:
        try:
            if os.path.getsize(path) <= _FUZZY_HASH_MAX_BYTES:
                fuzzy_hash = ppdeep.hash_from_file(path)
        except Exception as exc:
            logger.debug("ppdeep failed: %s", exc)
            
    return sha256_hash, fuzzy_hash


def run_recovery_scan(
    source_path: str,
    output_dir: str,
    ledger: AuditLedger,
    engines: list[RecoveryEngine] | None = None,
    progress_cb: ProgressCallback | None = None,
    target_label: str | None = None,
) -> ScanSummary:
    engines = engines if engines is not None else _default_engines()
    engines_used, engines_unavailable = [], []
    all_candidates: list[RecoveredFileCandidate] = []

    for engine in engines:
        if not engine.is_available():
            engines_unavailable.append(engine.name)
            continue
        if progress_cb:
            progress_cb(f"scanning with {engine.name}...")
        try:
            found = engine.scan(source_path, output_dir)
        except Exception as exc:  # noqa: BLE001 - a broken engine shouldn't kill the whole scan
            logger.error("engine %s failed: %s", engine.name, exc)
            found = []
        engines_used.append(engine.name)
        all_candidates.extend(found)

    if progress_cb:
        progress_cb("hashing and classifying recovered candidates...")

    hashes_by_value: dict[str, list[RecoveredFileCandidate]] = defaultdict(list)
    classifications = []
    for candidate in all_candidates:
        sha256_val, fuzzy_val = _hash_file(candidate.recovered_path)
        candidate.sha256 = sha256_val
        candidate.fuzzy_hash = fuzzy_val
        
        classification = classify(candidate.recovered_path, candidate.suggested_name)
        classifications.append(classification)
        candidate.file_type = classification.file_type
        candidate.confidence_reasons = list(classification.reasons)
        if candidate.sha256:
            hashes_by_value[candidate.sha256].append(candidate)

    for candidate, classification in zip(all_candidates, classifications):
        cross_engine = False
        if candidate.sha256:
            siblings = hashes_by_value[candidate.sha256]
            cross_engine = len({c.source_engine for c in siblings}) > 1
        score, score_reasons = score_candidate(classification, candidate, cross_engine_agreement=cross_engine)
        candidate.confidence_score = score
        candidate.confidence_reasons.extend(score_reasons)

    ledger.append_entry(
        action=ACTION_RECOVERY_SCAN,
        target=target_label or source_path,
        payload={
            "engines_used": engines_used,
            "engines_unavailable": engines_unavailable,
            "candidates_found": len(all_candidates),
            "candidates": [
                {
                    "suggested_name": c.suggested_name,
                    "source_engine": c.source_engine,
                    "file_type": c.file_type,
                    "size_bytes": c.size_bytes,
                    "sha256": c.sha256,
                    "fuzzy_hash": c.fuzzy_hash,
                    "confidence_score": c.confidence_score,
                    "is_fragmented": c.is_fragmented,
                }
                for c in all_candidates
            ],
        },
    )

    return ScanSummary(
        source_path=source_path,
        candidates=all_candidates,
        engines_used=engines_used,
        engines_unavailable=engines_unavailable,
    )
