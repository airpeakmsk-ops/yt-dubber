"""test_bot_pipeline.py — GREEN-тесты для bot/pipeline.py (Plan 03, BOT-02/03).

Мок src-функций через monkeypatch — проверяем ПОРЯДОК и НАБОР вызовов, не реальный пересчёт.
Реальные файлы не затрагиваются: shutil.copy2 тоже замокан.
"""
from __future__ import annotations

import pathlib
import sys
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_N = 42  # stub return value from report.main()


def _make_tmp_xlsx(tmp_path: pathlib.Path, name: str = "test_file.xlsx") -> pathlib.Path:
    """Создать фиктивный .xlsx файл в tmp_path (не пустой — validate_xlsx должен пройти)."""
    p = tmp_path / name
    # Minimal xlsx magic bytes so validate_xlsx doesn't reject it
    # (bot.backup.validate_xlsx проверяет что файл существует и не пустой)
    p.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    return p


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_xlsx(tmp_path):
    return _make_tmp_xlsx(tmp_path)


# ---------------------------------------------------------------------------
# Test 1: ledger steps
# ---------------------------------------------------------------------------

def test_ledger_steps(tmp_path, tmp_xlsx, monkeypatch):
    """run_pipeline('ledger', tmp) вызывает write_artifacts→build_master.main→
    compute_cost.main→report.main ровно по разу, в этом порядке.
    tmp скопирован в 'приходы остатки.xlsx'. Возвращает N от report.
    """
    import bot.pipeline as pipeline

    calls = []

    def fake_validate(path, ftype):
        calls.append(("validate", ftype))

    def fake_backup(ftype, config):
        calls.append(("backup", ftype))
        return pathlib.Path(tmp_path / "bak")

    def fake_restore(bak, config):
        calls.append(("restore",))

    def fake_copy2(src, dst):
        calls.append(("copy2", str(src), str(dst)))

    def fake_write_artifacts(path=None):
        calls.append(("write_artifacts", str(path)))
        return (100, 50)

    def fake_build_master():
        calls.append(("build_master",))

    def fake_compute_cost():
        calls.append(("compute_cost",))

    def fake_report():
        calls.append(("report",))
        return FAKE_N

    monkeypatch.setattr(pipeline, "load_config", lambda: object())
    monkeypatch.setattr(pipeline, "validate_xlsx", fake_validate)
    monkeypatch.setattr(pipeline, "backup_artifacts", fake_backup)
    monkeypatch.setattr(pipeline, "restore_artifacts", fake_restore)
    monkeypatch.setattr(pipeline.shutil, "copy2", fake_copy2)
    monkeypatch.setattr(pipeline, "_write_artifacts", fake_write_artifacts)
    monkeypatch.setattr(pipeline, "_build_master", fake_build_master)
    monkeypatch.setattr(pipeline, "_compute_cost", fake_compute_cost)
    monkeypatch.setattr(pipeline, "_report_main", fake_report)

    result = pipeline.run_pipeline("ledger", tmp_xlsx)

    assert result == FAKE_N

    # Порядок шагов (после validate/backup):
    step_calls = [c[0] for c in calls]
    assert "write_artifacts" in step_calls
    assert "build_master" in step_calls
    assert "compute_cost" in step_calls
    assert "report" in step_calls

    # write_artifacts РАНЬШЕ build_master, build_master РАНЬШЕ compute_cost, compute_cost РАНЬШЕ report
    idx = {name: step_calls.index(name) for name in ("write_artifacts", "build_master", "compute_cost", "report")}
    assert idx["write_artifacts"] < idx["build_master"] < idx["compute_cost"] < idx["report"]

    # Файл скопирован в 'приходы остатки.xlsx'
    copy_calls = [c for c in calls if c[0] == "copy2"]
    assert len(copy_calls) == 1
    assert "приходы остатки.xlsx" in copy_calls[0][2]

    # restore НЕ вызван (успех)
    assert "restore" not in step_calls


