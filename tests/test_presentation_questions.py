import pytest

from executive_docs.domain import (
    Artifact,
    Claim,
    ClaimStatus,
    JobStatus,
    NeedInputQuestion,
    ProjectState,
)
from executive_docs.presentation import public_payload, public_state, public_text
from executive_docs.questions import is_delegated_value, normalized_answer


def test_public_text_removes_hashes_uuids_and_internal_file_ids() -> None:
    value = (
        "Проект (SHA-256 28f1bb9a66ab01399fb61a5f69b4a761e5d3e82c49808d962eb1c35be89f9d53), "
        "файл 47da8fb4, задание 0da9de67-35c6-470c-9144-1c251061ea2b."
    )
    result = public_text(value)
    assert "SHA" not in result
    assert "28f1bb9a" not in result
    assert "47da8fb4" not in result
    assert "0da9de67" not in result
    assert "загруженный файл" in result
    assert (
        public_text("Ответы не являются допустимым human_confirmed evidence.")
        == "Ответы не являются подтверждёнными сведениями."
    )


def test_public_state_hides_internal_template_questions() -> None:
    state = ProjectState(
        job_id="44444444-4444-4444-4444-444444444444",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
        status=JobStatus.NEEDS_INPUT,
        questions=[
            NeedInputQuestion(
                id="q-fact",
                field_key="actual.start",
                prompt="Укажите дату",
                reason="Нет факта",
            ),
            NeedInputQuestion(
                id="q-contract",
                field_key="template.contract_and_sheet_selection",
                prompt="Утвердите внутренний контракт",
                reason="Внутренняя настройка",
            ),
        ],
        artifacts=[
            Artifact(
                id="deadbeef",
                original_name="Проект.pdf",
                stored_name="deadbeef-project.pdf",
                media_type="application/pdf",
                size=10,
                sha256="0" * 64,
            )
        ],
        claims=[
            Claim(
                key="template.ojr.Данные.B2",
                raw_value="P-42",
                normalized_value="P-42",
                source_kind="project_pdf",
                source_file_id="deadbeef",
                locator="page:1",
                evidence_fragment="Шифр P-42",
                status=ClaimStatus.OBSERVED,
            )
        ],
    )
    presented = public_state(state)
    assert [question.id for question in presented.questions] == ["q-fact"]
    assert public_payload(state)["job_id"] == state.public_ref
    assert state.job_id not in public_payload(state).values()
    assert "sha256" not in public_payload(state)["artifacts"][0]
    assert "stored_name" not in public_payload(state)["artifacts"][0]
    assert "id" not in public_payload(state)["artifacts"][0]
    assert "source_file_id" not in public_payload(state)["claims"][0]


def test_optional_answers_accept_text_or_yes_no_and_reject_delegation() -> None:
    text_question = NeedInputQuestion(
        id="q-text",
        field_key="actual.start",
        prompt="Дата",
        reason="Нет факта",
    )
    yes_no_question = NeedInputQuestion(
        id="q-change",
        field_key="change_state.execution_scheme",
        prompt="Изменения?",
        reason="Неизвестно",
    )
    assert normalized_answer(text_question, "") == ""
    assert normalized_answer(text_question, "01.07.2026") == "01.07.2026"
    assert normalized_answer(yes_no_question, "Да") == "YES"
    assert normalized_answer(yes_no_question, "нет") == "NO"
    assert is_delegated_value("Сделай как считаешь нужным")
    with pytest.raises(ValueError, match="фактического значения"):
        normalized_answer(text_question, "Сделай как считаешь нужным")
    with pytest.raises(ValueError, match="Да"):
        normalized_answer(yes_no_question, "Возможно")


def test_public_payload_exposes_only_draft_excel_filenames() -> None:
    state = ProjectState(
        job_id="44444444-4444-4444-4444-444444444444",
        branch_id="khimki",
        first_aosr_number=4,
        operator_name="Специалист",
        status=JobStatus.NEEDS_INPUT,
        draft_report_ready=True,
        draft_excel_files=[
            "output/drafts/r1-20260727/xlsx/ЧЕРНОВИК - АОСР КЛ-6кВ.xlsx"
        ],
    )

    payload = public_payload(state)

    assert payload["draft_excel_files"] == ["ЧЕРНОВИК - АОСР КЛ-6кВ.xlsx"]
    assert "output/drafts" not in str(payload["draft_excel_files"])
