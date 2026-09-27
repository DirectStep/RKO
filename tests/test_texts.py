from app.bot.keyboards import partner_documents_keyboard
from app.bot.texts import (
    CONSENT_TEXT,
    PARTNER_START_TEXT,
    START_TEXT,
    consent_prompt,
    partner_documents_prompt,
)


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


def test_lead_welcome_places_round_emoji_before_ready_prompt() -> None:
    payout_text = "Обычно выплата производится <b>через 1 месяц после активации счёта</b>."
    ready_text = '<tg-emoji emoji-id="5355294670119263003">⏳</tg-emoji> Готовы начать?'

    assert f"\n{payout_text}" in START_TEXT
    assert ready_text in START_TEXT
    assert "Готовы начать? ⬇️" not in START_TEXT


def test_consent_names_data_purpose_and_withdrawal() -> None:
    assert "номер телефона" in CONSENT_TEXT
    assert "помочь с открытием расчётного счёта" in CONSENT_TEXT
    assert "Отозвать согласие" in CONSENT_TEXT
    assert "@KryGerMan" in CONSENT_TEXT
    assert "Данелян Артем Каренович" in CONSENT_TEXT
    assert "Перед публичным запуском" not in CONSENT_TEXT


def test_consent_prompt_links_client_offer_and_privacy_documents() -> None:
    prompt = consent_prompt("https://app.example.test/?v=1")

    assert prompt == (
        "Нажимая «Принимаю оферту», я принимаю "
        '<a href="https://app.example.test/documents/oferta-client-20260927.pdf">'
        "Публичную оферту для клиента</a>.\n\n"
        "Нажимая «Даю согласие на ПДн», я даю "
        '<a href="https://app.example.test/documents/soglasie-pdn.pdf">'
        "Согласие на обработку персональных данных</a> и подтверждаю, что "
        "ознакомился(-ась) с "
        '<a href="https://app.example.test/documents/politika-pdn.pdf">'
        "Политикой обработки персональных данных</a>."
    )


def test_partner_documents_are_linked_and_confirmed_separately() -> None:
    prompt = partner_documents_prompt("https://app.example.test/?v=1")
    keyboard = partner_documents_keyboard(offer_accepted=False, pdn_consented=False)

    assert 'href="https://app.example.test/documents/oferta-partner-20260927.pdf"' in prompt
    assert 'href="https://app.example.test/documents/politika-pdn.pdf"' in prompt
    assert 'href="https://app.example.test/documents/soglasie-pdn.pdf"' in prompt
    assert "Нажимая «Принимаю оферту», я принимаю" in prompt
    assert "Нажимая «Даю согласие на ПДн», я даю" in prompt
    assert keyboard is not None
    assert [row[0].callback_data for row in keyboard.inline_keyboard] == [
        "partner:accept_offer",
        "partner:consent_pdn",
    ]
    remaining = partner_documents_keyboard(offer_accepted=True, pdn_consented=False)
    assert remaining is not None
    assert [row[0].callback_data for row in remaining.inline_keyboard] == [
        "partner:consent_pdn"
    ]
    assert partner_documents_keyboard(offer_accepted=True, pdn_consented=True) is None
