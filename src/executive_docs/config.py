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


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = ROOT / "data"
    runs_dir: Path = ROOT / "data" / "runs"
    db_path: Path = ROOT / "data" / "app.db"
    skill_dir: Path = ROOT / "agent-skill" / "prepare-executive-docs"
    contracts_dir: Path = ROOT / "templates" / "contracts"
    approved_templates_dir: Path = ROOT / "templates" / "approved"
    source_templates_dir: Path = ROOT / "template"
    profiles_dir: Path = ROOT / "profiles"
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.6")
    reasoning_effort: str = os.getenv("OPENAI_REASONING_EFFORT", "high")
    agent_mode: str = os.getenv("AGENT_MODE", "openai")
    host: str = os.getenv("APP_HOST", "127.0.0.1")
    port: int = int(os.getenv("APP_PORT", "8000"))
    max_file_bytes: int = int(os.getenv("MAX_FILE_MB", "50")) * 1024 * 1024
    max_job_bytes: int = int(os.getenv("MAX_JOB_MB", "250")) * 1024 * 1024
    max_agent_steps: int = int(os.getenv("MAX_AGENT_STEPS", "40"))
    max_agent_seconds: int = int(os.getenv("MAX_AGENT_SECONDS", "900"))
    openai_timeout_seconds: int = int(os.getenv("OPENAI_TIMEOUT_SECONDS", "300"))
    openai_max_retries: int = int(os.getenv("OPENAI_MAX_RETRIES", "2"))
    openai_max_output_tokens: int = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "32000"))
    soffice_path: str = os.getenv("SOFFICE_PATH", "soffice")

    def ensure_directories(self) -> None:
        for path in (
            self.data_dir,
            self.runs_dir,
            self.contracts_dir,
            self.approved_templates_dir,
            self.profiles_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)


settings = Settings()