# ---------------------------------------------------------------------------
# Test 2: weekly steps
# ---------------------------------------------------------------------------

def test_weekly_steps(tmp_path, tmp_xlsx, monkeypatch):
    """run_pipeline('weekly', tmp) вызывает ТОЛЬКО report.main.
    build_master/compute_cost/write_artifacts НЕ вызваны (BOT-02).
    tmp скопирован в 'остатки по неделям.xlsx'.
    """
    import bot.pipeline as pipeline

    calls = []

    def fake_validate(path, ftype):
        calls.append(("validate", ftype))

    def fake_backup(ftype, config):
        calls.append(("backup", ftype))
        return pathlib.Path(tmp_path / "bak")

    def fake_restore(bak, config):
        calls.append(("restore",))

    def fake_copy2(src, dst):
        calls.append(("copy2", str(src), str(dst)))

    def fake_write_artifacts(path=None):
        calls.append(("write_artifacts",))
        return (0, 0)

    def fake_build_master():
        calls.append(("build_master",))

    def fake_compute_cost():
        calls.append(("compute_cost",))

    def fake_report():
        calls.append(("report",))
        return FAKE_N

    monkeypatch.setattr(pipeline, "load_config", lambda: object())
    monkeypatch.setattr(pipeline, "validate_xlsx", fake_validate)
    monkeypatch.setattr(pipeline, "backup_artifacts", fake_backup)
    monkeypatch.setattr(pipeline, "restore_artifacts", fake_restore)
    monkeypatch.setattr(pipeline.shutil, "copy2", fake_copy2)
    monkeypatch.setattr(pipeline, "_write_artifacts", fake_write_artifacts)
    monkeypatch.setattr(pipeline, "_build_master", fake_build_master)
    monkeypatch.setattr(pipeline, "_compute_cost", fake_compute_cost)
    monkeypatch.setattr(pipeline, "_report_main", fake_report)

    result = pipeline.run_pipeline("weekly", tmp_xlsx)

    assert result == FAKE_N

    step_calls = [c[0] for c in calls]

    # Только report — никакого rebuild parquet
    assert "write_artifacts" not in step_calls, "weekly НЕ должен вызывать write_artifacts"
    assert "build_master" not in step_calls, "weekly НЕ должен вызывать build_master"
    assert "compute_cost" not in step_calls, "weekly НЕ должен вызывать compute_cost"
    assert "report" in step_calls

    # Файл скопирован в 'остатки по неделям.xlsx'
    copy_calls = [c for c in calls if c[0] == "copy2"]
    assert len(copy_calls) == 1
    assert "остатки по неделям.xlsx" in copy_calls[0][2]

    # restore НЕ вызван
    assert "restore" not in step_calls


# ---------------------------------------------------------------------------
# Test 3: invoice steps
# ---------------------------------------------------------------------------

