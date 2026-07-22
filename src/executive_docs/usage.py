from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .domain import ModelUsageRecord, ProjectState


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: float
    cached_per_million: float
    cache_write_per_million: float
    output_per_million: float


# Snapshot used only for an on-screen estimate. Deployment operators can still
# enforce token limits when a custom/unknown model has no price entry.
MODEL_PRICES: dict[str, ModelPrice] = {
    "gpt-5.6": ModelPrice(5.0, 0.50, 6.25, 30.0),
    "gpt-5.6-sol": ModelPrice(5.0, 0.50, 6.25, 30.0),
    "gpt-5.6-terra": ModelPrice(2.50, 0.25, 3.125, 15.0),
    "gpt-5.6-luna": ModelPrice(1.0, 0.10, 1.25, 6.0),
}
PRICING_SNAPSHOT_DATE = "2026-07-22"


class TokenBudgetExceeded(RuntimeError):
    pass


def price_for_model(model: str) -> ModelPrice | None:
    if model in MODEL_PRICES:
        return MODEL_PRICES[model]
    for prefix in sorted(MODEL_PRICES, key=len, reverse=True):
        if model.startswith(prefix + "-"):
            return MODEL_PRICES[prefix]
    return None


def _usage_payload(usage: Any) -> dict[str, Any]:
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return usage
    if hasattr(usage, "model_dump"):
        return usage.model_dump(mode="json")
    return {}


def usage_record(*, stage: str, revision: int, response_id: str, model: str, usage: Any) -> ModelUsageRecord:
    payload = _usage_payload(usage)
    input_details = payload.get("input_tokens_details") or {}
    output_details = payload.get("output_tokens_details") or {}
    input_tokens = int(payload.get("input_tokens") or 0)
    cached_tokens = int(input_details.get("cached_tokens") or payload.get("cached_tokens") or 0)
    cache_write_tokens = int(input_details.get("cache_write_tokens") or payload.get("cache_write_tokens") or 0)
    output_tokens = int(payload.get("output_tokens") or 0)
    reasoning_tokens = int(output_details.get("reasoning_tokens") or payload.get("reasoning_tokens") or 0)
    price = price_for_model(model)
    estimated_cost: float | None = None
    if price:
        ordinary = max(0, input_tokens - cached_tokens - cache_write_tokens)
        estimated_cost = round(
            (
                ordinary * price.input_per_million
                + cached_tokens * price.cached_per_million
                + cache_write_tokens * price.cache_write_per_million
                + output_tokens * price.output_per_million
            )
            / 1_000_000,
            6,
        )
    return ModelUsageRecord(
        stage=stage,  # type: ignore[arg-type]
        revision=revision,
        response_id=response_id,
        model=model,
        input_tokens=input_tokens,
        cached_tokens=cached_tokens,
        cache_write_tokens=cache_write_tokens,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        estimated_cost_usd=estimated_cost,
    )


def revision_input_tokens(state: ProjectState) -> int:
    return sum(item.input_tokens for item in state.model_usage if item.revision == state.revision)


def job_input_tokens(state: ProjectState) -> int:
    return sum(item.input_tokens for item in state.model_usage)


def revision_estimated_cost(state: ProjectState) -> float:
    return round(
        sum((item.estimated_cost_usd or 0.0) for item in state.model_usage if item.revision == state.revision),
        6,
    )


def job_estimated_cost(state: ProjectState) -> float | None:
    if any(item.estimated_cost_usd is None for item in state.model_usage):
        return None
    return round(sum(item.estimated_cost_usd or 0.0 for item in state.model_usage), 6)


def ensure_budget(
    state: ProjectState,
    *,
    next_input_tokens: int,
    next_output_tokens: int = 0,
    max_input_tokens_per_call: int,
    max_job_input_tokens: int,
    max_job_cost_usd: float,
    max_model_calls_per_job: int,
    model: str,
) -> None:
    calls = len(state.model_usage)
    if calls >= max_model_calls_per_job:
        raise TokenBudgetExceeded(
            f"Достигнут лимит {max_model_calls_per_job} модельных вызовов для задания."
        )
    if next_input_tokens > max_input_tokens_per_call:
        raise TokenBudgetExceeded(
            f"Запрос требует {next_input_tokens:,} входных токенов; лимит профиля {max_input_tokens_per_call:,}. "
            "Сократите выбранные страницы либо явно увеличьте MAX_INPUT_TOKENS_PER_CALL."
        )
    projected_tokens = job_input_tokens(state) + next_input_tokens
    if projected_tokens > max_job_input_tokens:
        raise TokenBudgetExceeded(
            f"Обработка потребует не менее {projected_tokens:,} входных токенов в задании; "
            f"лимит {max_job_input_tokens:,}."
        )
    price = price_for_model(model)
    if max_job_cost_usd > 0 and price is None:
        raise TokenBudgetExceeded(
            f"Для модели {model!r} нет тарифа в снимке {PRICING_SNAPSHOT_DATE}; "
            "долларовый лимит нельзя проверить. Добавьте тариф или явно отключите MAX_JOB_COST_USD=0."
        )
    if price and max_job_cost_usd > 0:
        # Before a response exists we do not yet know how much of the input
        # will be a cache write, cache hit, or ordinary input. Reserve the
        # most expensive possible input route and the configured output cap,
        # so the per-revision dollar estimate remains a conservative
        # guardrail for the dated pricing snapshot.
        conservative_input_rate = max(price.input_per_million, price.cache_write_per_million)
        conservative_next_cost = (
            next_input_tokens * conservative_input_rate
            + next_output_tokens * price.output_per_million
        ) / 1_000_000
        spent = job_estimated_cost(state)
        if spent is None:
            raise TokenBudgetExceeded(
                "В истории задания есть вызов с неизвестной стоимостью; новый платный вызов заблокирован."
            )
        projected_cost = spent + conservative_next_cost
        if projected_cost > max_job_cost_usd:
            raise TokenBudgetExceeded(
                f"Консервативная оценка стоимости достигла ${projected_cost:.2f}; "
                f"лимит задания ${max_job_cost_usd:.2f}."
            )
