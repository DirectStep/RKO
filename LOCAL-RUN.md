# РКО на ноутбуке

РКО переведён в Docker 3 октября 2026 года. Работают `bot`, `db` и `adminer` проекта Compose `rko-tracker`.

- `Start-RKO.cmd` запускает Docker Compose: базу, миграции, два Telegram-бота, миниапку и Adminer. Docker Desktop должен быть запущен.
- `Stop-RKO.cmd` останавливает контейнеры; данные сохраняются.
- Кабинет: https://app.xn--j1aalbgc.xn--p1ai (app.ркорко.рф). Открывайте его через кнопку в Telegram-боте: теперь вход требует данных Telegram.
- База и приложение имеют политику `restart: unless-stopped`. Если они были запущены, Docker Desktop восстановит их после перезапуска. После ручной остановки используйте `Start-RKO.cmd`.

Текущая база хранится в Docker volume `rko-tracker_postgres_data`. Она перенесена из свежего финального дампа `tmp/rko-docker-cutover-20261003-115100.dump` (50981 байт). Нативная база `tmp/pgdata-local` и настройки `tmp/windows-runtime.env` сохранены для восстановления; старый запуск остановлен. Не запускайте `tmp/rko_local.py start`: он предназначался для прежней конфигурации .env. Не удаляйте volume и не используйте `docker compose down -v`. Файлы из Downloads не изменены.

Миниапка привязана к 127.0.0.1 на хосте и опубликована через Cloudflare Tunnel. База не имеет опубликованного порта. APP_ENV=production, локальный вход администратора отключён. Без подписи Telegram /api/session возвращает 401; с корректной подписью /api/session и /api/dashboard возвращают 200. Проверено 3 октября 2026 года.

Туннель rko-local подключён на ноутбуке: 4 соединения Cloudflare зарегистрированы, HTTPS / возвращает 200 и миниапку. Контейнер cloudflared находится в локальном compose.override.yaml с профилем cloudflare. Он использует сеть контейнера bot (`network_mode: service:bot`), чтобы сохранённый маршрут Cloudflare `http://127.0.0.1:8090` работал без изменения удалённой конфигурации. Токен хранится в secrets/cloudflare-tunnel.token и монтируется read-only. Start-RKO.cmd запускает cloudflared вместе с приложением. При изменении контейнера bot запускайте все сервисы через Start-RKO.cmd, чтобы обновить и туннель.

Рабочие токены используются обоими ботами; экземпляр на прежнем компьютере должен оставаться остановленным. Доступ к Google Sheets действующий, фоновые синхронизации работают с общими таблицами. Интервал выгрузки установлен в 60 секунд, чтобы уменьшить число запросов к Google Sheets.

Логи текущего запуска: `docker compose logs bot`. Исторические логи Windows: `tmp/app.log`, `tmp/postgres.log`. Не публикуйте их целиком: они могут содержать персональные данные. Adminer доступен на http://localhost:8080.

Python-зависимости установлены из `requirements.txt` с ограничениями `constraints.txt`; для Windows дополнительно установлен `tzdata` (версия сохранена в `tmp/requirements-windows.txt`). Исполняемые файлы PostgreSQL находятся в `tmp/postgres-runtime`.
