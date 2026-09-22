"""Tests for CertificateGenerator's Ed25519 signing of exported certificates."""
import json

import pytest

from app.core.audit.certificate import CertificateGenerator
from app.core.audit.ledger import AuditLedger
from app.core.audit.signing import CertificateSigner

cryptography = pytest.importorskip("cryptography")

_TEST_KEY = b"test-only-fixed-key-not-for-production"


@pytest.fixture()
def signer(monkeypatch):
    monkeypatch.setattr(
        "app.core.audit.signing.get_or_create_secret",
        lambda key_name, nbytes=32: b"\x09" * 32,
    )
    monkeypatch.setattr("app.core.audit.signing.used_keystore", lambda: True)
    return CertificateSigner()


def test_generated_certificate_is_signed_and_verifiable(tmp_path, signer):
    ledger = AuditLedger(tmp_path / "audit.sqlite3", hmac_key=_TEST_KEY)
    erase_entry = ledger.append_entry("drive_erase", "diskA", {"standard": "nist_800_88_clear", "result": "success"})
    ledger.append_entry(
        "post_erase_verification",
        "diskA",
        {
            "candidates_found": 0,
            "engines_used": ["test_engine"],
            "erase_entry_id": erase_entry.entry_id,
        }
    )
    ledger.close()

    ledger = AuditLedger(tmp_path / "audit.sqlite3", hmac_key=_TEST_KEY)
    out_path = tmp_path / "cert.json"
    generator = CertificateGenerator(ledger, "Operator One", "Test Lab", signer=signer)
    cert = generator.generate_json_certificate("diskA", "Clear - overwrite verified", out_path)

    assert cert["signature_ed25519"] is not None
    assert cert["public_key_ed25519"] is not None
    assert CertificateSigner.verify(
        cert["public_key_ed25519"], cert["integrity_digest"].encode("ascii"), cert["signature_ed25519"]
    )

    on_disk = json.loads(out_path.read_text())
    assert on_disk == cert
    
    trail = cert["certificate"]["audit_trail"]
    assert len(trail) == 2
    assert trail[1]["action"] == "post_erase_verification"
    assert trail[1]["candidates_found"] == 0
    assert trail[1]["engines_used"] == ["test_engine"]
    assert trail[1]["erase_entry_id"] == 1  # 1 because it is the first entry in this test database
    assert isinstance(trail[1]["erase_entry_id"], int)

    limitations = " ".join(cert["certificate"]["limitations"])
    assert "not a digital signature" not in limitations
    assert "Ed25519" in limitations


def test_tampered_certificate_fails_signature_verification(tmp_path, signer):
    ledger = AuditLedger(tmp_path / "audit.sqlite3", hmac_key=_TEST_KEY)
    ledger.append_entry("drive_erase", "diskA", {"standard": "nist_800_88_clear", "result": "success"})
    out_path = tmp_path / "cert.json"
    generator = CertificateGenerator(ledger, "Operator One", "Test Lab", signer=signer)
    cert = generator.generate_json_certificate("diskA", "Clear - overwrite verified", out_path)
    ledger.close()

    tampered_digest = "0" * len(cert["integrity_digest"])
    assert not CertificateSigner.verify(
        cert["public_key_ed25519"], tampered_digest.encode("ascii"), cert["signature_ed25519"]
    )
