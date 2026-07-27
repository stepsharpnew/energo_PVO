from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace

from executive_docs.agent import ANALYSIS_TOOL, TOOLS, HeuristicAgent, OpenAIAgent
from executive_docs.config import Settings
from executive_docs.domain import Artifact, ClaimStatus, ProjectState
from executive_docs.knowledge import KnowledgeBase
from executive_docs.usage import TokenBudgetExceeded
import pytest


ROOT = Path(__file__).resolve().parents[1]


def make_text_artifact(root: Path, name: str, content: str) -> Artifact:
    path = root / "input" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    payload = path.read_bytes()
    return Artifact(
        id=sha256(name.encode()).hexdigest()[:8],
        original_name=name,
        stored_name=name,
        media_type="text/plain",
        size=len(payload),
        sha256=sha256(payload).hexdigest(),
    )


def test_skill_index_routes_approved_topics() -> None:
    knowledge = KnowledgeBase(ROOT / "agent-skill" / "prepare-executive-docs")
    assert {"workflow", "source_priority", "validation"}.issubset(knowledge.topics())
    assert "NEEDS_INPUT" in knowledge.instructions()
    assert "Required phases" in knowledge.load("workflow")
    assert len(knowledge.version()) == 12


def test_heuristic_agent_requires_human_facts_then_builds_stable_plan(tmp_path: Path) -> None:
    artifact = make_text_artifact(tmp_path, "АОСР 1-7 КЛ 6кВ.txt", "Исполнительная схема КЛ 6 кВ")
    state = ProjectState(
        job_id="33333333-3333-3333-3333-333333333333",
        branch_id="khimki",
        first_aosr_number=12,
        operator_name="Специалист",
        artifacts=[artifact],
    )
    agent = HeuristicAgent(KnowledgeBase(ROOT / "agent-skill" / "prepare-executive-docs"))
    first = agent.analyze(state, tmp_path)
    assert first.status == "NEEDS_INPUT"
    assert {q.field_key for q in first.questions} == {
        "actual.start",
        "actual.end",
        "materials.quality_documents",
        "changes.state",
        "customer.profile_confirmation",
    }
    state.questions = first.questions
    answers = {
        "actual.start": "01.06.2026",
        "actual.end": "08.06.2026",
        "materials.quality_documents": "Сертификат № 42 от 01.05.2026",
        "changes.state": "НЕТ",
        "customer.profile_confirmation": "Подтверждено специалистом",
    }
    for question in state.questions:
        question.answer = answers[question.field_key]
        question.confirmed_by = "Специалист"
    second = agent.analyze(state, tmp_path)
    assert second.status == "READY"
    assert len(second.work_items) == 7
    assert second.document_plans[0].first_number == 12
    assert second.document_plans[0].selected_sheets == [f"АОСР-{number}" for number in range(1, 8)]
    assert all(item.change_state.value == "NO" for item in second.work_items)
    assert all(claim.status == ClaimStatus.HUMAN_CONFIRMED for claim in second.claims)


def test_openai_agent_uses_structured_submit_and_writes_audit_log(tmp_path: Path, monkeypatch) -> None:
    artifact = make_text_artifact(tmp_path, "project.txt", "Рабочий проект")
    state = ProjectState(
        job_id="66666666-6666-6666-6666-666666666666",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
        artifacts=[artifact],
    )
    arguments = {
        "status": "NEEDS_INPUT",
        "summary": "Нужна дата",
        "claims": [],
        "work_items": [],
        "document_plans": [],
        "questions": [
            {
                "id": "q-date",
                "field_key": "actual.start",
                "prompt": "Дата?",
                "reason": "Нет источника",
            }
        ],
    }

    class FakeResponses:
        def create(self, **kwargs):
            assert kwargs["model"] == "test-model"
            assert kwargs["tools"]
            assert kwargs["parallel_tool_calls"] is True
            static_input = kwargs["input"][0]["content"][0]["text"]
            dynamic_input = kwargs["input"][0]["content"][1]["text"]
            assert "# Knowledge topic: workflow" in static_input
            assert '"inventory"' in dynamic_input
            assert not any(item.get("type") == "input_file" for item in kwargs["input"][0]["content"])
            return SimpleNamespace(
                id="resp_test",
                model="test-model",
                usage=SimpleNamespace(model_dump=lambda **_: {"input_tokens": 10, "output_tokens": 5}),
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="submit_analysis",
                        arguments=json.dumps(arguments, ensure_ascii=False),
                        call_id="call_test",
                    )
                ],
            )

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["api_key"] == "test-key"
            self.responses = FakeResponses()
            self.files = SimpleNamespace(delete=lambda _: None)

    monkeypatch.setattr("executive_docs.agent.OpenAI", FakeClient)
    settings = Settings(
        root=ROOT,
        skill_dir=ROOT / "agent-skill" / "prepare-executive-docs",
        openai_api_key="test-key",
        openai_model="test-model",
        openai_analysis_model="test-model",
        openai_review_model="test-model",
        agent_mode="openai",
        exact_token_preflight=False,
        max_job_cost_usd=0,
    )
    persisted = []
    result = OpenAIAgent(
        settings,
        KnowledgeBase(settings.skill_dir),
        persist_usage=lambda current: persisted.append(len(current.model_usage)),
    ).analyze(state, tmp_path)
    assert result.status == "NEEDS_INPUT"
    events = [json.loads(line) for line in (tmp_path / "state" / "agent-events.jsonl").read_text(encoding="utf-8").splitlines()]
    assert any(event.get("response_id") == "resp_test" for event in events)
    assert any(event.get("tool") == "submit_analysis" for event in events)
    assert state.model_usage[0].input_tokens == 10
    assert persisted == [1]


