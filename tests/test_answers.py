import asyncio

from executive_docs.domain import AnswerPayload, AnswersRequest, JobStatus, NeedInputQuestion, ProjectState
from executive_docs.main import answer_questions, draft_report


class RecordingRepository:
    def __init__(self, state: ProjectState):
        self.state = state
        self.saved = 0

    def get(self, job_id: str) -> ProjectState | None:
        return self.state if job_id == self.state.job_id else None

    def save(self, state: ProjectState) -> None:
        self.state = state
        self.saved += 1


class RecordingQueue:
    def __init__(self):
        self.enqueued: list[str] = []

    async def enqueue(self, job_id: str) -> None:
        self.enqueued.append(job_id)


def test_partial_answers_are_saved_without_reanalysis(monkeypatch) -> None:
    state = ProjectState(
        job_id="44444444-4444-4444-4444-444444444444",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
        status=JobStatus.NEEDS_INPUT,
        questions=[
            NeedInputQuestion(
                id="q-date",
                field_key="actual.start",
                prompt="Дата",
                reason="Нет факта",
            ),
            NeedInputQuestion(
                id="q-contract",
                field_key="template.contract_and_sheet_selection",
                prompt="Контракт",
                reason="Внутренняя настройка",
            ),
        ],
    )
    repository = RecordingRepository(state)
    queue = RecordingQueue()
    monkeypatch.setattr("executive_docs.main.repository", repository)
    monkeypatch.setattr("executive_docs.main.queue", queue)
    monkeypatch.setattr("executive_docs.main.write_report", lambda *args: None)

    result = asyncio.run(
        answer_questions(
            state.job_id,
            AnswersRequest(
                answers=[
                    AnswerPayload(
                        question_id="q-date",
                        value="",
                        comment="",
                        confirmed_by="Специалист",
                    )
                ]
            ),
        )
    )

    assert result["status"] == JobStatus.NEEDS_INPUT
    assert len(repository.state.questions) == 1
    assert repository.saved == 1
    assert queue.enqueued == []
    assert repository.state.draft_report_ready is True
    assert "Замечаний к отчёту: 1" in repository.state.summary


def test_complete_answers_continue_analysis(monkeypatch) -> None:
    state = ProjectState(
        job_id="55555555-5555-5555-5555-555555555555",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
        status=JobStatus.NEEDS_INPUT,
        questions=[
            NeedInputQuestion(
                id="q-change",
                field_key="change_state.execution_scheme",
                prompt="Изменения?",
                reason="Неизвестно",
            )
        ],
    )
    repository = RecordingRepository(state)
    queue = RecordingQueue()
    monkeypatch.setattr("executive_docs.main.repository", repository)
    monkeypatch.setattr("executive_docs.main.queue", queue)

    result = asyncio.run(
        answer_questions(
            state.job_id,
            AnswersRequest(
                answers=[
                    AnswerPayload(
                        question_id="q-change",
                        value="Нет",
                        comment="",
                        confirmed_by="Специалист",
                    )
                ]
            ),
        )
    )

    assert result["status"] == JobStatus.FILES_UPLOADED
    assert repository.state.draft_report_ready is False
    assert repository.state.questions[0].answer == "NO"
    assert repository.saved == 1
    assert queue.enqueued == [state.job_id]


def test_draft_report_can_be_downloaded_with_missing_answers(monkeypatch) -> None:
    state = ProjectState(
        job_id="66666666-6666-6666-6666-666666666666",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
        status=JobStatus.NEEDS_INPUT,
        draft_report_ready=True,
        questions=[
            NeedInputQuestion(
                id="q-passport",
                field_key="materials.quality_documents",
                prompt="Укажите паспорт",
                reason="Паспорт отсутствует",
            )
        ],
    )
    monkeypatch.setattr("executive_docs.main.repository", RecordingRepository(state))

    response = asyncio.run(draft_report(state.job_id, download=True))

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="draft-report-with-warnings.html"'
    assert "Паспорт отсутствует" in response.body.decode()
