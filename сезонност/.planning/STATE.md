---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
current_phase: 4
current_plan: 04 complete (checkpoint pending human-verify)
status: in_progress
last_updated: "2026-06-27T13:03:00Z"
progress:
  total_phases: 6
  completed_phases: 3
  total_plans: 9
  completed_plans: 10
  percent: 58
---

# STATE: Сезонная складская аналитика TIMON

> Project memory. Updated at phase transitions and significant decisions.

---

## Project Reference

**Core Value:** С одного взгляда видно, что дозаказать срочно (с учётом сезона), что залежалось, и сколько купить на 2 месяца.
**Project root:** `C:\Users\abirv\Desktop\CLODYA\сезонност`
**Google Sheet:** https://docs.google.com/spreadsheets/d/1ncF3ElaK8OWRfnajrdkiK9WcNQQ9r0UTKhx_xSaBtSE/edit
**Service account creds:** `C:\Users\abirv\Desktop\CLODYA\.env` (JSON файлы в `market_scout/`, `sales-bot/`, `TimonMaster/`)
**Platform:** Windows (win32), Python pythoncore-3.14-64, PowerShell + Bash

---

## Current Position

**Milestone:** 1
**Current Phase:** 6
**Current Plan:** 06-01 complete → 06-02 next
**Status:** In progress

```
[██████████] Phase 1: Парсинг и сопоставление ✓
[██████████] Phase 2: Себестоимость USD ✓
[██████████] Phase 3: Основной отчёт в Google Sheets ✓ (03-01 ✓, 03-02 ✓ — лист «Отчёт» заполнен)
[██████████] Phase 4: Ранжирование, сезонность и план дозаказа ✓ (04-01 ✓, 04-02 ✓, 04-03 ✓, 04-04 ✓)
[          ] Phase 5: Дашборды
[██        ] Phase 6: Telegram-бот обновления (06-01 ✓, 06-02..05 pending)

Progress: [████████░░] 75% (4/6 phases done, Phase 6 at 1/5 plans)
```

---

## Performance Metrics

| Metric | Value |
|--------|-------|
| Total phases | 6 |
| Total requirements | 26 |
| Requirements completed | 18 |
| Phases completed | 3 |
| Sessions elapsed | 7 |
| Phase 01-parsing-matching P04 | 4min | 3 tasks | 4 files |
| Phase 02-sebestoimost-usd P01 | 3min | 3 tasks | 3 files |
| Phase 03-osnovnoy-otchyot-google-sheets P01 | 7min | 3 tasks | 4 files |
| Phase 03-osnovnoy-otchyot-google-sheets P02 | 16min | 3 tasks | 4 files |
| Phase 04-ranzhirovanie-sezonnost-dozakaz P02 | 10min | 2 tasks | 2 files |
| Phase 04-ranzhirovanie-sezonnost-dozakaz P03 | 7min | 2 tasks | 2 files |

### Plan Execution

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01-parsing-matching P01 | 8min | 3 tasks | 8 files |
| Phase 01-parsing-matching P02 | 11min | 2 tasks | 3 files |
| Phase 01-parsing-matching P03 | 16min | 2 tasks | 3 files |
| Phase 01-parsing-matching P04 | 4min | 3 tasks | 4 files |
| Phase 02-sebestoimost-usd P01 | 3min | 3 tasks | 3 files |

---

## Accumulated Context

### Key Decisions

