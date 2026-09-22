import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from app.core.audit.ledger import AuditLedger
from app.core.audit.signing import CertificateSigner

_BASE_LIMITATIONS = [
    "Structure is modelled on the BSA 2023 Section 63 certificate (custodian + "
    "audit trail); it has not been reviewed by a legal professional and is not "
    "by itself admissible evidence.",
    "Erasure is software overwrite (NIST SP 800-88 Clear level at most). No "
    "Purge-level or firmware sanitize command (ATA/NVMe, IEEE 2883) was executed.",
    "On SSDs and copy-on-write filesystems, overwrite does not guarantee the "
    "original physical blocks were destroyed.",
]

_UNSIGNED_LIMITATION = (
    "integrity_digest is an unkeyed SHA-384 digest: it detects accidental or "
    "naive edits, but anyone can recompute it. It is not a digital signature "
    "('cryptography' package was not available when this certificate was generated)."
)

_SIGNED_NO_KEYSTORE_LIMITATION = (
    "integrity_digest is signed with Ed25519 (signature_ed25519), verifiable "
    "with the embedded public_key_ed25519 and no access to this machine. The "
    "private key came from a private key file, not the OS keystore, on the "
    "machine that generated this certificate — see keystore.py."
)

_SIGNED_LIMITATION = (
    "integrity_digest is signed with Ed25519 (signature_ed25519), verifiable "
    "with the embedded public_key_ed25519 and no access to this machine or its "
    "OS keystore. This proves the certificate was not altered after signing and "
    "that it came from whoever holds this machine's keystore-protected private "
    "key — it does not certify that machine's or that operator's identity; "
    "there is no certificate authority binding the public key to a person."
)


class CertificateGenerator:
    """Generates a JSON erasure/recovery certificate, structured after BSA Section 63."""

    def __init__(self, ledger: AuditLedger, operator_name: str, org_name: str, signer: CertificateSigner | None = None):
        self.ledger = ledger
        self.operator_name = operator_name
        self.org_name = org_name
        self._signer = signer if signer is not None else CertificateSigner()

    def generate_json_certificate(self, target_device: str, wipe_status: str, out_path: Path) -> dict:
        entries = self.ledger.get_entries()
        device_entries = [e for e in entries if e.target == target_device]
        chain = self.ledger.verify_chain()

        cert_data = {
            "certificate_id": f"CERT-{hashlib.sha256(datetime.now().isoformat().encode()).hexdigest()[:12].upper()}",
            "issue_date": datetime.now(timezone.utc).isoformat(),
            "format": "Modelled on BSA 2023 Section 63 certificate structure (not legally reviewed)",
            "operator": {
                "name": self.operator_name,
                "organization": self.org_name
            },
            "device": {
                "target": target_device,
                "status_as_entered_by_operator": wipe_status
            },
            "audit_chain_verified_at_issue": chain.ok,
            "audit_trail": [
                {
                    "action": e.action,
                    "timestamp": e.timestamp,
                    "entry_hash": e.entry_hash,
                    "result": e.payload.get("result"),
                    "standard": e.payload.get("standard"),
                    "candidates_found": e.payload.get("candidates_found"),
                    "engines_used": e.payload.get("engines_used"),
                    "erase_entry_id": e.payload.get("erase_entry_id"),
                }
                for e in device_entries
            ],
        }

        if not self._signer.available:
            cert_data["limitations"] = _BASE_LIMITATIONS + [_UNSIGNED_LIMITATION]
        elif self._signer.key_backed_by_os_keystore:
            cert_data["limitations"] = _BASE_LIMITATIONS + [_SIGNED_LIMITATION]
        else:
            cert_data["limitations"] = _BASE_LIMITATIONS + [_SIGNED_NO_KEYSTORE_LIMITATION]

        cert_json = json.dumps(cert_data, sort_keys=True)
        digest = hashlib.sha384(cert_json.encode("utf-8")).hexdigest()
        signature = self._signer.sign(digest.encode("ascii"))

        final_cert = {
            "certificate": cert_data,
            "integrity_digest": digest,
            "integrity_digest_algorithm": "SHA-384 over sorted certificate JSON",
            "signature_ed25519": signature,
            "public_key_ed25519": self._signer.public_key_b64(),
            "signature_algorithm": (
                "Ed25519 over integrity_digest, verifiable offline with public_key_ed25519"
                if signature is not None
                else "UNSIGNED — 'cryptography' package was not available at generation time"
            ),
        }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(final_cert, f, indent=4)

        return final_cert
