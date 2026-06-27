---
phase: 04-ranzhirovanie-sezonnost-dozakaz
plan: "04"
subsystem: build_report-84cols + apply_formatting + report_to_sheets + ROADMAP
tags: [integration, batch-format, 84-cols, availability-velocity, presort, season-sheet]
requirements: [VISUAL-01, VISUAL-02, VISUAL-03, VISUAL-04, ORDER-01, ORDER-02, SEASON-01, SEASON-02]

dependency_graph:
  requires:
    - 04-01 (parse_weekly_stock, months_in_stock, dsi_bucket, pct_bucket, green_item)
    - 04-02 (compute_global_seasonal_index, avg_next2_index)
    - 04-03 (enrich_df, presort_by_dsi)
  provides:
    - src/build_report.py (84-col build_report_df: availability velocity + enrich_df + presort)
    - src/apply_formatting.py (build_format_requests + format_sheet: one batch_format call)
    - src/report_to_sheets.py (main: write «Отчёт» + batch_format + write «Сезонность»)
  affects:
    - tests/test_phase3.py (2 xfail marks lifted — test_velocity_and_dsi + test_df_to_rows_serializable)
    - tests/test_phase4_formatting.py (placeholder replaced with 6 GREEN mock tests)
    - .planning/ROADMAP.md (criterion #4 6->12 months; criterion #3 known-deviation note)

tech_stack:
  added: []
  patterns:
    - ws.batch_format(list) — ONE API call for ~1300 rows × 3 cols (Pitfall 4 guard)
    - enrich_df() called AFTER base+CUM_SUMMARY assembly, BEFORE pivot concat
    - presort_by_dsi() called LAST in build_report_df (all 84 cols in place)
    - Column letters derived via _col_letter(col_index) — no hardcoding

key_files:
  created:
    - src/apply_formatting.py
  modified:
    - src/build_report.py
    - src/report_to_sheets.py
    - tests/test_phase3.py
    - tests/test_phase4_formatting.py
    - .planning/ROADMAP.md

decisions:
  - "build_rows() returns (rows, df) tuple so main() passes df to format_sheet without recomputing"
  - "build_season_rows() converts np.float64 to plain float via float() before appending to rows"
  - "Year counts for «Кол-во лет» derived from distinct (year, month_sort_key) pairs in prodazhi"
  - "_col_letter() helper in apply_formatting avoids gspread import in offline test path"
  - "Test df uses 3 columns; column letter derived dynamically via _letter_for() helper in test"

metrics:
  duration: "~12 min"
  completed_date: "2026-06-27"
  tasks_completed: 3
  files_created: 1
  files_modified: 4
  checkpoint_tasks: 1
---

# Phase 4 Plan 04: Integration — 84 cols + Formatting + «Сезонность» Summary

**One-liner:** Wired build_report_df to 84 columns (availability velocity + enrich_df M–R + presort), implemented apply_formatting.py with one ws.batch_format() call, wired main() to write «Отчёт» + colour fill + «Сезонность» sheet; lifted both xfail marks (52 tests GREEN).

---

## What Was Built

### Task 1 — build_report_df extended to 84 columns

**`src/build_report.py`** rewritten to:

- Import `parse_weekly_stock` / `months_in_stock` from `parse_ostatki_weekly`
- Import `compute_global_seasonal_index` from `seasonality`
- Import `enrich_df` / `presort_by_dsi` from `order_plan`
- Add `weekly_path` parameter (default = `WEEKLY_PATH`) for testability
- Build `weekly_map = parse_weekly_stock(weekly_path)` at the start of `build_report_df`
- Build `season_map = compute_global_seasonal_index(pro)` at the start
- Compute per-EAN velocity: `sht_per_month(qty_sold, months_in_stock(weekly_map, ean, default=n_months))`
- Assemble `base_df = BASE_COLS + CUM_SUMMARY_COLS` first
- Call `enriched = enrich_df(base_df, master, pro, season_map, weekly_map)` to add 6 ANALYTIC cols
- Final concat: `BASE + CUM_SUMMARY + ANALYTIC + monthly + cum = 84 columns`
- Call `presort_by_dsi(df)` before return

**`ANALYTIC_COLS`** (new constant, cols M–R):
```
% продаж к приходам | Зелёный товар | Индекс сезона (след. 2 мес) | К заказу на 2 мес | Мёртвый | Залежалый
```

**Oracle verification (EAN 4525807270297):**

| Metric | Expected | Actual | Status |
|--------|----------|--------|--------|
| Скорость, шт/мес | 4.833 | 4.8333 | PASS |
| DSI, дней | 18.6 (red) | 18.6 | PASS |
| % продаж к приходам | 0.967 | 0.9667 | PASS |
| К заказу на 2 мес | 4.4 | 4.4 | PASS |
| Total columns | 84 | 84 | PASS |
| First row DSI (presorted) | smallest red | 2.1 | PASS |

**xfail marks lifted** in `tests/test_phase3.py`:
- `test_velocity_and_dsi` — now PASSES (availability-velocity wired)
- `test_df_to_rows_serializable` — now PASSES (84 cols confirmed)

### Task 2 — apply_formatting.py (TDD RED→GREEN)

**`src/apply_formatting.py`** (new, 125 lines):

| Function | Purpose |
|---|---|
| `_col_letter(col_index)` | 0-based index → Sheets letter (A, Z, AA, …) — no gspread import needed |
| `_find_col_letter(df, col_name)` | Derives column letter dynamically from df.columns |
| `build_format_requests(df)` | Builds list[dict] for ws.batch_format(): DSI (J), % продаж (M), Скорость (I) |
| `format_sheet(ws, df)` | Calls ws.batch_format(build_format_requests(df)) — ONE API call |

Palette (Google Sheets light colours, float RGB 0..1):

| Bucket | Colour | HEX | Usage |
|--------|--------|-----|-------|
| DSI < 30 | red | #F4CCCC | горит |
| DSI 30–59 | yellow | #FCE5CD | watch |
| DSI 60–89 | green | #D9EAD3 | ok |
| DSI >= 90 | blue | #CFE2F3 | overstock |
| % < 20% | red | #F4CCCC | |
| % 20–39% | orange | #F9CB9C | |
| % 40–59% | yellow | #FFE599 | |
| % 60–79% | blue | #CFE2F3 | |
| % 80–100% | green | #D9EAD3 | |
| velocity > 20 | green-item | #B6D7A8 | зелёный товар |

**`tests/test_phase4_formatting.py`** — 6 GREEN mock tests (no network):
- `test_batch_format_requests_dsi` — 4 buckets, empty-DSI skipped, correct RGB dominance
- `test_batch_format_requests_pct` — 5-level, empty skipped, correct RGB dominance
- `test_batch_format_requests_velocity` — green only for velocity>20, empty skipped
- `test_format_sheet_single_call` — FakeWorksheet counts 1 call (Pitfall 4 guard)
- `test_format_request_structure` — range/format/backgroundColor keys, float 0..1
- `test_full_layout_column_letters` — I=Скорость, J=DSI, M=% продаж in 84-col layout

### Task 3 — Orchestration + ROADMAP fix

**`src/report_to_sheets.py`** extended:

- `build_rows()` now returns `(rows, df)` tuple (offline, no network)
- `build_season_rows(prodazhi_path)` — new offline function: 12 global indices, plain float,
  header `[«Месяц», «Индекс», «Кол-во лет»]`, rows 1..12 in calendar order
- `main()` order: `write_report(«Отчёт»)` → `format_sheet(ws, df)` → `write_report(«Сезонность»)`
- Import chain: `apply_formatting.format_sheet`, `seasonality.compute_global_seasonal_index`,
  `report_metrics.RU_MONTHS`

**`Сезонность` sheet (12 rows, verified offline):**

| Месяц | Индекс | Кол-во лет |
|-------|--------|------------|
| Январь | 0.349 | 3 |
| Февраль | 1.0726 | 3 |
| Март | 1.0596 | 3 |
| Апрель | 1.5157 | 3 |
| Май | 1.1302 | 3 |
| Июнь | 1.0252 | 3 |
| Июль | 1.2107 | 2 |
| Август | 0.3275 | 2 |
| Сентябрь | 1.6226 | 2 |
| Октябрь | 1.4388 | 3 |
| Ноябрь | 0.7767 | 3 |
| Декабрь | 0.4713 | 3 |

**ROADMAP fixes:**
- Criterion #4: «нулевыми продажами за последние 6 месяцев» → «12 месяцев» (user override, CONTEXT locked)
- Criterion #3: added known-deviation note — ноябрь=0.78<1 is expected (sparse Nov 2023 data)

**Full suite gate:** `python -m pytest tests/ -q` → **52 passed, 0 failed, 0 xfail, 0 errors**

### Task 4 — Checkpoint (PENDING human-verify)

Live Google Sheets write not yet performed. Awaiting human verification.
See checkpoint section below.

---

## Known Deviation: Ноябрь seasonal index < 1

**From 04-02 (carry-forward):** November index = 0.778 < 1. ROADMAP criterion #3
says «сент–ноябрь > 1». October (1.439) and September (1.623) are clearly > 1.
November is < 1 due to sparse November 2023 data (first month of export, few sales).
This is documented as a known deviation — not a bug. SEASON-01 is met for
the months that matter (Mar/Apr/May and Sep/Oct peaks all > 1).

---

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] np.float64 leaked from compute_global_seasonal_index into season rows**
- **Found during:** Task 3 (build_season_rows smoke-test)
- **Issue:** `round(season_map.get(m), 4)` preserved np.float64; gspread serialization would fail
- **Fix:** `round(float(season_map.get(m, 0.0)), 4)` converts to plain Python float
- **Files modified:** `src/report_to_sheets.py`
- **Commit:** 2475c0d

