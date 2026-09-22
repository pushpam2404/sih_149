import os

import pytest

from app.core.audit.ledger import AuditLedger
from app.core.erasure.file_eraser import erase_batch, erase_file, erase_folder


@pytest.fixture()
def ledger(tmp_path):
    led = AuditLedger(tmp_path / "audit.sqlite3", hmac_key=b"test-only-fixed-key-not-for-production")
    yield led
    led.close()


def test_erase_file_removes_it_and_logs(tmp_path, ledger):
    target = tmp_path / "secret.txt"
    target.write_text("sensitive content")

    result = erase_file(str(target), ledger)

    assert result.ok
    assert not target.exists()
    entries = ledger.get_entries()
    assert len(entries) == 1
    assert entries[0].action == "file_erase"
    assert entries[0].payload["ok"] is True


def test_erase_file_missing_target_fails_cleanly(tmp_path, ledger):
    missing = tmp_path / "does_not_exist.txt"
    result = erase_file(str(missing), ledger)
    assert not result.ok
    assert result.error is not None


def test_erase_batch_processes_all_files(tmp_path, ledger):
    paths = []
    for i in range(3):
        p = tmp_path / f"file_{i}.txt"
        p.write_text("data")
        paths.append(str(p))

    batch = erase_batch(paths, ledger)

    assert batch.ok
    assert len(batch.results) == 3
    assert all(not os.path.exists(p) for p in paths)


def test_erase_folder_removes_files_and_directory(tmp_path, ledger):
    folder = tmp_path / "to_erase"
    folder.mkdir()
    (folder / "a.txt").write_text("a")
    (folder / "sub").mkdir()
    (folder / "sub" / "b.txt").write_text("b")

    batch = erase_folder(str(folder), ledger)

    assert batch.ok
    assert not folder.exists()
