from app.bot.texts import CONSENT_TEXT, PARTNER_START_TEXT, START_TEXT


def test_start_text_explains_product() -> None:
    assert "расчётные счета" in START_TEXT
    assert "вопрос" in START_TEXT
    assert "до 20 000 ₽" in START_TEXT
    assert all(emoji in START_TEXT for emoji in ("📬", "💰", "🏦", "🧬", "🎯", "🛠️", "💸"))
    assert START_TEXT.count("<blockquote>") == START_TEXT.count("</blockquote>") == 4


def test_partner_start_text_explains_cabinet() -> None:
    assert "партнёрская ссылка" in PARTNER_START_TEXT
    assert "Статистика" in PARTNER_START_TEXT
    assert "Ваше вознаграждение" in PARTNER_START_TEXT
    assert all(emoji in PARTNER_START_TEXT for emoji in ("📬", "🏗️", "🔗", "📊", "💰"))
    assert PARTNER_START_TEXT.count("<blockquote>") == 1
    assert PARTNER_START_TEXT.count("</blockquote>") == 1


def test_welcome_texts_use_premium_custom_emoji() -> None:
    assert START_TEXT.count("<tg-emoji ") == START_TEXT.count("</tg-emoji>") == 9
    assert PARTNER_START_TEXT.count("<tg-emoji ") == 5
    assert PARTNER_START_TEXT.count("</tg-emoji>") == 5
    assert 'emoji-id="5199885118214255386"' in START_TEXT
    assert 'emoji-id="5199885118214255386"' in PARTNER_START_TEXT


def test_consent_names_data_purpose_and_withdrawal() -> None:
    assert "номер телефона" in CONSENT_TEXT
    assert "помочь с открытием расчётного счёта" in CONSENT_TEXT
    assert "Отозвать согласие" in CONSENT_TEXT
    assert "@KryGerMan" in CONSENT_TEXT