def test_invoice_steps(tmp_path, monkeypatch):
    """run_pipeline('invoice', tmp) вызывает build_master.main→compute_cost.main→report.main.
    write_artifacts (ledger-парсер) НЕ вызван. tmp скопирован в поступления товаров/.
    """
    import bot.pipeline as pipeline

    # Файл без маркера курса → копируется в в рублях/
    tmp_xlsx = tmp_path / "12 поступление.xlsx"
    tmp_xlsx.write_bytes(b"PK\x03\x04" + b"\x00" * 100)

    calls = []

    def fake_validate(path, ftype):
        calls.append(("validate", ftype))

    def fake_backup(ftype, config):
        calls.append(("backup", ftype))
        return pathlib.Path(tmp_path / "bak")

    def fake_restore(bak, config):
        calls.append(("restore",))

    def fake_copy2(src, dst):
        calls.append(("copy2", str(src), str(dst)))

    def fake_write_artifacts(path=None):
        calls.append(("write_artifacts",))
        return (0, 0)

    def fake_build_master():
        calls.append(("build_master",))

    def fake_compute_cost():
        calls.append(("compute_cost",))

    def fake_report():
        calls.append(("report",))
        return FAKE_N

    monkeypatch.setattr(pipeline, "load_config", lambda: object())
    monkeypatch.setattr(pipeline, "validate_xlsx", fake_validate)
    monkeypatch.setattr(pipeline, "backup_artifacts", fake_backup)
    monkeypatch.setattr(pipeline, "restore_artifacts", fake_restore)
    monkeypatch.setattr(pipeline.shutil, "copy2", fake_copy2)
    monkeypatch.setattr(pipeline, "_write_artifacts", fake_write_artifacts)
    monkeypatch.setattr(pipeline, "_build_master", fake_build_master)
    monkeypatch.setattr(pipeline, "_compute_cost", fake_compute_cost)
    monkeypatch.setattr(pipeline, "_report_main", fake_report)

    result = pipeline.run_pipeline("invoice", tmp_xlsx)

    assert result == FAKE_N

    step_calls = [c[0] for c in calls]

    # write_artifacts НЕ вызван (накладная не перестраивает леджер-parquet)
    assert "write_artifacts" not in step_calls, "invoice НЕ должен вызывать write_artifacts (ledger-парсер)"

    # build_master → compute_cost → report вызваны в порядке
    assert "build_master" in step_calls
    assert "compute_cost" in step_calls
    assert "report" in step_calls
    idx = {name: step_calls.index(name) for name in ("build_master", "compute_cost", "report")}
    assert idx["build_master"] < idx["compute_cost"] < idx["report"]

    # Файл скопирован в папку поступления товаров (с подпапкой или без)
    copy_calls = [c for c in calls if c[0] == "copy2"]
    assert len(copy_calls) == 1
    assert "поступления товаров" in copy_calls[0][2]

    # restore НЕ вызван
    assert "restore" not in step_calls


# ---------------------------------------------------------------------------
# Test 4: invoice with rate marker → root folder (not в рублях/)
# ---------------------------------------------------------------------------

def test_invoice_with_rate_goes_to_root(tmp_path, monkeypatch):
    """Накладная с маркером курса в имени → копируется в корень 'поступления товаров/',
    НЕ в 'в рублях/'.
    """
    import bot.pipeline as pipeline

    # Имя с маркером курса «103,79»
    tmp_xlsx = tmp_path / "12 приход 103,79.xlsx"
    tmp_xlsx.write_bytes(b"PK\x03\x04" + b"\x00" * 100)

    calls = []

    monkeypatch.setattr(pipeline, "load_config", lambda: object())
    monkeypatch.setattr(pipeline, "validate_xlsx", lambda p, ft: None)
    monkeypatch.setattr(pipeline, "backup_artifacts", lambda ft, cfg: tmp_path / "bak")
    monkeypatch.setattr(pipeline, "restore_artifacts", lambda bak, cfg: None)
    monkeypatch.setattr(pipeline.shutil, "copy2", lambda s, d: calls.append(("copy2", str(s), str(d))))
    monkeypatch.setattr(pipeline, "_write_artifacts", lambda path=None: (0, 0))
    monkeypatch.setattr(pipeline, "_build_master", lambda: None)
    monkeypatch.setattr(pipeline, "_compute_cost", lambda: None)
    monkeypatch.setattr(pipeline, "_report_main", lambda: FAKE_N)

    pipeline.run_pipeline("invoice", tmp_xlsx)

    copy_calls = [c for c in calls if c[0] == "copy2"]
    assert len(copy_calls) == 1
    dst = copy_calls[0][2]
    assert "поступления товаров" in dst
    assert "в рублях" not in dst, "Накладная с курсом должна идти в корень, не в в рублях/"


# ---------------------------------------------------------------------------
# Test 5: unknown type → ValueError
# ---------------------------------------------------------------------------

