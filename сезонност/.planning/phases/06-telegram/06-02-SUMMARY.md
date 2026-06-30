---
phase: 06-telegram
plan: 02
subsystem: testing
tags: [python-calamine, shutil, backup, restore, validation, pytest, bot]

# Dependency graph
requires:
  - phase: 06-telegram
    plan: 01
    provides: bot/ package (bot/config.py Config dataclass, bot_config fixture, fake_xlsx_short fixture, Wave 0 xfail stubs in test_bot_backup.py)
provides:
  - bot/backup.py: backup_artifacts(file_type, config)->Path, restore_artifacts(bak, config), validate_xlsx(path, file_type), _rotate (keep-5)
  - GREEN test suite for BOT-03: 5 tests replacing Wave 0 xfail stubs
affects:
  - 06-03 (pipeline handler calls backup_artifacts before replacing xlsx, restore_artifacts on exception)
  - 06-04 (handlers/scheduler — backup layer available for pre-replacement guard)

# Tech tracking
tech-stack:
  added: [shutil.copy2, threading.Lock (monotonic counter), python_calamine.CalamineWorkbook]
  patterns:
    - Backup ВЕСЬ набор parquet всегда (дёшево <300КБ) — устраняет Pitfall 7 (пропущенный файл)
    - Monotonic seq counter (_counter) для уникальности имён снапшотов даже при вызовах в одну секунду
    - fail-closed validate_xlsx: при любом сомнении — ValueError до пайплайна
    - _rotate guard (excess > 0): защита от Python slice [:neg] удаляющего лишнее при len<KEEP

key-files:
  created:
    - bot/backup.py
  modified:
    - tests/test_bot_backup.py (Wave 0 xfail стабы заменены 5 GREEN тестами)

key-decisions:
  - "Монотонный глобальный счётчик _counter вместо timestamp+collision-check: rotation может удалить dir с тем же timestamp, при следующем вызове base-имя снова свободно — образуется цикл create/rotate/create. Счётчик разрывает цикл."
  - "guard excess > 0 в _rotate: без него list[:negative] удаляет все кроме последних N, что убивает все снапшоты старше 2-х при каждом вызове."
  - "Бэкапим ВЕСЬ набор _ALL_PARQUET всегда (независимо от file_type): стоит <300КБ, исключает риск пропустить parquet при ротации типов."
  - "validate_xlsx через CalamineWorkbook.from_path (не полный парсинг): быстрая проверка sheet_names[0] + len(rows) < 12 — fail-closed без накладных расходов."
  - "restore_artifacts определяет dest по суффиксу: .parquet → INTERIM, .xlsx → project_root — кросс-платформенно."

patterns-established:
  - "Backup-before-step как первый вызов в pipeline handler: backup_artifacts → pipeline → при исключении restore_artifacts"
  - "validate_xlsx вызывается ДО backup_artifacts (fail-fast, не тратить место на бэкап заведомо плохого файла)"

requirements-completed: [BOT-03]

# Metrics
duration: ~12min
completed: 2026-06-30
---

# Phase 06 Plan 02: Backup/Restore/Validate Summary

**bot/backup.py — fail-closed слой безопасности данных: CalamineWorkbook-валидация + shutil.copy2 снапшот 6 parquet + xlsx до пайплайна + byte-for-byte откат + ротация keep-5 с монотонным счётчиком**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-06-30T (session start)
- **Completed:** 2026-06-30
- **Tasks:** 2/2 (Tasks 1+2 реализованы в одном модуле)
- **Files modified:** 2

## Accomplishments

- `bot/backup.py` создан: `backup_artifacts`, `restore_artifacts`, `validate_xlsx`, `_rotate` — полный backup/restore/validate цикл
- 5 новых GREEN тестов заменили Wave 0 xfail-стабы (`test_backup_before_replace`, `test_restore_on_failure`, `test_rotation_keeps_5`, `test_validate_rejects_short`, `test_validate_accepts_real`)
- Полная сьюта: 77 passed, 3 xfailed (Plans 03/04 Wave 0 стабы), 0 регрессий