def test_openai_analysis_schema_has_no_defaults_or_ref_siblings() -> None:
    def visit(value):
        if isinstance(value, dict):
            assert "default" not in value
            if "$ref" in value:
                assert set(value) == {"$ref"}
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(ANALYSIS_TOOL["parameters"])


def test_openai_agent_exposes_only_analysis_tools_after_preloading_context() -> None:
    assert [tool["name"] for tool in TOOLS] == ["read_source", "submit_analysis"]


def test_openai_agent_stops_before_paid_call_when_preflight_exceeds_budget(tmp_path: Path, monkeypatch) -> None:
    artifact = make_text_artifact(tmp_path, "project.txt", "Рабочий проект")
    state = ProjectState(
        job_id="77777777-7777-7777-7777-777777777777",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
        artifacts=[artifact],
    )

    class FakeCounter:
        def count(self, **kwargs):
            return SimpleNamespace(input_tokens=500)

    class FakeResponses:
        input_tokens = FakeCounter()

        def create(self, **kwargs):
            raise AssertionError("paid response must not start after the preflight limit")

    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()
            self.files = SimpleNamespace(delete=lambda _: None)

    monkeypatch.setattr("executive_docs.agent.OpenAI", FakeClient)
    settings = Settings(
        root=ROOT,
        skill_dir=ROOT / "agent-skill" / "prepare-executive-docs",
        openai_api_key="test-key",
        openai_analysis_model="test-model",
        agent_mode="openai",
        max_input_tokens_per_call=100,
    )
    with pytest.raises(TokenBudgetExceeded, match="500"):
        OpenAIAgent(settings, KnowledgeBase(settings.skill_dir)).analyze(state, tmp_path)


def test_openai_agent_compacts_local_evidence_before_paid_call(tmp_path: Path, monkeypatch) -> None:
    artifacts = [
        make_text_artifact(tmp_path, f"source-{number}.txt", f"Источник {number} " + "данные " * 1_200)
        for number in range(5)
    ]
    state = ProjectState(
        job_id="12121212-1212-1212-1212-121212121212",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
        artifacts=artifacts,
    )
    evidence_sizes: list[int] = []
    arguments = {
        "status": "NEEDS_INPUT",
        "summary": "Нужны сведения",
        "claims": [],
        "work_items": [],
        "document_plans": [],
        "questions": [
            {
                "id": "q-date",
                "field_key": "actual.start",
                "prompt": "Дата?",
                "reason": "Нет источника",
            }
        ],
    }

    class FakeCounter:
        def count(self, **kwargs):
            dynamic_input = json.loads(kwargs["input"][0]["content"][1]["text"])
            evidence_chars = sum(len(item["text"]) for item in dynamic_input["selected_local_evidence"])
            evidence_sizes.append(evidence_chars)
            return SimpleNamespace(input_tokens=120 if evidence_chars > 15_000 else 80)

    class FakeResponses:
        input_tokens = FakeCounter()

        def create(self, **kwargs):
            dynamic_input = json.loads(kwargs["input"][0]["content"][1]["text"])
            assert sum(len(item["text"]) for item in dynamic_input["selected_local_evidence"]) <= 15_000
            return SimpleNamespace(
                id="resp_compacted",
                model="gpt-5.6-terra",
                usage=SimpleNamespace(model_dump=lambda **_: {"input_tokens": 80, "output_tokens": 5}),
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="submit_analysis",
                        arguments=json.dumps(arguments, ensure_ascii=False),
                        call_id="call_compacted",
                    )
                ],
            )

    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()
            self.files = SimpleNamespace(delete=lambda _: None)

    monkeypatch.setattr("executive_docs.agent.OpenAI", FakeClient)
    settings = Settings(
        root=ROOT,
        skill_dir=ROOT / "agent-skill" / "prepare-executive-docs",
        openai_api_key="test-key",
        openai_analysis_model="gpt-5.6-terra",
        exact_token_preflight=True,
        max_input_tokens_per_call=100,
        max_job_cost_usd=0,
    )

    result = OpenAIAgent(settings, KnowledgeBase(settings.skill_dir)).analyze(state, tmp_path)

    assert result.status == "NEEDS_INPUT"
    assert evidence_sizes[0] > 15_000
    assert evidence_sizes[-1] <= 15_000
    events = [
        json.loads(line)
        for line in (tmp_path / "state" / "agent-events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert any(event["event"] == "context_compacted" for event in events)


def test_openai_agent_fails_closed_when_exact_preflight_errors(tmp_path: Path, monkeypatch) -> None:
    artifact = make_text_artifact(tmp_path, "project.txt", "Рабочий проект")
    state = ProjectState(
        job_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
        artifacts=[artifact],
    )

    class BrokenCounter:
        def count(self, **kwargs):
            raise RuntimeError("count unavailable")

    class FakeResponses:
        input_tokens = BrokenCounter()

        def create(self, **kwargs):
            raise AssertionError("paid response must not start without exact preflight")

    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()
            self.files = SimpleNamespace(delete=lambda _: None)

    monkeypatch.setattr("executive_docs.agent.OpenAI", FakeClient)
    settings = Settings(
        root=ROOT,
        skill_dir=ROOT / "agent-skill" / "prepare-executive-docs",
        openai_api_key="test-key",
        openai_analysis_model="gpt-5.6-terra",
        exact_token_preflight=True,
        allow_approximate_token_preflight=False,
    )
    with pytest.raises(TokenBudgetExceeded, match="точно посчитать"):
        OpenAIAgent(settings, KnowledgeBase(settings.skill_dir)).analyze(state, tmp_path)
