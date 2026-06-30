"""test_bot_backup.py — GREEN tests for BOT-03 (Plan 02).

Tests cover the backup/restore/validation layer for incoming files:
  - Backup is created BEFORE the file is replaced.
  - On pipeline failure, backup is restored (parquet reverted byte-for-byte).
  - Short / malformed xlsx is rejected before pipeline runs.
  - Rotation keeps last 5 snapshots per file_type.
"""
import shutil
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_PARQUET_NAMES = [
    "master.parquet",
    "master_cost.parquet",
    "ostatki.parquet",
    "prikhod_ledger.parquet",
    "prikhody.parquet",
    "prodazhi.parquet",
]


def _populate_interim(interim: Path) -> dict[str, bytes]:
    """Create fake *.parquet files in interim/ and return name→bytes map."""
    interim.mkdir(parents=True, exist_ok=True)
    content = {}
    for name in _PARQUET_NAMES:
        data = f"FAKE-{name}-ORIGINAL".encode()
        (interim / name).write_bytes(data)
        content[name] = data
    return content


# ---------------------------------------------------------------------------
# Task 1 tests
# ---------------------------------------------------------------------------


def test_backup_before_replace(bot_config, tmp_path):
    """backup_artifacts('ledger') snapshots all parquet + входной xlsx; originals untouched."""
    from bot.backup import backup_artifacts

    # wire project_root to tmp_path via bot_config
    # bot_config already has project_root=tmp_path (from fixture in conftest.py)
    interim = bot_config.project_root / "data" / "interim"
    original_content = _populate_interim(interim)

    # Create fake input xlsx for 'ledger'
    ledger_xlsx = bot_config.project_root / "приходы остатки.xlsx"
    ledger_xlsx.write_bytes(b"FAKE-LEDGER-XLS-ORIGINAL")

    bak = backup_artifacts("ledger", config=bot_config)

    # Backup dir exists
    assert bak.exists(), f"Backup directory not created: {bak}"

    # All parquet files are in backup
    for name in _PARQUET_NAMES:
        bak_file = bak / name
        assert bak_file.exists(), f"{name} missing from backup"
        assert bak_file.read_bytes() == original_content[name], f"{name} content mismatch in backup"

    # Input xlsx backed up for ledger type
    bak_xlsx = bak / "приходы остатки.xlsx"
    assert bak_xlsx.exists(), "Ledger xlsx not found in backup"
    assert bak_xlsx.read_bytes() == b"FAKE-LEDGER-XLS-ORIGINAL"

    # Originals are untouched
    for name in _PARQUET_NAMES:
        assert (interim / name).read_bytes() == original_content[name], \
            f"Original {name} was modified by backup!"


def test_restore_on_failure(bot_config, tmp_path):
    """restore_artifacts(bak) restores parquet byte-for-byte after simulated pipeline failure."""
    from bot.backup import backup_artifacts, restore_artifacts

    interim = bot_config.project_root / "data" / "interim"
    original_content = _populate_interim(interim)

    ledger_xlsx = bot_config.project_root / "приходы остатки.xlsx"
    ledger_xlsx.write_bytes(b"FAKE-LEDGER-XLS-ORIGINAL")

    # Create backup (before "pipeline" runs)
    bak = backup_artifacts("ledger", config=bot_config)

    # Simulate pipeline corruption: overwrite a parquet file with garbage
    corrupted_name = "master.parquet"
    (interim / corrupted_name).write_bytes(b"CORRUPTED-BY-PIPELINE")

    # Verify corruption happened
    assert (interim / corrupted_name).read_bytes() == b"CORRUPTED-BY-PIPELINE"

    # Restore from backup
    restore_artifacts(bak, config=bot_config)

    # All parquet restored byte-for-byte
    for name in _PARQUET_NAMES:
        restored = (interim / name).read_bytes()
        assert restored == original_content[name], \
            f"{name}: expected original bytes, got {restored!r}"


def test_rotation_keeps_5(bot_config, tmp_path):
    """6th backup_artifacts call keeps exactly 5 snapshots for same type; other types untouched."""
    from bot.backup import backup_artifacts

    interim = bot_config.project_root / "data" / "interim"
    _populate_interim(interim)

    # Also set up a weekly xlsx so those backups don't error on missing file
    weekly_xlsx = bot_config.project_root / "остатки по неделям.xlsx"
    weekly_xlsx.write_bytes(b"FAKE-WEEKLY")

    # Create 1 snapshot for a DIFFERENT type first (must be untouched by ledger rotation)
    backup_artifacts("weekly", config=bot_config)

    # Create 6 snapshots for 'ledger'
    ledger_xlsx = bot_config.project_root / "приходы остатки.xlsx"
    ledger_xlsx.write_bytes(b"FAKE-LEDGER")

    bak_paths = []
    for i in range(6):
        # Re-populate to avoid empty-dir issues
        _populate_interim(interim)
        b = backup_artifacts("ledger", config=bot_config)
        bak_paths.append(b)
        # tiny sleep substitute: ensure unique timestamp by checking name
        # (backup_artifacts must guarantee unique dir names even in quick succession)

    bak_dir = bot_config.project_root / "data" / "interim" / "_bak_bot"
    assert bak_dir.exists()

    ledger_snapshots = sorted(bak_dir.glob("ledger_*"))
    weekly_snapshots = sorted(bak_dir.glob("weekly_*"))

    assert len(ledger_snapshots) == 5, \
        f"Expected 5 ledger snapshots after rotation, got {len(ledger_snapshots)}: {[p.name for p in ledger_snapshots]}"

    # weekly snapshot untouched by ledger rotation
    assert len(weekly_snapshots) >= 1, "weekly snapshot was incorrectly removed by ledger rotation"


# ---------------------------------------------------------------------------
# Task 2 tests
# ---------------------------------------------------------------------------


def test_validate_rejects_short(bot_config, fake_xlsx_short):
    """validate_xlsx raises ValueError for a file with fewer than 12 rows."""
    from bot.backup import validate_xlsx

    with pytest.raises(ValueError, match=r"[Сс]лишком мало|мало строк|не читается"):
        validate_xlsx(fake_xlsx_short, "ledger")


def test_validate_accepts_real(bot_config):
    """validate_xlsx accepts the real «приходы остатки.xlsx» if it exists."""
    from bot.backup import validate_xlsx

    # Use the actual project root (conftest PROJECT_ROOT = parent of tests/)
    from pathlib import Path
    project_root = Path(__file__).resolve().parent.parent
    real_ledger = project_root / "приходы остатки.xlsx"

    if not real_ledger.exists():
        pytest.skip("Real «приходы остатки.xlsx» not present in CI — skipping acceptance test")

    # Should NOT raise
    validate_xlsx(real_ledger, "ledger")
