import json
import sqlite3

import pytest

from app.core.audit.ledger import AuditLedger

# Fixed test-only key: keeps these tests hermetic and avoids touching the
# real OS keystore (which AuditLedger uses by default — see keystore.py).
_TEST_KEY = b"test-only-fixed-key-not-for-production"


@pytest.fixture()
def ledger(tmp_path):
    led = AuditLedger(tmp_path / "audit.sqlite3", hmac_key=_TEST_KEY)
    yield led
    led.close()


def test_empty_chain_is_valid(ledger):
    result = ledger.verify_chain()
    assert result.ok
    assert result.entries_checked == 0


def test_appended_entries_form_a_valid_chain(ledger):
    ledger.append_entry("file_erase", "/tmp/a.txt", {"standard": "single_pass_zero"})
    ledger.append_entry("file_erase", "/tmp/b.txt", {"standard": "single_pass_zero"})
    ledger.append_entry("recovery_scan", "image.img", {"candidates_found": 3})

    entries = ledger.get_entries()
    assert len(entries) == 3
    assert entries[0].prev_hash == "0" * 64
    assert entries[1].prev_hash == entries[0].entry_hash
    assert entries[2].prev_hash == entries[1].entry_hash

    result = ledger.verify_chain()
    assert result.ok
    assert result.entries_checked == 3


def test_tampering_with_a_past_entry_is_detected(ledger, tmp_path):
    ledger.append_entry("file_erase", "/tmp/a.txt", {"standard": "single_pass_zero"})
    ledger.append_entry("file_erase", "/tmp/b.txt", {"standard": "single_pass_zero"})
    ledger.close()

    db_path = tmp_path / "audit.sqlite3"
    conn = sqlite3.connect(str(db_path))
    # The append-only triggers block UPDATE through normal SQL (see
    # docs/BACKLOG_PLATFORM_QUALITY.md item P4) — drop them here to simulate
    # an attacker with direct file-level access bypassing that app-level
    # control, which is the documented limitation verify_chain() still has
    # to catch via the hash chain itself.
    conn.execute("DROP TRIGGER IF EXISTS prevent_audit_update")
    conn.execute(
        "UPDATE audit_entries SET payload = ? WHERE entry_id = 1",
        (json.dumps({"standard": "TAMPERED"}),),
    )
    conn.commit()
    conn.close()

    reopened = AuditLedger(db_path, hmac_key=_TEST_KEY)
    result = reopened.verify_chain()
    reopened.close()

    assert not result.ok
    assert result.broken_at_entry_id == 1
    assert "modified" in result.reason


def test_ledger_created_before_mac_tags_still_opens_and_verifies(tmp_path):
    db_path = tmp_path / "old_audit.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE audit_entries (entry_id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL, "
        "actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL, payload TEXT NOT NULL, "
        "prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()

    ledger = AuditLedger(db_path, hmac_key=_TEST_KEY)
    ledger.append_entry("file_erase", "/tmp/a.txt", {"standard": "single_pass_zero"})
    result = ledger.verify_chain()
    ledger.close()

    assert result.ok
    assert result.entries_checked == 1


def test_default_hmac_key_is_loaded_from_keystore_not_hardcoded(tmp_path, monkeypatch):
    """Regression test for the previously-hardcoded HMAC key: with no explicit
    hmac_key, AuditLedger must ask keystore.get_or_create_secret() for it
    rather than falling back to a fixed literal baked into ledger.py."""
    calls = []

    def fake_get_or_create_secret(key_name, nbytes=32):
        calls.append((key_name, nbytes))
        return b"secret-from-keystore-not-a-literal-in-source"

    monkeypatch.setattr("app.core.audit.ledger.get_or_create_secret", fake_get_or_create_secret)

    led = AuditLedger(tmp_path / "audit.sqlite3")
    try:
        assert calls == [("hmac-ratchet-key", 32)]
        assert led._initial_key == b"secret-from-keystore-not-a-literal-in-source"
    finally:
        led.close()
