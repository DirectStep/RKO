from html.parser import HTMLParser

import pytest

from app.bot.texts import (
    application_registered_message,
    bank_selection_confirmation,
    client_status_changed_message,
)


class MessageMarkup(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[str] = []
        self.emoji_ids: list[str] = []
        self.quotes = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        assert tag in {"tg-emoji", "blockquote", "b", "i"}
        assert not (tag == "blockquote" and "blockquote" in self.stack)
        self.stack.append(tag)
        if tag == "tg-emoji":
            emoji_id = dict(attrs)["emoji-id"]
            assert emoji_id is not None
            self.emoji_ids.append(emoji_id)
        if tag == "blockquote":
            self.quotes += 1

    def handle_endtag(self, tag: str) -> None:
        assert self.stack.pop() == tag


@pytest.mark.parametrize(
    ("message", "emoji_ids", "quote_count"),
    [
        (
            bank_selection_confirmation("@manager"),
            ["5357146861880760304", "5226831738734400762", "5440621591387980068"],
            4,
        ),
        (
            application_registered_message("RKO-0059"),
            ["5357146861880760304", "5440621591387980068"],
            1,
        ),
        (
            client_status_changed_message("Выберите банки"),
            ["5188234920639632382", "5334544901428229844"],
            4,
        ),
    ],
)
def test_client_notification_markup_matches_reference(
    message: str, emoji_ids: list[str], quote_count: int
) -> None:
    parser = MessageMarkup()
    parser.feed(message)
    parser.close()
    assert parser.stack == []
    assert parser.emoji_ids == emoji_ids
    assert parser.quotes == quote_count


def test_selection_message_matches_requested_copy() -> None:
    message = bank_selection_confirmation("@manager")
    assert "Спасибо, выбор отправлен!" in message
    assert "Ваш персональный менеджер:\n<blockquote>@manager</blockquote>" in message
    assert (
        '<blockquote><tg-emoji emoji-id="5440621591387980068">🔜</tg-emoji>'
        "</blockquote>\n<blockquote>\u2800</blockquote>\n"
        "<blockquote>Скоро с вами свяжутся и создадут отдельную группу: "
        "там будут все инструкции и можно будет задать любые вопросы!</blockquote>"
    ) in message


def test_registration_keeps_application_number() -> None:
    message = application_registered_message("RKO-0059")
    assert "Заявка RKO-0059 успешно зарегистрирована\n\n" in message
    assert "Скоро с вами свяжется специалист!</blockquote>" in message


def test_status_message_highlights_actual_status_and_cabinet_hint() -> None:
    message = client_status_changed_message("Заявка завершена")
    assert "Статус вашей заявки изменён:\n" in message
    assert "<blockquote><b>Заявка завершена</b></blockquote>" in message
    assert "</tg-emoji></blockquote>\n<blockquote>\u2800</blockquote>\n" in message
    assert "<blockquote><i>Актуальная информация доступна в кабинете!</i></blockquote>" in message


@pytest.mark.parametrize(
    "formatter",
    [bank_selection_confirmation, application_registered_message, client_status_changed_message],
)
def test_dynamic_values_cannot_inject_telegram_markup(formatter) -> None:
    message = formatter('<b>Имя & "банк"</b>')
    assert "&lt;b&gt;Имя &amp; &quot;банк&quot;&lt;/b&gt;" in message
    parser = MessageMarkup()
    parser.feed(message)
    parser.close()
    assert parser.stack == []