def test_unknown_type(tmp_path, tmp_xlsx, monkeypatch):
    """run_pipeline('bogus', tmp) → ValueError (type-branching: unknown явно отклонён)."""
    import bot.pipeline as pipeline

    monkeypatch.setattr(pipeline, "load_config", lambda: object())
    monkeypatch.setattr(pipeline, "validate_xlsx", lambda p, ft: None)
    monkeypatch.setattr(pipeline, "backup_artifacts", lambda ft, cfg: tmp_path / "bak")

    restore_called = []
    monkeypatch.setattr(pipeline, "restore_artifacts", lambda bak, cfg: restore_called.append(True))

    with pytest.raises(ValueError, match="Unknown file_type"):
        pipeline.run_pipeline("bogus", tmp_xlsx)

    # restore вызван при ошибке
    assert restore_called, "restore_artifacts должен быть вызван при ValueError (unknown type)"


# ---------------------------------------------------------------------------
# Test 6: restore on pipeline error
# ---------------------------------------------------------------------------

def test_restore_on_pipeline_error(tmp_path, tmp_xlsx, monkeypatch):
    """Если build_master.main падает → restore_artifacts вызван с bak,
    исключение проброшено, report.main НЕ вызван (Sheet не трогается).
    """
    import bot.pipeline as pipeline

    fake_bak = tmp_path / "bak"
    restore_args = []
    report_called = []

    monkeypatch.setattr(pipeline, "load_config", lambda: object())
    monkeypatch.setattr(pipeline, "validate_xlsx", lambda p, ft: None)
    monkeypatch.setattr(pipeline, "backup_artifacts", lambda ft, cfg: fake_bak)
    monkeypatch.setattr(pipeline, "restore_artifacts", lambda bak, cfg: restore_args.append(bak))
    monkeypatch.setattr(pipeline.shutil, "copy2", lambda s, d: None)
    monkeypatch.setattr(pipeline, "_write_artifacts", lambda path=None: (5, 3))  # n_sales>0 → проходит guard
    monkeypatch.setattr(pipeline, "_build_master", lambda: (_ for _ in ()).throw(RuntimeError("build failed")))
    monkeypatch.setattr(pipeline, "_compute_cost", lambda: None)
    monkeypatch.setattr(pipeline, "_report_main", lambda: report_called.append(True) or FAKE_N)

    with pytest.raises(RuntimeError, match="build failed"):
        pipeline.run_pipeline("ledger", tmp_xlsx)

    # restore вызван с правильным аргументом
    assert len(restore_args) == 1
    assert restore_args[0] == fake_bak

    # report НЕ вызван — Sheet не трогается до полного успеха
    assert not report_called, "report.main НЕ должен быть вызван при ошибке до него"


def test_ledger_zero_sales_rejected(tmp_path, tmp_xlsx, monkeypatch):
    """Вырожденный леджер (0 строк продаж) → понятная ValueError + restore,
    БЕЗ тихой перезаписи отчёта нулями (баг 2026-07-06: файл без дат движений).
    """
    import bot.pipeline as pipeline

    restore_called = []
    report_called = []

    monkeypatch.setattr(pipeline, "load_config", lambda: object())
    monkeypatch.setattr(pipeline, "validate_xlsx", lambda p, ft: None)
    monkeypatch.setattr(pipeline, "backup_artifacts", lambda ft, cfg: tmp_path / "bak")
    monkeypatch.setattr(pipeline, "restore_artifacts", lambda bak, cfg: restore_called.append(True))
    monkeypatch.setattr(pipeline.shutil, "copy2", lambda s, d: None)
    monkeypatch.setattr(pipeline, "_write_artifacts", lambda path=None: (0, 954))  # 0 продаж
    monkeypatch.setattr(pipeline, "_build_master", lambda: None)
    monkeypatch.setattr(pipeline, "_compute_cost", lambda: None)
    monkeypatch.setattr(pipeline, "_report_main", lambda: report_called.append(True) or 1)

    with pytest.raises(ValueError, match="не содержит продаж"):
        pipeline.run_pipeline("ledger", tmp_xlsx)

    assert restore_called, "restore должен быть вызван при вырожденном леджере"
    assert not report_called, "report НЕ должен вызываться — Sheet не трогается"


