from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStatus(StrEnum):
    CREATED = "CREATED"
    FILES_UPLOADED = "FILES_UPLOADED"
    ANALYZING = "ANALYZING"
    NEEDS_INPUT = "NEEDS_INPUT"
    GENERATING = "GENERATING"
    VALIDATING = "VALIDATING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    APPROVED_FINAL = "APPROVED_FINAL"
    REVISION_REQUIRED = "REVISION_REQUIRED"
    FAILED_ANALYSIS = "FAILED_ANALYSIS"
    FAILED_GENERATION = "FAILED_GENERATION"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    CANCELLED = "CANCELLED"


class ClaimStatus(StrEnum):
    OBSERVED = "observed"
    DERIVED = "derived"
    HUMAN_CONFIRMED = "human_confirmed"
    CONFLICT = "conflict"
    REJECTED = "rejected"


class ChangeState(StrEnum):
    YES = "YES"
    NO = "NO"
    UNKNOWN = "UNKNOWN"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Artifact(StrictModel):
    id: str
    original_name: str
    stored_name: str
    media_type: str
    size: int
    sha256: str
    category: str = "unknown"
    pages: int | None = None


class Claim(StrictModel):
    key: str
    raw_value: str
    normalized_value: str
    unit: str | None = None
    source_kind: str
    source_file_id: str | None = None
    locator: str
    evidence_fragment: str
    status: ClaimStatus
    rule_id: str | None = None
    affected_documents: list[str] = Field(default_factory=list)


class Material(StrictModel):
    name: str
    quantity: str | None = None
    unit: str | None = None
    quality_document: str | None = None
    source_file_id: str | None = None


class WorkItem(StrictModel):
    id: str
    family: Literal["kl_04", "kl_6", "vrs"]
    work_type: str
    sequence_index: int = Field(ge=1)
    actual_start: str | None = None
    actual_end: str | None = None
    volume: str | None = None
    unit: str | None = None
    installation: str | None = None
    subsequent_work: str | None = None
    materials: list[Material] = Field(default_factory=list)
    change_state: ChangeState = ChangeState.UNKNOWN
    execution_scheme_id: str | None = None
    source_claim_keys: list[str] = Field(default_factory=list)


class FieldValue(StrictModel):
    key: str
    value: str


class DocumentPlan(StrictModel):
    template_id: Literal["aosr_kl_04", "aosr_kl_6", "aosr_vrs"]
    selected_sheets: list[str]
    work_item_ids: list[str]
    first_number: int = Field(ge=1)
    field_values: list[FieldValue] = Field(default_factory=list)
    attachments: list[str] = Field(default_factory=list)
    output_filename: str


class NeedInputQuestion(StrictModel):
    id: str
    field_key: str
    prompt: str
    reason: str
    required: bool = True
    answer: str | None = None
    comment: str | None = None
    confirmed_by: str | None = None
    answered_at: str | None = None


class ValidationIssue(StrictModel):
    code: str
    severity: Literal["error", "info"]
    message: str
    artifact: str | None = None
    locator: str | None = None


class ModelUsageRecord(StrictModel):
    stage: Literal["analysis", "review"]
    revision: int = Field(ge=1)
    response_id: str
    model: str
    input_tokens: int = Field(ge=0)
    cached_tokens: int = Field(ge=0)
    cache_write_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    reasoning_tokens: int = Field(ge=0)
    estimated_cost_usd: float | None = Field(default=None, ge=0)


class AnalysisResult(StrictModel):
    status: Literal["READY", "NEEDS_INPUT"]
    summary: str
    claims: list[Claim] = Field(default_factory=list)
    work_items: list[WorkItem] = Field(default_factory=list)
    document_plans: list[DocumentPlan] = Field(default_factory=list)
    questions: list[NeedInputQuestion] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_outcome(self) -> "AnalysisResult":
        if len({item.id for item in self.questions}) != len(self.questions):
            raise ValueError("Question IDs must be unique")
        if self.status == "NEEDS_INPUT" and not self.questions:
            raise ValueError("NEEDS_INPUT requires at least one question")
        if self.status == "READY" and (self.questions or not self.work_items or not self.document_plans):
            raise ValueError("READY requires work items and document plans, without questions")
        return self


class ModelReviewResult(StrictModel):
    status: Literal["PASS", "FAIL"]
    summary: str
    issues: list[ValidationIssue] = Field(default_factory=list)


class CorrectionPayload(StrictModel):
    artifact: str
    location: str
    current_value: str
    expected_value: str
    reason: str
    scope: Literal["project", "customer", "global"] = "project"


class ProjectState(StrictModel):
    job_id: str
    revision: int = 1
    branch_id: Literal["khimki", "solnechnogorsk"]
    first_aosr_number: int
    operator_name: str
    processing_profile: Literal["economy", "balanced", "quality"] = "balanced"
    status: JobStatus = JobStatus.CREATED
    artifacts: list[Artifact] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    work_items: list[WorkItem] = Field(default_factory=list)
    document_plans: list[DocumentPlan] = Field(default_factory=list)
    questions: list[NeedInputQuestion] = Field(default_factory=list)
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    corrections: list[CorrectionPayload] = Field(default_factory=list)
    model_usage: list[ModelUsageRecord] = Field(default_factory=list)
    summary: str = ""
    draft_report_ready: bool = False
    result_zip: str | None = None
    model: str = ""
    skill_version: str = "1"
    knowledge_version: str = "1"
    template_versions: dict[str, str] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
    error: str | None = None

    @property
    def public_ref(self) -> str:
        created = datetime.fromisoformat(self.created_at)
        return created.strftime("%Y%m%d-%H%M%S-%f")

    def touch(self) -> None:
        self.updated_at = utc_now()

    def answered_claims(self) -> list[Claim]:
        result: list[Claim] = []
        for question in self.questions:
            if question.answer:
                result.append(
                    Claim(
                        key=question.field_key,
                        raw_value=question.answer,
                        normalized_value=question.answer,
                        source_kind="human_answer",
                        locator=f"question:{question.id}",
                        evidence_fragment=(
                            f"Подтвердил: {question.confirmed_by}."
                            + (f" {question.comment}" if question.comment else "")
                            if question.confirmed_by
                            else question.comment or "Подтверждено специалистом"
                        ),
                        status=ClaimStatus.HUMAN_CONFIRMED,
                    )
                )
        return result


class AnswerPayload(StrictModel):
    question_id: str
    value: str
    comment: str = ""
    confirmed_by: str


class AnswersRequest(StrictModel):
    answers: list[AnswerPayload]


class ReviewRequest(StrictModel):
    action: Literal["approve", "request_revision", "cancel"]
    corrections: list[CorrectionPayload] = Field(default_factory=list)


class CorrectionReviewRequest(StrictModel):
    action: Literal["approve", "reject"]
    reviewed_by: str
    comment: str
    regression_passed: bool = False


def as_jsonable(value: BaseModel | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value
