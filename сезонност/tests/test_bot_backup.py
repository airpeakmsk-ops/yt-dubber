"""test_bot_backup.py — Wave 0 stubs for BOT-03 (Plan 02).

Tests cover the backup/restore/validation layer for incoming files:
  - Backup is created BEFORE the file is replaced.
  - On pipeline failure, backup is restored (parquet reverted).
  - Short / malformed xlsx is rejected before pipeline runs.

All tests are xfail until Plan 02 implements bot/backup.py with the actual
backup, restore, and validate logic.
"""
import pytest


@pytest.mark.xfail(
    reason="impl in Plan 02: бэкап создан до изменения файлов",
    strict=False,
)
def test_backup_before_replace(bot_config, tmp_path):
    """Backup is written before the incoming file replaces the existing one.

    Plan 02 will:
      - Set up fake «приходы остатки.xlsx» and «data/interim/*.parquet» in tmp_path.
      - Call bot.backup.create_backup(file_type='ledger', config=bot_config).
      - Assert backup copies exist in the backup directory.
      - Assert originals are still present (backup ≠ replace).
    """
    pytest.xfail("not implemented until Plan 02")


@pytest.mark.xfail(
    reason="impl in Plan 02: откат восстанавливает parquet",
    strict=False,
)
def test_restore_on_failure(bot_config, tmp_path):
    """On pipeline failure, backup is restored and originals are reverted.

    Plan 02 will:
      - Create fake backup snapshot.
      - Simulate pipeline failure (exception raised).
      - Call bot.backup.restore_backup(file_type='ledger', config=bot_config).
      - Assert original files match the backup (not the partially-written new ones).
      - Assert Google Sheet was NOT touched (no write_report calls).
    """
    pytest.xfail("not implemented until Plan 02")


@pytest.mark.xfail(
    reason="impl in Plan 02: короткий xlsx отклонён",
    strict=False,
)
def test_validate_rejects_short(bot_config, fake_xlsx_short):
    """An xlsx with fewer than the minimum expected rows is rejected before pipeline.

    Plan 02 will:
      - Call bot.backup.validate_file(path=fake_xlsx_short, file_type='ledger').
      - Assert it raises ValidationError (or returns False).
      - Assert pipeline steps are NOT called.

    Uses fake_xlsx_short fixture (5 rows, well below ledger minimum).
    """
    pytest.xfail("not implemented until Plan 02")