| Decision | Rationale | Status |
|----------|-----------|--------|
| python-calamine для xlsx | 1С TDSheet без sharedStrings.xml ломает openpyxl | ✓ Verified |
| Средневзвешенная себестоимость | Проще, устойчиво к скачкам курса | Pending impl |
| Курс для `в рублях/` = API ЦБ РФ по дате | Нет курса в имени файла | Pending impl |
| Формула USD = руб / курс / 1.038 / 1.16 | Проверено с пользователем | ✓ Locked |
| Только Google Sheets (без веб-дашборда) | Бесплатно, мобильно | ✓ Locked |
| MATCH — критический блок Phase 1 | Без единого ключа товара ничего не считается | ✓ In roadmap |
| BOT последней фазой | Нужен работающий пайплайн Phase 1-5 | ✓ In roadmap |
| EAN normalize: int(float(v)), не str(v) | calamine отдаёт float; str() оставляет хвост '.0' и портит ключ | ✓ Verified (01-01) |
| EAN-исключения в одной функции normalize_ean | Samples (9999...), test SKU (^\d{13}-\d+$), footer (<=1e12) — авторитет в одном месте | ✓ Verified (01-01) |
| Курс ЦБ: windows-1251 + запятая-десятич / Nominal | CBR XML_daily.asp возвращает так; dict-кэш по date.isoformat() | ✓ Verified (01-01) |
| Дубли EAN в одном приходе = партии, не дедуплицировать | Разные цены в одной накладной; Phase 2 считает средневзвешенную себестоимость | ✓ Verified (01-02) |
| rate_source ('filename'/'cbr_api') в каждой строке | Аудит источника курса для расчёта себестоимости | ✓ Verified (01-02) |
| sys.path bootstrap в __main__ парсеров | Модуль работает как `python src/...`, `-m` и под pytest без ModuleNotFoundError | ✓ Verified (01-02) |
| prodazhi: брать EAN-строку, эмитить (ean,месяц) только при ненулевом qty/revenue | Схлопывает Покупатель-группировку; 12409 строк vs 43098 при полной сетке | ✓ Verified (01-03) |
| ostatki: qty_stock может быть отрицательным (4 EAN, мин -24), не обнулять | В 1С резерв > остатка → отрицательный «Свободный остаток» = сигнал срочного дозаказа | ✓ Verified (01-03) |
| ostatki: col[1] «Свободный остаток» напрямую, без агрегации по складам | Файл уже сводный, разбивки по складам в нём нет | ✓ Verified (01-03) |
| MATCH: приходы=spine, продажи/остатки left-join на int EAN (без fuzzy/str) | Все 3 источника уже дают int EAN через normalize_ean; join int==int | ✓ Verified (01-04) |
| master хранит ссылку на продажи (has_sales+qty_sold_total), не 33 колонки | master = одна строка на EAN; помесячная детализация в prodazhi.parquet | ✓ Verified (01-04) |
| Партийная детализация прихода (partii list) сохранена в master | Phase 2 средневзвешенная себестоимость требует цену каждой партии | ✓ Verified (01-04) |
| qty_stock = NaN (не 0) для 345 EAN без остатка | Отличает «нет записи об остатке» от реального нуля | ✓ Verified (01-04) |
| cost_usd = price_rub / rate_usd / 1.038 / 1.16; price_rub PER-UNIT (делить напрямую) | Зафиксированная формула себестоимости (COST-01) | ✓ Verified (02-01) |
| Средневзвешенная себестоимость = вес qty (штуки), НЕ число партий | COST-02 «вес = количество»; на EAN 4525807270297 wavg=0.027056 ≠ наивное среднее партий 0.026153 | ✓ Verified (02-01) |
| Курс заморожен в Phase 1 — Phase 2 НЕ зовёт CBR API, читает rate_usd/rate_source из партий | Источник курса уже зафиксирован; повторный вызов = риск расхождения | ✓ Verified (02-01) |
| Коэффициенты в одном месте (COEF_LOGISTICS=1.038, COEF_MARKUP=1.16), не инлайнить | Единый источник истины для формулы себестоимости | ✓ Verified (02-01) |
| master_cost.parquet — новый файл, master.parquet не мутируется | Обратимость: Phase 1 артефакт остаётся стабильным | ✓ Verified (02-01) |
| Идемпотентная запись Sheets: clear→ОДИН update (не delete+recreate) | sheetId 862692016 сохранён для Phase 4; повторный прогон не дублирует | ✓ Verified (03-02) |
| Seasonal index formula: index[m] = avg_cal_month_sales / global_avg; 12 avg ≈ 1.0 | Нормированные, сравнимые между собой; неполные годы — среднее по доступным | ✓ Locked (04-02) |
| Per-model threshold: ≥30 total qty AND ≥6 cal months with sales | Claude's Discretion; 53/76 моделей прошли на реальных данных | ✓ Verified (04-02) |
| November seasonal index 0.778 < 1 — known deviation, не баг | Ноябрь 2023 скудный (первый месяц выгрузки, линейка ещё не появилась); тест не требует Nov>1 | ✓ Documented (04-02) |
| match_models из timon_normalize — единственный авторитет; ad-hoc regex запрещён | 76 канонических моделей + word-boundary + апостроф-устойчивость уже решены | ✓ Locked (04-02) |
| order_plan.py — чистый вычислительный модуль, НЕ импортирует build_report | Односторонняя зависимость build_report→order_plan; Pitfall 5 предотвращён | ✓ Verified (04-03) |
| avg_season_idx подаётся параметром в compute_order_qty/enrich_df | Избегает циклического импорта seasonality; caller вычисляет avg(jul,aug) один раз | ✓ Locked (04-03) |
| Залежалый порог: DSI > 90 дн ИЛИ возраст > 180 дн (при ненулевых продажах 12 мес) | Claude's Discretion задокументирован; STALE_DSI_THRESHOLD/STALE_AGE_THRESHOLD в order_plan.py | ✓ Documented (04-03) |
| presort_by_dsi НЕ вызывается внутри enrich_df — только из build_report после сборки всех колонок | Иначе sort переупорядочит строки до добавления monthly колонок | ✓ Locked (04-03) |
| build_rows() возвращает (rows, df) кортеж чтобы main() передал df в format_sheet без повторного пересчёта | Экономит ~40-50 сек парсинга; df нужен для format_sheet после write_report | ✓ Verified (04-04) |
| _col_letter() в apply_formatting: column letter из 0-based index без импорта gspread | Позволяет тестировать format_sheet с FakeWorksheet без сетевых зависимостей | ✓ Verified (04-04) |
| build_season_rows() явно float() конвертирует np.float64 сезонных индексов | gspread и df_to_rows требуют Python-типы; np.float64 — numpy leak | ✓ Verified (04-04) |
| ROADMAP критерий #4: «мёртвый остаток» = 12 мес (не 6) | User override задокументирован в 04-CONTEXT.md LOCKED; формула уже использует 12 мес в order_plan.py | ✓ Locked (04-04) |
| Креды gspread из env GOOGLE_APPLICATION_CREDENTIALS + fallback sibling-путь | .gitignore блокирует *.json/.env; ключ никогда не в VCS (проверено git check-ignore) | ✓ Verified (03-02) |
| Сетевой слой изолирован в sheets_client; build_rows() офлайн, main() единственная точка сети | Запись покрыта мок-тестом без сети; main() не вызывается на импорте | ✓ Verified (03-02) |
| .gitignore не игнорирует parquet/data (только секреты + *.xlsx) | Репо CLODYA — монорепо, parquet-артефакты осознанно версионируются; точечные ! для 2 легитимных interim JSON | ✓ Verified (03-02) |

