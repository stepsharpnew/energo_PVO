from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from executive_docs import main
from executive_docs.domain import ModelUsageRecord, ProjectState
from executive_docs.presentation import public_payload
from executive_docs.usage import TokenBudgetExceeded, ensure_budget, job_estimated_cost


def state_with_costs(*costs: float | None) -> ProjectState:
    return ProjectState(
        job_id="pricing-test", operator_name="test", revision=2,
        model_usage=[ModelUsageRecord(
            stage="analysis" if index == 0 else "review", revision=1 if index == 0 else 2,
            response_id=f"response-{index}", model="gpt-5.6-terra",
            input_tokens=100, cached_tokens=10, cache_write_tokens=0,
            output_tokens=20, reasoning_tokens=5, estimated_cost_usd=cost,
        ) for index, cost in enumerate(costs)],
    )


@pytest.mark.parametrize("cost,expected", [(0.3, 0.75), (0.10625, 0.265625), (0, 0),
                                          (0.000001, 0.0000025), (None, None)])
def test_public_service_cost_scales_without_mutating_usage(cost, expected):
    state = state_with_costs(cost)
    original = state.model_dump_json()
    for _ in range(3):
        payload = public_payload(state)
        assert payload["model_usage"][0]["estimated_cost_usd"] == expected
        assert set(payload["model_usage"][0]) == set(state.model_usage[0].model_dump())
        assert payload["model_usage"][0]["input_tokens"] == 100
        assert "SERVICE_PRICE_FACTOR" not in str(payload)
        assert state.model_dump_json() == original


def test_all_calls_and_revisions_are_scaled_without_early_rounding():
    state = state_with_costs(0.1, 0.2, 0.000001)
    usage = public_payload(state)["model_usage"]
    assert [item["estimated_cost_usd"] for item in usage] == [0.25, 0.5, 0.0000025]
    assert sum(Decimal(str(item["estimated_cost_usd"])) for item in usage) == Decimal("0.7500025")
    assert job_estimated_cost(state) == 0.300001
    assert public_payload(state_with_costs())["model_usage"] == []


def test_budget_uses_provider_cost_after_presentation():
    state = state_with_costs(0.1)
    assert public_payload(state)["model_usage"][0]["estimated_cost_usd"] == 0.25
    budget = dict(next_input_tokens=1, next_output_tokens=1, max_input_tokens_per_call=1000,
                  max_job_input_tokens=1000, max_model_calls_per_job=3, model="gpt-5.6-terra")
    ensure_budget(state, max_job_cost_usd=0.11, **budget)
    with pytest.raises(TokenBudgetExceeded):
        ensure_budget(state, max_job_cost_usd=0.09, **budget)
    assert job_estimated_cost(state) == 0.1


@pytest.mark.parametrize("route", ["/api/jobs/pricing-test", "/api/kits/pricing-test", "/api/jobs"])
def test_every_public_job_api_returns_service_cost_only(monkeypatch, route):
    state = state_with_costs(0.3, None)
    monkeypatch.setattr(main.repository, "get", lambda _: state)
    monkeypatch.setattr(main.repository, "list", lambda *args: [state])
    # No lifespan/queue startup: this is a local synthetic API check, not a job.
    response = TestClient(main.app).get(route)
    assert response.status_code == 200
    payload = response.json()[0] if route == "/api/jobs" else response.json()
    assert [item["estimated_cost_usd"] for item in payload["model_usage"]] == [0.75, None]
    assert state.model_usage[0].estimated_cost_usd == 0.3


def test_public_assets_contain_no_service_factor():
    root = Path(__file__).resolve().parents[1] / "src/executive_docs"
    for path in [*root.joinpath("static").glob("*.js"), *root.joinpath("templates").glob("*.html")]:
        text = path.read_text()
        assert "SERVICE_PRICE_FACTOR" not in text
        assert "наценк" not in text.casefold()
