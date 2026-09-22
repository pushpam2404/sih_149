"""Ed25519 digital signatures for exported audit certificates.

The ledger's forward-secure HMAC (hmac_auth.py) is a shared-secret MAC:
verifying a tag requires the same key that produced it, so verification
only ever happens on this app, with this key. Ed25519 is asymmetric — the
private key stays in the OS keystore (via keystore.py) and never leaves
this machine, but the public key travels inside the certificate itself, so
anyone holding a certificate can verify it was not altered after signing
without needing this app, this machine, or any shared secret.

This does not prove *who* signed it (there is no certificate authority
binding the public key to an identity) or that the machine itself is
trustworthy — only that the certificate's content matches what the holder
of the private key that generated the embedded public key actually signed.
"""
from __future__ import annotations

import base64

from app.core.audit.keystore import get_or_create_secret, used_keystore

_KEY_NAME = "ed25519-signing-seed"


class CertificateSigner:
    """Loads (or creates) this machine's Ed25519 key from the OS keystore.

    Degrades gracefully if the `cryptography` package is missing: `available`
    is False and sign()/public_key_b64() return None, matching this
    project's convention for optional forensics dependencies.
    """

    def __init__(self):
        self._private_key = None
        self._available = False
        self._used_keystore: bool | None = None
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

            seed = get_or_create_secret(_KEY_NAME, nbytes=32)
            self._used_keystore = used_keystore()
            self._private_key = Ed25519PrivateKey.from_private_bytes(seed)
            self._available = True
        except ImportError:
            pass

    @property
    def available(self) -> bool:
        return self._available

    @property
    def key_backed_by_os_keystore(self) -> bool | None:
        """True if the signing key came from the OS keystore, False if from
        the file fallback, None if signing is unavailable entirely."""
        return self._used_keystore

    def public_key_b64(self) -> str | None:
        if not self._available:
            return None
        from cryptography.hazmat.primitives import serialization

        raw = self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.b64encode(raw).decode("ascii")

    def sign(self, data: bytes) -> str | None:
        if not self._available:
            return None
        return self._private_key.sign(data).hex()

    @staticmethod
    def verify(public_key_b64: str, data: bytes, signature_hex: str) -> bool:
        """Independent verification: needs only the public key, the data,
        and the signature — no OS keystore access, no shared secret."""
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        except ImportError:
            return False
        try:
            pub = Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64))
            pub.verify(bytes.fromhex(signature_hex), data)
            return True
        except (InvalidSignature, ValueError):
            return False
