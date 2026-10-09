from html import escape


def manager_new_lead_message(
    application_number: str, client_name: str, telegram_username: str | None,
    phone: str, primary_admin: str,
) -> str:
    telegram = f"@{telegram_username.lstrip('@')}" if telegram_username else "Не указан"
    return (
        '<tg-emoji emoji-id="5244927342190541585">🆕</tg-emoji>'
        '<tg-emoji emoji-id="5244634919342192985">🆕</tg-emoji>\n'
        f"Новая заявка <code>{escape(application_number)}</code>\n\n"
        f"Клиент:\n<blockquote>{escape(client_name)}</blockquote>\n"
        f"Telegram:\n<blockquote>{escape(telegram)}</blockquote>\n"
        f"Телефон:\n<blockquote>{escape(phone)}</blockquote>\n\n"
        '<tg-emoji emoji-id="5226831738734400762">👤</tg-emoji> '
        "Первичный ответственный (ркошник):\n"
        f"<blockquote>{escape(primary_admin)}</blockquote>\n\n"
        '<tg-emoji emoji-id="5188234920639632382">🟢</tg-emoji> Статус:\n'
        "<blockquote>Клиент выбрал банки</blockquote>\n\n"
        '<tg-emoji emoji-id="5206357006864113601">👨‍💼</tg-emoji> '
        "Откройте заявку, чтобы взять её в работу и статус заявки перейдёт «в работе»\n\n\n"
        '<tg-emoji emoji-id="5188463524568926712">⚠️</tg-emoji> '
        "<i>Не забудьте сначала создать группу с лидом и ркошником и запросить "
        "недостающие данные <b>(улица и номер дома и ИНН)</b></i>"
    )


def bank_selection_confirmation(manager_name: str) -> str:
    return (
        '<tg-emoji emoji-id="5357146861880760304">🎉</tg-emoji> '
        "Спасибо, выбор отправлен!\n\n"
        '<tg-emoji emoji-id="5226831738734400762">👤</tg-emoji> '
        "Ваш персональный менеджер:\n"
        f"<blockquote>{escape(manager_name)}</blockquote>\n\n"
        '<blockquote><tg-emoji emoji-id="5440621591387980068">🔜</tg-emoji> '
        "Скоро с вами свяжутся и создадут отдельную группу: "
        "там будут все инструкции и можно будет задать любые вопросы!</blockquote>"
    )


def manager_changed_message(manager_name: str) -> str:
    return (
        '<tg-emoji emoji-id="5226831738734400762">👤</tg-emoji> '
        "Ваш персональный менеджер изменён:\n"
        f"<blockquote>{escape(manager_name)}</blockquote>\n\n"
        "Новый менеджер свяжется с вами и поможет с открытием счетов."
    )


def application_registered_message(application_number: str) -> str:
    return (
        '<tg-emoji emoji-id="5357146861880760304">🎉</tg-emoji> '
        f"Заявка {escape(application_number)} успешно зарегистрирована\n\n"
        '<blockquote><tg-emoji emoji-id="5440621591387980068">🔜</tg-emoji> '
        "Скоро с вами свяжется специалист!</blockquote>"
    )


def client_status_changed_message(status_label: str) -> str:
    return (
        '<tg-emoji emoji-id="5188234920639632382">🟢</tg-emoji> '
        "Статус вашей заявки изменён:\n"
        f"<blockquote><b>{escape(status_label)}</b></blockquote>\n\n"
        '<blockquote><tg-emoji emoji-id="5334544901428229844">ℹ️</tg-emoji> '
        "<i>Актуальная информация доступна в кабинете!</i></blockquote>"
    )


START_TEXT = (
    '<tg-emoji emoji-id="5199885118214255386">📬</tg-emoji> '
    "<b>ДОБРО ПОЖАЛОВАТЬ!</b>\n\n"
    '<tg-emoji emoji-id="5278467510604160626">💰</tg-emoji> '
    "<b>Открывайте расчётные счета — получайте до 20 000 ₽</b>\n\n"
    '<tg-emoji emoji-id="5332455502917949981">🏦</tg-emoji> '
    "Выбирайте банки, открывайте расчётные счета и получайте деньги за их открытие.\n\n"
    "<b>КАК ВСЁ ПРОИСХОДИТ?</b>\n\n"
    '<blockquote><tg-emoji emoji-id="5381828389663431280">🧬</tg-emoji> '
    "<b>1. Оформляете расширенную самозанятость (ИП на НПД)</b>\n"
    "Короткая встреча с представителем банка и ожидание регистрации около "
    "5 рабочих дней.</blockquote>\n\n"
    '<blockquote><tg-emoji emoji-id="5382051178207007027">🎯</tg-emoji> '
    "<b>2. Выбираете банки и открываете счета</b>\n"
    "Вы сами решаете, в каких банках открыть счета и сколько их будет. "
    "Часть банков открывается онлайн, часть — после короткой встречи.</blockquote>\n\n"
    '<blockquote><tg-emoji emoji-id="5379910025340802255">🛠️</tg-emoji> '
    "<b>3. Выполняете действия для активации счетов</b>\n"
    "Персональный менеджер даст понятные инструкции и поможет на каждом этапе.</blockquote>\n\n"
    '<blockquote><tg-emoji emoji-id="5388624247696412237">💸</tg-emoji> '
    "<b>4. Получаете выплату</b>\n"
    "После выполнения условий банка остаётся дождаться вознаграждения. "
    "Если счета вам больше не нужны, после выплаты их можно закрыть в обычном порядке."
    "</blockquote>\n\n"
    '<tg-emoji emoji-id="5372957680174384345">🛰️</tg-emoji> '
    "Мы сопровождаем вас на каждом этапе и помогаем пройти весь процесс.\n\n"
    "Обычно выплата производится <b>через 1 месяц после активации счёта</b>.\n\n"
    '<tg-emoji emoji-id="5355294670119263003">⏳</tg-emoji> '
    "Готовы начать?\n\n"
    "Нажмите «Продолжить», чтобы ответить на несколько коротких вопросов."
)

