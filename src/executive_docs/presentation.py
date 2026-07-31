from __future__ import annotations

from pathlib import Path
import re

from .domain import NeedInputQuestion, ProjectState
from .questions import is_internal_question


SHA_REFERENCE = re.compile(r"\s*\(\s*SHA-?256\s*[:=]?\s*[0-9a-f]{64}\s*\)", re.IGNORECASE)
SHA_VALUE = re.compile(r"\b(?:SHA-?256\s*[:=]?\s*)?[0-9a-f]{64}\b", re.IGNORECASE)
UUID_VALUE = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
FILE_ID_REFERENCE = re.compile(r"\b(?:файл|file)\s+[0-9a-f]{8}\b", re.IGNORECASE)

PUBLIC_FAILURE_MESSAGES = {
    "FAILED_ANALYSIS": (
        "Не удалось завершить анализ PDF. Повторите анализ; если ошибка "
        "повторится, обратитесь к администратору."
    ),
    "FAILED_GENERATION": (
        "Не удалось сформировать черновой Excel. Повторите формирование; "
        "если ошибка повторится, обратитесь к администратору."
    ),
    "FAILED_VALIDATION": (
        "Черновой Excel не прошёл техническую проверку. Подробности доступны "
        "администратору."
    ),
}


def public_text(value: str | None) -> str:
    """Remove storage identifiers from text intended for an operator."""

    text = value or ""
    text = SHA_REFERENCE.sub("", text)
    text = SHA_VALUE.sub("", text)
    text = UUID_VALUE.sub("", text)
    text = FILE_ID_REFERENCE.sub("загруженный файл", text)
    text = re.sub(r"\s+и\s+контракт(?:ы)?\s+шаблонов", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"не\s+являются\s+допустимым\s+human_confirmed\s+evidence",
        "не являются подтверждёнными сведениями",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\bhuman_confirmed\s+evidence\b",
        "подтверждёнными сведениями",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\(\s*\)", "", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def public_question(question: NeedInputQuestion) -> NeedInputQuestion:
    return question.model_copy(
        update={
            "prompt": public_text(question.prompt),
            "reason": public_text(question.reason),
        }
    )


def public_state(state: ProjectState) -> ProjectState:
    failure_message = (
        PUBLIC_FAILURE_MESSAGES.get(state.status.value)
        if state.error
        else None
    )
    draft_failure_message = (
        "Не удалось сформировать черновой Excel. Повторите формирование; "
        "если ошибка повторится, обратитесь к администратору."
        if state.draft_excel_error
        else None
    )
    return state.model_copy(
        update={
            "summary": (
                failure_message
                or draft_failure_message
                or public_text(state.summary)
            ),
            "error": failure_message or public_text(state.error) or None,
            "draft_excel_error": draft_failure_message,
            "questions": [
                public_question(question)
                for question in state.questions
                if not is_internal_question(question)
            ],
        }
    )


def public_payload(state: ProjectState) -> dict:
    payload = public_state(state).model_dump(mode="json")
    payload["job_id"] = state.public_ref
    payload["draft_excel_files"] = [Path(path).name for path in state.draft_excel_files]
    payload.pop("selected_template_sha256", None)
    payload.pop("selected_template_contract_sha256", None)
    payload.pop("template_assignments", None)
    payload.pop("template_unresolved_findings", None)
    for artifact in payload["artifacts"]:
        artifact.pop("id", None)
        artifact.pop("sha256", None)
        artifact.pop("stored_name", None)
    for claim in payload["claims"]:
        claim.pop("source_file_id", None)
    return payload
