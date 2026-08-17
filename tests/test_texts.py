from app.bot.texts import START_TEXT


def test_start_text_explains_product() -> None:
    assert "расчётные счета" in START_TEXT
    assert "вопрос" in START_TEXT
