from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from executive_docs.config import Settings
from executive_docs.domain import ProjectState
from executive_docs.knowledge import KnowledgeBase
from executive_docs.review import REVIEW_TOOL, IndependentReviewer


ROOT = Path(__file__).resolve().parents[1]


def test_reviewer_uses_review_route_and_records_usage(monkeypatch) -> None:
    class FakeCounter:
        def count(self, **kwargs):
            assert kwargs["model"] == "test-review"
            return SimpleNamespace(input_tokens=120)

    class FakeResponses:
        input_tokens = FakeCounter()

        def create(self, **kwargs):
            assert kwargs["model"] == "test-review"
            assert kwargs["reasoning"] == {"effort": "low", "context": "current_turn"}
            assert kwargs["max_output_tokens"] == 500
            return SimpleNamespace(
                id="review-response",
                model="test-review",
                usage=SimpleNamespace(model_dump=lambda **_: {"input_tokens": 120, "output_tokens": 20}),
                output=[
                    SimpleNamespace(
                        type="function_call",
                        name="submit_review",
                        call_id="review-call",
                        arguments=json.dumps({"status": "PASS", "summary": "Проверено", "issues": []}),
                    )
                ],
            )

    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()
            self.files = SimpleNamespace(delete=lambda _: None)

    monkeypatch.setattr("executive_docs.review.OpenAI", FakeClient)
    settings = Settings(
        root=ROOT,
        skill_dir=ROOT / "agent-skill" / "prepare-executive-docs",
        openai_api_key="test-key",
        openai_review_model="test-review",
        openai_review_effort="low",
        openai_review_max_output_tokens=500,
        agent_mode="openai",
        max_job_cost_usd=0,
    )
    state = ProjectState(
        job_id="99999999-9999-9999-9999-999999999999",
        branch_id="khimki",
        first_aosr_number=1,
        operator_name="Специалист",
    )
    issues = IndependentReviewer(settings, KnowledgeBase(settings.skill_dir)).review(state, [])
    assert {item.code for item in issues} == {"MODEL_REVIEW_PASS"}
    assert state.model_usage[0].stage == "review"
    assert state.model_usage[0].model == "test-review"


def test_review_schema_has_no_defaults() -> None:
    def visit(value):
        if isinstance(value, dict):
            assert "default" not in value
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(REVIEW_TOOL["parameters"])
