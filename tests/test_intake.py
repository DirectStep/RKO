import pytest

from app.bot.handlers import parse_answer_callback
from app.bot.keyboards import retry_submission_keyboard, yes_no_keyboard
from app.domain.intake import QUESTIONS, QuestionKind, normalize_phone


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


def test_answer_button_contains_question_index() -> None:
    keyboard = yes_no_keyboard(3)
    assert keyboard.inline_keyboard[0][0].callback_data == "answer:3:yes"
    assert keyboard.inline_keyboard[0][1].callback_data == "answer:3:no"


def test_answer_callback_parser_rejects_malformed_value() -> None:
    assert parse_answer_callback("answer:2:yes") == (2, "yes")
    with pytest.raises(ValueError, match="Некорректный"):
        parse_answer_callback("answer:yes")


def test_retry_submission_button_has_stable_callback() -> None:
    keyboard = retry_submission_keyboard()
    assert keyboard.inline_keyboard[0][0].callback_data == "application:retry"
