from app.bot.texts import CONSENT_TEXT, START_TEXT


def test_start_text_explains_product() -> None:
    assert "расчётные счета" in START_TEXT
    assert "вопрос" in START_TEXT


def test_consent_names_data_purpose_and_withdrawal() -> None:
    assert "номер телефона" in CONSENT_TEXT
    assert "помочь с открытием расчётного счёта" in CONSENT_TEXT
    assert "Отозвать согласие" in CONSENT_TEXT
    assert "@KryGerMan" in CONSENT_TEXT
