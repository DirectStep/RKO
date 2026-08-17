# РКО-трекер лидов

Новый Telegram-бот для учёта партнёрских РКО-лидов, банков и выплат.

## Локальный запуск

1. Скопировать `.env.example` в `.env` и указать Telegram-токен.
2. Запустить `docker compose up --build`.
3. Проверить подключение к БД: `docker compose run --rm bot python3 -m app.healthcheck`.

## Проверки

```powershell
python3 -m pip install -r requirements-dev.txt -c constraints.txt
python3 -m ruff check .
python3 -m mypy app
python3 -m pytest
```

## Структура

- `app/bot` — Telegram-обработчики и тексты интерфейса.
- `app/config.py` — конфигурация окружения.
- `app/database.py` — подключение к PostgreSQL.
- `app/domain` — бизнес-правила без зависимости от Telegram и внешних API.
- `app/integrations` — Google Sheets и другие внешние сервисы.
- `app/workers` — фоновые задания и расписание.
- `app/reports` — формирование Excel-отчётов.
- `app/models.py` — ORM-модели.
- `migrations` — миграции Alembic.
- `tests` — автоматические проверки.
