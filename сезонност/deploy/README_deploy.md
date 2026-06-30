# Деплой skladetbot на VPS 155.212.142.12

Telegram-бот обновления складской аналитики TIMON. Принимает xlsx (леджер / недельные остатки /
накладная), пересчитывает пайплайн и обновляет Google Sheet, отвечает «обновлено N строк».
Раз в неделю (пн 09:00 МСК) шлёт владельцу напоминание.

**VPS:** `root@155.212.142.12` (Beget, Python 3.12.3, timezone UTC).
**Каталог:** `/root/skladetbot/`.

---

## ⛔ Секреты — только на VPS, НЕ в VCS

Три переменные в `/root/skladetbot/.env` + JSON-ключ сервис-аккаунта на VPS. В репозиторий не
коммитятся (`.gitignore` блокирует `*.json`/`.env`).

| Переменная | Значение / источник |
|---|---|
| `skladetbot_BOT_TOKEN` | ключ `skladetbot_BOT_TOKEN` из `C:/Users/abirv/Desktop/CLODYA/.env` |
| `GOOGLE_APPLICATION_CREDENTIALS` | `/root/skladetbot/google_credentials.json` |
| `ALLOWED_USER_ID` | `188032358` (владелец) |

Service-account: `bot-worker@sales-bot-personal` (тот же, что в Phase 3 делал живой write).
Файл: `C:/Users/abirv/Desktop/CLODYA/market_scout/google_credentials.json`.

---

## Шаги

### 1. Доставка проекта
```bash
rsync -az --delete \
  --exclude '.git' --exclude '.planning' --exclude 'data/interim/_bak*' \
  --exclude '__pycache__' --exclude '.pytest_cache' --exclude 'tests' \
  ./ root@155.212.142.12:/root/skladetbot/
```
(Если `/root/skladetbot` уже существует — снапшот перед заменой: `cp -a /root/skladetbot /root/skladetbot.bak_<ts>`.)

### 2. venv + зависимости
```bash
ssh root@155.212.142.12 "python3 -m venv /root/skladetbot/venv && \
  /root/skladetbot/venv/bin/pip install -q --upgrade pip && \
  /root/skladetbot/venv/bin/pip install -q \
    aiogram==3.15.0 python-dotenv==1.0.1 aiofiles apscheduler==3.11.2 \
    python-calamine pyarrow pandas gspread==6.1.4 google-auth==2.37.0"
```
Проверка импорта (Pitfall 2 — calamine):
```bash
ssh root@155.212.142.12 "/root/skladetbot/venv/bin/python -c 'import python_calamine, aiogram, gspread, pandas, pyarrow, apscheduler; print(\"DEPS_OK\")'"
```

### 3. Секреты
```bash
scp C:/Users/abirv/Desktop/CLODYA/market_scout/google_credentials.json \
  root@155.212.142.12:/root/skladetbot/google_credentials.json
# .env создаётся на VPS; значение токена вписывает владелец (не выводится в чат).
ssh root@155.212.142.12 "test -f /root/skladetbot/.env && test -f /root/skladetbot/google_credentials.json && echo SECRETS_OK"
```

### 4. systemd
```bash
scp deploy/skladetbot.service root@155.212.142.12:/etc/systemd/system/skladetbot.service
ssh root@155.212.142.12 "systemctl daemon-reload && systemctl enable skladetbot && systemctl start skladetbot && systemctl is-active skladetbot"
```

### 5. Логи / smoke
```bash
ssh root@155.212.142.12 "journalctl -u skladetbot -n 30 --no-pager"
```
Ожидаем старт polling, без traceback про creds (Pitfall 1) или calamine (Pitfall 2).

---

## Живой e2e (владелец, с телефона)
1. `/start` в @skladetbot → инструкция.
2. Прислать `приходы остатки.xlsx` документом → выбрать «Леджер (приходы+продажи)».
3. Через ~1-2 мин — «обновлено N строк» (N ~1300); лист «Отчёт» в Sheet обновлён.
4. (Опц.) fail-closed: с чужого аккаунта файл → бот молчит.

---

## Verified (2026-06-30)

- Проект доставлен в `/root/skladetbot/` (tar over ssh; rsync на VPS отсутствует).
- venv создан, зависимости установлены; `DEPS_OK` (python_calamine/aiogram/gspread/pandas/pyarrow/apscheduler) + `BOT_IMPORT_OK` (bot.main/handlers/scheduler/pipeline/backup).
- Секреты: `/root/skladetbot/.env` (chmod 600) + `google_credentials.json` (chmod 600, `bot-worker@sales-bot-personal`). Токен передан по ssh, в чат/VCS не попадал.
- Токен валиден: `getMe` → **@skladetbot** id=8847131438, allowed_user=188032358.
- systemd: `is-active=active`, `is-enabled=enabled` (автозапуск после ребута).
- Логи старта: `Start polling`, `Run polling for bot @skladetbot`, scheduler «Weekly ledger reminder» добавлен. Нет traceback про creds (Pitfall 1) / calamine (Pitfall 2).
- **Ожидается:** живой e2e владельцем с телефона (Task 4, human-verify).
