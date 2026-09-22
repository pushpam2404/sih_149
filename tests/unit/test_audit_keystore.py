"""Tests for the OS-keystore-backed secret storage used by the audit ledger.

These force the file-fallback path deliberately (rather than touching the
real OS keychain/Credential Manager/Secret Service, which would make the
suite depend on this machine's keystore state and could hang waiting on an
interactive unlock prompt in CI).
"""
import builtins

import pytest

from app.core.audit import keystore


def _block_keyring_import(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "keyring" or name.startswith("keyring."):
            raise ImportError("keyring intentionally unavailable in this test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_falls_back_to_file_when_keystore_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.DATA_DIR", tmp_path)
    _block_keyring_import(monkeypatch)

    value = keystore.get_or_create_secret("some-key", nbytes=16)

    assert len(value) == 16
    assert keystore.used_keystore() is False


def test_fallback_secret_is_stable_across_calls(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.DATA_DIR", tmp_path)
    _block_keyring_import(monkeypatch)

    first = keystore.get_or_create_secret("stable-key")
    second = keystore.get_or_create_secret("stable-key")

    assert first == second


def test_fallback_file_is_not_world_readable(tmp_path, monkeypatch):
    import os
    import stat
    import sys

    if sys.platform == "win32":
        pytest.skip("POSIX permission bits don't apply on Windows")

    monkeypatch.setattr("app.config.settings.DATA_DIR", tmp_path)
    _block_keyring_import(monkeypatch)

    keystore.get_or_create_secret("perm-check-key")

    key_file = tmp_path / ".perm-check-key.key"
    assert key_file.exists()
    mode = stat.S_IMODE(os.stat(key_file).st_mode)
    assert mode == stat.S_IRUSR | stat.S_IWUSR


def test_different_key_names_get_different_secrets(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.DATA_DIR", tmp_path)
    _block_keyring_import(monkeypatch)

    a = keystore.get_or_create_secret("key-a")
    b = keystore.get_or_create_secret("key-b")

    assert a != b
