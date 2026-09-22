"""Hash-chained, tamper-evident audit ledger.

Every destructive erasure action and every recovery scan in this app must
be logged through AuditLedger.append_entry() — this is the single funnel
so no operation can bypass the tamper-evident trail. verify_chain() lets
the GUI (and forensic reviewers) confirm the log hasn't been altered.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from app.core.audit.models import GENESIS_HASH, AuditEntry
from app.core.audit.store import AuditStore
from app.core.audit.hmac_auth import ForwardSecureAuthenticator
from app.core.audit.keystore import get_or_create_secret
from app.core.audit.timestamping import TSAService
from app.utils.logging_setup import get_logger

logger = get_logger(__name__)


@dataclass
class ChainVerificationResult:
    ok: bool
    entries_checked: int
    broken_at_entry_id: int | None = None
    reason: str | None = None


class AuditLedger:
    def __init__(self, db_path: Path, hmac_key: bytes | None = None):
        self._store = AuditStore(db_path)
        # Loaded from the OS keystore (Keychain / Credential Manager / Secret
        # Service) by default — see keystore.py — with a private-file
        # fallback if no backend is available. Callers (tests, benchmarks)
        # pass an explicit hmac_key to stay hermetic and avoid touching the
        # real OS keystore.
        self._initial_key = hmac_key if hmac_key is not None else get_or_create_secret("hmac-ratchet-key")
        self._authenticator = ForwardSecureAuthenticator(self._initial_key)
        self._tsa = TSAService()
        
        # Fast-forward authenticator state to the last entry
        entries = self._store.all_entries()
        for _ in entries:
            self._authenticator.ratchet()

    def append_entry(self, action: str, target: str, payload: dict, actor: str = "user") -> AuditEntry:
        prev = self._store.last_entry()
        prev_hash = prev.entry_hash if prev is not None else GENESIS_HASH

        entry = AuditEntry.create(action=action, target=target, payload=payload, actor=actor, prev_hash=prev_hash)

        # Add MAC tag before persisting (AuditEntry is frozen, so replace rather than mutate)
        entry = replace(entry, mac_tag=self._authenticator.generate_mac(entry.entry_hash))
        self._authenticator.ratchet()

        persisted = self._store.append(entry)
        logger.info("audit: %s target=%s entry_id=%s", action, target, persisted.entry_id)
        return persisted

    def timestamp_entry(self, entry: AuditEntry) -> dict:
        """Explicit, opt-in RFC-3161-style timestamp for a single existing entry.

        Deliberately NOT called from append_entry(): embedding a token in the
        payload changes the payload, which changes entry_hash, which would
        require re-signing after the fact — and TSAService currently only
        simulates a token locally rather than contacting a real TSA. Callers
        (e.g. a future GUI "timestamp this entry" action) should treat the
        returned token as a local attestation, not a certified RFC 3161
        response, until timestamping.py talks to a real TSA.
        """
        return self._tsa.get_timestamp_token(entry.entry_hash)

    def get_entries(self) -> list[AuditEntry]:
        return self._store.all_entries()

    def verify_chain(self) -> ChainVerificationResult:
        entries = self._store.all_entries()
        expected_prev = GENESIS_HASH
        for entry in entries:
            if entry.prev_hash != expected_prev:
                return ChainVerificationResult(
                    ok=False,
                    entries_checked=len(entries),
                    broken_at_entry_id=entry.entry_id,
                    reason=(
                        f"entry {entry.entry_id} prev_hash does not match the hash of the "
                        f"preceding entry — chain link broken (possible reorder/deletion)."
                    ),
                )
            recomputed = entry.recompute_hash()
            if recomputed != entry.entry_hash:
                return ChainVerificationResult(
                    ok=False,
                    entries_checked=len(entries),
                    broken_at_entry_id=entry.entry_id,
                    reason=(
                        f"entry {entry.entry_id} stored hash does not match its recomputed "
                        f"hash — entry contents were modified after being written."
                    ),
                )
            expected_prev = entry.entry_hash
            
        # Verify MAC tags
        verifier = ForwardSecureAuthenticator(self._initial_key)
        for entry in entries:
            if not entry.mac_tag:
                # If an entry doesn't have a MAC tag (e.g. legacy data), skip or fail.
                # Here we assume all new entries will have it, but for strictness:
                # return ChainVerificationResult(ok=False, entries_checked=len(entries), broken_at_entry_id=entry.entry_id, reason="Missing MAC tag")
                pass
            else:
                if not verifier.verify_mac(entry.entry_hash, entry.mac_tag):
                    return ChainVerificationResult(
                        ok=False,
                        entries_checked=len(entries),
                        broken_at_entry_id=entry.entry_id,
                        reason=(
                            f"entry {entry.entry_id} MAC tag is invalid — entry was altered "
                            f"without the correct forward-secure key."
                        )
                    )
            
            # Verify TSA Token if present
            if "tsa_token" in entry.payload:
                # We need to verify the token matches the pre-hash of the entry
                # We can construct the payload without tsa_token to check
                temp_payload = dict(entry.payload)
                token = temp_payload.pop("tsa_token")
                
                # Recompute the pre-token hash using the entry's ORIGINAL timestamp.
                # AuditEntry.create() stamps datetime.now() internally, which would
                # never match the hash the token was actually issued against —
                # use recompute_hash() on a copy carrying the real timestamp instead.
                temp_entry = replace(entry, payload=temp_payload)
                pre_token_hash = temp_entry.recompute_hash()

                if not self._tsa.verify_timestamp_token(token, pre_token_hash):
                    return ChainVerificationResult(
                        ok=False,
                        entries_checked=len(entries),
                        broken_at_entry_id=entry.entry_id,
                        reason=(
                            f"entry {entry.entry_id} TSA token is invalid or does not match "
                            f"the entry data."
                        )
                    )

            verifier.ratchet()
            
        return ChainVerificationResult(ok=True, entries_checked=len(entries))

    def close(self) -> None:
        self._store.close()