### Source Data Files

| Файл | Содержимое | Особенность |
|------|-----------|-------------|
| `поступления товаров/*.xlsx` | Приходы, курс в имени файла | TDSheet, python-calamine |
| `поступления товаров/в рублях/*.xlsx` | Приходы без курса (5 файлов) | Курс = API ЦБ РФ по дате |
| `все продажи с 2023 по 26июня2026.xlsx` | Помесячные продажи Покупатель→Номенклатура | окт.2023–июнь.2026 |
| `остатки все 260626.xlsx` | Остатки по EAN, уже сводные | Только «Свободный остаток» (col[1]), без разбивки по складам |
| `снасти приманки продажи по неделям.xlsx` | Справочно, листы «По моделям», «Сезонность» | Без разбивки на цвета |

### Known Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Сопоставление имён (3 схемы наименования: приход EAN+«Товар», продажи/остатки «Номенклатура») | HIGH — критический | EAN как первичный ключ + fuzzy по имени + отчёт о несопоставленных (MATCH-02) |
| Файлы `в рублях/` без курса | MEDIUM | API ЦБ РФ по дате накладной |
| Google Sheets API лимиты при большом числе строк | LOW | Batch writes, gspread |

### Todos

- [ ] Перед Phase 1: уточнить, какой из service-account JSON файлов использовать для целевого Sheet
- [ ] Перед Phase 1: проверить диапазон реальных данных (сколько уникальных товаров в приходах)
- [ ] Перед Phase 6: уточнить хостинг бота (Railway/Amvera по образцу sales-bot)

### Blockers

None.

---

## Session Log