## Task Commits

1. **Task 1+2: bot/backup.py + GREEN tests** — `da91f0f` (feat)

## Files Created/Modified

- `bot/backup.py` — backup_artifacts (снапшот parquet+xlsx), restore_artifacts (откат), validate_xlsx (CalamineWorkbook fail-closed), _rotate (keep-5 с guard)
- `tests/test_bot_backup.py` — 5 GREEN тестов (заменили 3 Wave 0 xfail стаба + добавлены test_rotation_keeps_5, test_validate_accepts_real)

## Decisions Made

- Монотонный глобальный `_counter` с `threading.Lock` вместо timestamp+collision-loop: ротация удаляет dir с тем же timestamp → на следующем вызове base-имя снова свободно → бесконечный цикл create/delete/create. Счётчик делает имя всегда уникальным.
- `excess > 0` guard в `_rotate`: Python `list[:negative]` возвращает все элементы кроме последних N — без guard при каждом из первых 4 вызовов (когда snap count < KEEP) удалялись бы все снапшоты кроме двух.
- `validate_xlsx` вызывает `CalamineWorkbook.from_path` — уже имеющийся движок пайплайна, без опenpyxl зависимости; порог 12 строк — минимум для непустого файла 1С.
- Бэкап ВСЕГО набора `_ALL_PARQUET` независимо от `file_type` (дёшево, исключает Pitfall 7).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Ротация удаляла снапшоты при каждом вызове вместо только при >5**
- **Found during:** Task 1 (TDD GREEN phase, тест `test_rotation_keeps_5`)
- **Issue:** `snapshots[:excess]` при `excess = len-5 < 0` → `[:negative]` = все кроме последних 2. При 3-м вызове excess=-2, удалялся 1 из 3 снапшотов; к 6-му вызову оставалось 2 вместо 5.
- **Fix:** Добавлен guard `if excess > 0:` перед циклом удаления.
- **Files modified:** `bot/backup.py`
- **Verification:** `test_rotation_keeps_5` GREEN; финальный glob = ровно 5 снапшотов `ledger_*`, `weekly_*` не тронуты.
- **Committed in:** `da91f0f`

**2. [Rule 1 - Bug] Timestamp+collision-counter создавал зацикливание при ротации**
- **Found during:** Task 1 (trace-отладка — 6 вызовов в 1 секунду → после ротации base-имя удалено → следующий вызов пересоздаёт то же base-имя → оно снова попадает в rotation candidate)
- **Fix:** Заменил collision-counter на монотонный `_counter` с `threading.Lock` — имя формата `{type}_{ts}_{seq:04d}` уникально независимо от времени и ротации.
- **Files modified:** `bot/backup.py`
- **Verification:** Trace показал 6 уникальных dirs; `test_rotation_keeps_5` держит ровно 5 при повторных прогонах.
- **Committed in:** `da91f0f`

---

**Total deviations:** 2 auto-fixed (оба Rule 1 — баги в реализации ротации, обнаружены TDD)
**Impact on plan:** Оба фикса необходимы для корректности ротации. Scope не расширялся.

## Issues Encountered

- Python `list[:negative]` silent bug — распространённая ловушка при `excess = len - KEEP` без guard. Выявлена немедленно через TDD тест ротации.
- Timestamp+collision naming — race condition при быстрых последовательных вызовах в тестах (все в одну секунду). Решено монотонным счётчиком.

## User Setup Required

None — модуль использует только stdlib (shutil, threading, time) и уже имеющийся python_calamine. Нет внешних зависимостей.

## Next Phase Readiness

- `backup_artifacts` / `restore_artifacts` / `validate_xlsx` готовы к использованию в Plan 03 (pipeline handler)
- Вызывать: `validate_xlsx(path, ftype)` → `bak = backup_artifacts(ftype, config)` → pipeline → при исключении `restore_artifacts(bak, config)`
- Wave 0 стабы Plans 03/04 остаются xfail — готовы к реализации

---
*Phase: 06-telegram*
*Completed: 2026-06-30*