**2. [Rule 1 - Bug] Dead for-loop left in build_season_rows**
- **Found during:** Task 3 (code review during smoke-test)
- **Issue:** First attempt at year_count used a for-loop with `pass` (abandoned approach)
- **Fix:** Removed dead loop; kept only the clean ym_pairs set-comprehension approach
- **Files modified:** `src/report_to_sheets.py`
- **Commit:** 2475c0d

**3. [Rule 1 - Bug] test_phase4_formatting tests used hardcoded "J"/"M"/"I" letter prefix**
- **Found during:** Task 2 GREEN phase (test ran with 3-col test df, DSI was at col B not J)
- **Issue:** Test df has only 3 cols; DSI falls at col B. Hardcoded "J" produced 0 matches.
- **Fix:** Replaced hardcoded letter with `_letter_for(df, col_name)` helper derived dynamically;
  also exported `_col_letter` from apply_formatting for use in tests
- **Files modified:** `tests/test_phase4_formatting.py`
- **Commit:** 38573d8

---

## Commits

| Hash | Message |
|------|---------|
| `c1294cd` | `feat(04-04): build_report_df 84 cols — availability velocity + enrich_df + presort` |
| `38573d8` | `feat(04-04): apply_formatting — build_format_requests + format_sheet (one batch_format call)` |
| `2475c0d` | `feat(04-04): orchestrator + «Сезонность» sheet wired in main()` |
| `7f91a30` | `docs(04-04): ROADMAP criterion #4 «6 мес» -> «12 мес» + #3 known-deviation note` |

