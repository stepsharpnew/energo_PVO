from __future__ import annotations

import re

from .domain import NeedInputQuestion


YES_VALUES = {"yes", "y", "да", "1", "true"}
NO_VALUES = {"no", "n", "нет", "0", "false"}
DELEGATED_VALUES = {
    "как считаешь нужным",
    "сделай как считаешь нужным",
    "на твое усмотрение",
    "на твоё усмотрение",
    "реши сам",
    "не знаю",
}
INTERNAL_FIELD_PREFIXES = ("template.contract",)


def is_yes_no_question(question: NeedInputQuestion) -> bool:
    key = question.field_key.casefold()
    return "change_state" in key or key in {"changes.state", "change.state"}


def is_internal_question(question: NeedInputQuestion) -> bool:
    return question.field_key.casefold().startswith(INTERNAL_FIELD_PREFIXES)


def is_delegated_value(value: str) -> bool:
    normalized = re.sub(r"\s+", " ", value).casefold().strip(" .!?")
    return normalized in DELEGATED_VALUES


def normalized_answer(question: NeedInputQuestion, value: str) -> str:
    answer = re.sub(r"\s+", " ", value).strip()
    if not answer:
        return ""
    normalized = answer.casefold().strip(" .!?")
    if is_delegated_value(answer):
        raise ValueError(
            "Ответ не содержит фактического значения. Оставьте поле пустым либо укажите подтверждённые сведения."
        )
    if is_yes_no_question(question):
        if normalized in YES_VALUES:
            return "YES"
        if normalized in NO_VALUES:
            return "NO"
        raise ValueError("Для этого вопроса выберите только «Да» или «Нет».")
    return answer
