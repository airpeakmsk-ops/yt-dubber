---
phase: 06-telegram
plan: 03
subsystem: bot-pipeline
tags: [pipeline, orchestrator, type-branching, backup, restore, tdd, pytest]

# Dependency graph
requires:
  - phase: 06-telegram
    plan: 01
    provides: bot/config.py Config dataclass + load_config
  - phase: 06-telegram
    plan: 02
    provides: bot/backup.py backup_artifacts / restore_artifacts / validate_xlsx
  - phase: 04-ranzhirovanie-sezonnost-dozakaz
    provides: src/* pipeline functions (parse_ledger, build_master, compute_cost, report_to_sheets)
provides:
  - bot/pipeline.py: run_pipeline(file_type, tmp_path)->int — synchronous orchestrator for asyncio.to_thread
  - type-branching map: ledger/weekly/invoice→steps, unknown→ValueError
  - backup→try→restore-on-error wrapper: Sheet updated only on full success

affects:
  - 06-04 (handlers + scheduler — calls run_pipeline via asyncio.to_thread)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Proxy wrapper functions (_write_artifacts, _build_master, _compute_cost, _report_main) monkeypatchable in tests
    - sys.path bootstrap at module level (PROJECT_ROOT insert, same pattern as src/ parsers)
    - validate_xlsx fail-closed BEFORE backup (no bak dir created for invalid files)
    - restore_artifacts called in except block, then raise (Sheet not touched until full success)
    - _RATE_RE pattern from parse_prikhody for invoice subfolder routing

key-files:
  created:
    - bot/pipeline.py
  modified:
    - tests/test_bot_pipeline.py (replaced xfail stubs with 6 GREEN tests)

key-decisions:
  - "Proxy wrapper functions (_write_artifacts etc.) instead of direct src imports — allows monkeypatch without patching deep import chains in tests"
  - "validate_xlsx called BEFORE backup_artifacts — fail-closed before any state change, no orphan backup dirs"
  - "weekly: copy only, NO build_master/compute_cost — BOT-02 contract: приходная/себест parquet untouched"
  - "invoice subfolder routing: _RATE_RE match on filename stem → root folder; no match → в рублях/ (mirrors parse_prikhody logic)"
  - "test_rotation_keeps_5 failure in test_bot_backup.py is Plan 02 pre-existing issue, out of scope; logged to deferred-items"

# Metrics
duration: ~10min
completed: 2026-06-30
---

# Phase 06 Plan 03: Pipeline Orchestrator Summary

**run_pipeline(file_type, tmp_path)->int — синхронный оркестратор с картой тип→шаги и backup/restore-обёрткой; 6 GREEN-тестов (mocked src)**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-06-30
- **Completed:** 2026-06-30
- **Tasks:** 1/1
- **Files modified:** 2

## Accomplishments

- `bot/pipeline.py` создан: `run_pipeline(file_type, tmp_path) -> int` — синхронная функция для `asyncio.to_thread`
- Карта тип→шаги: `ledger` (copy→write_artifacts→build_master→compute_cost→report), `weekly` (copy→report only, BOT-02), `invoice` (copy→build_master→compute_cost→report)
- Маршрутизация накладной по подпапке: курс в имени → `поступления товаров/`, нет курса → `поступления товаров/в рублях/`
- backup→try→restore-on-error: Sheet (report.main) вызывается только при полном успехе всех предшествующих шагов
- `validate_xlsx` вызывается ДО backup — fail-closed до любых изменений состояния
- Прокси-функции `_write_artifacts`, `_build_master`, `_compute_cost`, `_report_main` — monkeypatch-точки для тестов без реального пересчёта
- 6 GREEN тестов: `test_ledger_steps`, `test_weekly_steps`, `test_invoice_steps`, `test_invoice_with_rate_goes_to_root`, `test_unknown_type`, `test_restore_on_pipeline_error`

## Task Commits

1. **Task 1: run_pipeline + tests** — `e8bceb9` (feat)

## Files Created/Modified

- `bot/pipeline.py` — run_pipeline оркестратор (82 строки); _run_ledger/_run_weekly/_run_invoice/_run_report; sys.path bootstrap; _RATE_RE для маршрутизации накладных
- `tests/test_bot_pipeline.py` — 6 GREEN тестов (заменили 3 xfail стаба)

## Decisions Made

- Прокси-функции вместо прямых src-импортов: `monkeypatch.setattr(pipeline, "_build_master", fake)` работает без патчинга глубокой цепочки импортов
- `validate_xlsx` до `backup_artifacts`: ошибка валидации не создаёт orphan-backup директорий
- weekly: только copy + report, NO build_master/compute_cost — BOT-02 контракт (приходная/себест parquet не перезаписывается)
- _RATE_RE из parse_prikhody: одна точка истины для определения типа накладной (с курсом / в рублях)

## Deviations from Plan

### Out-of-scope pre-existing issues

**1. [Out of scope] test_rotation_keeps_5 failure in test_bot_backup.py**
- **Found during:** Full suite run after Plan 03 GREEN
- **Issue:** Plan 02's `test_rotation_keeps_5` fails — backup rotation keeps 2 snapshots instead of 5
- **Action:** Logged to deferred-items; NOT fixed (Plan 02 scope, parallel agent)
- **Scope boundary:** Plan 03 touches only `bot/pipeline.py` + `tests/test_bot_pipeline.py`

## Full Suite Result

- `tests/test_bot_pipeline.py`: **6 passed** (0 failures)
- `tests/` full suite: 76 passed, 3 xfailed, **1 pre-existing failure** (test_bot_backup.py::test_rotation_keeps_5 — Plan 02 scope)

## Self-Check

- [x] `bot/pipeline.py` exists and contains `def run_pipeline`
- [x] `tests/test_bot_pipeline.py` has 6 real tests (no xfail stubs)
- [x] Commit `e8bceb9` exists
- [x] All 6 pipeline tests GREEN
- [x] type-branching: unknown→ValueError tested and working
- [x] restore_artifacts called on error, report.main NOT called

## Self-Check: PASSED

All created files verified, commit confirmed, all 6 tests pass.

---
*Phase: 06-telegram*
*Completed: 2026-06-30*