| Date | Session | What happened |
|------|---------|---------------|
| 2026-06-26 | 1 | Project initialized. PROJECT.md + REQUIREMENTS.md + ROADMAP.md + STATE.md created. 26 requirements mapped to 6 phases. |
| 2026-06-26 | 2 | Executed plan 01-01 (foundation). normalize_ean + cbr_rates.get_usd_rate built TDD; 5 green tests + 10 red-pending Test Map. DATA-04, MATCH-01, MATCH-01b done. Stopped at: Completed 01-01-PLAN.md. |
| 2026-06-26 | 3 | Executed plan 01-02 (приход parser). parse_prikhody.py built TDD; 4 green приход tests. 21 files → prikhody.parquet (2788 rows, 1300 EAN). курс из имени (16) + CBR по дате (5). DATA-01, DATA-04, MATCH-01b done. Stopped at: Completed 01-02-PLAN.md. |
| 2026-06-26 | 3 | Executed plan 01-03 (продажи + остатки parsers). parse_prodazhi.py (12409 строк, 1306 EAN, 33 месяца) + parse_ostatki.py (959 EAN, отрицательные остатки сохранены) built TDD; 3 green tests. DATA-02, DATA-03 done. Stopped at: Completed 01-03-PLAN.md. |
| 2026-06-26 | 4 | Executed plan 01-04 (matcher). build_master.py built TDD — приходы=spine (1300 EAN), left-join продажи/остатки на int EAN. master.parquet (1300 строк, партийная детализация) + unmatched_report.json (24 sale + 4 stock без прихода). Coverage: sales 98.16% (1282/1306), stock 99.58% (955/959), оба >90%. Все 15 тестов Phase 1 green. MATCH-01, MATCH-02 done. Phase 1 COMPLETE. Stopped at: Completed 01-04-PLAN.md. |
| 2026-06-27 | 5 | Executed plan 02-01 (себестоимость USD). compute_cost.py built TDD — cost_usd_per_unit (формула руб/курс/1.038/1.16, 3 оракла) + weighted_avg_cost (вес=qty, 0.027056 на EAN 4525807270297) + enrich (читает master.parquet input-only, БЕЗ CBR). master_cost.parquet (1300 EAN / 2788 партий, cost_usd на каждой партии + per-EAN cost_usd_wavg). Все 19 тестов (15 Phase 1 + 4 Phase 2) green, без регрессий. master.parquet не тронут. COST-01/02/03 done. Phase 2 COMPLETE. Финализация (SUMMARY/STATE/ROADMAP/REQUIREMENTS) выполнена в этой сессии — код был закоммичен ранее. Stopped at: Completed 02-01-PLAN.md. |
| 2026-06-27 | 6 | Executed plan 03-01 (основной отчёт — сборка DataFrame). report_metrics.py (month_sort_key/sht_per_month/dsi_days/stock_age_days/cumulative) + build_report.py (build_report_df 1300×78 + df_to_rows сериализация) built TDD. Spine = master_cost (все 1300 EAN, samples отсутствуют); 33 хронологических помесячных + 33 «Кум. » колонки; DSI «» при NaN/≤0/нулевой скорости; возраст=RUN_DATE−max invoice_date. Oracle EANs 4525807270297/270280 — накопит. продажи совпали с prodazhi. Все 25 тестов (19 Phase 1/2 + 6 Phase 3) green, без регрессий. gspread НЕ импортируется (запись — Plan 02). REPORT-01..05 done. Auto-fix Rule 1: возраст как native-int (dtype=object) против np.int64-апкаста. Stopped at: Completed 03-01-PLAN.md. |
| 2026-06-27 | 8 | Executed plan 04-02 (сезонные индексы). src/seasonality.py built TDD — compute_global_seasonal_index (12 нормированных индексов, avg≈1.0), avg_next2_index (Jul+Aug=0.770 — ORDER-02 multiplier), extract_model (match_models()[0] из TIMON справочника), compute_model_seasonal_index (53/76 TIMON моделей прошли порог min_qty=30/min_months=6), season_index_for_ean (model или global fallback). Oracle verified: Apr=1.516, Sep=1.623, Oct=1.439 >1; Jan=0.349 <1. Known deviation: Nov=0.778<1 (sparse Nov 2023, зафиксировано в SUMMARY). 6 новых тестов GREEN; full suite 44 passed, 0 regressions. SEASON-01 done. Commit 4e91b91. Stopped at: Completed 04-02-PLAN.md. |
| 2026-06-27 | 7 | Executed plan 03-02 (запись в Google Sheets). .gitignore (SECURITY-гейт первым: *.json/.env/credentials блокированы, легитимные interim JSON через !; проверено git check-ignore, NO_KEY_TRACKED_OK). sheets_client.py (get_client из env GOOGLE_APPLICATION_CREDENTIALS+fallback; идемпотентная write_report clear→ОДИН update). report_to_sheets.py (build_rows() офлайн 1301×78; main() живой write). Мок-тест test_write_is_idempotent_mocked — clear-before-update, single-update, no-dup, без сети; полная сьюта 26 green. ЖИВОЙ WRITE выполнен (human-verify gate предочищен — Editor подтверждён): 1300 строк в лист «Отчёт», sheetId 862692016, месяцы Окт2023→Июн2026, oracle 270297 (87==offline) / 270280 (61==offline), idempotent на повторном прогоне. Auto-fix Rule 3: scope .gitignore под монорепо CLODYA (root, не сезонност) — parquet не игнорируется (осознанно версионируется). REPORT-01..05 done. Phase 3 COMPLETE. Stopped at: Completed 03-02-PLAN.md. |

