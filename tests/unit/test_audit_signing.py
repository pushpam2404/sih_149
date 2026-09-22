"""Tests for Ed25519 certificate signing (app/core/audit/signing.py).

Uses a fixed seed via keystore.get_or_create_secret monkeypatching so these
never touch the real OS keystore.
"""
import pytest

from app.core.audit.signing import CertificateSigner

cryptography = pytest.importorskip("cryptography")


@pytest.fixture()
def signer(monkeypatch):
    monkeypatch.setattr(
        "app.core.audit.signing.get_or_create_secret",
        lambda key_name, nbytes=32: b"\x01" * 32,
    )
    monkeypatch.setattr("app.core.audit.signing.used_keystore", lambda: True)
    return CertificateSigner()


def test_signer_is_available_with_cryptography_installed(signer):
    assert signer.available
    assert signer.key_backed_by_os_keystore is True


def test_sign_and_verify_roundtrip(signer):
    data = b"some certificate digest bytes"
    signature = signer.sign(data)
    pubkey = signer.public_key_b64()

    assert signature is not None
    assert pubkey is not None
    assert CertificateSigner.verify(pubkey, data, signature)


def test_verify_rejects_tampered_data(signer):
    data = b"some certificate digest bytes"
    signature = signer.sign(data)
    pubkey = signer.public_key_b64()

    assert not CertificateSigner.verify(pubkey, b"different data", signature)


def test_verify_rejects_wrong_public_key(signer):
    data = b"some certificate digest bytes"
    signature = signer.sign(data)

    # Give the "other" signer a different seed so its public key differs.
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "app.core.audit.signing.get_or_create_secret",
            lambda key_name, nbytes=32: b"\x02" * 32,
        )
        mp.setattr("app.core.audit.signing.used_keystore", lambda: True)
        other_signer = CertificateSigner()

    assert not CertificateSigner.verify(other_signer.public_key_b64(), data, signature)


def test_same_seed_produces_stable_public_key(monkeypatch):
    monkeypatch.setattr(
        "app.core.audit.signing.get_or_create_secret",
        lambda key_name, nbytes=32: b"\x03" * 32,
    )
    monkeypatch.setattr("app.core.audit.signing.used_keystore", lambda: True)

    first = CertificateSigner()
    second = CertificateSigner()

    assert first.public_key_b64() == second.public_key_b64()
