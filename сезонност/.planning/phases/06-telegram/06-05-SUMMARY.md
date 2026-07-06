---
phase: 06-telegram
plan: 05
subsystem: deploy-vps
tags: [systemd, vps, ssh, e2e, aiogram, incremental-gap]
completed: 2026-07-06
tasks: 3/4 (Task 4 e2e выявил дизайн-разрыв → план 06-06)
---

# Phase 06 Plan 05: Деплой skladetbot на VPS + e2e

## Итог
Бот **@skladetbot** (id 8847131438) развёрнут на VPS 155.212.142.12 как systemd-сервис
(`skladetbot`, polling, Restart=always, autostart). Живой e2e прошёл частично: базовый
поток работает (приём xlsx → выбор типа → пересчёт → «обновлено N строк»), но вскрыл
дизайн-разрыв (full-replace vs инкремент) → план 06-06.

## Задачи
1. **systemd unit + доставка + venv** — `deploy/skladetbot.service`, `deploy/README_deploy.md`;
   проект доставлен tar-over-ssh (rsync на VPS нет); venv + deps; `DEPS_OK`+`BOT_IMPORT_OK`. ✓
2. **Секреты** — `/root/skladetbot/.env` (chmod 600) + `google_credentials.json`
   (`bot-worker@sales-bot-personal`). Токен передан по ssh без вывода в чат; `getMe` →
   @skladetbot валиден. Замечание: ключ в `CLODYA/.env` был закомментирован (`#`). ✓
3. **systemd запуск** — `is-active=active`, `is-enabled=enabled`, логи чистые. ✓
4. **Живой e2e** — выявил дефекты (исправлены) + дизайн-разрыв (→ 06-06). См. ниже.

## Дефекты, найденные и исправленные в e2e
1. **Сигнатура backup_artifacts (06-02↔06-03).** pipeline звал `backup_artifacts(file_type)`
   без `config`; producer требует `(file_type, config)`. Скрыто 1-арг моками. Фикс:
   `load_config()` + передача config; +2 реальных integration-теста. Commit `754dce1`.
2. **Пустая строка 1С после артикула.** parse_ledger сбрасывал `cur_ean` на любой не-EAN
   не-дата строке (вкл. пустую) → все движения orphan → 0 продаж → `float division by zero`
   в build_master. Фикс: пустой col0 не сбрасывает cur_ean (только текст-заголовок);
   guard деления; guard 0-продаж; +тесты. 0 регресса на исходном файле. Commit `f421a28`.
3. **Логирование:** handler не логировал traceback исключения пайплайна (только str(e)
   пользователю) — traceback пришлось воспроизводить на VPS. TODO для 06-06: логировать
   traceback в journal.

## Дизайн-разрыв → план 06-06 (BLOCKING для «готово»)
Пайплайн леджера делает **full-replace** (`write_artifacts` пересобирает prodazhi целиком).
Рабочий процесс пользователя — **инкрементальный** (шлёт только новый период, бот мержит).
1-месячный файл затёр историю (восстановлено из бэкапа; Google откатил пользователь).
Подтверждённая merge-семантика и настройки выгрузки — в `06-06-REQUIREMENTS.md`.

## Артефакты
- `deploy/skladetbot.service`, `deploy/README_deploy.md` (commit `fe030be`).
- VPS: `/root/skladetbot/` (venv, .env, creds, unit). Baseline parquet восстановлен (33 мес).

## Self-Check
- [x] systemd active + enabled, polling @skladetbot
- [x] Секреты только на VPS (не в VCS/чате)
- [x] Базовый e2e-поток работает (full-replace)
- [ ] Инкрементальный поток — план 06-06 (не реализован)

## Self-Check: PARTIAL (deploy done; incremental gap → 06-06)