| 2026-06-27 | 9 | Executed plan 04-03 (order_plan pure compute). src/order_plan.py создан: pct_sales, compute_order_qty (ORDER-01/02, порог 60%, neg-stock=0), is_dead, is_stale (SEASON-02, 12 мес Jul2025..Jun2026), presort_by_dsi (VISUAL-03, red-first secondary DSI asc), enrich_df (6 колонок M-R). Pitfall 5 guard: build_report НЕ импортируется. Oracle EAN 4525807270297: К заказу = 4.4 шт (verified). 8 новых тестов; полная сьюта 44 passed (было 30), 0 регрессий. Commit 5acd0b2. ORDER-01/02, SEASON-02, VISUAL-03 done. Stopped at: Completed 04-03-PLAN.md. |
| 2026-06-27 | 10 | Executed plan 04-04 (integration). build_report_df расширен до 84 колонок: availability-velocity (months_in_stock per EAN из weekly файла), enrich_df M-R, presort_by_dsi. Oracle DSI=18.6/К заказу=4.4 подтверждены. apply_formatting.py создан: build_format_requests + format_sheet (один ws.batch_format). report_to_sheets.py расширен: build_rows()->(rows,df), build_season_rows() (12 индексов, plain float), main() пишет «Отчёт»+заливку+«Сезонность». Оба xfail сняты. 52 тестов GREEN. ROADMAP крит#4=12 мес, крит#3 known-deviation note добавлена. Commits c1294cd/38573d8/2475c0d/7f91a30. Stopped at: CHECKPOINT human-verify Task 4 (live Sheets write pending). |
| 2026-06-30 | 11 | Executed plan 06-01 (Phase 6 foundation). Task 1: report_to_sheets.main()->int (return n, sweep 0 callers, 843ca9c). Task 2: bot/ package — config.py (Config dataclass, load_config, env-secrets, allowed_user_id=188032358), keyboards.py (file_type_keyboard 3 ftype: buttons), __init__.py (d659806). Task 3: Wave 0 pytest scaffold — tests/test_bot_handlers.py + test_bot_pipeline.py + test_bot_backup.py + test_bot_scheduler.py (9 xfail stubs BOT-01..04); conftest.py + bot_config + fake_xlsx_short fixtures (dc0863c). Full suite: 66 passed, 9 xfailed, 0 collection errors. BOT-01/02/03/04 scaffolded. Stopped at: Completed 06-01-PLAN.md. |

---

## Next Action

Phase 6 Plan 01 COMPLETE. Следующий шаг: выполнить 06-02-PLAN.md (backup/restore/validate — бэкап+откат+валидация входящих файлов, fail-closed логика). Стабы test_bot_backup.py уже в месте, fixture bot_config готова.

---
*STATE created: 2026-06-26*
*Last updated: 2026-06-27 (session 9 — completed 04-03, order_plan pure compute, 44 tests green)*
