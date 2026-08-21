import re
from dataclasses import dataclass
from enum import StrEnum


class QuestionKind(StrEnum):
    YES_NO = "yes_no"
    TEXT = "text"


@dataclass(frozen=True)
class Question:
    key: str
    text: str
    review_label: str
    kind: QuestionKind = QuestionKind.YES_NO


QUESTIONS = (
    Question("has_ip", "У тебя открыто ИП?", "ИП"),
    Question(
        "city",
        "В каком городе ты сейчас находишься?",
        "Город",
        QuestionKind.TEXT,
    ),
    Question(
        "full_name",
        "Напиши полностью фамилию, имя и отчество.",
        "ФИО",
        QuestionKind.TEXT,
    ),
    Question(
        "email",
        "Укажи свой e-mail.",
        "E-mail",
        QuestionKind.TEXT,
    ),
    Question(
        "has_social_benefits",
        "Получаешь ли ты социальные выплаты: пенсию, пособие по инвалидности или другие пособия?",
        "Социальные выплаты",
    ),
    Question("adult", "Тебе уже исполнилось 18 лет?", "Совершеннолетие"),
    Question(
        "has_bankruptcy_or_arrests",
        "Были ли у тебя банкротства или аресты на счетах?",
        "Банкротства или аресты",
    ),
    Question("is_civil_servant", "Ты являешься госслужащим?", "Госслужба"),
)


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    if len(digits) < 11 or len(digits) > 15:
        raise ValueError("Введите корректный номер телефона")
    return "+" + digits


def normalize_full_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    parts = normalized.split()
    if len(parts) < 3 or any(len(part) < 2 for part in parts):
        raise ValueError("Напиши фамилию, имя и отчество полностью")
    if len(normalized) > 200:
        raise ValueError("ФИО слишком длинное")
    return normalized


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) > 254 or not re.fullmatch(
        r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+",
        normalized,
    ):
        raise ValueError("Введи корректный e-mail")
    return normalized


def is_eligible(answers: dict[str, str]) -> bool:
    return (
        answers.get("adult") != "no"
        and answers.get("has_bankruptcy_or_arrests") != "yes"
        and answers.get("is_civil_servant") != "yes"
    )
