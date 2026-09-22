"""Persistent, OS-keystore-backed secret storage for the audit ledger.

Secrets (the HMAC ratchet key, the Ed25519 signing seed) are generated once
per machine/user and stored in the platform's native credential store via
`keyring` — macOS Keychain, Windows Credential Manager, or a Linux Secret
Service provider. This replaces a fixed value baked into source: anyone
with the source code no longer has the key, only whoever can unlock this
machine's keystore does.

If no keystore backend is available (e.g. a headless Linux box with no
D-Bus/Secret Service session — common on CI runners), this falls back to a
private, mode-0600 file under the app's data directory. That fallback is
still a per-machine generated secret, not a hardcoded one, but it is not
OS-keystore-protected — callers should not claim keystore-backed security
without checking `used_keystore()`.
"""
from __future__ import annotations

import base64
import os
import secrets
import stat
from pathlib import Path

from app.utils.logging_setup import get_logger

logger = get_logger(__name__)

_SERVICE_NAME = "SIH149-SecureEraseRecovery"

# Set by get_or_create_secret() to record which backend served the most
# recent call — surfaced via used_keystore() so callers (and docs/certs)
# can state plainly whether the key is OS-keystore-protected.
_last_used_keystore: bool | None = None


def used_keystore() -> bool | None:
    """Whether the most recent get_or_create_secret() call used the OS
    keystore (True) or the file fallback (False). None if never called."""
    return _last_used_keystore


def _fallback_path(key_name: str) -> Path:
    from app.config.settings import DATA_DIR

    return DATA_DIR / f".{key_name}.key"


def _read_fallback_file(path: Path) -> bytes | None:
    if not path.exists():
        return None
    return base64.b64decode(path.read_text().strip())


def _write_fallback_file(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(base64.b64encode(value).decode("ascii"))
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass  # best-effort — some filesystems/platforms don't support POSIX bits


def get_or_create_secret(key_name: str, nbytes: int = 32) -> bytes:
    """Returns a stable per-machine/per-user secret, generating it on first use.

    Tries the OS keystore first; falls back to a private file if no backend
    is available. Never falls back to a fixed value.
    """
    global _last_used_keystore
    try:
        import keyring
        import keyring.errors  # noqa: F401  (imported to fail fast if backend is broken)

        existing = keyring.get_password(_SERVICE_NAME, key_name)
        if existing:
            _last_used_keystore = True
            return base64.b64decode(existing)
        value = secrets.token_bytes(nbytes)
        keyring.set_password(_SERVICE_NAME, key_name, base64.b64encode(value).decode("ascii"))
        _last_used_keystore = True
        return value
    except Exception as exc:  # ImportError, NoKeyringError, or a locked/unavailable backend
        logger.warning(
            "OS keystore unavailable for '%s' (%s) — falling back to a per-user key file. "
            "Still a per-machine generated secret, not a hardcoded one, but not "
            "OS-keystore-protected until a backend is available.",
            key_name, exc,
        )
        _last_used_keystore = False
        path = _fallback_path(key_name)
        existing = _read_fallback_file(path)
        if existing is not None:
            return existing
        value = secrets.token_bytes(nbytes)
        _write_fallback_file(path, value)
        return value
