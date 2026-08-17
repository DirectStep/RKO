from app.bot.texts import START_TEXT


def test_start_text_explains_product() -> None:
    assert "РКО" in START_TEXT
    assert "заявк" in START_TEXT
