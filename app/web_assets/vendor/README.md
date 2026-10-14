# Telegram Mini Apps SDK

`telegram-web-app.js` — неизменённая копия официального SDK,
полученная 14 октября 2026 года из `https://telegram.org/js/telegram-web-app.js?59`.

SHA-256: `124bdff7ba3fe86c8ba5143467afec21e020405e74abdb92cfdda6c0ee3b5908`.

Лицензия MIT и copyright Telegram Messenger находятся в `Telegram-SDK-LICENSE.txt`;
источник лицензии: `https://github.com/TelegramMessenger/TGMiniAppsJsSDK/blob/master/LICENSE`.

Сервер встраивает SDK в HTML до кода приложения. Запуск кабинета и сигнал
`web_app_ready` не зависят от отдельного запроса к telegram.org на устройстве.
При обновлении скачайте официальный файл без изменений, проверьте его checksum,
обновите параметр версии в index.html и маркер в build_mini_app_html.