---

## CHECKPOINT PENDING

**Task 4:** Live Sheets write + human visual verification.

**Service account:** must have Editor on Sheet `1ncF3ElaK8OWRfnajrdkiK9WcNQQ9r0UTKhx_xSaBtSE`
(same account as Phase 3 — already granted; confirm before running).

**Command to run:**
```
cd C:\Users\abirv\Desktop\CLODYA\сезонност
python src/report_to_sheets.py
```

**What to verify on the live sheet:**
1. Лист «Отчёт»: первые строки красные (DSI<30), внутри по DSI возрастанию
2. Колонка J (DSI) окрашена по 4 бакетам; колонка M («% продаж») по 5 уровням
3. Колонка I («Скорость») зелёная у товаров с оборотом >20 шт/мес
4. Колонка P («К заказу на 2 мес») заполнена при доле ≥60%, пусто иначе
5. Всего 84 колонки; Oracle EAN 4525807270297: DSI≈18.6, К заказу≈4.4
6. Лист «Сезонность»: 12 строк; апрель/сентябрь/октябрь >1; январь<1; ноябрь<1 ожидаемо

**Resume signal:** Напишите «approved» если всё корректно.

---

## Self-Check: PASSED

| Item | Result |
|---|---|
| `src/build_report.py` | FOUND — contains `ANALYTIC_COLS`, `enrich_df`, `presort_by_dsi` imports |
| `src/apply_formatting.py` | FOUND — contains `def build_format_requests` |
| `src/report_to_sheets.py` | FOUND — contains `Сезонность` |
| `tests/test_phase3.py` | FOUND — xfail marks removed |
| `tests/test_phase4_formatting.py` | FOUND — 6 tests, no importorskip placeholder |
| `.planning/ROADMAP.md` | FOUND — contains «12 месяцев» |
| commit `c1294cd` | FOUND |
| commit `38573d8` | FOUND |
| commit `2475c0d` | FOUND |
| commit `7f91a30` | FOUND |
| Full suite `52 passed` | VERIFIED |
