import pytest

from app.bot.handlers import format_application_review, parse_answer_callback
from app.bot.keyboards import (
    admin_lead_keyboard,
    admin_leads_keyboard,
    admin_partner_keyboard,
    application_edit_keyboard,
    application_review_keyboard,
    cabinet_keyboard,
    consent_document_keyboard,
    continue_keyboard,
    retry_submission_keyboard,
    yes_no_keyboard,
)
from app.domain.intake import QUESTIONS, QuestionKind, normalize_phone


def test_cabinet_button_requires_https() -> None:
    assert cabinet_keyboard("http://localhost:8090") is None
    keyboard = cabinet_keyboard("https://example.test/cabinet")
    assert keyboard is not None
    assert keyboard.inline_keyboard[0][0].web_app.url == "https://example.test/cabinet"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("8 (999) 123-45-67", "+79991234567"),
        ("+7 999 123 45 67", "+79991234567"),
        ("9991234567", "+79991234567"),
    ],
)
def test_normalize_russian_phone(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize("raw", ["123", "телефон", "+1234567890123456"])
def test_invalid_phone_is_rejected(raw: str) -> None:
    with pytest.raises(ValueError, match="корректный"):
        normalize_phone(raw)


def test_business_questionnaire_contains_six_questions_and_city() -> None:
    assert len(QUESTIONS) == 6
    assert (
        next(question for question in QUESTIONS if question.key == "city").kind is QuestionKind.TEXT
    )


def test_yes_no_questions_do_not_use_negative_wording() -> None:
    forbidden_fragments = ("нет ", "не являешься")

    for question in QUESTIONS:
        if question.kind is QuestionKind.YES_NO:
            assert not any(fragment in question.text.lower() for fragment in forbidden_fragments)


def test_answer_button_contains_question_index() -> None:
    keyboard = yes_no_keyboard(3)
    assert keyboard.inline_keyboard[0][0].callback_data == "answer:3:yes"
    assert keyboard.inline_keyboard[0][1].callback_data == "answer:3:no"


def test_answer_callback_parser_rejects_malformed_value() -> None:
    assert parse_answer_callback("answer:2:yes") == (2, "yes")
    with pytest.raises(ValueError, match="Некорректный"):
        parse_answer_callback("answer:yes")


def test_application_review_allows_confirmation_and_field_selection() -> None:
    review = application_review_keyboard()
    edit = application_edit_keyboard([(0, "Возраст"), (2, "Город")])

    assert review.inline_keyboard[0][0].text == "Да, всё верно"
    assert review.inline_keyboard[0][0].callback_data == "application:confirm"
    assert edit.inline_keyboard[0][0].callback_data == "application:edit:phone"
    assert edit.inline_keyboard[2][0].callback_data == "application:edit:question:2"


def test_application_review_formats_phone_and_answers() -> None:
    answers = {question.key: "no" for question in QUESTIONS}
    answers["adult"] = "yes"
    answers["city"] = "Москва"

    text = format_application_review({"phone": "+79991234567", "answers": answers})

    assert "Телефон: +79991234567" in text
    assert "Возраст: Да" in text
    assert "Город: Москва" in text
    assert "Да, всё верно" in text


def test_retry_submission_button_has_stable_callback() -> None:
    keyboard = retry_submission_keyboard()
    assert keyboard.inline_keyboard[0][0].callback_data == "application:retry"


def test_consent_can_be_opened_before_and_during_application() -> None:
    welcome = continue_keyboard()
    document = consent_document_keyboard(application_started=True)

    assert welcome.inline_keyboard[1][0].callback_data == "privacy:show"
    assert document.inline_keyboard[0][0].callback_data == "consent:accept"
    assert document.inline_keyboard[1][0].callback_data == "consent:back"


def test_admin_lead_button_contains_stable_id() -> None:
    keyboard = admin_leads_keyboard([("8a124766-93ec-4e02-9c85-2260ebad0422", "RKO-0001")])

    assert (
        keyboard.inline_keyboard[0][0].callback_data
        == "admin:lead:8a124766-93ec-4e02-9c85-2260ebad0422"
    )


def test_source_assignment_callbacks_fit_telegram_limit() -> None:
    lead_id = "8a124766-93ec-4e02-9c85-2260ebad0422"
    keyboard = admin_lead_keyboard(lead_id, "pending")
    callback_values = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]

    assert f"admin:source:confirm:{lead_id}" in callback_values
    assert f"admin:source:direct:{lead_id}" in callback_values
    assert all(len(value.encode()) <= 64 for value in callback_values)


def test_partner_card_keeps_referral_link_available() -> None:
    keyboard = admin_partner_keyboard(
        "8a124766-93ec-4e02-9c85-2260ebad0422",
        True,
        [("Telegram", "https://t.me/RKOrko_bot?start=ref-code")],
    )

    assert keyboard.inline_keyboard[0][0].text == "Ссылка: Telegram"
    assert keyboard.inline_keyboard[0][0].url == "https://t.me/RKOrko_bot?start=ref-code"
    callback_values = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert any(value.startswith("admin:pd:a:") for value in callback_values)
    assert all(len(value.encode()) <= 64 for value in callback_values)
