from __future__ import annotations

import html
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
    return state.model_copy(
        update={
            "summary": public_text(state.summary),
            "error": public_text(state.error) or None,
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
    for artifact in payload["artifacts"]:
        artifact.pop("id", None)
        artifact.pop("sha256", None)
        artifact.pop("stored_name", None)
    return payload


def public_draft_report_html(state: ProjectState) -> str:
    """Build a user-facing draft report without storage identifiers."""

    presented = public_state(state)
    unresolved = [question for question in presented.questions if not question.answer]
    answered = [question for question in presented.questions if question.answer]
    warning_rows = "".join(
        (
            "<article class='warning'>"
            f"<h2>{html.escape(question.prompt)}</h2>"
            f"<p>{html.escape(question.reason)}</p>"
            "<strong>Не заполнено — требуется уточнить перед финальным выпуском</strong>"
            "</article>"
        )
        for question in unresolved
    ) or "<p class='empty'>Незаполненных сведений нет.</p>"
    answer_rows = "".join(
        (
            "<tr>"
            f"<th>{html.escape(question.prompt)}</th>"
            f"<td>{html.escape(public_text(question.answer))}</td>"
            "</tr>"
        )
        for question in answered
    ) or "<tr><td colspan='2'>Подтверждённые ответы не указаны.</td></tr>"
    branch = "Химки" if presented.branch_id == "khimki" else "Солнечногорск"
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Черновой отчёт с замечаниями</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ max-width: 980px; margin: 36px auto; padding: 0 24px; color: #26352f; font: 14px Arial, sans-serif; }}
    h1 {{ margin-bottom: 8px; color: #12382a; }}
    .meta {{ color: #6f7873; }}
    .notice {{ margin: 24px 0; padding: 18px; border: 2px solid #f05f52; background: #fff1e9; }}
    .warning {{ margin: 12px 0; padding: 16px; border-left: 5px solid #f05f52; background: #fffaf6; }}
    .warning h2 {{ margin: 0 0 7px; color: #12382a; font-size: 16px; }}
    .warning p {{ margin: 0 0 8px; color: #6f7873; line-height: 1.5; }}
    .warning strong {{ color: #8b3b24; font-size: 12px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 16px 0 28px; }}
    th, td {{ padding: 11px; border: 1px solid #d8ddd5; text-align: left; vertical-align: top; }}
    th {{ width: 48%; color: #12382a; background: #f4f7ef; }}
    .actions {{ display: flex; gap: 10px; margin-bottom: 24px; }}
    button {{ padding: 11px 16px; border: 0; color: white; background: #12382a; cursor: pointer; }}
    @media print {{ .actions {{ display: none; }} body {{ margin: 0; max-width: none; }} }}
  </style>
</head>
<body>
  <div class="actions"><button type="button" onclick="window.print()">Печать / сохранить в PDF</button></div>
  <h1>Черновой отчёт с замечаниями</h1>
  <p class="meta">Филиал: {html.escape(branch)} · Первый номер АОСР: {presented.first_aosr_number}</p>
  <div class="notice">
    <strong>Это не финальный комплект АОСР.</strong>
    В документе {len(unresolved)} незаполненных полей. Отсутствующие значения не были придуманы или подставлены автоматически.
  </div>
  <h2>Заполненные сведения</h2>
  <table>{answer_rows}</table>
  <h2>Замечания к отчёту</h2>
  {warning_rows}
</body>
</html>"""