PARTNER_START_TEXT = (
    '<tg-emoji emoji-id="5199885118214255386">📬</tg-emoji> '
    "<b>ДОБРО ПОЖАЛОВАТЬ!</b>\n\n"
    '<tg-emoji emoji-id="5332455502917949981">🏗️</tg-emoji> '
    "Здесь начинается ваш путь к дополнительному доходу с помощью "
    "партнёрской программы РКО.\n\n"
    "Привлекайте свою аудиторию и получайте вознаграждение за каждого "
    "привлечённого клиента.\n\n"
    "<b>Всё необходимое — в одном месте:</b>\n\n"
    '<blockquote><tg-emoji emoji-id="5271604874419647061">🔗</tg-emoji> '
    "<b>Ваша партнёрская ссылка</b>\n"
    "Привлекайте клиентов быстро и удобно.\n\n"
    '<tg-emoji emoji-id="5190806721286657692">📊</tg-emoji> '
    "<b>Статистика</b>\n"
    "Отслеживайте привлечённых клиентов и результаты своей работы.\n\n"
    '<tg-emoji emoji-id="5278467510604160626">💰</tg-emoji> '
    "<b>Ваше вознаграждение</b>\n"
    "Контролируйте размер начисленных бонусов.</blockquote>\n\n"
    "Мы сделали кабинет максимально простым, чтобы вы могли сосредоточиться "
    "на главном — привлечении клиентов и увеличении своего дохода."
)

PARTNER_OFFER_VERSION = "27.09.2026"
PARTNER_PDN_VERSION = "20.09.2026"
PRIVACY_DOCUMENT_VERSION = "20261009-2"


def consent_prompt(mini_app_url: str) -> str:
    public_root = mini_app_url.partition("?")[0].rstrip("/")
    consent_url = f"{public_root}/documents/soglasie-pdn.pdf?v={PRIVACY_DOCUMENT_VERSION}"
    policy_url = f"{public_root}/documents/politika-pdn.pdf?v={PRIVACY_DOCUMENT_VERSION}"
    offer_url = f"{public_root}/documents/oferta-client-20260927.pdf"
    return (
        "Нажимая «Принимаю оферту», я принимаю "
        f'<a href="{offer_url}">Публичную оферту для клиента</a>.\n\n'
        "Нажимая «Даю согласие на ПДн», я даю "
        f'<a href="{consent_url}">Согласие на обработку персональных данных</a> '
        "и подтверждаю, что ознакомился(-ась) с "
        f'<a href="{policy_url}">Политикой обработки персональных данных</a>.'
    )


def partner_documents_prompt(mini_app_url: str) -> str:
    public_root = mini_app_url.partition("?")[0].rstrip("/")
    return (
        "Партнёрский кабинет подключён.\n\n"
        "Нажимая «Принимаю оферту», я принимаю "
        f'<a href="{public_root}/documents/oferta-partner-20260927.pdf">'
        "Публичную оферту для партнёра</a>.\n\n"
        "Нажимая «Даю согласие на ПДн», я даю "
        f'<a href="{public_root}/documents/soglasie-pdn.pdf?v={PRIVACY_DOCUMENT_VERSION}">'
        "Согласие на обработку персональных данных</a> и подтверждаю, что "
        "ознакомился(-ась) с "
        f'<a href="{public_root}/documents/politika-pdn.pdf?v={PRIVACY_DOCUMENT_VERSION}">'
        "Политикой обработки персональных данных</a>.\n\n"
        "Кабинет уже доступен."
    )

CONSENT_TEXT = (
    "Согласие на обработку персональных данных\n\n"
    "Нажимая «Согласен», я добровольно разрешаю оператору сервиса «РКО» "
    "обрабатывать мои имя, Telegram-имя, Telegram ID, номер телефона, город "
    "и ответы анкеты.\n\n"
    "Данные используются, чтобы принять заявку, проверить её, связаться со мной "
    "и помочь с открытием расчётного счёта. Оператор может записывать, хранить, "
    "уточнять и удалять эти данные, а также передавать их сотрудникам и банкам "
    "только в объёме, необходимом для обработки заявки.\n\n"
    "Согласие действует до достижения этой цели или моего отзыва. Отозвать согласие "
    "можно сообщением администратору @KryGerMan. После отзыва данные удаляются, "
    "если закон не требует хранить их дольше.\n\n"
    "Оператор сервиса: Данелян Артем Каренович."
)
