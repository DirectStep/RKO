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
    kind: QuestionKind = QuestionKind.YES_NO


QUESTIONS = (
    Question("adult", "Тебе уже исполнилось 18 лет?"),
    Question("has_ip", "У тебя открыто ИП?"),
    Question("city", "В каком городе ты сейчас находишься?", QuestionKind.TEXT),
    Question("has_bankruptcy_or_arrests", "Были ли у тебя банкротства или аресты на счетах?"),
    Question("is_civil_servant", "Ты являешься госслужащим?"),
    Question(
        "has_social_benefits",
        "Получаешь ли ты социальные выплаты: пенсию, пособие по инвалидности или другие пособия?",
    ),
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