# ---------------------------------------------------------------------------
# Test 7-8: РЕАЛЬНЫЙ backup/restore (integration) — ловит дрейф сигнатуры
# producer↔consumer. Баг рантайма 06-02↔06-03: pipeline звал
# backup_artifacts(file_type) без config → TypeError только на VPS, т.к. все
# юнит-тесты мокали backup 1-арг фейком (мок закодировал битую сигнатуру).
# Здесь backup_artifacts/restore_artifacts НЕ мокаются — только heavy src + report.
# ---------------------------------------------------------------------------

def _make_real_proj(tmp_path):
    """tmp project_root с data/interim/master.parquet + weekly xlsx + реальный Config."""
    import bot.config as botconfig

    proj = tmp_path / "proj"
    (proj / "data" / "interim").mkdir(parents=True)
    (proj / "data" / "interim" / "master.parquet").write_bytes(b"ORIG-MASTER")
    (proj / "остатки по неделям.xlsx").write_bytes(b"orig-weekly")
    cfg = botconfig.Config(
        bot_token="x",
        allowed_user_id=1,
        project_root=proj,
        creds_path="",
    )
    return proj, cfg


def test_run_pipeline_real_backup_happy(tmp_path, monkeypatch):
    """INTEGRATION happy-path: run_pipeline зовёт РЕАЛЬНЫЙ backup_artifacts(file_type, config).
    Если сигнатура pipeline↔backup рассогласована → TypeError (регресс пойман)."""
    import bot.pipeline as pipeline

    proj, cfg = _make_real_proj(tmp_path)
    monkeypatch.setattr(pipeline, "load_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "PROJECT_ROOT", proj)  # _run_weekly копирует внутрь proj
    monkeypatch.setattr(pipeline, "validate_xlsx", lambda p, ft: None)
    monkeypatch.setattr(pipeline, "_report_main", lambda: 1300)

    src = tmp_path / "incoming.xlsx"
    src.write_bytes(b"new-weekly")

    n = pipeline.run_pipeline("weekly", src)  # РЕАЛЬНЫЙ backup_artifacts(file_type, cfg)

    assert n == 1300
    snaps = list((proj / "data" / "interim" / "_bak_bot").glob("weekly_*"))
    assert snaps, "реальный backup_artifacts должен создать снапшот"
    assert (snaps[0] / "master.parquet").read_bytes() == b"ORIG-MASTER"


def test_run_pipeline_real_restore_on_error(tmp_path, monkeypatch):
    """INTEGRATION error-path: РЕАЛЬНЫЙ restore_artifacts(bak, config).
    _report_main портит master и падает → restore возвращает оригинал;
    пробрасывается RuntimeError (НЕ TypeError от битой сигнатуры restore)."""
    import bot.pipeline as pipeline

    proj, cfg = _make_real_proj(tmp_path)
    master = proj / "data" / "interim" / "master.parquet"

    monkeypatch.setattr(pipeline, "load_config", lambda: cfg)
    monkeypatch.setattr(pipeline, "PROJECT_ROOT", proj)
    monkeypatch.setattr(pipeline, "validate_xlsx", lambda p, ft: None)

    def corrupt_then_fail():
        master.write_bytes(b"CORRUPT")
        raise RuntimeError("report failed")

    monkeypatch.setattr(pipeline, "_report_main", corrupt_then_fail)

    src = tmp_path / "incoming.xlsx"
    src.write_bytes(b"new-weekly")

    with pytest.raises(RuntimeError, match="report failed"):
        pipeline.run_pipeline("weekly", src)  # РЕАЛЬНЫЙ backup + restore(bak, cfg)

    # restore реально вызван с 2 арг и вернул оригинал master
    assert master.read_bytes() == b"ORIG-MASTER"
