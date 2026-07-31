from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ProcessingPolicy:
    name: str
    analysis_model: str
    analysis_effort: str
    review_model: str
    review_effort: str
    pdf_detail: str
    max_evidence_chars: int
    max_visual_pages: int
    max_agent_steps: int


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = ROOT / "data"
    runs_dir: Path = ROOT / "data" / "runs"
    db_path: Path = ROOT / "data" / "app.db"
    skill_dir: Path = ROOT / "agent-skill" / "prepare-executive-docs"
    contracts_dir: Path = ROOT / "templates" / "contracts"
    fill_contracts_dir: Path = ROOT / "templates" / "fill-contracts"
    approved_templates_dir: Path = ROOT / "templates" / "approved"
    source_templates_dir: Path = ROOT / "template"
    profiles_dir: Path = ROOT / "profiles"
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    # OPENAI_MODEL is retained as a compatibility/display fallback. Stage and
    # profile-specific models below are used by the paid pipeline.
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.6-sol")
    reasoning_effort: str = os.getenv("OPENAI_REASONING_EFFORT", "high")
    processing_profile: str = os.getenv("PROCESSING_PROFILE", "balanced")
    openai_economy_model: str = os.getenv("OPENAI_ECONOMY_MODEL", "gpt-5.6-luna")
    openai_analysis_model: str = os.getenv("OPENAI_ANALYSIS_MODEL", "gpt-5.6-terra")
    openai_review_model: str = os.getenv("OPENAI_REVIEW_MODEL", "gpt-5.6-terra")
    openai_quality_model: str = os.getenv("OPENAI_QUALITY_MODEL", "gpt-5.6-sol")
    openai_economy_effort: str = os.getenv("OPENAI_ECONOMY_REASONING_EFFORT", "low")
    openai_analysis_effort: str = os.getenv("OPENAI_ANALYSIS_REASONING_EFFORT", "medium")
    openai_review_effort: str = os.getenv("OPENAI_REVIEW_REASONING_EFFORT", "medium")
    openai_quality_effort: str = os.getenv("OPENAI_QUALITY_REASONING_EFFORT", "high")
    agent_mode: str = os.getenv("AGENT_MODE", "openai")
    host: str = os.getenv("APP_HOST", "127.0.0.1")
    port: int = int(os.getenv("APP_PORT", "8000"))
    max_file_bytes: int = int(os.getenv("MAX_FILE_MB", "50")) * 1024 * 1024
    max_job_bytes: int = int(os.getenv("MAX_JOB_MB", "250")) * 1024 * 1024
    max_agent_steps: int = int(os.getenv("MAX_AGENT_STEPS", "8"))
    max_agent_seconds: int = int(os.getenv("MAX_AGENT_SECONDS", "900"))
    openai_timeout_seconds: int = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "300"))
    openai_max_retries: int = int(os.getenv("OPENAI_MAX_RETRIES", "2"))
    openai_max_output_tokens: int = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "12000"))
    openai_review_max_output_tokens: int = int(os.getenv("OPENAI_REVIEW_MAX_OUTPUT_TOKENS", "4000"))
    max_input_tokens_per_call: int = int(os.getenv("MAX_INPUT_TOKENS_PER_CALL", "100000"))
    max_job_input_tokens: int = int(os.getenv("MAX_JOB_INPUT_TOKENS", "400000"))
    max_job_cost_usd: float = float(os.getenv("MAX_JOB_COST_USD", "2.00"))
    max_model_calls_per_job: int = int(os.getenv("MAX_MODEL_CALLS_PER_JOB", "8"))
    max_source_chars_per_read: int = int(os.getenv("MAX_SOURCE_CHARS_PER_READ", "18000"))
    max_source_pages_per_read: int = int(os.getenv("MAX_SOURCE_PAGES_PER_READ", "8"))
    max_source_chars_per_job: int = int(os.getenv("MAX_SOURCE_CHARS_PER_JOB", "70000"))
    exact_token_preflight: bool = _env_bool("OPENAI_EXACT_TOKEN_PREFLIGHT", True)
    allow_approximate_token_preflight: bool = _env_bool("ALLOW_APPROXIMATE_TOKEN_PREFLIGHT", False)
    soffice_path: str = os.getenv("SOFFICE_PATH", "soffice")

    def policy(self, profile: str | None = None) -> ProcessingPolicy:
        selected = profile or self.processing_profile
        if selected == "economy":
            return ProcessingPolicy(
                name="economy",
                analysis_model=self.openai_economy_model,
                analysis_effort=self.openai_economy_effort,
                review_model=self.openai_economy_model,
                review_effort=self.openai_economy_effort,
                pdf_detail="low",
                max_evidence_chars=35_000,
                max_visual_pages=24,
                max_agent_steps=min(self.max_agent_steps, 4),
            )
        if selected == "quality":
            return ProcessingPolicy(
                name="quality",
                analysis_model=self.openai_quality_model,
                analysis_effort=self.openai_quality_effort,
                review_model=self.openai_quality_model,
                review_effort=self.openai_quality_effort,
                pdf_detail="high",
                max_evidence_chars=120_000,
                max_visual_pages=60,
                max_agent_steps=min(self.max_agent_steps, 8),
            )
        if selected != "balanced":
            raise ValueError(f"Неизвестный профиль расхода: {selected}")
        return ProcessingPolicy(
            name="balanced",
            analysis_model=self.openai_analysis_model,
            analysis_effort=self.openai_analysis_effort,
            review_model=self.openai_review_model,
            review_effort=self.openai_review_effort,
            pdf_detail="low",
            max_evidence_chars=70_000,
            max_visual_pages=40,
            max_agent_steps=min(self.max_agent_steps, 6),
        )

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.runs_dir,
            self.contracts_dir,
            self.fill_contracts_dir,
            self.approved_templates_dir,
            self.profiles_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
